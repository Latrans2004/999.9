"""The guard that keeps already published years from moving.

Appending a year - a new Comtrade year, a back-filled USGS edition - must leave
every figure that is already on the site exactly where it was. These tests fix
that contract: an append is silent, a revision is loud, and the only slack in
between is a relative 1e-9 that is always reported when it is used.
"""

import copy
import json
from pathlib import Path

import pytest

from pipeline import invariance

ROOT = Path(__file__).resolve().parents[2]


def profile(hs_code, year, hhi=2000.0, shares=((('AUS'), 60.0), (('CHL'), 40.0)), **overrides):
    record = {'hs_code': hs_code, 'year': year, 'hhi': hhi, 'band': 'high', 'cr1': 60.0,
              'cr3': 100.0, 'cr5': 100.0, 'effective_suppliers': 1.92, 'total': 1000.0,
              'reporters': 2, 'coverage': None, 'coverage_pct': 88.0, 'unit': 't',
              'top': [{'name': name, 'code': None, 'quantity': share * 10, 'share': share}
                      for name, share in shares]}
    record.update(overrides)
    return record


def snapshot(*profiles, production=()):
    return {'concentration': list(profiles), 'production': list(production)}


def production_row(year, country, **overrides):
    row = {'year': year, 'country': country, 'production_t': 1000.0, 'world_total_t': 5000.0,
           'edition': 2026, 'status': 'reported',
           'source_url': 'https://pubs.usgs.gov/periodicals/mcs2026/mcs2026-lithium.pdf'}
    row.update(overrides)
    return row


def test_identical_snapshots_report_nothing():
    before = snapshot(profile('283691', 2024), production=[production_row(2024, 'CHL')])
    report = invariance.compare(before, copy.deepcopy(before))
    assert report.ok
    assert report.differences == [] and report.tolerated == []
    assert report.checked == {'concentration': 1, 'shares': 2, 'production': 1}


def test_appending_a_new_year_is_not_a_change():
    before = snapshot(profile('283691', 2024))
    after = snapshot(profile('283691', 2024), profile('283691', 2025, hhi=3100.0))
    assert invariance.compare(before, after).ok


def test_back_filling_earlier_years_is_not_a_change():
    """Task B appends *older* years; a plain year cutoff would not see that."""
    before = snapshot(production=[production_row(2024, 'CHL'), production_row(2025, 'CHL')])
    after = snapshot(production=[production_row(y, 'CHL') for y in range(2017, 2026)])
    assert invariance.compare(before, after).ok


def test_a_moved_index_is_reported():
    before = snapshot(profile('283691', 2024, hhi=2000.0))
    after = snapshot(profile('283691', 2024, hhi=2001.0))
    report = invariance.compare(before, after)
    assert not report.ok
    (difference,) = report.differences
    assert (difference['kind'], difference['field']) == ('concentration', 'hhi')
    assert (difference['previous'], difference['current']) == (2000.0, 2001.0)
    assert difference['relative_change'] == pytest.approx(0.0005)


def test_moved_cr3_coverage_and_world_total_are_each_reported():
    before = snapshot(profile('282520', 2023))
    after = snapshot(profile('282520', 2023, cr3=99.0, coverage_pct=77.0, total=1001.0))
    fields = {d['field'] for d in invariance.compare(before, after).differences}
    assert fields == {'cr3', 'coverage_pct', 'total'}


def test_a_moved_country_share_is_reported():
    before = snapshot(profile('283691', 2022))
    after = snapshot(profile('283691', 2022, shares=(('AUS', 61.0), ('CHL', 39.0))))
    report = invariance.compare(before, after)
    assert {(d['kind'], d['key'], d['field']) for d in report.differences} == {
        ('share', '283691 2022 AUS', 'quantity'), ('share', '283691 2022 AUS', 'share'),
        ('share', '283691 2022 CHL', 'quantity'), ('share', '283691 2022 CHL', 'share')}


