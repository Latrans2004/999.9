import pytest
from pipeline import graphite
from pipeline import graphite_usgs
from pipeline import graphite_anchor
from pipeline import graphite_companies


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


def test_anchor_never_selects_a_weight():
    decisions = [{'country': 'MOZ', 'year': 2022, 'hs_code': '250410',
                  'reported_weight_t': 648262.0, 'mirror_observed_weight_t': 159438.0}]
    production = [{'country': 'MOZ', 'year': 2022, 'kind': 'country', 'production_t': 166000}]
    result = graphite_anchor.audit(decisions, production)[0]
    assert result['selected_weight_t'] is None
    assert result['favours'] == 'mirror'
    assert result['review_class'] == 'production_adjudicable'


def test_anchor_favours_reported_when_mirror_is_the_outlier():
    assert graphite_anchor.classify(35305.0, 74768.0, 39000) == ('production_adjudicable', 'reported')


def test_anchor_declines_reexport_hub():
    # Germany mines hundreds of tonnes and ships tens of thousands, so neither
    # side of a genuine dispute can be checked against mine output.
    assert graphite_anchor.classify(15517.0, 25482.0, 300) == ('reexport_hub', None)


def test_anchor_ignores_a_hub_whose_observations_agree():
    assert graphite_anchor.classify(18429.0, 13966.0, 140) == ('no_dispute', None)


def test_anchor_declines_domestic_consumption_producer():
    # India mines 35 kt and exports almost none of it.
    assert graphite_anchor.classify(1068.0, 2374.0, 35000) == ('domestic_consumption_producer', None)


def test_anchor_declines_without_mine_production():
    assert graphite_anchor.classify(100.0, 900.0, 0) == ('no_mine_production', None)
    assert graphite_anchor.classify(100.0, 900.0, None) == ('no_mine_production', None)


def test_anchor_ignores_agreeing_observations():
    assert graphite_anchor.classify(100.0, 95.0, 100) == ('no_dispute', None)


def test_anchor_requires_both_observations():
    assert graphite_anchor.classify(None, 95.0, 100) == ('incomplete_trade_observation', None)


def _disclosure_env(tmp_path, monkeypatch, rows, pin=True):
    sources = tmp_path / 'sources.json'
    entry = {'kind': 'document', 'company': 'Syrah Resources', 'operation': 'Balama',
             'country': 'MOZ', 'url': 'https://example.invalid/q4.pdf',
             'sha256': 'abc' if pin else None, 'path': 'data/raw/company/q4.pdf',
             'review_date': '2026-09-14'}
    sources.write_bytes(graphite.archive.encode({'note': 't', 'documents': [entry]}))
    monkeypatch.setattr(graphite_companies, 'SOURCES', sources)
    csv_path = tmp_path / graphite_companies.REVIEWED_CSV
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.write_text(','.join(graphite_companies.COLUMNS) + '\n' + ''.join(rows), encoding='utf-8')
    return tmp_path


GOOD = ('MOZ,2022,production,163000,Syrah Resources,Balama,'
        'https://example.invalid/q4.pdf,Quarterly report page 3,2026-09-14\n')


def test_disclosures_empty_until_reviewed():
    # The committed file carries a header and no invented figures.
    assert graphite_companies.load() == []


def test_disclosure_requires_pinned_source(tmp_path, monkeypatch):
    root = _disclosure_env(tmp_path, monkeypatch, [GOOD], pin=False)
    with pytest.raises(ValueError, match='Unpinned source'):
        graphite_companies.load(root)


def test_disclosure_accepts_reviewed_row(tmp_path, monkeypatch):
    root = _disclosure_env(tmp_path, monkeypatch, [GOOD])
    row = graphite_companies.load(root)[0]
    assert row['value_t'] == 163000.0
    assert row['source']['sha256'] == 'abc'


def test_disclosure_rejects_blank_locator(tmp_path, monkeypatch):
    root = _disclosure_env(tmp_path, monkeypatch, [GOOD.replace('Quarterly report page 3', '')])
    with pytest.raises(ValueError, match='Blank locator'):
        graphite_companies.load(root)


