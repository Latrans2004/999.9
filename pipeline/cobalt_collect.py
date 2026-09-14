"""Small authenticated cobalt observations; no adoption or publication."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import os
from pathlib import Path
import time

import requests

from . import archive, strict_comtrade

URL = 'https://comtradeapi.un.org/data/v1/get/C/A/HS'
LIMIT = 5000


def plan():
    scopes = [(year, code, reporter, flow, '')
              for year in (2017, 2024) for code in ('260500', '810520')
              for reporter, flow in (('180', 'X'), ('156', 'M'))]
    scopes += [(2024, code, '', 'X', '0') for code in ('260500', '810520')]
    scopes += [(2024, '282200', reporter, flow, '')
               for reporter, flow in (('180', 'X'), ('156', 'M'))]
    return [dict(period=str(y), cmdCode=code, reporterCode=reporter,
                 flowCode=flow, partnerCode=partner, partner2Code='0',
                 customsCode='C00', motCode='0', maxRecords=LIMIT,
                 includeDesc='true', breakdownMode='classic')
            for y, code, reporter, flow, partner in scopes]


def diagnose(body, query):
    payload = json.loads(body)
    if not isinstance(payload, dict) or payload.get('error') or payload.get('errorMessage'):
        raise ValueError('API error payload')
    data = payload.get('data')
    if not isinstance(data, list) or type(payload.get('count')) is not int:
        raise ValueError('Missing data/count')
    if payload['count'] != len(data):
        raise ValueError('Count mismatch')
    if not data:
        return {'status': 'empty', 'rows': 0}, []
    normalized = strict_comtrade.normalize(payload, query, LIMIT)
    for row, native in zip(normalized, data, strict=True):
        classification = native.get('classificationCode')
        if classification not in {'H0', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6'}:
            raise ValueError('Unrecognized HS version')
        for field in ('isReported', 'isAggregate', 'isNetWgtEstimated', 'isQtyEstimated',
                      'legacyEstimationFlag', 'qtyUnitCode', 'fobvalue', 'cifvalue'):
            row[field] = native.get(field)
        row['publishable'] = False
    return dict(status='observed', rows=len(data),
                classifications=sorted({r['classification'] for r in normalized}),
                missing_net_weight=sum(r['net_weight_kg'] is None for r in normalized),
                estimated_net_weight=sum(r['isNetWgtEstimated'] is True for r in normalized)), normalized


def retry_delay(value, attempt):
    if value:
        try:
            return max(3.0, float(value))
        except ValueError:
            try:
                return max(3.0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                pass
    return 3.0 * 2 ** attempt


def put(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_bytes(archive.encode(value))
    temp.replace(path)


def collect(root):
    key = os.environ.get('COMTRADE_API_KEY', '').strip()
    if not key:
        raise ValueError('Missing Actions secret')
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_bytes()) if manifest_path.exists() else {
        'schema_version': 1, 'publishable': False, 'queries': plan(), 'attempts': []}
    if manifest['queries'] != plan():
        raise ValueError('Plan changed; use a separate archive')
    # Validate prior response bodies before reusing observations.
    replay(root, manifest)
    session = requests.Session()
    session.headers['Ocp-Apim-Subscription-Key'] = key
    for query in plan():
        previous = [a for a in manifest['attempts'] if a['query'] == query]
        if previous and previous[-1]['status'] in ('observed', 'empty'):
            continue
        for attempt in range(3):
            entry = {'query': query, 'publishable': False, 'attempted_at': archive.now()}
            delay, again = 3, False
            try:
                response = session.get(URL, params=query, timeout=60, allow_redirects=False)
                entry.update(http_status=response.status_code, retry_after=response.headers.get('Retry-After'))
                # No request headers or exception text are persisted.
                if key.encode() in response.content:
                    entry['status'] = 'secret_echo_rejected'
                else:
                    entry['raw'] = archive.save(root, 'comtrade-auth', response.content, url=URL, query=query)
                    if response.status_code == 200:
                        diagnostic, _ = diagnose(response.content, query)
                        entry.update(diagnostic)
                    else:
                        entry['status'] = 'http_error'
                        again = response.status_code in (429, 500, 502, 503, 504)
                        delay = retry_delay(entry['retry_after'], attempt)
            except requests.RequestException as exc:
                entry.update(status='transport_error', error_type=type(exc).__name__)
                again, delay = True, 3 * 2 ** attempt
            except (ValueError, TypeError, KeyError) as exc:
                entry.update(status='invalid_response', error_type=type(exc).__name__)
            manifest['attempts'].append(entry)
            put(manifest_path, manifest)
            print(query['period'], query['cmdCode'], query['reporterCode'] or 'all', query['flowCode'], entry['status'], flush=True)
            if not again or attempt == 2 or delay > 60:
                time.sleep(3)
                break
            time.sleep(delay)
    replay(root, manifest)
    latest = {json.dumps(a['query'], sort_keys=True): a for a in manifest['attempts']}
    if len(latest) != len(plan()) or any(a['status'] not in ('observed', 'empty') for a in latest.values()):
        raise ValueError('Some queries failed; see archived manifest')


def replay(root, manifest=None):
    manifest = manifest if manifest is not None else json.loads((root / 'manifest.json').read_bytes())
    if manifest['queries'] != plan() or manifest['publishable'] is not False:
        raise ValueError('Unexpected plan/publication flag')
    latest = {}
    for entry in manifest['attempts']:
        if entry['query'] not in plan():
            raise ValueError('Out-of-plan observation')
        raw = entry.get('raw')
        if raw:
            path = (root / raw['path']).resolve()
            if not path.is_relative_to(root.resolve() / 'data/raw'):
                raise ValueError('Raw path escapes archive')
            body = path.read_bytes()
            if hashlib.sha256(body).hexdigest() != raw['sha256']:
                raise ValueError('Raw hash mismatch')
            sidecar = json.loads(path.with_suffix('.meta.json').read_bytes())
            if sidecar != raw or raw['query'] != entry['query'] or raw['url'] != URL:
                raise ValueError('Raw metadata mismatch')
            if entry['status'] in ('observed', 'empty'):
                diagnostic, rows = diagnose(body, entry['query'])
                if entry.get('http_status') != 200 or any(entry.get(k) != v for k, v in diagnostic.items()):
                    raise ValueError('Replayed diagnostic mismatch')
                latest[json.dumps(entry['query'], sort_keys=True)] = [dict(r, raw_path=raw['path']) for r in rows]
        elif entry['status'] in ('observed', 'empty'):
            raise ValueError('Accepted observation missing Raw')
    # These query groups overlap (world/bilateral); retain query provenance, never sum globally.
    put(root / 'observations.json', {'publishable': False, 'query_groups': latest})
    return latest


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--root', type=Path, default=Path('data/review/cobalt/auth'))
    args = parser.parse_args()
    if args.collect:
        collect(args.root)
    else:
        replay(args.root)


if __name__ == '__main__':
    main()
