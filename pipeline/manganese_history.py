"""Resumable public historical acquisition; observed coverage, not certified totals."""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
import shutil

from . import archive, graphite, manganese as mn
from . import manganese_evidence as evidence

# Production countries and major importing/processing economies. Inclusion is
# a retrieval scope, NOT a mirror allowlist or reliability judgement.
REPORTERS = [36, 76, 156, 266, 288, 356, 384, 392, 410, 458, 484, 528, 578, 710, 804, 842]


def plan(world=False):
    return [dict(year=y, hs_code=mn.HS_CODE, flow=f, reporter=r, partner='0' if world else '')
            for y in mn.YEARS for r in ([''] if world else REPORTERS) for f in ('X', 'M')]


def identity(q):
    return tuple(str(q[k]) for k in ('year', 'hs_code', 'flow', 'reporter', 'partner'))


def validate_cached(q):
    if q.get('status') not in {'ok', 'failed'}:
        raise ValueError('Invalid cached query status')
    if q.get('status') == 'ok' and not q.get('raw'):
        raise ValueError('Successful cached query needs Raw')
    if q.get('raw'):
        raw_query = q['raw']['query']
        actual = tuple(str(raw_query[k]) for k in
                       ('period', 'cmdCode', 'flowCode', 'reporterCode', 'partnerCode'))
        if identity(q) != actual:
            raise ValueError('Cached query dimensions differ from Raw')


def copy_ref(source_root, target_root, ref):
    evidence.verify_raw(source_root, ref)
    if source_root.resolve() == target_root.resolve():
        return
    for rel in (Path(ref['path']), Path(ref['path']).with_suffix('.meta.json')):
        source, target = source_root / rel, target_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise ValueError('Existing history archive differs; refusing overwrite')
        if not target.exists():
            shutil.copyfile(source, target)


def collect(root, *, world=False, seeds=(), revalidate_failed=False):
    root = mn.isolated_output(root)
    root.mkdir(parents=True, exist_ok=True)
    cached = {}
    # Existing output takes precedence over optional seed snapshots. Validate
    # every seeded bundle before reusing it, including rejected Raw responses.
    paths = ([root / 'bundle.json'] if (root / 'bundle.json').exists() else []) + list(seeds)
    for path in paths:
        _, bundle = mn.replay(path)
        for q in bundle.get('queries', []):
            validate_cached(q)
            cached.setdefault(identity(q), (path.parent, q))
    rows, sources, queries = [], [], []
    for spec in plan(world):
        item = dict(spec)
        if identity(spec) in cached:
            origin, previous = cached[identity(spec)]
            item.update(previous, reused_archived_query=True)
            if item.get('raw'):
                copy_ref(origin, root, item['raw'])
            if revalidate_failed and item['status'] == 'failed' and item.get('raw'):
                try:
                    ref = item['raw']
                    batch = mn.strict_comtrade.normalize(json.loads(evidence.verify_raw(root, ref)),
                                                        ref['query'], ref['query']['maxRecords'])
                    for row in batch:
                        row.update(raw_path=ref['path'], retrieved_at=ref['retrieved_at'])
                    graphite.enrich(root, batch, ref)
                    mn.validate_rows(batch)
                    item['previous_failure'] = {k: item[k] for k in ('status', 'error_type', 'reason_code') if k in item}
                    item.pop('error_type', None)
                    item.pop('reason_code', None)
                    item.update(status='ok', rows=len(batch), raw_path=ref['path'], revalidated_from_raw=True)
                except ValueError:
                    pass  # Keep the original rejected response, never invent zero.
            if item['status'] == 'ok':
                ref = item['raw']
                body = evidence.verify_raw(root, ref)
                batch = mn.strict_comtrade.normalize(json.loads(body), ref['query'], ref['query']['maxRecords'])
                for row in batch:
                    row.update(raw_path=ref['path'], retrieved_at=ref['retrieved_at'])
                graphite.enrich(root, batch, ref)
                mn.validate_rows(batch)
                rows.extend(batch)
                sources.append(ref)
        else:
            try:
                batch, ref = mn.fetch(root, mn.HS_CODE, spec['year'], spec['flow'],
                                      reporter=spec['reporter'], partner=spec['partner'])
                item['raw'] = ref
                graphite.enrich(root, batch, ref)
                mn.validate_rows(batch)
                item.update(status='ok', rows=len(batch), raw_path=ref['path'])
                rows.extend(batch)
                sources.append(ref)
            except Exception as exc:
                item.update(status='failed', error_type=type(exc).__name__)
                if getattr(exc, 'raw_ref', None):
                    item.update(raw=exc.raw_ref, reason_code=exc.reason_code)
        queries.append(item)
        graphite.put(root, 'bundle.json', dict(trade=rows, sources=sources, queries=queries,
                     acquisition_scope='sample', sample_design='all_observed_world_rows' if world else 'historical_reporter_panel',
                     requested_queries=plan(world), publishable=False))
        graphite.put(root, 'queries.json', queries)
        logging.info('%s %s reporter=%s: %s (%s rows)', spec['year'], spec['flow'], spec['reporter'],
                     item['status'], item.get('rows', 0))
    mn.validate_rows(rows)
    return mn.run(root, replay_path=root / 'bundle.json')


def coverage(world_path, panel_path, output):
    world_rows, _ = mn.replay(world_path)
    panel_rows, _ = mn.replay(panel_path)
    items = []
    for year in mn.YEARS:
        for flow in ('X', 'M'):
            observed = {r['reporter']: r for r in world_rows if r['year'] == year and r['flow'] == flow
                        and r['partner'] == 'W00' and mn.countries.trade_eligibility(r)[0]}
            panel = {r['reporter']: r for r in panel_rows if r['year'] == year and r['flow'] == flow and r['partner'] == 'W00'}
            total = sum(r['weight_t'] for r in observed.values() if r['weight_t'] is not None)
            covered = sum(r['weight_t'] for c, r in observed.items() if c in panel and panel[c]['weight_t'] is not None and r['weight_t'] is not None)
            items.append(dict(year=year, flow=flow, observed_reporters=len(observed), panel_reporters=len(panel),
                              panel_share_of_observed_world_row_weight=covered / total if total else None,
                              missing_world_weight_reporters=sorted(c for c,r in observed.items() if r['weight_t'] is None),
                              known_reporters_outside_panel=sorted(set(observed)-set(panel)),
                              denominator='Available reporter World rows only; not world trade',
                              global_coverage=None, publishable=False))
    graphite.put(mn.isolated_output(output), 'coverage.json', items)
    return items


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=mn.ROOT / '.cache/manganese-history')
    parser.add_argument('--world', action='store_true')
    parser.add_argument('--seed', type=Path, action='append', default=[])
    parser.add_argument('--revalidate-failed', action='store_true',
                        help='Revalidate archived failures with current researched classification rules; no refetch')
    parser.add_argument('--coverage-world', type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if args.coverage_world:
        coverage(args.coverage_world, args.output / 'bundle.json', args.output)
        return 0
    summary, code = collect(args.output, world=args.world, seeds=args.seed, revalidate_failed=args.revalidate_failed)
    print(json.dumps(summary, sort_keys=True))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