def test_disclosure_rejects_duplicate(tmp_path, monkeypatch):
    root = _disclosure_env(tmp_path, monkeypatch, [GOOD, GOOD])
    with pytest.raises(ValueError, match='Duplicate disclosure'):
        graphite_companies.load(root)


def test_disclosure_rejects_unknown_measure(tmp_path, monkeypatch):
    root = _disclosure_env(tmp_path, monkeypatch, [GOOD.replace(',production,', ',guess,')])
    with pytest.raises(ValueError, match='Unknown measure'):
        graphite_companies.load(root)


def test_disclosure_fails_closed_on_revised_document(tmp_path, monkeypatch):
    root = _disclosure_env(tmp_path, monkeypatch, [GOOD])
    target = root / 'data/raw/company/q4.pdf'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'revised bytes')
    with pytest.raises(ValueError, match='Primary document revised'):
        graphite_companies.verify_archived(root)


def test_adjudicated_reports_evidence_without_selecting(tmp_path, monkeypatch):
    root = _disclosure_env(tmp_path, monkeypatch, [GOOD])
    anchor = [{'country': 'MOZ', 'year': 2022, 'review_class': 'production_adjudicable',
               'favours': 'mirror', 'selected_weight_t': None},
              {'country': 'DEU', 'year': 2020, 'review_class': 'reexport_hub',
               'favours': None, 'selected_weight_t': None}]
    result = graphite_companies.adjudicated(anchor, graphite_companies.load(root))
    assert len(result) == 1
    assert result[0]['evidence_available'] is True
    assert result[0]['selected_weight_t'] is None


def test_discover_never_fetches_an_index_entry(tmp_path, monkeypatch):
    sources = tmp_path / 'sources.json'
    entry = {'kind': 'index', 'company': 'X', 'operation': 'Y', 'country': 'MOZ',
             'url': 'https://example.invalid/should-not-be-fetched'}
    sources.write_bytes(graphite.archive.encode({'note': 't', 'documents': [entry]}))
    monkeypatch.setattr(graphite_companies, 'SOURCES', sources)

    class ExplodingHttp:
        def get(self, *a, **k):
            raise AssertionError('index entries must never be fetched')

    packet = graphite_companies.discover(tmp_path, ExplodingHttp())
    assert packet == [{'url': entry['url'], 'company': 'X', 'operation': 'Y',
                       'path': None, 'sha256': None, 'pinned_sha256': None,
                       'status': 'index_not_fetched'}]


def test_discover_reports_fetch_failure_without_raising(tmp_path, monkeypatch):
    sources = tmp_path / 'sources.json'
    entry = {'kind': 'document', 'company': 'X', 'operation': 'Y', 'country': 'MOZ',
             'url': 'https://example.invalid/missing.pdf', 'sha256': None}
    sources.write_bytes(graphite.archive.encode({'note': 't', 'documents': [entry]}))
    monkeypatch.setattr(graphite_companies, 'SOURCES', sources)

    class FailingHttp:
        def get(self, *a, **k):
            raise ValueError('HTTP 404')

    packet = graphite_companies.discover(tmp_path, FailingHttp())
    assert packet[0]['status'] == 'fetch_failed'
    assert 'HTTP 404' in packet[0]['error']


def test_verify_archived_rejects_pin_without_path(tmp_path, monkeypatch):
    sources = tmp_path / 'sources.json'
    entry = {'kind': 'document', 'company': 'X', 'operation': 'Y', 'country': 'MOZ',
             'url': 'https://example.invalid/report.pdf', 'sha256': 'abc'}
    sources.write_bytes(graphite.archive.encode({'note': 't', 'documents': [entry]}))
    monkeypatch.setattr(graphite_companies, 'SOURCES', sources)
    with pytest.raises(ValueError, match='no archived path'):
        graphite_companies.verify_archived(tmp_path)
