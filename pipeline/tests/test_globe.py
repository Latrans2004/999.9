"""The globe page's data and the five checks that guard it.

The globe draws published shares and nothing else. These tests hold it to
that: every number it carries agrees with the figure the mineral page shows,
nothing under review reaches its files, every country it names has a polygon,
and the mineral list is the catalog's.
"""

import copy
import json
from pathlib import Path

import pytest

from pipeline import globe, render

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'critical-minerals/data'
CATALOG = json.loads((DATA / 'catalog.json').read_text(encoding='utf-8'))
INDEX = json.loads((DATA / 'index.json').read_text(encoding='utf-8'))
SUMMARIES = {m['slug']: m for m in INDEX['minerals']}


def rows(catalog=CATALOG):
    return render.screener_rows(catalog, SUMMARIES)


def built(catalog=CATALOG):
    return globe.build(catalog, rows(catalog))


def layer(files, slug, layer_id):
    return next(l for l in files[slug]['layers'] if l['id'] == layer_id)


def assert_fails(index, files, fragment, catalog=CATALOG):
    with pytest.raises(globe.GlobeError) as caught:
        globe.verify(catalog, rows(catalog), index, files, globe.load_borders())
    assert fragment in str(caught.value)


# ------------------------------------------------------------ the real data

def test_current_data_passes_every_check():
    index, files = built()
    globe.verify(CATALOG, rows(), index, files, globe.load_borders())


def test_committed_globe_files_are_what_a_render_writes():
    index, files = built()
    on_disk = json.loads((DATA / 'globe/index.json').read_text(encoding='utf-8'))
    assert on_disk == index
    for slug, payload in files.items():
        assert json.loads((DATA / f'globe/{slug}.json').read_text(encoding='utf-8')) == payload
    written = sorted(p.name for p in (DATA / 'globe').glob('*.json'))
    assert written == sorted(['index.json'] + [f'{s}.json' for s in files])


def test_lithium_layers_are_the_published_mine_and_trade_stages():
    index, files = built()
    lithium = next(m for m in index['minerals'] if m['id'] == 'lithium')
    assert [l['id'] for l in lithium['layers']] == [
        'mine_production_share', 'export_share_headline', 'export_share_ore',
        'export_share_carbonate', 'export_share_hydroxide',
    ]
    assert all(l['status'] == 'published' for l in lithium['layers'])
    assert index['default'] == {'mineral': 'lithium', 'layer': 'mine_production_share'}


def test_mine_figures_are_the_mineral_page_figures():
    _, files = built()
    for slug in ('lithium', 'natural-graphite'):
        latest = render.load_mineral(slug)['production']['latest']
        mine = layer(files, slug, 'mine_production_share')
        assert mine['year'] == latest['year']
        assert mine['summary'] == {
            'leader': latest['top'][0]['code'], 'leader_share': latest['top'][0]['share'],
            'cr3': latest['cr3'], 'hhi': latest['hhi'], 'band': latest['band'],
        }
        recomputed = globe.recompute(mine['values'])
        assert recomputed['hhi'] == pytest.approx(latest['hhi'], abs=globe.TOL_HHI)


def test_stage_figures_are_the_stage_panel_figures():
    _, files = built()
    stages = render.load_stages('lithium')
    by_key = {t['key']: t['panels'][0]['latest'] for t in stages['tabs']}
    for layer_id, key in (('export_share_headline', 'headline_usd'), ('export_share_ore', '253090'),
                          ('export_share_carbonate', '283691'), ('export_share_hydroxide', '282520')):
        latest, got = by_key[key], layer(files, 'lithium', layer_id)
        assert got['year'] == latest['year']
        assert got['provisional'] == latest['provisional']
        assert got['summary']['hhi'] == latest['hhi']
        assert got['summary']['cr3'] == latest['cr3']
        assert got['summary']['leader'] == latest['rows'][0]['country']
        assert len(got['values']) == len(latest['rows'])