def test_a_country_appearing_or_disappearing_is_reported():
    before = snapshot(profile('283691', 2021))
    after = snapshot(profile('283691', 2021, shares=(('AUS', 60.0), ('ARG', 40.0))))
    report = invariance.compare(before, after)
    assert ('share', '283691 2021 CHL', 'published', 'missing') in {
        (d['kind'], d['key'], d['previous'], d['current']) for d in report.differences}
    assert ('share', '283691 2021 ARG', 'absent', 'added') in {
        (d['kind'], d['key'], d['previous'], d['current']) for d in report.differences}


def test_a_dropped_published_year_is_reported():
    before = snapshot(profile('253090', 2019), profile('253090', 2020))
    after = snapshot(profile('253090', 2020))
    (difference,) = invariance.compare(before, after).differences
    assert (difference['key'], difference['current']) == ('253090 2019', 'missing')


def test_a_revised_production_row_is_reported():
    before = snapshot(production=[production_row(2024, 'CHL', production_t=48900.0)])
    after = snapshot(production=[production_row(2024, 'CHL', production_t=49000.0, edition=2027)])
    fields = {d['field'] for d in invariance.compare(before, after).differences}
    assert fields == {'production_t', 'edition'}


def test_a_withheld_row_turning_into_a_number_is_reported():
    before = snapshot(production=[production_row(2024, 'USA', production_t=None, status='withheld')])
    after = snapshot(production=[production_row(2024, 'USA', production_t=5000.0)])
    fields = {d['field'] for d in invariance.compare(before, after).differences}
    assert fields == {'production_t', 'status'}


def test_summation_order_noise_is_tolerated_but_always_recorded():
    before = snapshot(profile('283691', 2024, total=1000.0))
    after = snapshot(profile('283691', 2024, total=1000.0 + 1e-8))
    report = invariance.compare(before, after)
    assert report.ok
    (entry,) = report.tolerated
    assert (entry['kind'], entry['field']) == ('concentration', 'total')
    assert entry['relative_change'] == pytest.approx(1e-11)
    assert 'tolerated' in invariance.summarise(report)


def test_tolerance_does_not_cover_a_real_move():
    before = snapshot(profile('283691', 2024, total=1000.0))
    after = snapshot(profile('283691', 2024, total=1000.0 + 1e-5))
    report = invariance.compare(before, after)
    assert not report.ok and report.tolerated == []


def test_a_move_away_from_zero_has_no_relative_scale_and_is_reported():
    before = snapshot(profile('283691', 2024, coverage_pct=0.0))
    after = snapshot(profile('283691', 2024, coverage_pct=1e-12))
    (difference,) = invariance.compare(before, after).differences
    assert difference['relative_change'] is None


def test_a_changed_band_or_source_string_is_reported():
    before = snapshot(profile('283691', 2024, band='high'),
                      production=[production_row(2024, 'CHL')])
    after = snapshot(profile('283691', 2024, band='moderate'),
                     production=[production_row(2024, 'CHL', source_url='https://example.usgs.gov/x.pdf')])
    fields = {d['field'] for d in invariance.compare(before, after).differences}
    assert fields == {'band', 'source_url'}


def test_max_year_narrows_the_check_without_hiding_earlier_revisions():
    before = snapshot(profile('283691', 2024, hhi=2000.0), profile('283691', 2025, hhi=2500.0))
    after = snapshot(profile('283691', 2024, hhi=2000.0), profile('283691', 2025, hhi=2600.0))
    assert invariance.compare(before, after, max_year=2024).ok
    assert not invariance.compare(before, after).ok


def test_no_previous_snapshot_is_not_a_failure():
    assert invariance.compare(None, snapshot(profile('283691', 2024))).ok


def test_duplicate_keys_are_refused_rather_than_silently_deduplicated():
    doubled = snapshot(profile('283691', 2024), profile('283691', 2024))
    with pytest.raises(ValueError):
        invariance.compare(doubled, doubled)


def test_the_committed_snapshot_is_invariant_against_itself():
    """A real snapshot, real field names: the guard must read what we publish."""
    published = json.loads((ROOT / 'data/processed/lithium/snapshot.json').read_text(encoding='utf-8'))
    report = invariance.compare(published, copy.deepcopy(published), max_year=2024)
    assert report.ok and report.tolerated == []
    assert report.checked['concentration'] > 0
    assert report.checked['shares'] > 0
    assert report.checked['production'] > 0
