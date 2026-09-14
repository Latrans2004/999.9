"""Bounded A0 public diagnostics. No selection, conversion, or publication.

Run with --fetch to acquire; default verifies archived bytes offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path

from .archive import encode, save

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/review/cobalt'


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--retry-failed', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    ledger = OUT / 'a0-probe.json'
    if args.fetch or args.retry_failed:
        import requests
        if ledger.exists() and not args.retry_failed:
            raise SystemExit('Ledger exists; replay offline instead of overwriting.')
        tracked = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()
        baseline = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                    for p in tracked if p.startswith('critical-minerals/') or p.endswith('.html')}
        if not (OUT / 'baseline.json').exists():
            (OUT / 'baseline.json').write_bytes(encode(baseline))
        session = requests.Session()
        jobs = []
        for code in ('260500', '810520'):
            for reporter, flow in ((180, 'X'), (156, 'M')):
                query = dict(period='2024', reporterCode=reporter, partnerCode=0,
                             partner2Code=0, cmdCode=code, flowCode=flow,
                             customsCode='C00', motCode=0, maxrecords=500)
                jobs.append(('comtrade-preview', 'https://comtradeapi.un.org/public/v1/preview/C/A/HS', query, '.json'))
        jobs += [('usgs-cobalt', f'https://pubs.usgs.gov/periodicals/mcs{year}/mcs{year}-cobalt.pdf', {}, '.pdf')
                 for year in (2025, 2026)]
        jobs.append(('github-prs', 'https://api.github.com/repos/latrans2004/999.9/pulls', {'state': 'open', 'per_page': 100}, '.json'))
        records = json.loads(ledger.read_text(encoding='utf-8')) if args.retry_failed else []
        if args.retry_failed:
            latest = {(e['url'], json.dumps(e['query'], sort_keys=True)): e for e in records}
            jobs = [(e['source'], e['url'], e['query'], '.json') for e in latest.values()
                    if e['status'] == 'http_error' and e['http_status'] in (429, 500, 502, 503, 504)]
        for source, url, query, suffix in jobs:
            entry = dict(source=source, url=url, query=query, publishable=False)
            try:
                if source == 'comtrade-preview':
                    time.sleep(3)
                response = session.get(url, params=query, timeout=45)
                entry['http_status'] = response.status_code
                entry['retry_after'] = response.headers.get('Retry-After')
                entry['raw'] = save(OUT, source, response.content, url=url, query=query, suffix=suffix)
                if response.status_code != 200:
                    entry['status'] = 'http_error'
                elif source == 'comtrade-preview':
                    body = response.json()
                    rows = body.get('data') or []
                    entry.update(count=body.get('count'), rows=len(rows),
                                 classification_codes=sorted({str(r.get('classificationCode')) for r in rows}),
                                 missing_net_weight=sum(r.get('netWgt') is None for r in rows),
                                 status='diagnostic_only' if rows and len(rows) < 500 and body.get('count') == len(rows) else 'needs_review')
                elif source == 'usgs-cobalt':
                    entry['status'] = 'unreviewed_pdf' if response.content.startswith(b'%PDF') else 'invalid_pdf'
                else:
                    prs = response.json()
                    entry['status'] = 'read_only_inventory'
                    entry['open_prs'] = [{'number': p['number'], 'title': p['title'], 'head': p['head']['ref']} for p in prs]
                    entry['pagination_pending'] = 'next' in response.links
            except requests.RequestException as exc:
                entry.update(status='transport_error', error_type=type(exc).__name__)
            except (ValueError, TypeError, KeyError) as exc:
                entry.update(status='invalid_response', error_type=type(exc).__name__)
            records.append(entry)
            print(source, entry['status'], flush=True)
            ledger.write_bytes(encode(records))
    records = json.loads(ledger.read_text(encoding='utf-8'))
    for entry in records:
        if 'raw' in entry:
            raw = entry['raw']
            assert hashlib.sha256((OUT / raw['path']).read_bytes()).hexdigest() == raw['sha256'], raw['path']
    baseline = json.loads((OUT / 'baseline.json').read_text(encoding='utf-8'))
    for path, digest in baseline.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    print(f'Verified {sum("raw" in e for e in records)} archived bodies; {len(baseline)} public baseline files unchanged.')


if __name__ == '__main__':
    main()
