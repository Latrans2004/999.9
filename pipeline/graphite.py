"""Natural graphite audit. Writes review artifacts only, never public data."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import hashlib
import logging
import os
import shutil
from pathlib import Path

from . import archive, countries, entity_diagnostics, hhi, strict_comtrade

YEARS = list(range(2017, 2025))
HS_CODES = ['250410', '250490']
ROOT = Path(__file__).resolve().parents[1]


def put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(archive.encode(value))


def observed_sum(rows, field):
    values = [r[field] for r in rows if r[field] is not None]
    return sum(values) if values else None


def relative_gap(a, b):
    if a is None or b is None:
        return None
    return abs(a - b) / max(a, b) if max(a, b) else 0.0


def enrich(root, rows, ref):
    """Keep native flags and valuations without altering the lithium adapter."""
    raw = json.loads((root / ref['path']).read_bytes())['data']
    for row, native in zip(rows, raw, strict=True):
        for name in ('isQtyEstimated', 'isNetWgtEstimated', 'isReported',
                     'isAggregate', 'legacyEstimationFlag', 'qtyUnitCode',
                     'fobvalue', 'cifvalue'):
            row[name] = native.get(name)
        row['weight_estimated'] = native.get(
            'isNetWgtEstimated' if row['weight_source'] == 'netWgt' else 'isQtyEstimated')


def collect(root):
    if not os.environ.get('COMTRADE_API_KEY', '').strip():
        raise ValueError('COMTRADE_API_KEY must be injected by Actions; preview is not sufficient')
    rows, queries, sources = [], [], []
    for year in YEARS:
        for hs in HS_CODES:
            for flow in ('X', 'M'):
                audit = {'year': year, 'hs_code': hs, 'flow': flow}
                try:
                    batch, ref = strict_comtrade.fetch(root, hs, year, flow)
                    enrich(root, batch, ref)
                    rows.extend(batch)
                    sources.append(ref)
                    audit.update(status='ok', rows=len(batch),
                                 reporters=len({r['reporter'] for r in batch}),
                                 missing_weight=sum(r['weight_t'] is None for r in batch),
                                 estimated_weight=sum(r['weight_estimated'] is True for r in batch),
                                 unknown_weight_flag=sum(r['weight_estimated'] is None for r in batch),
                                 missing_value=sum(r['value_usd'] is None for r in batch))
                except Exception as exc:
                    # Never serialize exception text that might include an HTTP body.
                    audit.update(status='failed', error_type=type(exc).__name__)
                queries.append(audit)
                put(root, 'queries.json', queries)
                put(root, 'bundle.json', {'trade': rows, 'sources': sources})
                logging.info('%s %s %s: %s (%s rows)', year, hs, flow,
                             audit['status'], audit.get('rows', 0))
    return rows, queries


def compare(rows):
    seen = set()
    groups = defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in ('year', 'hs_code', 'flow', 'reporter', 'partner'))
        if key in seen:
            raise ValueError('Duplicate normalized trade identity')
        seen.add(key)
        if row['year'] not in YEARS or row['hs_code'] not in HS_CODES or row['flow'] not in ('X', 'M'):
            raise ValueError('Unexpected graphite scope')
        for field in ('weight_t', 'value_usd'):
            strict_comtrade.number(row[field])
        if countries.trade_eligibility(row)[0]:
            groups[row['year'], row['hs_code']].append(row)
    decisions = []
    for (year, hs), group in sorted(groups.items()):
        exporters = {r['reporter'] for r in group if r['flow'] == 'X'}
        exporters |= {r['partner'] for r in group if r['flow'] == 'M' and r['partner'] != 'W00'}
        for country in sorted(exporters):
            own = [r for r in group if r['flow'] == 'X' and r['reporter'] == country]
            world = next((r for r in own if r['partner'] == 'W00'), None)
            bilateral = [r for r in own if r['partner'] != 'W00']
            mirror = [r for r in group if r['flow'] == 'M' and r['partner'] == country]
            matched = {r['reporter'] for r in mirror}
            destinations = {r['partner'] for r in bilateral}
            reported = world['weight_t'] if world else None
            mirrored = observed_sum(mirror, 'weight_t')
            gap = relative_gap(reported, mirrored)
            reason = 'Reported world net weight; no detected material discrepancy in observed mirror.'
            flags = []
            if reported is None:
                flags.append('missing_reported_world_weight')
            if world and world.get('weight_estimated') is not False:
                flags.append('estimated_or_unknown_weight_flag')
            if not mirror or mirrored is None:
                flags.append('no_usable_mirror')
            # Screening thresholds trigger review only; they never choose a larger value.
            if gap is not None and gap > 0.25:
                flags.append('weight_gap_over_25_percent_of_larger')
            if any(r['weight_t'] is None or r.get('weight_estimated') is not False for r in mirror):
                flags.append('mirror_missing_or_estimated_weight')
            if destinations - matched:
                flags.append('unobserved_export_destinations')
            if reported == 0 and world and (world['value_usd'] or 0) > 0:
                flags.append('positive_value_zero_weight')
            if flags:
                reason = '; '.join(flags) + '; external review required, no automatic correction.'
            decisions.append({
                'year': year, 'hs_code': hs, 'country': country,
                'reported_weight_t': reported, 'mirror_observed_weight_t': mirrored,
                'reported_value_usd': world['value_usd'] if world else None,
                'mirror_observed_value_usd': observed_sum(mirror, 'value_usd'),
                'weight_relative_gap': gap,
                'value_relative_gap': relative_gap(world['value_usd'] if world else None,
                                                  observed_sum(mirror, 'value_usd')),
                'mirror_reporters': sorted(matched),
                'missing_observed_destinations': sorted(destinations - matched),
                'mirror_world_complete': False,
                'mirror_scope': 'Observed importing reporters only; global completeness not established.',
                'valuation_note': 'Import primaryValue generally CIF (national exceptions); export FOB. No adjustment.',
                'decision': 'unresolved' if flags else 'reported',
                'selected_weight_t': None if flags else reported,
                'reason': reason, 'flags': flags,
                'sources': sorted({r['raw_path'] for r in own + mirror}),
            })
    return decisions


def metrics(decisions):
    result = []
    groups = defaultdict(list)
    for row in decisions:
        groups[row['hs_code'], row['year']].append(row)
    for (hs, year), group in sorted(groups.items()):
        selected = {r['country']: r['selected_weight_t'] for r in group
                    if r['decision'] != 'unresolved' and r['selected_weight_t'] is not None}
        profile = hhi.concentration(year, selected)
        reported = sum(r['reported_weight_t'] for r in group if r['reported_weight_t'] is not None)
        total = sum(selected.values())
        result.append({'hs_code': hs, 'year': year,
                       'scope': 'Reviewed observed exporters, not world or battery anode supply',
                       'unit': 'metric tonnes of traded natural graphite',
                       'profile': profile.to_dict() if profile else None,
                       'selected_total_t': total,
                       'observed_exporter_count': len(group),
                       'unresolved_count': sum(r['decision'] == 'unresolved' for r in group),
                       'reported_weight_coverage': total / reported if reported else None,
                       'global_coverage': None, 'publishable': False})
    previous = {}
    for row in result:
        old = previous.get(row['hs_code'])
        row['yoy'] = None
        if old and old['year'] == row['year'] - 1:
            row['yoy'] = {'total_ratio': row['selected_total_t'] / old['selected_total_t']
                          if old['selected_total_t'] else None,
                          'hhi_delta': row['profile']['hhi'] - old['profile']['hhi']
                          if row['profile'] and old['profile'] else None,
                          'country_count_delta': (row['profile']['reporters'] if row['profile'] else 0) -
                                                 (old['profile']['reporters'] if old['profile'] else 0)}
        if row['profile']:
            assert 0 <= row['profile']['hhi'] <= 10000
            assert 0 <= row['profile']['cr3'] <= 100
        row['quality_flags'] = []
        if not row['profile'] or row['profile']['reporters'] < 5:
            row['quality_flags'].append('fewer_than_5_selected_exporters')
        if row['reported_weight_coverage'] is None or row['reported_weight_coverage'] < 0.90:
            row['quality_flags'].append('less_than_90_percent_of_observed_reported_weight')
        if row['yoy']:
            ratio = row['yoy']['total_ratio']
            if ratio is None or not 0.7 <= ratio <= 1.3:
                row['quality_flags'].append('selected_total_yoy_requires_review')
            if row['yoy']['hhi_delta'] is not None and abs(row['yoy']['hhi_delta']) > 1000:
                row['quality_flags'].append('selected_hhi_yoy_requires_review')
        previous[row['hs_code']] = row
    return result


def attach_reviews(decisions):
    reviews = json.loads(Path(__file__).with_name('graphite_reviews.json').read_bytes())
    for row in decisions:
        row['external_reviews'] = [review for review in reviews
                                   if row['country'] in review['countries'] and row['year'] in review['years']
                                   and row['hs_code'] in review['hs_codes']]
        if row['external_reviews']:
            row.update(decision='unresolved', selected_weight_t=None)
            row['reason'] = ' '.join(r['reason'] for r in row['external_reviews'])
    return decisions


def measurement_audit(rows):
    observations = []
    for row in rows:
        flags = []
        weight, value = row['weight_t'], row['value_usd']
        if weight is None:
            flags.append('missing_weight')
        if value is None:
            flags.append('missing_value')
        if weight == 0 and value and value > 0:
            flags.append('positive_value_zero_weight')
        if value == 0 and weight and weight > 0:
            flags.append('positive_weight_zero_value')
        if row.get('weight_estimated') is True:
            flags.append('estimated_weight')
        if row.get('weight_estimated') is None:
            flags.append('unknown_weight_estimation_flag')
        eligible, reason = countries.trade_eligibility(row)
        observations.append({k: row[k] for k in ('year', 'hs_code', 'flow', 'reporter', 'partner', 'raw_path')} |
                            {'flags': flags, 'metric_eligible_entity': eligible, 'entity_reason': reason,
                             'unit_value_usd_t': value / weight if value is not None and weight else None})
    return observations


def replay_bundle(path):
    bundle = json.loads(path.read_bytes())
    rows = []
    for ref in bundle['sources']:
        source_path = (path.parent / ref['path']).resolve()
        if not source_path.is_relative_to(path.parent.resolve()):
            raise ValueError('Raw reference escapes audit archive')
        body = source_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != ref['sha256']:
            raise ValueError('Comtrade raw hash mismatch')
        batch = strict_comtrade.normalize(json.loads(body), ref['query'], ref['query']['maxRecords'])
        for row in batch:
            row.update(raw_path=ref['path'], retrieved_at=ref['retrieved_at'])
        enrich(path.parent, batch, ref)
        rows.extend(batch)
    if rows != bundle['trade']:
        raise ValueError('Normalized bundle differs from archived responses')
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.cache/graphite-audit')
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--replay-usgs', action='store_true', help='Verify and parse archived pinned PDFs in output')
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or output == ROOT / 'critical-minerals' or ROOT / 'critical-minerals' in output.parents or output == ROOT / 'data':
        parser.error('Output must be an isolated audit directory')
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if args.replay:
        rows = replay_bundle(args.replay)
        if args.replay.parent.resolve() != output:
            shutil.copytree(args.replay.parent / 'data/raw', output / 'data/raw', dirs_exist_ok=True)
        queries = []
    else:
        rows, queries = collect(output)
    decisions = attach_reviews(compare(rows))
    put(output, 'decisions.json', decisions)
    put(output, 'discrepancies.json', sorted(
        [r for r in decisions if r['flags']],
        key=lambda r: r['weight_relative_gap'] if r['weight_relative_gap'] is not None else -1,
        reverse=True))
    put(output, 'metrics.json', metrics(decisions))
    put(output, 'entities.json', entity_diagnostics.summarize(rows))
    put(output, 'measurements.json', measurement_audit(rows))
    expected = {(y, hs, f) for y in YEARS for hs in HS_CODES for f in ('X', 'M')}
    actual = {(r['year'], r['hs_code'], r['flow']) for r in rows}
    failures = [q for q in queries if q['status'] != 'ok']
    usgs_status = 'ok'
    try:
        from . import graphite_usgs
        graphite_usgs.collect(output, replay=args.replay_usgs)
    except Exception as exc:
        usgs_status = type(exc).__name__
    if usgs_status == 'ok':
        from . import graphite_anchor
        production = json.loads((output / 'production.json').read_bytes())
        put(output, 'anchor.json', graphite_anchor.audit(decisions, production))
    put(output, 'status.json', {'requested_years': YEARS, 'rows': len(rows),
                              'queries_complete': expected == actual and not failures,
                              'global_completeness': 'unverified', 'publishable': False,
                              'missing_queries': sorted(expected - actual),
                              'failed_queries': failures})
    put(output, 'usgs-status.json', {'status': usgs_status, 'publishable': False})
    return 1 if failures or expected != actual or usgs_status != 'ok' else 0


if __name__ == '__main__':
    raise SystemExit(main())
