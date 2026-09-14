"""Verified-archive BGS historical candidates; no export selection or review writes."""
from __future__ import annotations
import argparse
from collections import defaultdict
import io
import json
from pathlib import Path
import re

from pypdf import PdfReader
from . import countries, graphite, manganese as mn, manganese_evidence as evidence

EDITIONS = {'bgs-2017-2021': (2017, 53, 30), 'bgs-2020-2024': (2020, 55, 32)}
ALIASES = {'Congo, Democratic Republic': 'COD', 'Ivory Coast': 'CIV', 'Côte d’Ivoire': 'CIV', 'Turkey': 'TUR'}
CELL = re.compile(r'(?:(\([a-e]\))\s*)?(\*\s*)?(—|\d{1,3}(?: \d{3})*)')
NOTES = {'a': 'Marketable', 'b': 'Including beneficiated and direct shipping ore',
         'c': 'Years ended 30 June of that stated',
         'd': 'Years ended 31 March following that stated',
         'e': 'Years ended 20 March following that stated'}


def parse(text, edition, raw):
    start, page, expected = EDITIONS[edition]
    if 'Production of manganese ore tonnes (metric)' not in text:
        raise ValueError('BGS product/unit header changed')
    header = 'Country ' + ' '.join(str(y) for y in range(start, start + 5))
    if header not in text or 'Note(s)' not in text:
        raise ValueError('BGS years/table boundary changed')
    for key, value in NOTES.items():
        if not re.search(r'\(' + key + r'\)\s+' + re.escape(value), text):
            raise ValueError('BGS footnote definition changed')
    table = text.split(header, 1)[1].split('Note(s)', 1)[0]
    # Two broken initial letters in this archived PDF's text layer.
    table = table.replace('Z\nambia', 'Zambia').replace('V\nietnam', 'Vietnam')
    rows, seen = [], set()
    for line in table.splitlines():
        line = line.strip()
        if not line or line.startswith('World total'):
            continue  # Rounded world aggregate is not a national observation.
        match = re.fullmatch(r'(.+?)\s{2,}(.*)', line)
        if not match:
            raise ValueError('Unrecognized BGS country row')
        name, tail = match.groups()
        country = ALIASES.get(name) or countries.normalize(name)
        if country in seen:
            raise ValueError('Duplicate BGS country')
        seen.add(country)
        row_note = re.match(r'\(([a-e])\)\s{2,}', tail)
        if row_note:
            tail = tail[row_note.end():]
        matches = list(CELL.finditer(tail))
        if len(matches) != 5 or CELL.sub('', tail).strip():
            raise ValueError('BGS must have exactly five valid annual cells')
        for year, cell in zip(range(start, start + 5), matches):
            cell_note, estimated, token = cell.groups()
            note = cell_note[1] if cell_note else row_note[1] if row_note else None
            if note == 'c':
                period_start, period_end = f'{year-1}-07-01', f'{year}-06-30'
            elif note == 'd':
                period_start, period_end = f'{year}-04-01', f'{year+1}-03-31'
            elif note == 'e':
                # Calendar conversion/leap-day definition needs source review.
                period_start, period_end = None, f'{year+1}-03-20'
            else:
                period_start, period_end = f'{year}-01-01', f'{year}-12-31'
            rows.append(dict(country=country, year=year, measure='production',
                value_t=0 if token == '—' else int(token.replace(' ', '')),
                native_token=cell[0].strip(), native_unit='metric_tonnes_ore',
                estimate_status='estimated' if estimated else 'not_marked_estimated',
                quantity_status='nil' if token == '—' else 'less_than_half_unit' if token == '0' else 'reported',
                weight_basis=mn.WEIGHT_BASIS, product_scope=evidence.PRODUCT,
                product_qualification=NOTES.get(note), coverage_scope='national',
                period_start=period_start, period_end=period_end,
                period_review_required=note in {'c', 'd', 'e'},
                source_vintage=edition, source_url=raw['url'], raw=raw,
                locator=f'PDF page {page+1}, printed p.46, {name}, {year} column',
                review_status='unreviewed_machine_extraction',
                eligible_as_reviewed_anchor=False, publishable=False))
    if len(seen) != expected:
        raise ValueError('BGS country population changed; review parser')
    return rows


def run(root, output):
    output = mn.isolated_output(output)
    graphite.put(output, 'status.json', dict(status='validating', publishable=False))
    rows = []
    try:
        items = json.loads((root / 'discover.json').read_bytes())
        seen = set()
        for item in items:
            if item['id'] not in EDITIONS:
                continue
            if item['id'] in seen:
                raise ValueError('Duplicate BGS edition')
            seen.add(item['id'])
            if item.get('status') != 'downloaded_unreviewed':
                raise ValueError('BGS source is missing')
            raw = item['raw']
            if raw['url'] != item['source_url']:
                raise ValueError('BGS source URL mismatch')
            body = evidence.verify_raw(root, raw)
            page = EDITIONS[item['id']][1]
            text = PdfReader(io.BytesIO(body)).pages[page].extract_text()
            rows.extend(parse(text, item['id'], raw))
        if seen != set(EDITIONS):
            raise ValueError('Required BGS editions missing')
        groups = defaultdict(list)
        for row in rows:
            groups[row['country'], row['year']].append(row)
        revisions = [dict(country=c, year=y,
                         observations=[{k: r[k] for k in ('source_vintage', 'value_t', 'native_token', 'locator', 'raw')} for r in values],
                         changed=len({r['value_t'] for r in values}) > 1,
                         selected_value_t=None, publishable=False)
                     for (c, y), values in sorted(groups.items()) if len(values) > 1]
        summary = dict(status='extracted_unreviewed', annual_observations=len(rows),
                       unique_country_years=len(groups), countries=len({r['country'] for r in rows}),
                       years=sorted({r['year'] for r in rows}),
                       overlap_country_years=len(revisions), changed_values=sum(r['changed'] for r in revisions),
                       fiscal_observations=sum(r['period_review_required'] for r in rows),
                       missing_observations=sum(r['value_t'] is None for r in rows),
                       nil_observations=sum(r['quantity_status'] == 'nil' for r in rows),
                       adopted_values=0, publishable=False)
        graphite.put(output, 'production-candidates.json', rows)
        graphite.put(output, 'vintage-comparison.json', revisions)
        graphite.put(output, 'status.json', summary)
        return summary
    except Exception as exc:
        graphite.put(output, 'status.json', dict(status='failed', error_type=type(exc).__name__, publishable=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence-root', type=Path, default=mn.ROOT / 'data/review/manganese-additional-evidence')
    parser.add_argument('--output', type=Path, default=mn.ROOT / 'data/review/manganese-bgs-history')
    args = parser.parse_args()
    print(json.dumps(run(args.evidence_root, args.output), sort_keys=True))


if __name__ == '__main__':
    main()
