"""Strict fetch -> raw -> process -> validate -> stage render -> publish.

    python -m pipeline.update_minerals --mineral lithium
    python -m pipeline.update_minerals --mineral lithium --input-bundle bundle.json
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid
from contextlib import contextmanager

from . import archive, countries, entity_diagnostics, hhi, process_trade, strict_comtrade, strict_usgs, validate_data
from .build import summarise

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger('orelysis.strict')


@contextmanager
def staging_directory(root):
    # Normal inherited ACLs also support Windows restricted execution accounts.
    cache=(root/'.cache').resolve()
    cache.mkdir(exist_ok=True)
    target=cache/('mineral-stage-'+uuid.uuid4().hex)
    target.mkdir()
    try:
        yield target
    finally:
        if target.resolve().parent != cache:
            raise ValueError('Staging path escaped cache')
        shutil.rmtree(target)


def read(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def put(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(archive.encode(value))


def collect(root, settings):
    if not os.environ.get('COMTRADE_API_KEY', '').strip():
        raise ValueError('COMTRADE_API_KEY is required for complete bilateral updates; preview is limited to 500 rows')
    rows, refs = [], []
    for year in range(settings['start_year'], settings['end_year'] + 1):
        for hs in settings['hs_codes']:
            for flow in ['X', 'M']:
                log.info('Fetching Comtrade %s %s %s', year, hs, flow)
                batch, ref = strict_comtrade.fetch(root, hs, year, flow, max_records=settings['max_records'])
                rows.extend(batch)
                refs.append(ref)
                put(root, 'entity-diagnostics.json', entity_diagnostics.summarize(rows))
    production, production_refs = strict_usgs.collect(root, settings['usgs'])
    return {'trade': rows, 'production': production, 'sources': refs + production_refs}


def pack(by_year, source, unit, unit_ja, stage, world=None):
    labels = {countries.label(code): code for values in by_year.values() for code in values}
    named = {y: {countries.label(c): v for c, v in values.items()} for y,values in by_year.items()}
    series = hhi.series(named, codes=labels, universe_totals=world)
    if not series:
        raise ValueError(f'{source}: no valid concentration series')
    return {'available': True, 'source': source, 'unit': unit, 'unit_ja': unit_ja,
            'stage': stage, 'latest_year': series[-1].year,
            'latest': series[-1].to_dict(top_n=10),
            'series': [{k:r.to_dict()[k] for k in ['year','hhi','cr3','reporters','coverage']} for r in series],
            'trend': hhi.trend(series), 'notes': []}


def assemble(bundle, settings, entry):
    rows = bundle['trade']
    # Input bundles are for reproducible audited replays, not an unchecked publication bypass.
    expected = {(hs,y,f) for hs in settings['hs_codes'] for y in range(settings['start_year'],settings['end_year']+1) for f in ['X','M']}
    actual = {(r['hs_code'],r['year'],r['flow']) for r in rows}
    if expected != actual:
        raise ValueError(f'Trade query coverage changed: missing={expected-actual}, unexpected={actual-expected}')
    for hs,y,_ in expected:
        if not any(r['hs_code']==hs and r['year']==y and r['flow']=='X' and r['partner']=='W00' for r in rows):
            raise ValueError(f'{hs} {y}: missing reported world export totals')
    seen, unknowns = set(), set()
    for r in rows:
        key=(r['hs_code'],r['year'],r['flow'],r['reporter'],r['partner'])
        if key in seen: raise ValueError(f'Duplicate normalized trade row: {key}')
        seen.add(key)
        for dimension in ('reporter', 'partner'):
            entity = countries.row_entity(r, dimension)
            if entity.key != r[dimension]:
                raise ValueError(f'Invalid normalized entity: {dimension} {r[dimension]}')
            if entity.kind == 'unknown':
                unknowns.add(entity.key)
        for field in ['weight_t','value_usd']:
            strict_comtrade.number(r[field])
    if unknowns:
        log.warning('Unknown entities retained but excluded from metrics: %s', ', '.join(sorted(unknowns)))
    selected = process_trade.build(rows, settings)
    concentration = process_trade.metrics(selected)
    # Report completeness is a property of the filing year, not of the selection policy,
    # so it is attached after the metrics rather than computed inside them.
    coverage = process_trade.report_coverage(rows)
    for profile in concentration:
        profile['coverage_pct'] = coverage.get((profile['hs_code'], profile['year']))
    exports = defaultdict(lambda: defaultdict(float))
    for r in rows:
        if countries.trade_eligibility(r)[0] and r['hs_code'] in settings['headline_hs_codes'] and r['flow'] == 'X' and r['partner'] == 'W00':
            if r['value_usd'] is None:
                raise ValueError('Missing headline export value')
            exports[r['year']][r['reporter']] += r['value_usd']
    production, totals = defaultdict(dict), {}
    production_seen = set()
    for r in bundle['production']:
        key = (r['year'],r['country'])
        if key in production_seen: raise ValueError('Duplicate production key')
        production_seen.add(key)
        if r['production_t'] is not None:
            production[r['year']][countries.normalize(r['country'])] = strict_comtrade.number(r['production_t'])
        if r['world_total_t'] is not None:
            world = strict_comtrade.number(r['world_total_t'])
            if r['year'] in totals and totals[r['year']] != world:
                raise ValueError('Conflicting USGS world totals')
            totals[r['year']] = world
    for year, values in production.items():
        world = totals.get(year)
        if world and abs(sum(values.values()) / world - 1) > .05:
            raise ValueError(f'USGS {year}: country sum differs from world total by >5%')
    # Validate both public headlines and all stage measurements using the same gates.
    audit_selected = list(selected)
    for stage, yearly in [('headline_usd',exports),('mine_li_t',production)]:
        for year, amounts in sorted(yearly.items()):
            profile = hhi.concentration(year, amounts)
            if profile is None: raise ValueError(f'{stage} {year}: empty profile')
            # Single-source stages have no self-report/mirror duality and therefore no
            # report-completeness question; null is the honest answer, not 100.
            concentration.append({'hs_code':stage, 'unit':'USD' if stage == 'headline_usd' else 't Li',
                                  'coverage_pct':None, **profile.to_dict()})
            for code, value in amounts.items():
                audit_selected.append({'hs_code':stage,'year':year,'country':code,'reported_value':value,
                                       'mirror_value':None,'selected_value':value,'included':True})
    data = dict(entry)
    data['production'] = pack(production, 'USGS Mineral Commodity Summaries', 'share of reported mine production',
                              '報告された鉱山生産量に占める割合', 'mine', totals)
    data['trade'] = pack(exports, 'UN Comtrade', 'share of reported export value (USD, FOB)',
                        '報告された輸出額(USドル、FOB)に占める割合', entry.get('trade_stage','export'))
    source_quality=[]
    for hs,y,flow in sorted(expected):
        group=[r for r in rows if (r['hs_code'],r['year'],r['flow'])==(hs,y,flow)]
        source_quality.append({'hs_code':hs,'year':y,'flow':flow,'rows':len(group),
                               'reporters':len({r['reporter'] for r in group}),
                               'missing_value_fraction':sum(r['value_usd'] is None for r in group)/len(group)})
    return {'selected':audit_selected,'concentration':concentration,'trade_rows':rows,'source_quality':source_quality,
            'entity_diagnostics':entity_diagnostics.summarize(rows), 'production':bundle['production']}, data


def content_fingerprint(payload):
    def clean(value):
        if isinstance(value, dict):
            return {k:clean(v) for k,v in value.items() if k not in {'raw_path','raw_paths','retrieved_at','sources'}}
        if isinstance(value, list):
            return sorted((clean(v) for v in value), key=lambda v: archive.encode(v))
        return value
    return hashlib.sha256(archive.encode(clean(payload))).hexdigest()


def commit_files(root, staged, paths):
    """Rollback on filesystem errors; CI git commit/deployment is the publication boundary."""
    backups = {}
    try:
        for rel in paths:
            target = root / rel
            backups[rel] = target.read_bytes() if target.exists() else None
            target.parent.mkdir(parents=True,exist_ok=True)
            temp = target.with_name(target.name + '.updating')
            temp.write_bytes((staged / rel).read_bytes())
            os.replace(temp, target)
    except BaseException:
        for rel, body in backups.items():
            target = root / rel
            if body is None: target.unlink(missing_ok=True)
            else: target.write_bytes(body)
            target.with_name(target.name + '.updating').unlink(missing_ok=True)
        raise


def run(root=ROOT, mineral='lithium', bundle=None, *, render_command=None):
    configuration = read(root / 'pipeline/minerals.json')
    settings = configuration['minerals'][mineral]
    catalog = read(root / 'critical-minerals/data/catalog.json')
    entry = next(e for e in catalog['minerals'] if e['slug'] == mineral)
    if entry['hs_codes'] != settings['headline_hs_codes']:
        raise ValueError('Headline HS codes differ from the existing site catalog')
    if settings['end_year'] < settings['start_year']:
        raise ValueError('Invalid year range')
    unknown_stages = set(settings.get('provisional_years', {})) - set(settings['stages'])
    if unknown_stages:
        raise ValueError(f'provisional_years names unknown stages: {sorted(unknown_stages)}')
    bundle = collect(root, settings) if bundle is None else bundle
    processed, site = assemble(bundle, settings, entry)
    accepted_path = f'data/processed/{mineral}/snapshot.json'
    previous = read(root / accepted_path)
    report = validate_data.validate(processed,previous,settings['validation'])
    # Include configuration and catalog copy changes, not changing retrieval clocks.
    fingerprint = content_fingerprint({'data':processed,'settings':settings,'entry':entry,
                                      'methodology':configuration['methodology_version']})
    if previous and previous.get('fingerprint') == fingerprint:
        log.info('Validated unchanged upstream data; no data/HTML rewrite or commit')
        return False
    stamp = archive.now()
    metadata = {'source':['UN Comtrade','USGS Mineral Commodity Summaries'],
                'retrieved_at':max((s['retrieved_at'] for s in bundle['sources']),default=stamp),
                'data_year':sorted({r['year'] for r in processed['concentration']}),
                'last_updated':stamp,'methodology_version':configuration['methodology_version'],
                'fingerprint':fingerprint,'sources':bundle['sources'],
                'usgs_mode':'reviewed_csv_with_automatic_publication_archive',
                'provisional_years':settings.get('provisional_years', {}),
                'validation':report}
    metadata['entity_diagnostics_url'] = 'entities.json'
    metadata['unknown_entities'] = [e['id'] for e in processed['entity_diagnostics']['entities'] if e['kind'] == 'unknown']
    processed.update({'fingerprint':fingerprint,'metadata':metadata})
    site.update({'generated_at':stamp,'metadata':metadata,
                 'audit_data_url':f'../data/{mineral}/metadata.json'})
    index = read(root/'critical-minerals/data/index.json',{})
    if index.get('fixtures'):
        raise ValueError('Refuse to publish into a synthetic-fixtures site')
    by_slug={m['slug']:m for m in index.get('minerals',[])}
    by_slug[mineral]=summarise(site)
    index.update({'section':catalog['section'],'conventions':catalog['conventions'],
                  'fixtures':False,'generated_at':stamp,'failures':[],
                  'minerals':[by_slug[e['slug']] for e in catalog['minerals'] if e['slug'] in by_slug]})
    # Staging is beneath .cache (never deployed or committed).
    (root/'.cache').mkdir(exist_ok=True)
    with staging_directory(root) as tmp:
        stage=Path(tmp)/'site'
        stage.mkdir()
        for name in ('pipeline','assets'):
            shutil.copytree(root/name,stage/name,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
        shutil.copy2(root/'site.json',stage/'site.json')
        shutil.copytree(root/'critical-minerals/data',stage/'critical-minerals/data',dirs_exist_ok=True)
        put(stage,accepted_path,processed)
        base=f'critical-minerals/data/{mineral}'
        put(stage,f'{base}/production.json',{'metadata':metadata,'records':processed['production']})
        put(stage,f'{base}/trade.json',{'metadata':metadata,'records':[r for r in processed['selected'] if r['hs_code'] not in ('headline_usd','mine_li_t')]})
        put(stage,f'{base}/concentration.json',{'metadata':metadata,'records':processed['concentration']})
        put(stage,f'{base}/metadata.json',metadata)
        put(stage,f'{base}/entities.json',processed['entity_diagnostics'])
        put(stage,f'critical-minerals/data/minerals/{mineral}.json',site)
        put(stage,'critical-minerals/data/index.json',index)
        table=io.StringIO(newline='')
        fields=['hs_code','year','country','reported_value','mirror_value','selected_value','selected_source','unit','included','classification','unverified','selection_note','supplement_source_url']
        writer=csv.DictWriter(table,fieldnames=fields,extrasaction='ignore')
        writer.writeheader()
        writer.writerows(r for r in processed['selected'] if r['hs_code'] not in ('headline_usd','mine_li_t'))
        (stage/f'{base}/trade.csv').write_text(table.getvalue(),encoding='utf-8')
        subprocess.run(render_command or [sys.executable,'-m','pipeline.render'],cwd=stage,check=True)
        paths=[p.relative_to(stage) for p in stage.rglob('*.html')]
        paths += [p.relative_to(stage) for p in (stage/base).iterdir()]
        paths += [Path(accepted_path),Path(f'critical-minerals/data/minerals/{mineral}.json'),Path('critical-minerals/data/index.json')]
        commit_files(root,stage,paths)
    log.info('Accepted %s: %s; staged rendering and all validation gates passed',mineral,report)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mineral',default='lithium')
    parser.add_argument('--input-bundle',type=Path,help='Replay a normalized audited bundle; no API calls')
    args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try:
        run(mineral=args.mineral,bundle=read(args.input_bundle) if args.input_bundle else None)
    except Exception:
        log.exception('Update failed. Last accepted data and published site retained.')
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
