"""The back-filled USGS production years, checked without a network.

The pipeline reads a reviewed CSV, not a PDF, so nothing downstream would
notice if the archived publication behind those rows were swapped, truncated by
a checkout, or if a row quietly named an edition that does not report its year.
These checks close that gap using only files in the repository: the archived
bytes against their recorded hash, every row against the edition that settles
its year, and every year's countries against the world total printed beside
them.
"""

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SOURCES = json.loads((ROOT / 'pipeline/lithium_usgs_sources.json').read_text(encoding='utf-8'))
SETTINGS = json.loads((ROOT / 'pipeline/minerals.json').read_text(encoding='utf-8'))['minerals']['lithium']
PINNED = SETTINGS['usgs']


def rows():
    text = (ROOT / SETTINGS['usgs']['reviewed_csv']).read_text(encoding='utf-8-sig')
    return list(csv.DictReader(io.StringIO(text)))


def editions():
    """Every edition whose lithium table this repository can point at."""
    return {entry['edition'] for entry in SOURCES} | {PINNED['edition']}


def test_every_archived_publication_matches_its_recorded_hash():
    for entry in SOURCES:
        archived = ROOT / entry['archived_path']
        assert archived.exists(), f'{entry["edition"]}: {entry["archived_path"]} is missing'
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == entry['archived_sha256'], \
            f'{entry["edition"]}: archived bytes differ from the reviewed publication'


def test_archive_sidecar_agrees_with_the_sources_file():
    for entry in SOURCES:
        sidecar = (ROOT / entry['archived_path']).with_suffix('.meta.json')
        metadata = json.loads(sidecar.read_text(encoding='utf-8'))
        assert metadata['sha256'] == entry['archived_sha256']
        assert entry['edition'] in metadata['query']['editions']
        assert entry['chapter_url'] in metadata['query']['chapter_urls']


def test_each_year_is_taken_from_the_newest_edition_that_reports_it():
    # An edition prints the previous year as an estimate and the year before it
    # revised, so the newest edition carrying a year is the settled reading.
    known = editions()
    for row in rows():
        year, edition = int(row['year']), int(row['edition'])
        assert edition in known, f'{year}: edition {edition} has no archived publication'
        reporting = {e for e in known if e - 2 <= year <= e - 1}
        assert edition == max(reporting), \
            f'{year}: taken from MCS {edition} while MCS {max(reporting)} also reports it'


def test_every_row_names_the_publication_its_edition_was_read_from():
    chapters = {entry['edition']: entry['chapter_url'] for entry in SOURCES}
    chapters[PINNED['edition']] = PINNED['publication_url']
    for row in rows():
        assert row['source_url'] == chapters[int(row['edition'])], \
            f'{row["year"]} {row["country"]}: source URL does not match its edition'


def test_the_published_years_still_come_from_the_pinned_publication():
    """The years already on the site must not have moved to another edition."""
    settled = [r for r in rows() if int(r['year']) >= 2024]
    assert {int(r['edition']) for r in settled} == {PINNED['edition']}
    assert {r['source_url'] for r in settled} == {PINNED['publication_url']}
    assert sum(float(r['production_t']) for r in settled if r['production_t']) == pytest.approx(511350)


def test_countries_sum_to_the_printed_world_total_within_the_usgs_rounding():
    by_year = {}
    for row in rows():
        year = int(row['year'])
        bucket = by_year.setdefault(year, {'sum': 0.0, 'world': float(row['world_total_t'])})
        assert bucket['world'] == float(row['world_total_t']), f'{year}: conflicting world totals'
        if row['production_t']:
            bucket['sum'] += float(row['production_t'])
    assert sorted(by_year) == list(range(2017, 2026))
    for year, bucket in sorted(by_year.items()):
        difference = bucket['sum'] / bucket['world'] - 1
        # USGS rounds the world total, so a small residual is expected; a
        # transcription that lost or gained a row is not that small.
        assert abs(difference) <= 0.05, f'{year}: countries differ from the world total by {difference:.1%}'


def test_the_extraction_record_covers_every_source_edition():
    record = json.loads((ROOT / 'data/review/lithium-usgs-history/extraction.json').read_text(encoding='utf-8'))
    assert {table['edition'] for table in record['editions']} == {entry['edition'] for entry in SOURCES}
    assert record['source_sha256'] == SOURCES[0]['archived_sha256']
    for table in record['editions']:
        assert table['footnote_spans_excluded'] > 0, f'{table["edition"]}: no footnote marks separated'
        for year, check in table['checks'].items():
            assert abs(check['difference_pct']) <= 5, f'{table["edition"]} {year}: {check["difference_pct"]}%'
