"""The stage tabs on a mineral page.

Two properties matter more than the markup. The first is that the tabs are a
reading of the configuration rather than a list someone typed into a template:
a stage added to pipeline/minerals.json must appear, and one renamed must
follow, without an edit anywhere else. The second is that rendering the page
reads the published data and writes nothing back to it, so the figures on the
page and the figures in critical-minerals/data/ cannot drift apart.
"""

import copy
import json
from pathlib import Path

import pytest

from pipeline import i18n, process_trade, render

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'critical-minerals/data'
CONCENTRATION = json.loads((DATA / 'lithium/concentration.json').read_text(encoding='utf-8'))
TRADE = json.loads((DATA / 'lithium/trade.json').read_text(encoding='utf-8'))


def stages():
    return render.load_stages('lithium')


def panels(bundle):
    return [panel for tab in bundle['tabs'] for panel in tab['panels']]


def test_tabs_are_read_from_the_configuration_not_the_template(tmp_path, monkeypatch):
    """Rename a stage's policy and reorder the stages; the tabs must follow."""
    configuration = json.loads((ROOT / 'pipeline/minerals.json').read_text(encoding='utf-8'))
    lithium = configuration['minerals']['lithium']
    reordered = dict(reversed(list(lithium['stages'].items())))
    reordered['283691'] = dict(reordered['283691'], policy='brine_carbonate')
    lithium['stages'] = reordered
    path = tmp_path / 'minerals.json'
    path.write_text(json.dumps(configuration), encoding='utf-8')
    monkeypatch.setattr(render, 'MINERALS_PATH', path)

    keys = [tab['key'] for tab in stages()['tabs']]
    assert keys == ['headline_usd', '282520', '283691', '253090', 'mine_li_t']
    # An unknown policy still gets a tab, named after itself rather than blank.
    carbonate = next(t for t in stages()['tabs'] if t['key'] == '283691')
    assert carbonate['label_key'] == 'stage.brine_carbonate'
    assert carbonate['label'] == 'brine carbonate'


def test_headline_is_the_default_tab_and_keeps_its_definition():
    bundle = stages()
    assert bundle['tabs'][0]['key'] == 'headline_usd'
    entry = json.loads((DATA / 'catalog.json').read_text(encoding='utf-8'))
    lithium = next(m for m in entry['minerals'] if m['slug'] == 'lithium')
    assert lithium['headline_hs_codes'] == ['283691', '282520']
    # The tab shows the published headline series itself, not a recomputation.
    site = json.loads((DATA / 'minerals/lithium.json').read_text(encoding='utf-8'))
    headline = bundle['tabs'][0]['panels'][0]
    assert [(y['year'], y['hhi'], y['cr3']) for y in headline['years']] == \
           [(p['year'], p['hhi'], p['cr3']) for p in site['trade']['series']]


def test_a_mineral_without_configured_stages_has_no_tabs():
    assert render.load_stages('cobalt') is None


def test_every_series_in_the_published_data_reaches_a_tab():
    published = {r['hs_code'] for r in CONCENTRATION['records']}
    rendered = {panel['hs_code'] for panel in panels(stages())}
    assert rendered == published


def test_a_stage_counted_from_both_sides_becomes_a_side_toggle():
    ore = next(t for t in stages()['tabs'] if t['key'] == '253090')
    assert [p['side_key'] for p in ore['panels']] == ['world_export', 'china_import']
    assert [p['hs_code'] for p in ore['panels']] == ['253090', '253090_china_import']
    # Stages filed from one side only must not grow an empty toggle.
    for tab in stages()['tabs']:
        if tab['key'] != '253090':
            assert len(tab['panels']) == 1


def test_figures_are_copied_from_concentration_json_unchanged():
    records = {(r['hs_code'], r['year']): r for r in CONCENTRATION['records']}
    seen = 0
    for panel in panels(stages()):
        for year in panel['years']:
            source = records[(panel['hs_code'], year['year'])]
            assert (year['hhi'], year['cr3'], year['reporters'], year['coverage_pct']) == \
                   (source['hhi'], source['cr3'], source['reporters'], source['coverage_pct'])
            seen += 1
        latest = records[(panel['hs_code'], panel['latest']['year'])]
        assert panel['latest']['hhi'] == latest['hhi']
        assert [(r['country'], r['share']) for r in panel['latest']['rows']] == \
               [(t['name'], t['share']) for t in latest['top']]
    assert seen == len(CONCENTRATION['records'])


def test_every_selected_source_that_can_reach_a_row_has_a_badge_group():
    """A new selection reason must be given a group rather than rendering blank."""
    reachable = {r['selected_source'] for r in TRADE['records'] if r.get('included')}
    assert reachable, 'no included rows to check'
    assert reachable <= set(render.SOURCE_GROUPS)
    for group in set(render.SOURCE_GROUPS.values()):
        assert i18n.label_ja('source.' + group)
        assert i18n.label_en('source.' + group) != group


