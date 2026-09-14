"""Reviewed operator disclosures for the exporters mine output can adjudicate.

Mirror statistics cannot say which side of a disputed export figure is wrong, and
USGS mine output is contextual rather than an export measurement. An operator's
audited production and sales for a named mine is specific evidence, so it is
carried the way lithium carries its reviewed production: a committed CSV whose
every row cites a primary document, validated here and never invented.

Acquisition runs in Actions, where the network is open. `discover` archives the
listed primary documents and reports their hashes for visual review; a reviewed
hash is then pinned in graphite_company_sources.json and the extracted figures
are entered in data/manual/natural-graphite-company-disclosures.csv. `load`
refuses any row whose source is unpinned or whose bytes have changed.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from . import archive

ROOT = Path(__file__).resolve().parents[1]
REVIEWED_CSV = 'data/manual/natural-graphite-company-disclosures.csv'
SOURCES = Path(__file__).with_name('graphite_company_sources.json')
COLUMNS = ['country', 'year', 'measure', 'value_t', 'company', 'operation',
           'source_url', 'locator', 'review_date']
MEASURES = {'production', 'sales'}


def pinned_sources():
    """URLs whose bytes a human has reviewed, keyed by url."""
    manifest = json.loads(SOURCES.read_bytes())['documents']
    pinned = {}
    for entry in manifest:
        if entry.get('sha256'):
            if entry['url'] in pinned:
                raise ValueError(f'Duplicate pinned source {entry["url"]}')
            pinned[entry['url']] = entry
    return pinned


def load(root=ROOT):
    """Reviewed disclosures, refusing anything not backed by a pinned source."""
    path = Path(root) / REVIEWED_CSV
    pinned = pinned_sources()
    rows, seen = [], set()
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ValueError(f'Unexpected disclosure columns: {reader.fieldnames}')
        for line in reader:
            for column in COLUMNS:
                if not (line[column] or '').strip():
                    raise ValueError(f'Blank {column}; a missing disclosure is a missing row, never zero')
            if line['measure'] not in MEASURES:
                raise ValueError(f'Unknown measure {line["measure"]}')
            value = float(line['value_t'])
            if value < 0:
                raise ValueError('Negative disclosed tonnage')
            key = (line['country'], int(line['year']), line['measure'],
                   line['company'], line['operation'])
            if key in seen:
                raise ValueError(f'Duplicate disclosure {key}')
            seen.add(key)
            if line['source_url'] not in pinned:
                raise ValueError(f'Unpinned source {line["source_url"]}; archive and review it first')
            rows.append({**line, 'year': int(line['year']), 'value_t': value,
                         'source': pinned[line['source_url']]})
    return rows


def verify_archived(root=ROOT):
    """Fail closed when a pinned primary document's bytes have changed."""
    root = Path(root)
    for url, entry in sorted(pinned_sources().items()):
        body = (root / entry['path']).read_bytes()
        if hashlib.sha256(body).hexdigest() != entry['sha256']:
            raise ValueError(f'Primary document revised; review required before accepting {url}')


def discover(root, http):
    """Archive listed primary documents and report hashes for visual review.

    Runs in Actions. Nothing is accepted here: a newly archived document is only
    a candidate until a reviewer pins its hash and enters the figures.
    """
    packet = []
    for entry in json.loads(SOURCES.read_bytes())['documents']:
        if entry.get('kind') != 'document':
            # An index page (an announcements list, a news feed) is for a human
            # to browse for the real document URL, never a source to archive.
            packet.append({'url': entry['url'], 'company': entry.get('company'),
                           'operation': entry.get('operation'), 'path': None,
                           'sha256': None, 'pinned_sha256': None, 'status': 'index_not_fetched'})
            continue
        try:
            body = http.get(entry['url'], binary=True, use_cache=False)
        except Exception as exc:
            packet.append({'url': entry['url'], 'company': entry.get('company'),
                           'operation': entry.get('operation'), 'path': None,
                           'sha256': None, 'pinned_sha256': entry.get('sha256'),
                           'status': 'fetch_failed', 'error': f'{type(exc).__name__}: {exc}'})
            continue
        suffix = entry.get('suffix', '.pdf')
        ref = archive.save(root, 'company', body, url=entry['url'], suffix=suffix)
        digest = hashlib.sha256(body).hexdigest()
        packet.append({'url': entry['url'], 'company': entry.get('company'),
                       'operation': entry.get('operation'), 'path': ref['path'],
                       'sha256': digest, 'pinned_sha256': entry.get('sha256'),
                       'status': 'already_pinned' if entry.get('sha256') == digest
                                 else 'awaiting_visual_review'})
    return packet


def adjudicated(anchor_rows, disclosures):
    """Attach disclosures to the cases mine output says it could adjudicate.

    Still selects nothing: it reports whether specific evidence now exists for a
    case, so a reviewer can record a decision in graphite_reviews.json.
    """
    by_key = {}
    for row in disclosures:
        by_key.setdefault((row['country'], row['year']), []).append(row)
    results = []
    for row in anchor_rows:
        if row['review_class'] != 'production_adjudicable':
            continue
        evidence = by_key.get((row['country'], row['year']), [])
        results.append({**row, 'disclosures': evidence,
                        'evidence_available': bool(evidence),
                        'selected_weight_t': None})
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.cache/graphite-companies')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / '.cache'):
        parser.error('Discovery must stay under .cache')
    from .sources import http
    args.output.mkdir(parents=True, exist_ok=True)
    packet = discover(args.output, http)
    (args.output / 'discovery.json').write_bytes(archive.encode(packet))
    for item in packet:
        detail = item.get('error') or item['sha256']
        print(f'{item["status"]:24} {detail}  {item["url"]}')


if __name__ == '__main__':
    main()