def test_withheld_usgs_figure_is_no_data_not_zero():
    _, files = built()
    mine = layer(files, 'lithium', 'mine_production_share')
    assert mine['no_data'] == ['USA']
    assert 'USA' not in mine['values']
    assert mine['world_coverage'] == render.load_mineral('lithium')['production']['latest']['coverage']


def test_a_usgs_nil_entry_is_a_published_zero():
    _, files = built()
    # The 2024 table lists the United States with "—".
    assert layer(files, 'natural-graphite', 'mine_production_share')['values']['USA'] == 0.0


def test_graphite_trade_under_review_carries_no_number_anywhere():
    index, files = built()
    graphite = next(m for m in index['minerals'] if m['id'] == 'natural-graphite')
    review = [l for l in graphite['layers'] if l['status'] != 'published']
    assert review == [{'id': 'export_share_headline', 'kind': 'export_share', 'year': None,
                       'status': 'under_review', 'label': 'Exports', 'label_ja': '輸出'}]
    assert [l['id'] for l in files['natural-graphite']['layers']] == ['mine_production_share']
    text = (DATA / 'globe/natural-graphite.json').read_text(encoding='utf-8')
    assert 'export' not in text


def test_pending_minerals_are_listed_unselectable_and_have_no_file():
    index, files = built()
    pending = [m for m in index['minerals'] if m['status'] == 'pending']
    assert {m['id'] for m in pending} == {'cobalt', 'nickel', 'manganese', 'rare-earths', 'vanadium', 'copper'}
    assert all(not m['selectable'] and m['layers'] == [] for m in pending)
    assert not set(files) & {m['id'] for m in pending}


def test_iso_codes_that_natural_earth_keys_differently_are_mapped():
    borders = globe.load_borders()
    for iso, adm0 in globe.ISO_TO_ADM0.items():
        assert adm0 in borders, iso
        assert globe.adm0(iso) == adm0
    # France and Norway are why ISO_A3 is not the key: both join by ADM0_A3.
    assert {'FRA', 'NOR', 'HKG', 'SGP', 'MLT'} <= set(borders)


# ------------------------------------------------ the checks catch breakage

def test_check_1_an_unjoinable_country_fails_by_name():
    index, files = built()
    files = copy.deepcopy(files)
    layer(files, 'lithium', 'export_share_headline')['values']['ZZZ'] = 0.0
    assert_fails(index, files, 'no border polygon for ZZZ')


def test_check_2_shares_over_one_fail():
    index, files = built()
    files = copy.deepcopy(files)
    layer(files, 'lithium', 'mine_production_share')['other_share'] = 0.05
    assert_fails(index, files, 'more than 1')


def test_check_3_a_share_that_disagrees_with_the_published_hhi_fails():
    index, files = built()
    files = copy.deepcopy(files)
    values = layer(files, 'lithium', 'export_share_carbonate')['values']
    values['ARG'], values['KOR'] = values['ARG'] - 0.02, values['KOR'] + 0.02
    assert_fails(index, files, 'HHI')


def test_check_3_a_different_leader_fails():
    index, files = built()
    files = copy.deepcopy(files)
    layer(files, 'lithium', 'mine_production_share')['summary']['leader'] = 'CHN'
    assert_fails(index, files, 'leader AUS from the shares, CHN published')


def test_check_4_an_unpublished_layer_in_a_file_fails():
    index, files = built()
    files = copy.deepcopy(files)
    leaked = copy.deepcopy(layer(files, 'natural-graphite', 'mine_production_share'))
    leaked.update(id='export_share_headline', kind='export_share', status='under_review')
    files['natural-graphite']['layers'].append(leaked)
    assert_fails(index, files, 'unpublished layer written with numbers')


