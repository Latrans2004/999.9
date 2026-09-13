"""Archive fixed USGS natural graphite editions and extract tables for review."""
import argparse
import io
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader
from . import archive
from .sources import http
from .graphite import put
from . import countries, hhi


def parse_table(table, year, source):
    header = re.search(rf'\b{year}\s+{year + 1}e\b', table)
    if not header:
        raise ValueError('USGS production column headings changed')
    records = []
    for line in table[header.end():].splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r'\s*(.+?)\s+(e?[\d,]+|\u2014|W|NA)\s+(e?[\d,]+|\u2014|W|NA)\s+.*', line)
        if not match:
            raise ValueError(f'Unrecognized USGS production row: {line}')
        name, token = match[1], match[2]
        kind = 'world' if name == 'World total (rounded)' else 'residual' if name == 'Other' else 'country'
        aliases = {'Korea, North': 'PRK', 'Korea, Republic of': 'KOR', 'Turkey': 'TUR'}
        country = aliases.get(name) or (countries.normalize(name) if kind == 'country' else None)
        value = None if token in ('W', 'NA') else 0 if token == '\u2014' else int(token.lstrip('e').replace(',', ''))
        records.append({'year': year, 'country': country, 'name': name, 'kind': kind,
                        'production_t': value, 'native_token': token,
                        'status': 'withheld' if token == 'W' else 'missing' if token == 'NA' else
                                  'estimated' if token.startswith('e') else 'reported',
                        'source': source})
    if sum(r['kind'] == 'world' for r in records) != 1:
        raise ValueError('USGS world total absent or duplicated')
    if len({r['name'] for r in records}) != len(records):
        raise ValueError('Duplicate USGS production row')
    return records


def profiles(records):
    results = []
    for year in range(2017, 2025):
        group = [r for r in records if r['year'] == year]
        world = next(r['production_t'] for r in group if r['kind'] == 'world')
        amounts = {r['country']: r['production_t'] for r in group
                   if r['kind'] == 'country' and r['production_t'] is not None}
        profile = hhi.concentration(year, amounts, universe_total=world)
        if profile is None or world is None or world <= 0:
            raise ValueError('USGS empty production universe')
        residual = sum(r['production_t'] or 0 for r in group if r['kind'] == 'residual')
        rounding_difference = (sum(amounts.values()) + residual - world) / world
        if abs(rounding_difference) > 0.01:
            raise ValueError('USGS country plus residual differs from rounded world by over 1%')
        results.append({'year': year, 'profile': profile.to_dict(),
                        'rounded_world_total_t': world, 'other_t': residual,
                        'rounding_relative_difference': rounding_difference,
                        'estimated_countries': [r['country'] for r in group if r['status'] == 'estimated'],
                        'scope': 'USGS natural graphite mine output; identified producers; estimates retained',
                        'source_edition': year + 2})
    for index, result in enumerate(results):
        result['yoy'] = None
        result['quality_flags'] = []
        if index:
            old, current = results[index - 1]['profile'], result['profile']
            result['yoy'] = {'total_ratio': current['total'] / old['total'],
                             'hhi_delta': current['hhi'] - old['hhi'],
                             'cr3_delta': current['cr3'] - old['cr3'],
                             'country_count_delta': current['reporters'] - old['reporters']}
            if not 0.7 <= result['yoy']['total_ratio'] <= 1.3 or abs(result['yoy']['hhi_delta']) > 1000:
                result['quality_flags'].append('year_or_source_vintage_change_requires_review')
        result['publishable'] = False
    return results


def collect(root, *, replay=False):
    sources, tables, records = [], [], []
    manifest = json.loads(Path(__file__).with_name('graphite_usgs_sources.json').read_bytes())
    if {s['edition'] for s in manifest} != set(range(2019, 2027)):
        raise ValueError('USGS source edition coverage changed')
    for source in manifest:
        edition, url = source['edition'], source['url']
        body = (root / source['path']).read_bytes() if replay else http.get(url, binary=True, use_cache=False)
        ref = archive.save(root, 'usgs', body, url=url, suffix='.pdf')
        if hashlib.sha256(body).hexdigest() != source['sha256']:
            raise ValueError('USGS PDF revised; table review required before accepting changed values')
        sources.append(ref)
        pages = PdfReader(io.BytesIO(body)).pages
        text = '\n'.join(page.extract_text() for page in pages)
        start = text.index('World Mine Production and Reserves:')
        end = text.index('World Resources:', start)
        table = text[start:end]
        tables.append({'edition': edition, 'year': edition - 2, 'text': table,
                       'source': ref, 'status': 'visually_reviewed_2026-09-13'})
        records.extend(parse_table(table, edition - 2, ref))
        put(root, 'usgs-tables.json', tables)
    put(root, 'production.json', records)
    put(root, 'production-metrics.json', profiles(records))
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.cache/graphite-usgs'))
    args = parser.parse_args()
    collect(args.output)
