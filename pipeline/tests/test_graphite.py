import pytest
from pipeline import graphite


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
