"""Historical acquisition and vintage evidence must remain unreviewed."""
import copy
import json
from pathlib import Path
import pytest
from pipeline import manganese as mn, manganese_history as history, manganese_bgs as bgs
from pipeline import manganese_evidence as evidence


def test_plan_has_no_overlapping_query_dimensions():
    specs = history.plan()
    assert len(specs) == len({history.identity(q) for q in specs}) == 256
    assert {q['year'] for q in specs} == set(range(2017, 2025))
    assert {q['hs_code'] for q in specs} == {'260200'}
    assert len(history.plan(True)) == 16
    assert all(q['partner'] == '0' for q in history.plan(True))


@pytest.mark.parametrize('field', ['year', 'hs_code', 'flow', 'reporter', 'partner', 'status'])
def test_reuse_rejects_query_metadata_changes(field):
    bundle = json.loads((mn.ROOT / 'data/review/manganese-sample/bundle.json').read_bytes())
    q = copy.deepcopy(bundle['queries'][0])
    history.validate_cached(q)
    q[field] = 'invalid'
    with pytest.raises(ValueError):
        history.validate_cached(q)


def test_historical_raw_replays_and_all_decisions_remain_pending():
    root = mn.ROOT / 'data/review/manganese-history'
    rows, bundle = mn.replay(root / 'bundle.json')
    assert len(rows) == 2572
    assert len(bundle['queries']) == 256
    for q in bundle['queries']:
        history.validate_cached(q)
    policy = json.loads((mn.ROOT / 'pipeline/manganese_policy.json').read_bytes())
    diagnostics = mn.compare(rows, policy)
    assert len(diagnostics) == 518
    assert all(d['selected_weight_t'] is None and not d['publishable'] for d in diagnostics)


def test_researched_hs2007_revalidation_retains_original_failure_and_raw():
    original = json.loads((mn.ROOT / 'data/review/manganese-history/bundle.json').read_bytes())
    rows, revised = mn.replay(mn.ROOT / 'data/review/manganese-history-validated/bundle.json')
    assert len(rows) == 2642
    assert all(q['reused_archived_query'] for q in revised['queries'])
    accepted = [q for q in revised['queries'] if q.get('revalidated_from_raw')]
    assert len(accepted) == 6
    assert {(q['year'], q['reporter']) for q in accepted} == {(y, 266) for y in (2017, 2018, 2019)}
    old = {history.identity(q): q for q in original['queries']}
    for q in accepted:
        assert q['previous_failure']['status'] == 'failed'
        assert q['raw'] == old[history.identity(q)]['raw']
    failures = [q for q in revised['queries'] if q['status'] == 'failed']
    assert len(failures) == 65
    assert all(q['reason_code'] == 'empty_response_not_zero_trade' for q in failures)


def test_real_bgs_candidates_preserve_vintages_fiscal_periods_and_gates():
    from pypdf import PdfReader
    import io
    root = mn.ROOT / 'data/review/manganese-additional-evidence'
    items = json.loads((root / 'discover.json').read_bytes())
    rows = []
    for item in items[:2]:
        body = evidence.verify_raw(root, item['raw'])
        text = PdfReader(io.BytesIO(body)).pages[bgs.EDITIONS[item['id']][1]].extract_text()
        rows.extend(bgs.parse(text, item['id'], item['raw']))
    assert len(rows) == 310
    assert len({(r['country'], r['year']) for r in rows}) == 254
    aus = [r for r in rows if r['country'] == 'AUS' and r['year'] == 2020]
    assert [r['value_t'] for r in aus] == [4752200, 6425848]
    india = next(r for r in rows if r['country'] == 'IND' and r['year'] == 2024)
    assert india['period_start'] == '2024-04-01' and india['period_end'] == '2025-03-31'
    assert india['period_review_required']
    assert all(not r['publishable'] and not r['eligible_as_reviewed_anchor'] for r in rows)
    assert all(r['review_status'] == 'unreviewed_machine_extraction' for r in rows)
    assert all(r['weight_basis'] != 'contained_mn' for r in rows)
    nil = [r for r in rows if r['quantity_status'] == 'nil']
    assert len(nil) == 16 and all(r['value_t'] == 0 for r in nil)


@pytest.mark.parametrize('mutation', ['unit', 'year', 'footnote', 'cell', 'duplicate'])
def test_bgs_changes_rejected(mutation, monkeypatch):
    monkeypatch.setitem(bgs.EDITIONS, 'test', (2020, 0, 1))
    text = ('Production of manganese ore tonnes (metric)\n'
            'Country 2020 2021 2022 2023 2024\n'
            'Australia    10 000  20 000  30 000  40 000  50 000\nNote(s)\n' +
            '\n'.join(f'({k}) {v}' for k,v in bgs.NOTES.items()))
    assert len(bgs.parse(text, 'test', {'url':'https://example.test'})) == 5
    if mutation == 'unit': text = text.replace('tonnes (metric)', 'contained manganese')
    if mutation == 'year': text = text.replace('2020 2021', '2019 2021')
    if mutation == 'footnote': text = text.replace('30 June', '31 July')
    if mutation == 'cell': text = text.replace('50 000', 'NA')
    if mutation == 'duplicate': text = text.replace('Note(s)', 'Australia    1  2  3  4  5\nNote(s)')
    with pytest.raises(ValueError): bgs.parse(text, 'test', {'url':'https://example.test'})
