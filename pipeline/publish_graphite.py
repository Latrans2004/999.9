"""Publish reviewed fixed-vintage mine data; withhold graphite trade metrics.

    python -m pipeline.publish_graphite

Replays committed Raw without credentials. New years or revised inputs require
a new review; an audit's publishable flag is never a publication authorization.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys

from . import archive, graphite, graphite_usgs
from .build import summarise
from .update_minerals import ROOT, commit_files, pack, put, read, staging_directory

SLUG = 'natural-graphite'
POLICY = 'pipeline/graphite_publication.json'
PUBLIC = f'critical-minerals/data/{SLUG}'
MINERAL = f'critical-minerals/data/minerals/{SLUG}.json'
SNAPSHOT = f'data/processed/{SLUG}/snapshot.json'


def production_digest(records):
    # Review pins native quantities, identities and flags independently of clocks.
    values = [{k: v for k, v in r.items() if k != 'source'} for r in records]
    return hashlib.sha256(archive.encode(values)).hexdigest()


def assemble(records, policy, entry):
    if policy['production']['decision'] != 'publish_fixed_vintages':
        raise ValueError('Mine publication has not been approved')
    if policy['trade']['decision'] != 'withhold':
        raise ValueError('Trade publication requires a separate implementation and review')
    if production_digest(records) != policy['production']['records_sha256']:
        raise ValueError('Production changed; publication review required')
    if sorted({r['year'] for r in records}) != policy['years']:
        raise ValueError('Production year coverage changed')
    keys = [(r['year'], r['kind'], r['country']) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate production identity')
    profiles = graphite_usgs.profiles(records)
    flagged = [p['year'] for p in profiles if p['quality_flags']]
    if flagged != policy['production']['reviewed_flag_years']:
        raise ValueError('Mine quality flags changed; review required')
    values, totals = defaultdict(dict), {}
    for row in records:
        if row['kind'] == 'world':
            totals[row['year']] = row['production_t']
        elif row['kind'] == 'country' and row['production_t'] is not None:
            values[row['year']][row['country']] = row['production_t']
    site = dict(entry)
    site['production'] = pack(
        values, 'USGS Mineral Commodity Summaries (fixed 2019–2026 editions)',
        'share of identified natural graphite mine production',
        '天然黒鉛の国別鉱山生産量に占める割合', 'mine', totals)
    site['production'].update(publishable=True, series_key='mine_natural_graphite_t',
                              measurement_unit='t natural graphite', verification_status='not_applicable')
    site['production']['trend'] = None  # Mixed vintages are not a uniform growth series.
    site['production']['trend_note'] = 'Fixed historical editions; annual changes may include revisions.'
    site['production']['trend_note_ja'] = '過去の版を固定して収録。年次変化には改訂が含まれます。'
    site['trade'] = {
        'available': False, 'publishable': False, 'publication_status': 'under_review',
        'source': 'UN Comtrade', 'stage': 'raw',
        'unit': 'natural graphite trade', 'unit_ja': '天然黒鉛の貿易',
        'verification_status': 'unverified',
        'notes': [policy['trade']['note']], 'notes_ja': [policy['trade']['note_ja']],
    }
    site['caveats'] = list(entry.get('caveats', [])) + [policy['production']['note']]
    site['caveats_ja'] = list(entry.get('caveats_ja', [])) + [policy['production']['note_ja']]
    production = []
    for row in records:
        production.append(dict(row, selected_source='reported',
                               verification_status='not_applicable',
                               unit='t natural graphite',
                               included=row['kind'] == 'country' and row['production_t'] is not None
                                        and row['production_t'] > 0))
    for p in profiles:
        p.update(publishable=True, series_key='mine_natural_graphite_t',
                 unit='t natural graphite', review_note=policy['production']['note'])
    return site, production, profiles


def run(root=ROOT, *, render_command=None):
    root = Path(root)
    policy = read(root / POLICY)
    index = read(root / 'critical-minerals/data/index.json', {})
    if index.get('fixtures'):
        raise ValueError('Refuse to publish into a synthetic-fixtures site')
    catalog = read(root / 'critical-minerals/data/catalog.json')
    entry = next(e for e in catalog['minerals'] if e['slug'] == SLUG)
    if entry['headline_hs_codes'] != graphite.HS_CODES:
        raise ValueError('Graphite headline scope changed')
    audit = root / f'data/review/{SLUG}'
    # Strict replay verifies Raw hashes and every normalized row, then validates
    # scope and duplicate identities. It never promotes the selected sample.
    rows = graphite.replay_bundle(audit / 'bundle.json')
    expected = {(y, hs, flow) for y in policy['years'] for hs in graphite.HS_CODES for flow in ('X', 'M')}
    if {(r['year'], r['hs_code'], r['flow']) for r in rows} != expected:
        raise ValueError('Trade query coverage changed')
    decisions = graphite.attach_reviews(graphite.compare(rows))
    trade_status = {'publishable': False, 'publication_status': 'under_review',
                    'queries_complete': True, 'global_coverage': None,
                    'rows': len(rows), 'decisions': len(decisions),
                    'unresolved': sum(d['decision'] == 'unresolved' for d in decisions),
                    'note': policy['trade']['note'], 'note_ja': policy['trade']['note_ja']}
    with staging_directory(root) as tmp:
        # USGS replay writes only to staging, including any archive sidecars.
        shutil.copytree(audit / 'data/raw/usgs', tmp / 'data/raw/usgs')
        records = graphite_usgs.collect(tmp, replay=True)
        site, production, profiles = assemble(records, policy, entry)
        metadata = {'methodology_version': policy['methodology_version'],
                    'publication_review': policy, 'data_year': policy['years'],
                    'sources': read(root / 'pipeline/graphite_usgs_sources.json'),
                    'production_publishable': True, 'trade_publishable': False}
        site.update(metadata=metadata, generated_at=policy['reviewed_at'],
                    audit_data_url=f'../data/{SLUG}/metadata.json')
        snapshot = {'metadata': metadata, 'production': production,
                    'concentration': profiles, 'trade_status': trade_status}
        by_slug = {m['slug']: m for m in index.get('minerals', [])}
        by_slug[SLUG] = summarise(site)
        index['minerals'] = [by_slug[e['slug']] for e in catalog['minerals'] if e['slug'] in by_slug]
        index['fixtures'] = False
        # Preserve unrelated source/failure metadata and timestamps.
        for name in ('pipeline', 'assets'):
            shutil.copytree(root / name, tmp / name, ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
        shutil.copy2(root / 'site.json', tmp / 'site.json')
        shutil.copytree(root / 'critical-minerals/data', tmp / 'critical-minerals/data')
        outputs = {SNAPSHOT: snapshot, MINERAL: site, 'critical-minerals/data/index.json': index,
                   f'{PUBLIC}/metadata.json': metadata,
                   f'{PUBLIC}/production.json': {'metadata': metadata, 'records': production},
                   f'{PUBLIC}/concentration.json': {'metadata': metadata, 'records': profiles},
                   f'{PUBLIC}/trade-status.json': trade_status}
        for path, payload in outputs.items():
            put(tmp, path, payload)
        subprocess.run(render_command or [sys.executable, '-m', 'pipeline.render'], cwd=tmp, check=True)
        paths = [Path(p) for p in outputs] + [p.relative_to(tmp) for p in tmp.rglob('*.html')]
        changed = [p for p in paths if not (root / p).exists() or (root / p).read_bytes() != (tmp / p).read_bytes()]
        commit_files(root, tmp, changed)
    return bool(changed)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()


if __name__ == '__main__':
    main()
