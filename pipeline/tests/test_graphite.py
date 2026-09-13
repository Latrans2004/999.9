import pytest
from pipeline import graphite
from pipeline import graphite_usgs


def row(flow='X', reporter='CHN', partner='W00', weight=100, **extra):
    return dict(year=2024, hs_code='250410', flow=flow, reporter=reporter,
                partner=partner, weight_t=weight, value_usd=100000,
                weight_estimated=False, raw_path='raw/test.json', **extra)


def test_no_larger_value_correction():
    decisions = graphite.compare([row(), row('M', 'USA', 'CHN', 1000)])
    assert decisions[0]['decision'] == 'unresolved'
    assert decisions[0]['selected_weight_t'] is None


def test_partial_mirror_not_world():
    decisions = graphite.compare([row(), row(partner='USA', weight=50),
                                  row(partner='JPN', weight=50), row('M', 'USA', 'CHN', 90)])
    assert decisions[0]['missing_observed_destinations'] == ['JPN']
    assert decisions[0]['mirror_world_complete'] is False
    assert decisions[0]['decision'] == 'unresolved'


def test_missing_not_zero():
    decisions = graphite.compare([row(weight=None), row('M', 'USA', 'CHN', 100)])
    assert decisions[0]['reported_weight_t'] is None
    assert decisions[0]['selected_weight_t'] is None
    assert graphite.observed_sum([row(weight=None)], 'weight_t') is None


def test_estimated_not_accepted():
    own = row()
    own['weight_estimated'] = True
    assert graphite.compare([own, row('M', 'USA', 'CHN')])[0]['decision'] == 'unresolved'


def test_duplicate_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        graphite.compare([row(), row()])


def test_synthetic_excluded():
    own = row()
    own['hs_code'] = '380110'
    with pytest.raises(ValueError, match='scope'):
        graphite.compare([own])


def test_metrics_do_not_claim_global_coverage():
    decisions = graphite.compare([row(), row('M', 'USA', 'CHN')])
    result = graphite.metrics(decisions)[0]
    assert result['profile']['hhi'] == 10000
    assert result['profile']['cr3'] == 100
    assert result['global_coverage'] is None
    assert result['publishable'] is False


def test_usgs_zero_estimate_residual_and_reserves():
    text = '2017 2018e\nUnited States \u2014 \u2014 (3)\nChina e100 120 900000\nOther 5 6 (3)\nWorld total (rounded) 105 126 900000\n'
    records = graphite_usgs.parse_table(text, 2017, {})
    assert records[0]['production_t'] == 0
    assert records[1]['production_t'] == 100
    assert records[1]['status'] == 'estimated'
    assert records[2]['kind'] == 'residual'
    assert records[3]['kind'] == 'world'


def test_usgs_withheld_not_zero():
    records = graphite_usgs.parse_table('2017 2018e\nChina W W (3)\nWorld total (rounded) 100 100 (3)', 2017, {})
    assert records[0]['production_t'] is None


def test_usgs_changed_columns_rejected():
    with pytest.raises(ValueError, match='column'):
        graphite_usgs.parse_table('2018 2019e\nChina 100 120 9000', 2017, {})


def test_usgs_duplicate_rejected():
    with pytest.raises(ValueError, match='Duplicate'):
        graphite_usgs.parse_table('2017 2018e\nChina 100 120 9000\nChina 100 120 9000\nWorld total (rounded) 200 240 9000', 2017, {})


def test_missing_secret_before_network(monkeypatch, tmp_path):
    monkeypatch.delenv('COMTRADE_API_KEY', raising=False)
    monkeypatch.setattr(graphite.strict_comtrade, 'fetch', lambda *a, **k: pytest.fail('must not fetch preview'))
    with pytest.raises(ValueError, match='Actions'):
        graphite.collect(tmp_path)


def test_external_context_does_not_substitute_mine_output():
    item = {'country': 'MOZ', 'year': 2022, 'hs_code': '250410', 'decision': 'reported',
            'selected_weight_t': 647761.188}
    reviewed = graphite.attach_reviews([item])[0]
    assert reviewed['decision'] == 'unresolved'
    assert reviewed['selected_weight_t'] is None
    assert reviewed['external_reviews']


def test_committed_raw_replay_matches_normalized_bundle():
    records = graphite.replay_bundle(graphite.ROOT / 'data/review/natural-graphite/bundle.json')
    assert len(records) == 23458
    assert {r['year'] for r in records} == set(graphite.YEARS)
    assert {r['hs_code'] for r in records} == set(graphite.HS_CODES)


def test_measurement_audit_preserves_missing_and_zero():
    result = graphite.measurement_audit([row(weight=None), row(weight=0)])
    assert result[0]['unit_value_usd_t'] is None
    assert 'missing_weight' in result[0]['flags']
    assert 'positive_value_zero_weight' in result[1]['flags']
