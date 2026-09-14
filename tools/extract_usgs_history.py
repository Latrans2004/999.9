"""Read the world mine production table out of archived USGS MCS lithium chapters.

Offline, one-shot, and deliberately outside the package the pipeline imports:
the published path ingests the reviewed CSV this writes, never a PDF. Run it
again only to re-derive or extend the snapshot.

    pip install -r tools/requirements-extract.txt
    python tools/extract_usgs_history.py <pdf> --out data/review/lithium-usgs-history

What makes it deterministic rather than a reading of the text:

* Pages are chosen by content, not by number: a page is a production table when
  it carries both LITHIUM and "World Mine Production".
* Every span's font size is known, so footnote markers - superscript digits at
  6.48pt against 9.96pt body text - are separated from the figures rather than
  concatenated into them. Without that separation the reference mark in front
  of a world total reads as part of the number (an "8" before 69,000 makes
  869,000), which is how a transcription silently gains a digit.
* Columns are found by clustering the RIGHT edge of each span, because the
  figures are right-aligned and their left edge moves with the digit count.
* A printed row is not flat: spans on one line differ by a couple of points in
  y, so lines are bound within 5pt.
* USGS marks an estimate with a superscript e, either once in a column header
  (the whole column is estimated) or beside a single figure. Those same small
  spans that must stay out of the numbers carry that reading, so they are kept
  aside rather than dropped.

Nothing is inferred: a figure absent from the page is absent from the output,
W stays withheld, and the country total is checked against the printed world
total rather than replacing it.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

import pymupdf

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import countries  # noqa: E402  (repository module, not a package dependency)

ROW_TOLERANCE_PT = 5.0          # one printed line, allowing for baseline drift
COLUMN_TOLERANCE_PT = 9.0       # right edges of one column across rows
LABEL_MAX_X = 240.0             # country labels sit left of the figure columns
SMALL_SPAN_RATIO = 0.9          # anything below this share of body size is a mark
WITHHELD = {'W'}
NIL = {'—', '–', '-', '--'}
NOT_AVAILABLE = {'NA', 'N/A'}
NUMBER = re.compile(r'^\d[\d,]*$')
YEAR = re.compile(r'^(19|20)\d{2}$')
TOTAL_LABEL = re.compile(r'world\s+total', re.I)


def spans_of(page):
    out = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                text = span['text'].strip()
                if text:
                    out.append({'text': text, 'size': round(span['size'], 2),
                                'x0': span['bbox'][0], 'x1': span['bbox'][2], 'y': span['bbox'][1]})
    return out


def body_size(spans):
    weight = {}
    for span in spans:
        weight[span['size']] = weight.get(span['size'], 0) + len(span['text'])
    return max(weight.items(), key=lambda item: item[1])[0]


def bind_rows(spans, tolerance=ROW_TOLERANCE_PT):
    rows, current = [], []
    for span in sorted(spans, key=lambda s: (s['y'], s['x0'])):
        if current and span['y'] - current[0]['y'] > tolerance:
            rows.append(sorted(current, key=lambda s: s['x0']))
            current = []
        current.append(span)
    if current:
        rows.append(sorted(current, key=lambda s: s['x0']))
    return rows


def cluster_columns(edges, tolerance=COLUMN_TOLERANCE_PT):
    clusters = []
    for edge in sorted(edges):
        if clusters and edge - clusters[-1][-1] <= tolerance:
            clusters[-1].append(edge)
        else:
            clusters.append([edge])
    return [sum(c) / len(c) for c in clusters]


def nearest(value, centres, tolerance=COLUMN_TOLERANCE_PT):
    best = min(centres, key=lambda c: abs(c - value), default=None)
    return best if best is not None and abs(best - value) <= tolerance else None


def to_number(text):
    return float(text.replace(',', '')) if NUMBER.match(text) else None


def read_page(page, page_number):
    """One production table: its two data years, its countries and its total."""
    every = spans_of(page)
    base = body_size(every)
    figures = [s for s in every if s['size'] >= base * SMALL_SPAN_RATIO]
    marks = [s for s in every if s['size'] < base * SMALL_SPAN_RATIO]

    rows = bind_rows(figures)
    header = next((r for r in rows if sum(bool(YEAR.match(s['text'])) for s in r) >= 2), None)
    if header is None:
        raise ValueError(f'page {page_number}: no year header row in the production table')
    years = [s for s in header if YEAR.match(s['text'])][:2]

    numeric_edges = [s['x1'] for row in rows for s in row
                     if to_number(s['text']) is not None and s['x0'] > LABEL_MAX_X]
    centres = cluster_columns(numeric_edges + [s['x1'] for s in years])
    columns = {}
    for span in years:
        centre = nearest(span['x1'], centres)
        if centre is None:
            raise ValueError(f'page {page_number}: year {span["text"]} matches no figure column')
        columns[centre] = int(span['text'])

    # A superscript e on a year header estimates that whole column; beside a
    # figure it estimates only that figure.
    estimated_columns = set()
    for mark in marks:
        if 'e' not in mark['text']:
            continue
        for span in years:
            if abs(mark['y'] - span['y']) <= ROW_TOLERANCE_PT and 0 <= mark['x0'] - span['x1'] <= 12:
                estimated_columns.add(columns[nearest(span['x1'], list(columns))])

    records, total, footnote_spans = [], {}, 0
    started = False
    for row in rows:
        if row is header:
            started = True
            continue
        if not started:
            continue
        label = ' '.join(s['text'] for s in row if s['x1'] <= LABEL_MAX_X).strip()
        values = {}
        for span in row:
            if span['x1'] <= LABEL_MAX_X:
                continue
            centre = nearest(span['x1'], list(columns))
            if centre is None:
                continue                      # reserves and other columns
            year = columns[centre]
            text = span['text'].strip()
            number = to_number(text)
            estimated = year in estimated_columns or any(
                'e' in m['text'] and abs(m['y'] - span['y']) <= ROW_TOLERANCE_PT
                and 0 <= m['x0'] - span['x1'] <= 12 for m in marks)
            if number is not None:
                values[year] = {'value': number, 'status': 'estimated' if estimated else 'reported'}
            elif text in WITHHELD:
                values[year] = {'value': None, 'status': 'withheld'}
            elif text in NIL:
                values[year] = {'value': 0.0, 'status': 'estimated' if estimated else 'reported'}
            elif text in NOT_AVAILABLE:
                values[year] = {'value': None, 'status': 'not_available'}
        if not label and not values:
            continue
        if TOTAL_LABEL.search(label):
            total = {year: v['value'] for year, v in values.items()}
            break
        if values:
            records.append({'label': label, 'values': values})
    footnote_spans = sum(1 for m in marks if m['y'] >= header[0]['y'] - ROW_TOLERANCE_PT)
    return {'page': page_number, 'body_font_pt': base, 'years': sorted(columns.values()),
            'estimated_years': sorted(estimated_columns), 'columns': {str(int(c)): y for c, y in columns.items()},
            'countries': records, 'world_total': total,
            'footnote_spans_excluded': footnote_spans,
            'footnote_span_sizes': sorted({m['size'] for m in marks})}


def read_pdf(path: Path):
    document = pymupdf.open(path)
    editions = []
    for number, page in enumerate(document):
        text = page.get_text()
        if 'LITHIUM' not in text or 'World Mine Production' not in text:
            continue
        edition = re.search(r'Mineral Commodity Summaries,\s*\w+\s+(20\d{2})', text)
        if not edition:
            raise ValueError(f'page {number}: production table without an edition line')
        table = read_page(page, number)
        table['edition'] = int(edition.group(1))
        editions.append(table)
    document.close()
    return editions


def check(table):
    """Country sum against the printed world total, per data year."""
    out = {}
    for year in table['years']:
        named = sum(c['values'][year]['value'] for c in table['countries']
                    if year in c['values'] and c['values'][year]['value'] is not None)
        printed = table['world_total'].get(year)
        out[year] = {'country_sum_t': named, 'world_total_t': printed,
                     'difference_pct': None if not printed else round((named / printed - 1) * 100, 2)}
    return out


def adoption(editions):
    """Each data year belongs to the newest edition that reports it.

    An edition prints the previous year as an estimate and the one before it
    revised, so a year is provisional in the edition that first carries it and
    settled in the next. Taking the newest edition is therefore taking the
    settled figure, and it is recorded per row so the choice stays auditable.
    """
    chosen = {}
    for table in editions:
        for year in table['years']:
            if year not in chosen or table['edition'] > chosen[year]:
                chosen[year] = table['edition']
    return chosen


def production_rows(editions, sources, existing_years):
    """Reviewed-CSV rows for the years this PDF settles and the CSV lacks."""
    by_edition = {table['edition']: table for table in editions}
    rows, skipped = [], []
    for year, edition in sorted(adoption(editions).items()):
        if year in existing_years:
            skipped.append((year, edition))
            continue
        table = by_edition[edition]
        source = sources[str(edition)]
        world = table['world_total'].get(year)
        for record in table['countries']:
            value = record['values'].get(year)
            if not value or value['status'] == 'not_available':
                continue
            code = countries.normalize(record['label'])
            if not code:
                skipped.append((year, record['label']))
                continue
            rows.append({'year': year, 'country': code,
                         'production_t': '' if value['value'] is None else f'{value["value"]:g}',
                         'world_total_t': f'{world:g}', 'edition': edition,
                         'status': value['status'], 'source_url': source['chapter_url']})
    return rows, skipped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--note', default='')
    parser.add_argument('--sources', type=Path, help='edition -> official URLs, for the row provenance')
    parser.add_argument('--production-csv', type=Path, help='reviewed table to extend; existing years are left alone')
    args = parser.parse_args()

    body = args.pdf.read_bytes()
    editions = read_pdf(args.pdf)
    for table in editions:
        table['checks'] = check(table)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'extraction.json').write_text(json.dumps(
        {'source_sha256': hashlib.sha256(body).hexdigest(), 'source_note': args.note,
         'editions': editions}, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')

    with (args.out / 'extraction.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle, lineterminator='\n')   # the repository stores LF
        writer.writerow(['edition', 'data_year', 'country_label', 'production_t', 'status', 'page'])
        for table in editions:
            for record in table['countries']:
                for year in table['years']:
                    value = record['values'].get(year)
                    if value:
                        writer.writerow([table['edition'], year, record['label'],
                                         '' if value['value'] is None else value['value'],
                                         value['status'], table['page']])
            for year in table['years']:
                printed = table['world_total'].get(year)
                if printed is not None:
                    writer.writerow([table['edition'], year, 'World total (rounded)', printed, 'printed', table['page']])

    if args.production_csv:
        sources = {str(e['edition']): e for e in json.loads(args.sources.read_text(encoding='utf-8'))}
        lines = args.production_csv.read_text(encoding='utf-8').splitlines(keepends=True)
        header, body = lines[0], lines[1:]
        existing = {int(line.split(',')[0]) for line in body if line.strip()}
        rows, skipped = production_rows(editions, sources, existing)
        fields = header.strip().split(',')
        added = ''.join(','.join(str(row[f]) for f in fields) + '\n' for row in rows)
        # New years are written above the block already in the file, so the years
        # read in order while every line that was already reviewed stays untouched.
        args.production_csv.write_text(header + added + ''.join(body), encoding='utf-8')
        print(f'added {len(rows)} reviewed rows for years {sorted({r["year"] for r in rows})}; '
              f'left {sorted(existing)} untouched')
        for item in skipped:
            print(f'  not adopted: {item}')

    for table in editions:
        print(f"MCS {table['edition']} page {table['page']}: years {table['years']} "
              f"estimated {table['estimated_years']} countries {len(table['countries'])} "
              f"footnote spans excluded {table['footnote_spans_excluded']}")
        for year, result in sorted(table['checks'].items()):
            print(f"    {year}: countries {result['country_sum_t']:,.0f} vs printed "
                  f"{result['world_total_t']:,} -> {result['difference_pct']}%")


if __name__ == '__main__':
    main()
