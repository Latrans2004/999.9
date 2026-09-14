"""The screener rows on the hub and section pages.

Two rules matter more than the layout. A trade block that the publication
process withholds must never reach the table as a number, whatever else is
on disk: that is Task D's decision and the presentation layer honours it.
And every figure that does reach the table is a copy of a published one,
so the screener cannot disagree with the pages it links to.
"""

import copy
import json
from pathlib import Path

from pipeline import i18n, render

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'critical-minerals/data'
CATALOG = json.loads((DATA / 'catalog.json').read_text(encoding='utf-8'))
INDEX = json.loads((DATA / 'index.json').read_text(encoding='utf-8'))
SUMMARIES = {m['slug']: m for m in INDEX['minerals']}


def rows():
    return {r['slug']: r for r in render.screener_rows(CATALOG, SUMMARIES)}


def test_every_catalog_entry_is_a_row_in_catalog_order():
    order = [r['slug'] for r in render.screener_rows(CATALOG, SUMMARIES)]
    assert order == [m['slug'] for m in CATALOG['minerals']]
    assert all(r['category']['key'] == 'battery-metals' for r in rows().values())


def test_graphite_trade_is_under_review_and_never_a_number():
    graphite = rows()['natural-graphite']
    assert graphite['export'] == {'kind': 'review'}
    # The mine figure is the published one and still sets the band and year.
    published = SUMMARIES['natural-graphite']['production']
    assert graphite['mine']['hhi'] == published['hhi']
    assert graphite['band'] == published['band']
    assert graphite['year'] == published['year']


def test_a_withheld_trade_block_wins_even_when_a_summary_figure_exists():
    """If a summary ever carried a trade figure for a withheld block, the
    publication status still decides what the screener shows."""
    entry = next(m for m in CATALOG['minerals'] if m['slug'] == 'natural-graphite')
    summary = copy.deepcopy(SUMMARIES['natural-graphite'])
    summary['trade'] = {'hhi': 1234.5, 'year': 2024, 'band': 'moderate'}
    data = render.load_mineral('natural-graphite')
    assert data['trade']['publication_status'] == 'under_review'
    assert render.export_cell(entry, summary, data, None) == {'kind': 'review'}


def test_lithium_quotes_the_catalog_headline_stage_at_its_last_confirmed_year():
    entry = next(m for m in CATALOG['minerals'] if m['slug'] == 'lithium')
    assert entry['headline_trade_stage'] == '283691'
    export = rows()['lithium']['export']
    assert export['kind'] == 'value'
    assert export['stage_key'] == '283691'
    concentration = json.loads((DATA / 'lithium/concentration.json').read_text(encoding='utf-8'))
    provisional = set(concentration['metadata']['provisional_years'].get('283691') or [])
    settled = [r for r in concentration['records']
               if r['hs_code'] == '283691' and r['year'] not in provisional]
    latest = max(settled, key=lambda r: r['year'])
    assert (export['year'], export['hhi'], export['band']) == (latest['year'], latest['hhi'], latest['band'])
    assert export['provisional'] is False
    assert export['stage_label'] == i18n.label_en('stage.carbonate')
    assert export['stage_label_ja'] == i18n.label_ja('stage.carbonate')


def test_without_a_headline_stage_the_cell_points_at_the_page():
    entry = dict(next(m for m in CATALOG['minerals'] if m['slug'] == 'lithium'))
    entry.pop('headline_trade_stage')
    stages = render.load_stages('lithium')
    cell = render.export_cell(entry, SUMMARIES['lithium'], render.load_mineral('lithium'), stages)
    assert cell['kind'] == 'stages'
    assert cell['count'] == len([t for t in stages['tabs'] if t['key'] not in render.DERIVED_SERIES])


def test_a_mineral_without_stages_quotes_the_published_headline():
    entry = {'slug': 'x', 'name': 'X'}
    summary = {'trade': {'hhi': 2500.0, 'year': 2023, 'band': 'high'}}
    cell = render.export_cell(entry, summary, None, None)
    assert cell['kind'] == 'value' and cell['hhi'] == 2500.0 and cell['stage_key'] is None


def test_pending_minerals_have_no_figures_and_are_not_live():
    for slug in ('cobalt', 'nickel', 'manganese', 'rare-earths', 'vanadium', 'copper'):
        row = rows()[slug]
        assert row['mine'] is None and row['export'] == {'kind': 'pending'}
        assert row['band'] is None and row['year'] is None and row['live'] is False


def test_confirmed_latest_skips_provisional_years_but_never_returns_nothing():
    years = [{'year': 2023, 'provisional': False}, {'year': 2024, 'provisional': False},
             {'year': 2025, 'provisional': True}]
    assert render.confirmed_latest(years)['year'] == 2024
    assert render.confirmed_latest([{'year': 2025, 'provisional': True}])['year'] == 2025
    assert render.confirmed_latest([]) is None


def test_first_sentence_breaks_on_the_right_terminator():
    assert render.first_sentence('One. Two.') == 'One.'
    assert render.first_sentence('一つ。二つ。') == '一つ。'
    assert render.first_sentence('No terminator') == 'No terminator'
    assert render.first_sentence(None) == ''


def test_rendered_hub_shows_no_graphite_trade_number_and_all_rows():
    html = (ROOT / 'index.html').read_text(encoding='utf-8')
    assert html.count('data-category="battery-metals"') == len(CATALOG['minerals'])
    graphite = html[html.index('data-search="natural graphite'):]
    graphite = graphite[:graphite.index('</tr>')]
    assert 'Under review' in graphite
    assert 'data-k-export=""' in graphite
    assert 'Orelysis' not in html


def test_every_screener_string_has_japanese():
    for key in ('screener.search', 'screener.category', 'screener.all_categories',
                'screener.pending', 'screener.under_review', 'screener.no_match',
                'screener.showing', 'col.mineral', 'col.mine_hhi', 'col.top_supplier',
                'col.export_hhi', 'col.band', 'col.year', 'legend.title',
                'quote.mine_hhi', 'quote.export_hhi', 'quote.top_producer', 'quote.updated'):
        assert i18n.STRINGS_JA.get(key), key
