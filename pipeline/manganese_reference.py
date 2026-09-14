"""Offline USGS reference diagnostics; extracted candidates are NOT human reviews.

Only the explicitly researched MCS2026/2024 first column is supported. This
command never writes disclosure CSVs, review manifests, decisions or site data.
"""
from __future__ import annotations
import argparse
from collections import Counter
import io
import json
from pathlib import Path
import re

from pypdf import PdfReader
from . import graphite, graphite_usgs, manganese as mn, manganese_anchor as anchor
from . import manganese_evidence as evidence

URL = 'https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-manganese.pdf'


def parse_usgs(text, raw):
    if not re.search(r'Data in thousand metric tons,\s*gross weight, unless otherwise specified', text):
        raise ValueError('USGS native unit header changed')
    start_label = 'World Mine Production (manganese content) and Reserves:'
    if start_label not in text or 'World Resources:' not in text:
        raise ValueError('USGS manganese-content table heading changed')
    table = text.split(start_label, 1)[1].split('World Resources:', 1)[0]
    table = table.replace('Other countries', 'Other').replace('Côte d’Ivoire', "Côte d'Ivoire")
    parsed = graphite_usgs.parse_table(table, 2024, raw)
    result = []
    for r in parsed:
        result.append(dict(country=r['country'], name=r['name'], year=2024, measure='production',
                           value_t=r['production_t'] * 1000 if r['production_t'] is not None else None,
                           weight_basis='contained_mn', product_scope=evidence.PRODUCT,
                           period_start='2024-01-01', period_end='2024-12-31',
                           coverage_scope='national' if r['kind'] == 'country' else r['kind'],
                           native_token=r['native_token'], native_unit='thousand_metric_tonnes_contained_mn',
                           estimate_status=r['status'], source_url=URL, raw=raw,
                           locator='MCS 2026 manganese p.2, World Mine Production, 2024 column',
                           review_status='unreviewed_machine_extraction', publishable=False))
    return result


def run(trade_bundle, evidence_root, output):
    output = mn.isolated_output(output)
    graphite.put(output, 'status.json', {'status': 'validating', 'publishable': False})
    try:
        rows, _ = mn.replay(Path(trade_bundle))
        items = json.loads((evidence_root / 'discover.json').read_bytes())
        bodies = {}
        for item in items:
            if item.get('raw'):
                body = evidence.verify_raw(evidence_root, item['raw'])
                if item['source_url'] != item['raw']['url']:
                    raise ValueError('Discover URL/archive mismatch')
                if item['source_url'] in bodies:
                    raise ValueError('Duplicate reference source')
                bodies[item['source_url']] = (body, item['raw'])
        if URL not in bodies:
            raise ValueError('MCS2026 archive is missing; no reference extraction available')
        body, raw = bodies[URL]
        pages = PdfReader(io.BytesIO(body)).pages
        if len(pages) != 2:
            raise ValueError('USGS manganese document layout changed')
        text = '\n'.join(page.extract_text(extraction_mode='layout') for page in pages)
        production = parse_usgs(text, raw)
        policy = json.loads((mn.ROOT / 'pipeline/manganese_policy.json').read_bytes())
        trade = mn.compare(rows, policy)
        contexts = [r for r in production if r['coverage_scope'] == 'national']
        checks = [anchor.diagnose(d, contexts, policy['country_context'].get(d['country'])) |
                  {'reference_review_status': 'unreviewed_machine_extraction',
                   'eligible_as_reviewed_anchor': False} for d in trade]
        summary = dict(status='diagnosed', trade_rows=len(rows), production_rows=len(production),
                       production_country_rows=len(contexts), exporter_years=len(checks),
                       classification_counts=dict(Counter(c['classification'] for c in checks)),
                       comparability_issue_counts=dict(Counter(x for c in checks for x in c['comparability_issues'])),
                       reference_review_status='unreviewed_machine_extraction', adopted_values=0,
                       publishable=False)
        graphite.put(output, 'production-candidates.json', production)
        graphite.put(output, 'reference-diagnostics.json', checks)
        graphite.put(output, 'status.json', summary)
        return summary
    except Exception as exc:
        graphite.put(output, 'status.json', {'status': 'failed', 'error_type': type(exc).__name__, 'publishable': False})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trade-bundle', type=Path, default=mn.ROOT / 'data/review/manganese-sample/bundle.json')
    parser.add_argument('--evidence-root', type=Path, default=mn.ROOT / 'data/review/manganese-evidence')
    parser.add_argument('--output', type=Path, default=mn.ROOT / '.cache/manganese-reference')
    args = parser.parse_args()
    print(json.dumps(run(args.trade_bundle, args.evidence_root, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
