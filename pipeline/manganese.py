"""HS260200 audit (2017-2024); isolated artifacts, permanently closed publication gate."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import logging
import os
from pathlib import Path
import shutil

from . import archive, countries, entity_diagnostics, graphite, strict_comtrade
from . import manganese_anchor as anchor
from . import manganese_evidence as evidence

ROOT = Path(__file__).resolve().parents[1]
YEARS = list(range(2017, 2025))
HS_CODE = '260200'
WEIGHT_BASIS = 'ore_mass_unspecified_moisture'
SAMPLE_REPORTERS = [36, 76, 156, 266, 356, 528, 710, 842]


def fetch(root, hs_code, year, flow, *, reporter='', partner=''):
    """Same strict dimensions and archive as lithium, with rejected Raw refs."""
    from .sources import comtrade, http
    key = os.environ.get('COMTRADE_API_KEY', '').strip()
    limit = 100000 if key else 500
    query = dict(period=str(year), cmdCode=hs_code, flowCode=flow,
                 reporterCode=str(reporter), partnerCode=str(partner), partner2Code='0',
                 customsCode='C00', motCode='0', maxRecords=limit, includeDesc='true', breakdownMode='classic')
    url = comtrade.FULL_URL if key else comtrade.PREVIEW_URL
    body = http.get(url, params=query, headers={'Ocp-Apim-Subscription-Key': key} if key else {}, use_cache=False)
    ref = archive.save(root, 'comtrade', body, url=url, query=query)
    try:
        rows = strict_comtrade.normalize(json.loads(body), query, limit)
    except ValueError as exc:
        exc.raw_ref = ref
        # Do not serialize arbitrary exception/HTTP-body strings.
        exc.reason_code = 'strict_normalization_rejected'
        try:
            if json.loads(body).get('data') == []:
                exc.reason_code = 'empty_response_not_zero_trade'
        except (ValueError, AttributeError):
            pass
        raise
    for row in rows:
        row.update(raw_path=ref['path'], retrieved_at=ref['retrieved_at'])
    return rows, ref


def isolated_output(path):
    path = Path(path).resolve()
    # Only established review/cache subtrees, including symlink resolution.
    if not any(path.is_relative_to(base.resolve()) and path != base.resolve()
               for base in (ROOT / '.cache', ROOT / 'data/review')):
        raise ValueError('Output must be a subdirectory of .cache or data/review')
    return path


def validate_rows(rows):
    seen = set()
    for row in rows:
        evidence.required(row, ('year', 'hs_code', 'flow', 'reporter', 'partner', 'raw_path', 'classification'))
        if row['year'] not in YEARS or row['hs_code'] != HS_CODE or row['flow'] not in {'X', 'M'}:
            raise ValueError('Unexpected manganese scope')
        # Confirmed 2007, 2012, 2017, 2022 definitions. Earlier nomenclatures are
        # retained in Raw but require research before normalization is accepted.
        if row['classification'] not in {'H3', 'H4', 'H5', 'H6'}:
            raise ValueError('Unverified manganese HS classification')
        identity = tuple(row[k] for k in ('year', 'hs_code', 'flow', 'reporter', 'partner'))
        if identity in seen:
            raise ValueError('Duplicate normalized trade identity')
        seen.add(identity)
        for field in ('weight_t', 'value_usd'):
            if field not in row or row[field] != strict_comtrade.number(row[field]):
                raise ValueError('Invalid normalized measurement')
    return rows


def query_plan(sample=False):
    return [{'year': y, 'hs_code': HS_CODE, 'flow': f, 'reporter': r, 'partner': ''}
            for y in ([2024] if sample else YEARS)
            for r in (SAMPLE_REPORTERS if sample else ['']) for f in ('X', 'M')]


def collect(root, sample=False):
    rows, refs, queries = [], [], []
    for spec in query_plan(sample):
        result = dict(spec)
        try:
            if not sample and not os.environ.get('COMTRADE_API_KEY', '').strip():
                raise ValueError('Full audit requires COMTRADE_API_KEY')
            batch, ref = fetch(root, HS_CODE, spec['year'], spec['flow'],
                               reporter=spec['reporter'], partner=spec['partner'])
            result['raw'] = ref
            graphite.enrich(root, batch, ref)
            validate_rows(batch)
            rows.extend(batch)
            refs.append(ref)
            result.update(status='ok', rows=len(batch), raw_path=ref['path'])
        except Exception as exc:
            result.update(status='failed', error_type=type(exc).__name__)
            if getattr(exc, 'raw_ref', None):
                result['raw'] = exc.raw_ref
                result['reason_code'] = exc.reason_code
        queries.append(result)
        graphite.put(root, 'queries.json', queries)
        graphite.put(root, 'bundle.json', {'trade': rows, 'sources': refs,
                     'acquisition_scope': 'sample' if sample else 'full', 'queries': queries})
        logging.info('%s %s reporter=%s: %s', spec['year'], spec['flow'], spec['reporter'], result['status'])
    validate_rows(rows)
    return rows, queries


def replay(path):
    bundle = json.loads(path.read_bytes())
    rows, seen = [], set()
    for query in bundle.get('queries', []):
        if query.get('raw'):
            evidence.verify_raw(path.parent, query['raw'])
    for ref in bundle['sources']:
        body = evidence.verify_raw(path.parent, ref)
        q = ref['query']
        identity = tuple(str(q[k]) for k in ('period', 'cmdCode', 'flowCode', 'reporterCode', 'partnerCode'))
        if identity in seen:
            raise ValueError('Duplicate archived query')
        seen.add(identity)
        batch = strict_comtrade.normalize(json.loads(body), q, q['maxRecords'])
        for row in batch:
            row.update(raw_path=ref['path'], retrieved_at=ref['retrieved_at'])
        graphite.enrich(path.parent, batch, ref)
        rows.extend(batch)
    validate_rows(rows)
    if rows != bundle['trade']:
        raise ValueError('Normalized bundle differs from archived responses')
    return rows, bundle


def compare(rows, policy):
    validate_rows(rows)
    if policy.get('gap_threshold') is not None or policy.get('anchor_ratio_band') is not None:
        raise ValueError('Manganese thresholds are deferred pending a reviewed design')
    groups = defaultdict(list)
    for row in rows:
        if countries.trade_eligibility(row)[0]:
            groups[row['year']].append(row)
    results = []
    for year, group in sorted(groups.items()):
        exporters = {r['reporter'] for r in group if r['flow'] == 'X'}
        exporters |= {r['partner'] for r in group if r['flow'] == 'M' and r['partner'] != 'W00'}
        for country in sorted(exporters):
            own = [r for r in group if r['flow'] == 'X' and r['reporter'] == country]
            world = next((r for r in own if r['partner'] == 'W00'), None)
            mirror = [r for r in group if r['flow'] == 'M' and r['partner'] == country]
            destinations = {r['partner'] for r in own if r['partner'] != 'W00'}
            matched = {r['reporter'] for r in mirror}
            reported = world['weight_t'] if world else None
            mirrored = graphite.observed_sum(mirror, 'weight_t')
            own_flags, coverage_flags = [], []
            if reported is None:
                own_flags.append('missing_reported_world_weight')
            if world and world.get('weight_estimated') is not False:
                own_flags.append('estimated_or_unknown_reported_weight')
            if world and reported == 0 and (world['value_usd'] or 0) > 0:
                own_flags.append('positive_value_zero_weight')
            if not mirror or mirrored is None:
                coverage_flags.append('no_usable_mirror')
            if any(r['weight_t'] is None for r in mirror):
                coverage_flags.append('missing_mirror_weights')
            if any(r.get('weight_estimated') is not False for r in mirror):
                coverage_flags.append('estimated_or_unknown_mirror_weights')
            if destinations - matched:
                coverage_flags.append('unobserved_export_destinations')
            if reported is None or mirrored is None:
                comparison = 'missing'
            elif own_flags or coverage_flags:
                comparison = 'indeterminate'
            elif reported == mirrored:
                comparison = 'no_dispute'
            else:
                comparison = 'observed_difference_threshold_deferred'
            results.append(dict(country=country, year=year, hs_code=HS_CODE,
                reported_weight_t=reported, mirror_observed_weight_t=mirrored,
                reported_value_usd=world['value_usd'] if world else None,
                mirror_observed_value_usd=graphite.observed_sum(mirror, 'value_usd'),
                weight_relative_gap=graphite.relative_gap(reported, mirrored),
                value_relative_gap=graphite.relative_gap(world['value_usd'] if world else None,
                                                        graphite.observed_sum(mirror, 'value_usd')),
                reported_measurement_flags=own_flags, mirror_coverage_flags=coverage_flags,
                reported_reliability='unverified', comparison_status=comparison,
                missing_observed_destinations=sorted(destinations - matched),
                mirror_reporters=sorted(matched), mirror_world_complete=False,
                mirror_global_coverage=None,
                mirror_observed_rows=len(mirror),
                mirror_missing_weight_rows=sum(r['weight_t'] is None for r in mirror),
                mirror_review_allowed=country in policy['mirror_allowlist'],
                weight_basis=WEIGHT_BASIS, product_scope=evidence.PRODUCT,
                valuation_note='Imports generally CIF; exports FOB; no freight adjustment.',
                selected_weight_t=None, decision='pending_human_review', publishable=False,
                sources=sorted({r['raw_path'] for r in own + mirror})))
    return results


def run(output, *, replay_path=None, sample=False, evidence_root=None,
        reviewed_manifest=None, disclosures_path=None, decisions_path=None, policy_path=None):
    output = isolated_output(output)
    output.mkdir(parents=True, exist_ok=True)
    # Write the closed gate before reading any input; stale successful status
    # cannot survive a later validation error.
    graphite.put(output, 'status.json', {'status': 'validating', 'publishable': False})
    try:
        if replay_path:
            rows, bundle = replay(Path(replay_path))
            sample = bundle.get('acquisition_scope') == 'sample'
            queries = bundle.get('queries', [])
            if Path(replay_path).parent.resolve() != output:
                refs = bundle['sources'] + [q['raw'] for q in queries if q.get('raw')]
                for ref in refs:
                    for rel in (Path(ref['path']), Path(ref['path']).with_suffix('.meta.json')):
                        target = output / rel
                        target.parent.mkdir(parents=True, exist_ok=True)
                        original = Path(replay_path).parent / rel
                        if target.exists() and target.read_bytes() != original.read_bytes():
                            raise ValueError('Existing replay archive differs; refusing overwrite')
                        if not target.exists():
                            shutil.copyfile(original, target)
            graphite.put(output, 'bundle.json', bundle)
            graphite.put(output, 'queries.json', queries)
        else:
            rows, queries = collect(output, sample)
        policy = json.loads(Path(policy_path or ROOT / 'pipeline/manganese_policy.json').read_bytes())
        source_items = json.loads(Path(reviewed_manifest or ROOT / 'pipeline/manganese_reviewed_sources.json').read_bytes())
        sources = evidence.reviewed_sources(evidence_root or ROOT / 'data/review/manganese-evidence', source_items)
        disclosures = evidence.parse_disclosures(Path(disclosures_path or ROOT / 'data/manual/manganese-disclosures.csv').read_bytes(), sources)
        diagnostics = compare(rows, policy)
        anchors = [anchor.diagnose(d, disclosures, policy['country_context'].get(d['country'])) for d in diagnostics]
        decisions = evidence.load_decisions(json.loads(Path(decisions_path or ROOT / 'pipeline/manganese_reviews.json').read_bytes()),
                                            diagnostics, sources, policy['mirror_allowlist'])
        expected = {(y, HS_CODE, f) for y in YEARS for f in ('X', 'M')}
        actual = {(r['year'], r['hs_code'], r['flow']) for r in rows}
        failures = [q for q in queries if q['status'] != 'ok']
        # Query presence alone cannot certify global acquisition. Replay must
        # contain unrestricted authenticated final endpoint requests for all 16.
        bundle = json.loads((output / 'bundle.json').read_bytes())
        from .sources.comtrade import FULL_URL
        full_queries = {(int(s['query']['period']), s['query']['cmdCode'], s['query']['flowCode'])
                        for s in bundle['sources'] if s['url'] == FULL_URL
                        and s['query']['reporterCode'] == '' and s['query']['partnerCode'] == ''}
        full = not sample and not failures and expected == actual == full_queries
        summary = dict(input_rows=len(rows), exporter_years=len(diagnostics),
                       comparison_counts=dict(Counter(d['comparison_status'] for d in diagnostics)),
                       anchor_counts=dict(Counter(d['classification'] for d in anchors)),
                       reviewed_disclosures=len(disclosures), human_decisions=len(decisions),
                       adopted_values=sum(d['selected_weight_t'] is not None for d in decisions),
                       publishable=False)
        for name, value in [('diagnostics.json', diagnostics), ('anchors.json', anchors),
                            ('decisions.json', decisions), ('disclosures.json', disclosures),
                            ('entities.json', entity_diagnostics.summarize(rows)),
                            ('measurements.json', graphite.measurement_audit(rows)), ('summary.json', summary)]:
            graphite.put(output, name, value)
        status = dict(status='diagnosed', acquisition_scope='sample' if sample else 'full',
                      queries_complete=full, attempted_queries=len(queries), failed_queries=failures,
                      missing_year_flows=sorted(expected - actual), global_completeness='unverified',
                      publishable=False, rows=len(rows), unresolved_decisions=len(diagnostics) - len(decisions),
                      limitations=['human_review_required', 'manganese_thresholds_deferred',
                                   'production_trade_comparability_not_established'])
        graphite.put(output, 'status.json', status)
        return summary, (1 if failures or (not sample and not full) else 0)
    except Exception as exc:
        graphite.put(output, 'status.json', {'status': 'failed', 'error_type': type(exc).__name__, 'publishable': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.cache/manganese-audit')
    parser.add_argument('--replay', type=Path)
    parser.add_argument('--sample', action='store_true', help='Explicit 2024 public API sample; never full coverage')
    parser.add_argument('--evidence-root', type=Path)
    parser.add_argument('--reviewed-manifest', type=Path)
    parser.add_argument('--disclosures', type=Path)
    parser.add_argument('--decisions', type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    summary, status = run(args.output, replay_path=args.replay, sample=args.sample,
                          evidence_root=args.evidence_root, reviewed_manifest=args.reviewed_manifest,
                          disclosures_path=args.disclosures, decisions_path=args.decisions)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
