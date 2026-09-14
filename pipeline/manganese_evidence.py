"""Strict, offline human-review boundary for manganese evidence.

Discover manifests are observations, never approvals. A human must copy BOTH
path and sha256 into the reviewed manifest and attest the annual measurement.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from . import archive, countries, strict_comtrade

FIELDS = ('country', 'year', 'measure', 'value_t', 'company', 'operation',
          'source_url', 'locator', 'review_date', 'weight_basis', 'product_scope',
          'period_start', 'period_end', 'coverage_scope')
BASES = {'ore_mass_unspecified_moisture', 'dry_ore_mass', 'wet_ore_mass', 'contained_mn'}
PRODUCT = 'manganese_ores_concentrates'


def required(item, fields):
    for field in fields:
        if field not in item or item[field] is None or str(item[field]).strip() == '':
            raise ValueError(f'Missing required field: {field}')


def date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Invalid ISO date')
    result = dt.date.fromisoformat(value)
    if result > dt.datetime.now(dt.timezone.utc).date():
        raise ValueError('Future review/measurement date')
    return result


def year(value):
    if not re.fullmatch(r'20\d{2}', str(value)) or int(value) not in range(2017, 2025):
        raise ValueError('Year outside manganese scope 2017-2024')
    return int(value)


def country(value):
    entity = countries.resolve(code=value)
    if entity.key != value or not countries.metric_eligibility(entity)[0]:
        raise ValueError('Invalid country identity')
    return value


def annual(item):
    y = year(item['year'])
    start, end = date(item['period_start']), date(item['period_end'])
    if end.year != y or (end - start).days not in (364, 365):
        raise ValueError('Annual period required; quarterly and YTD values are forbidden')
    return y


def source_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
        raise ValueError('Expected public HTTPS source URL without credentials or fragment')
    return url


def verify_raw(root, ref):
    required(ref, ('path', 'sha256', 'url', 'query', 'retrieved_at', 'source'))
    path = PurePosixPath(ref['path'])
    if '\\' in ref['path'] or path.is_absolute() or '..' in path.parts or path.parts[:2] != ('data', 'raw'):
        raise ValueError('Raw path must stay inside data/raw')
    full = (Path(root) / path).resolve()
    if not full.is_relative_to(Path(root).resolve()):
        raise ValueError('Raw path escapes archive')
    if not re.fullmatch(r'[0-9a-f]{64}', ref['sha256']):
        raise ValueError('Invalid sha256 pin')
    body = full.read_bytes()
    if hashlib.sha256(body).hexdigest() != ref['sha256']:
        raise ValueError('Raw archive sha256 mismatch')
    expected_name = hashlib.sha256(archive.encode({'url': ref['url'], 'query': ref['query']}) + body).hexdigest()
    if full.stem != expected_name:
        raise ValueError('Raw content-addressed path mismatch')
    sidecar = json.loads(full.with_suffix('.meta.json').read_bytes())
    if any(sidecar.get(k) != ref[k] for k in ('path', 'sha256', 'url', 'query', 'retrieved_at', 'source')):
        raise ValueError('Raw archive metadata mismatch')
    return body


def reviewed_sources(root, manifest):
    """Validate all pins, even when the measurement CSV is empty."""
    result = {}
    for item in manifest:
        required(item, ('kind', 'source_url', 'reviewer', 'review_date', 'review_status', 'raw'))
        if item['kind'] != 'document' or item['review_status'] != 'human_reviewed':
            raise ValueError('Source is not a human-reviewed document')
        date(item['review_date'])
        url = source_url(item['source_url'])
        if url in result:
            raise ValueError('Duplicate reviewed source URL')
        if item['raw'].get('url') != url:
            raise ValueError('Source URL differs from pinned archive')
        verify_raw(root, item['raw'])
        result[url] = item
    return result


def parse_disclosures(body, sources):
    reader = csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
    if reader.fieldnames is None or len(reader.fieldnames) != len(set(reader.fieldnames)) or set(reader.fieldnames) != set(FIELDS):
        raise ValueError('Invalid disclosure CSV schema')
    records, seen = [], set()
    for item in reader:
        if None in item:
            raise ValueError('Extra CSV cells')
        required(item, FIELDS)
        item = {k: v.strip() for k, v in item.items()}
        item['country'] = country(item['country'])
        item['year'] = annual(item)
        if item['measure'] not in {'production', 'sales'}:
            raise ValueError('Disclosure measure must be production or sales')
        value = strict_comtrade.number(item['value_t'])
        if value is None:
            raise ValueError('Missing disclosure value')
        item['value_t'] = value
        if item['weight_basis'] not in BASES or item['product_scope'] != PRODUCT:
            raise ValueError('Invalid disclosure weight basis or product scope')
        if item['coverage_scope'] not in {'operation_100_percent', 'equity_share', 'national'}:
            raise ValueError('Invalid coverage scope')
        date(item['review_date'])
        source = sources.get(item['source_url'])
        if not source:
            raise ValueError('Unpinned disclosure source')
        if item['review_date'] < source['review_date']:
            raise ValueError('Measurement review predates source review')
        # An annual document can include quarterly columns. Pin each reviewed
        # annual cell's meaning, not merely the document containing it.
        identity = {k: item[k] for k in FIELDS if k != 'review_date'}
        if identity not in source.get('measurements', []):
            raise ValueError('Annual measurement not attested in human review')
        key = tuple(item[k] for k in ('country', 'year', 'measure', 'company', 'operation'))
        if key in seen:
            raise ValueError('Duplicate disclosure observation')
        seen.add(key)
        records.append(item | {'raw': source['raw'], 'reviewer': source['reviewer']})
    return records


def load_decisions(items, diagnostics, sources, mirror_allowlist):
    """Human decisions remain separate; no diagnostics may supply adoption."""
    known = {(d['country'], d['year']): d for d in diagnostics}
    seen, result = set(), []
    for item in items:
        required(item, ('country', 'year', 'hs_code', 'decision', 'reason', 'reviewer',
                        'review_date', 'review_status', 'source_url', 'locator', 'evidence_sha256',
                        'evidence_path', 'weight_basis', 'product_scope'))
        key = (country(item['country']), year(item['year']))
        if key in seen or key not in known:
            raise ValueError('Duplicate or unobserved review decision')
        seen.add(key)
        if item['hs_code'] != '260200' or item['review_status'] != 'human_reviewed':
            raise ValueError('Decision must be a human review of HS260200')
        date(item['review_date'])
        source = sources.get(item['source_url'])
        if not source or any(item['evidence_' + k] != source['raw'][k] for k in ('path', 'sha256')):
            raise ValueError('Unpinned decision evidence')
        if item['review_date'] < source['review_date']:
            raise ValueError('Decision predates source review')
        if item['weight_basis'] != 'ore_mass_unspecified_moisture' or item['product_scope'] != PRODUCT:
            raise ValueError('Decision unit or product scope incompatible with trade')
        choice = item['decision']
        if choice not in {'reported', 'mirror', 'external', 'exclude'}:
            raise ValueError('Invalid human decision')
        value = strict_comtrade.number(item.get('selected_weight_t'))
        if choice == 'exclude':
            if value is not None:
                raise ValueError('Excluded value must be null')
        elif value is None:
            raise ValueError('Adoption requires selected_weight_t')
        d = known[key]
        if choice == 'reported' and value != d['reported_weight_t']:
            raise ValueError('Decision differs from reported observation')
        if choice == 'mirror' and (key[0] not in mirror_allowlist or value != d['mirror_observed_weight_t']):
            raise ValueError('Mirror decision outside allowlist or observed value')
        # Primary evidence must specifically attest annual NATIONAL exports;
        # production/sales context cannot authorize an export replacement.
        attestation = {k: item[k] for k in ('country', 'year', 'hs_code', 'locator', 'weight_basis', 'product_scope')}
        attestation.update(year=key[1], measure='exports', coverage_scope='national', value_t=value)
        if attestation not in source.get('trade_decisions', []):
            raise ValueError('Primary annual export evidence not attested')
        result.append(dict(item, year=key[1], selected_weight_t=value, publishable=False))
    return result