def test_the_grouping_keeps_the_raw_value_and_does_not_change_the_data():
    provenance = {(r['hs_code'], r['year'], r['country']): r for r in TRADE['records']}
    checked = 0
    for panel in panels(stages()):
        for row in panel['latest']['rows']:
            key = (panel['hs_code'], panel['latest']['year'], row['country'])
            if key not in provenance:
                # headline_usd and mine_li_t are not per-country selections at all.
                assert row['source'] is None and row['verification'] is None
                continue
            source = provenance[key]['selected_source']
            if row['source'] is None:
                assert source not in render.SOURCE_GROUPS
                continue
            assert row['source']['raw'] == source
            assert row['source']['key'] == 'source.' + render.SOURCE_GROUPS[source]
            checked += 1
    assert checked


def test_mirror_group_covers_the_four_values_it_is_meant_to():
    mirrors = {k for k, v in render.SOURCE_GROUPS.items() if v == 'mirror'}
    assert mirrors == {'mirror_missing_report', 'mirror_underreported',
                       'mirror_lower_bound', 'reported_china_import'}


def test_only_the_three_verification_values_are_badged():
    assert set(render.SHOWN_VERIFICATION) == \
        set(process_trade.VERIFICATION_STATUSES) - {'not_applicable', 'no_adjustment'}
    provenance = {(r['hs_code'], r['year'], r['country']): r for r in TRADE['records']}
    badged = 0
    for panel in panels(stages()):
        for row in panel['latest']['rows']:
            key = (panel['hs_code'], panel['latest']['year'], row['country'])
            status = provenance.get(key, {}).get('verification_status')
            if status in render.SHOWN_VERIFICATION:
                assert row['verification']['raw'] == status
                badged += 1
            else:
                assert row['verification'] is None
    assert badged


def test_a_conflicting_row_carries_the_ledger_note_in_both_languages():
    conflicting = [(panel, row) for panel in panels(stages())
                   for row in panel['latest']['rows']
                   if row['verification'] and row['verification']['raw'] == 'externally_conflicting']
    assert conflicting, 'the ore stage is expected to publish a conflicting row'
    bundle = stages()
    notes = {n['id']: n for n in bundle['notes']}
    for panel, row in conflicting:
        note = notes[row['evidence']]
        assert note['country'] == row['country']
        assert note['outcome'] == 'externally_conflicting'
        assert note['note'] and note['note_ja'] and note['note'] != note['note_ja']
        assert note['source_name']
    # Every note carried into the page is reachable from a row that is rendered.
    reachable = {row['evidence'] for panel in panels(bundle) for row in panel['latest']['rows']}
    assert set(notes) <= reachable


def test_provisional_years_come_from_the_published_metadata(monkeypatch):
    published = CONCENTRATION['metadata']['provisional_years']
    for panel in panels(stages()):
        stage = panel['hs_code'].split('_')[0]
        expected = [y['year'] for y in panel['years']
                    if y['year'] in (published.get(stage) or [])]
        assert panel['provisional_years'] == expected
        assert [y['year'] for y in panel['years'] if y['provisional']] == expected

    # Flag a year that is actually published and the panel must mark it.
    doctored = copy.deepcopy(CONCENTRATION)
    # Flag the stage's own latest published year, whichever it is, so the check
    # follows the data rather than the year that happened to be latest when it
    # was written.
    latest = max(r['year'] for r in CONCENTRATION['records'] if r['hs_code'] == '283691')
    doctored['metadata']['provisional_years'] = {'283691': [latest]}
    real = render.read_json

    def patched(path):
        if path.name == 'concentration.json':
            return doctored
        return real(path)

    monkeypatch.setattr(render, 'read_json', patched)
    carbonate = next(t for t in stages()['tabs'] if t['key'] == '283691')
    assert carbonate['panels'][0]['provisional_years'] == [latest]
    assert carbonate['panels'][0]['latest']['provisional'] is True


def test_rendering_reads_the_data_and_writes_none_of_it(tmp_path):
    before = {p: p.read_bytes() for p in DATA.rglob('*') if p.is_file()}
    render.render_all()
    assert {p: p.read_bytes() for p in DATA.rglob('*') if p.is_file()} == before


def test_the_stage_panel_names_no_stage_in_the_template():
    """The wording lives in pipeline/i18n.py; the template only looks it up."""
    template = (ROOT / 'pipeline/templates/mineral.html').read_text(encoding='utf-8')
    configured = json.loads((ROOT / 'pipeline/minerals.json').read_text(encoding='utf-8'))
    policies = {s['policy'] for s in configured['minerals']['lithium']['stages'].values()}
    for policy in policies:
        assert policy not in template
    for label in ('Ore and concentrate', 'Carbonate', 'Hydroxide'):
        assert label not in template