def test_check_4_a_file_for_a_pending_mineral_fails():
    index, files = built()
    files = copy.deepcopy(files)
    files['cobalt'] = copy.deepcopy(files['lithium'])
    assert_fails(index, files, 'cobalt: file layers')


def test_check_5_an_index_that_drifts_from_the_catalog_fails():
    index, files = built()
    index = copy.deepcopy(index)
    index['minerals'][1]['status'] = 'published'
    assert_fails(index, files, 'cobalt: status published but the screener shows pending')
    index = copy.deepcopy(built()[0])
    index['minerals'].pop()
    assert_fails(index, files, 'do not match the catalog')


def test_an_unknown_unit_fails():
    index, files = built()
    files = copy.deepcopy(files)
    layer(files, 'lithium', 'mine_production_share')['unit'] = 't'
    assert_fails(index, files, "unit 't'")


def test_a_list_cut_to_ten_with_no_full_record_is_an_error_not_a_guess(monkeypatch):
    data = copy.deepcopy(render.load_mineral('lithium'))
    latest = data['trade']['latest']
    assert latest['reporters'] > len(latest['top'])
    monkeypatch.setattr(render, 'read_json', lambda path: None)
    with pytest.raises(globe.GlobeError, match='not in the published data'):
        globe.full_rows('lithium', latest, 'export')


# ------------------------------------------------ growth without code change

def test_a_new_catalog_mineral_appears_unselectable_without_code_change():
    catalog = copy.deepcopy(CATALOG)
    catalog['minerals'].append({
        'slug': 'tin', 'name': 'Tin', 'name_ja': 'スズ', 'symbol': 'Sn',
        'category': 'battery-metals', 'usgs_commodity': 'Tin', 'headline_hs_codes': ['800110'],
    })
    index, files = built(catalog)
    globe.verify(catalog, rows(catalog), index, files, globe.load_borders())
    tin = index['minerals'][-1]
    assert tin == {'id': 'tin', 'name_en': 'Tin', 'name_ja': 'スズ', 'symbol': 'Sn',
                   'group': 'battery-metals', 'status': 'pending', 'selectable': False,
                   'page_url': 'minerals/tin.html', 'layers': []}
    assert 'tin' not in files


def test_a_new_category_becomes_its_own_group():
    catalog = copy.deepcopy(CATALOG)
    catalog['categories']['platinum-group'] = {'label': 'Platinum group', 'label_ja': '白金族'}
    catalog['minerals'].append({'slug': 'palladium', 'name': 'Palladium', 'category': 'platinum-group'})
    index, _ = built(catalog)
    assert [g['key'] for g in index['groups']] == ['battery-metals', 'platinum-group']
    assert index['minerals'][-1]['group'] == 'platinum-group'


def test_reserves_na_withheld_and_large_are_no_data_and_carry_the_note():
    """No pipeline publishes reserves yet; this is the contract one fills."""
    data = {'reserves': {'available': True, 'source': 'USGS Mineral Commodity Summaries', 'latest': {
        'year': 2025, 'cr3': 80.0,
        'top': [
            {'code': 'CHL', 'share': 50.0}, {'code': 'AUS', 'share': 20.0},
            {'code': 'ARG', 'share': 10.0}, {'code': 'CHN', 'share': 20.0},
            {'code': 'USA', 'share': None}, {'code': 'ZWE', 'share': 'Large'},
        ],
    }}}
    got = globe.reserves_layer('example', data)
    assert got['values'] == {'CHL': 0.5, 'AUS': 0.2, 'ARG': 0.1, 'CHN': 0.2}
    assert got['no_data'] == ['USA', 'ZWE']
    assert 'hhi' not in got['summary']
    assert got['note_en'].startswith('Reserves are not supply concentration')
    assert got['note_ja'].startswith('埋蔵量は供給集中度そのものではなく')
    review = globe.reserves_layer('example', {'reserves': {'publication_status': 'under_review'}})
    assert review['status'] == 'under_review' and 'values' not in review
