"""Safety contracts. All invented measurements/documents here are test-only."""
import copy
import csv
import io
import json
from pathlib import Path

import pytest

from pipeline import archive, manganese as mn, manganese_anchor as anchor
from pipeline import manganese_disclosures as discover, manganese_evidence as ev
from pipeline import manganese_reference as reference
from pipeline.tests.test_strict_pipeline import api_row, query


def policy():
    return {'mirror_allowlist': [], 'gap_threshold': None, 'anchor_ratio_band': None, 'country_context': {}}


def row(flow='X', reporter='ZAF', partner='W00', weight=100, **extra):
    return dict(year=2024, hs_code='260200', flow=flow, reporter=reporter, partner=partner,
                weight_t=weight, value_usd=1000, weight_estimated=False,
                classification='H6', raw_path='data/raw/test.json', **extra)


def diagnostic():
    return mn.compare([row(), row('M', 'CHN', 'ZAF', 200)], policy())[0]


def disclosure(**extra):
    result = dict(country='ZAF', year=2024, measure='production', value_t=100,
                  company='Test company', operation='Test mine',
                  source_url='https://example.test/annual.pdf', locator='Annual table, p. 2',
                  review_date='2026-09-14', weight_basis=mn.WEIGHT_BASIS,
                  product_scope=ev.PRODUCT, period_start='2024-01-01', period_end='2024-12-31',
                  coverage_scope='national')
    return result | extra


def csv_bytes(items):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=ev.FIELDS)
    writer.writeheader()
    writer.writerows(items)
    return stream.getvalue().encode()


def pinned(tmp_path, item=None):
    item = item or disclosure()
    ref = archive.save(tmp_path, 'external', b'%PDF-test-only', url=item['source_url'], suffix='.pdf')
    source = dict(kind='document', source_url=item['source_url'], reviewer='Synthetic test reviewer',
                  review_date='2026-09-14', review_status='human_reviewed', raw=ref,
                  measurements=[{k: v for k, v in item.items() if k != 'review_date'}])
    return source


@pytest.mark.parametrize('weight', [0, 50, 100, 150, 200, 10000, None])
def test_neither_gap_nor_production_selects_weight(weight):
    result = mn.compare([row(), row('M', 'CHN', 'ZAF', weight)], policy())[0]
    assert result['selected_weight_t'] is None and result['publishable'] is False
    d = anchor.diagnose(result, [disclosure()])
    assert 'selected_weight_t' not in d
    assert d['reported_production_ratio'] is None
    assert d['threshold_status'] == 'deferred_no_manganese_evidence'


def test_mirror_absence_does_not_discredit_reported():
    result = mn.compare([row(), row(partner='JPN'), row('M', 'CHN', 'ZAF')], policy())[0]
    assert result['reported_measurement_flags'] == []
    assert result['reported_reliability'] == 'unverified'
    assert result['missing_observed_destinations'] == ['JPN']
    assert result['mirror_world_complete'] is False
    assert result['mirror_global_coverage'] is None
    assert result['reported_weight_t'] == 100


def test_partial_mirror_sum_explicit_and_zero_preserved():
    result = mn.compare([row(weight=0), row('M', 'CHN', 'ZAF', 0), row('M', 'JPN', 'ZAF', None)], policy())[0]
    assert result['mirror_observed_weight_t'] == 0
    assert result['mirror_missing_weight_rows'] == 1
    assert result['reported_weight_t'] == 0
    assert result['comparison_status'] == 'indeterminate'
    assert 'positive_value_zero_weight' in result['reported_measurement_flags']


@pytest.mark.parametrize('mutate', ['duplicate', 'alloy', 'metal', 'battery', 'year', 'classification', 'negative', 'nan', 'bool'])
def test_bad_scope_and_numbers_rejected(mutate):
    r = row()
    rows = [r]
    if mutate == 'duplicate': rows.append(dict(r))
    if mutate in {'alloy', 'metal', 'battery'}: r['hs_code'] = {'alloy': '720230', 'metal': '811100', 'battery': '282010'}[mutate]
    if mutate == 'year': r['year'] = 2025
    if mutate == 'classification': r['classification'] = 'S4'
    if mutate == 'negative': r['weight_t'] = -1
    if mutate == 'nan': r['weight_t'] = float('nan')
    if mutate == 'bool': r['weight_t'] = True
    with pytest.raises(ValueError): mn.compare(rows, policy())


@pytest.mark.parametrize('threshold', [0, .25, .5, 1.5])
def test_unjustified_thresholds_rejected(threshold):
    p = policy() | {'gap_threshold': threshold}
    with pytest.raises(ValueError, match='deferred'): mn.compare([row()], p)


@pytest.mark.parametrize('role,expected', [('hub', 'hub'), ('domestic_consumption', 'domestic_consumption'), ('unknown', 'indeterminate')])
def test_industry_role_not_inferred_from_ratios(role, expected):
    d = anchor.diagnose(diagnostic(), [disclosure()], {'role': role})
    assert d['classification'] == expected and d['reported_production_ratio'] is None


@pytest.mark.parametrize('change,reason', [({'weight_basis': 'contained_mn'}, 'weight_basis_mismatch'),
    ({'weight_basis': 'dry_ore_mass'}, 'weight_basis_mismatch'),
    ({'weight_basis': 'wet_ore_mass'}, 'weight_basis_mismatch'),
    ({'product_scope': 'manganese_alloys'}, 'product_scope_mismatch'),
    ({'coverage_scope': 'equity_share'}, 'operation_is_not_national_production'),
    ({'coverage_scope': 'operation_100_percent'}, 'operation_is_not_national_production'),
    ({'period_start': '2023-07-01', 'period_end': '2024-06-30'}, 'fiscal_calendar_mismatch')])
def test_incomparable_anchors_do_not_produce_ratios(change, reason):
    d = anchor.diagnose(diagnostic(), [disclosure(**change)])
    assert d['classification'] == 'incomparable'
    assert reason in d['comparability_issues']
    assert d['reported_production_ratio'] is None


def test_missing_no_dispute_zero_anchor_and_sales_distinct():
    d = diagnostic()
    assert anchor.diagnose(d, [])['reason'] == 'no_human_reviewed_annual_production'
    assert anchor.diagnose(d, [disclosure(measure='sales')])['classification'] == 'missing'
    assert anchor.diagnose(d, [disclosure(value_t=0)])['reason'] == 'ambiguous_or_zero_production_anchor'
    equal = mn.compare([row(), row('M', 'CHN', 'ZAF')], policy())[0]
    assert anchor.diagnose(equal, [])['classification'] == 'no_dispute'
    absent = dict(d, reported_weight_t=None)
    assert anchor.diagnose(absent, [])['reason'] == 'missing_reported_trade'


def test_discover_only_documents_and_failure_isolation(tmp_path):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        assert kwargs['headers'] == {}
        if 'fail' in url: raise RuntimeError('secret body must not be logged')
        return b'%PDF-test-only'
    manifest = [dict(id=k, kind=kind, format='pdf', title=k, source_url='https://example.test/' + k)
                for k, kind in [('index', 'index'), ('fail', 'document'), ('ok', 'document')]]
    results = discover.discover(tmp_path, manifest, get)
    assert [r['status'] for r in results] == ['skipped_index', 'failed', 'downloaded_unreviewed']
    assert len(calls) == 2 and 'index' not in calls[0]
    assert all(r['review_status'] == 'unreviewed' for r in results)
    assert 'secret' not in (tmp_path / 'discover.json').read_text()
    assert results[-1]['raw']['path'] and results[-1]['raw']['sha256']


def test_discover_wrong_body_archived_and_not_success(tmp_path):
    result = discover.discover(tmp_path, [dict(id='x', kind='document', format='pdf', title='x',
                                             source_url='https://example.test/x')], lambda *a, **k: b'<html>denied</html>')[0]
    assert result['status'] == 'failed' and (tmp_path / result['raw']['path']).exists()


def test_valid_annual_reviewed_csv(tmp_path):
    source = pinned(tmp_path)
    sources = ev.reviewed_sources(tmp_path, [source])
    parsed = ev.parse_disclosures(csv_bytes([disclosure()]), sources)
    assert parsed[0]['value_t'] == 100
    assert parsed[0]['raw']['sha256'] == source['raw']['sha256']


@pytest.mark.parametrize('field', ev.FIELDS)
def test_all_disclosure_fields_required(tmp_path, field):
    sources = ev.reviewed_sources(tmp_path, [pinned(tmp_path)])
    item = disclosure() | {field: ''}
    with pytest.raises(ValueError, match='Missing required'): ev.parse_disclosures(csv_bytes([item]), sources)


@pytest.mark.parametrize('change', [{'measure': 'exports'}, {'value_t': '-1'}, {'value_t': 'NaN'},
    {'value_t': 'inf'}, {'country': 'World'}, {'year': 2025}, {'review_date': '2026-02-30'},
    {'period_start': '2024-10-01'}, {'product_scope': 'manganese_alloys'},
    {'weight_basis': 'tonnes'}, {'source_url': 'https://example.test/unpinned.pdf'},
    {'value_t': 200}])
def test_invalid_or_unattested_disclosures_rejected(tmp_path, change):
    sources = ev.reviewed_sources(tmp_path, [pinned(tmp_path)])
    with pytest.raises(ValueError): ev.parse_disclosures(csv_bytes([disclosure(**change)]), sources)


def test_duplicate_csv_and_header_rejected(tmp_path):
    sources = ev.reviewed_sources(tmp_path, [pinned(tmp_path)])
    with pytest.raises(ValueError, match='Duplicate'): ev.parse_disclosures(csv_bytes([disclosure()] * 2), sources)
    with pytest.raises(ValueError, match='schema'): ev.parse_disclosures(b'country,country\n', sources)


@pytest.mark.parametrize('mutation', ['path', 'sha256', 'bytes', 'metadata', 'escape', 'unreviewed', 'reviewer', 'index'])
def test_pin_and_archive_integrity(tmp_path, mutation):
    source = pinned(tmp_path)
    if mutation in {'path', 'sha256'}: del source['raw'][mutation]
    if mutation == 'bytes': (tmp_path / source['raw']['path']).write_bytes(b'changed')
    if mutation == 'metadata': (tmp_path / source['raw']['path']).with_suffix('.meta.json').write_text('{}')
    if mutation == 'escape': source['raw']['path'] = '../outside.pdf'
    if mutation == 'unreviewed': source['review_status'] = 'unreviewed'
    if mutation == 'reviewer': source['reviewer'] = ''
    if mutation == 'index': source['kind'] = 'index'
    with pytest.raises(ValueError): ev.reviewed_sources(tmp_path, [source])


def decision(source):
    return dict(country='ZAF', year=2024, hs_code='260200', decision='reported',
                reason='Synthetic customs annual evidence', reviewer='Test human', review_date='2026-09-14',
                review_status='human_reviewed', source_url=source['source_url'], locator='annual exports p.3',
                evidence_path=source['raw']['path'], evidence_sha256=source['raw']['sha256'],
                selected_weight_t=100, weight_basis=mn.WEIGHT_BASIS, product_scope=ev.PRODUCT)


def attest_decision(source, item):
    source['trade_decisions'] = [{k: item[k] for k in ('country', 'year', 'hs_code', 'locator', 'weight_basis', 'product_scope')} |
                                 dict(measure='exports', coverage_scope='national', value_t=item['selected_weight_t'])]


def test_production_source_cannot_approve_trade(tmp_path):
    source = pinned(tmp_path)
    item = decision(source)
    sources = ev.reviewed_sources(tmp_path, [source])
    with pytest.raises(ValueError, match='export evidence'): ev.load_decisions([item], [diagnostic()], sources, [])
    attest_decision(source, item)
    selected = ev.load_decisions([item], [diagnostic()], sources, [])
    assert selected[0]['selected_weight_t'] == 100 and selected[0]['publishable'] is False


@pytest.mark.parametrize('mutation', ['unreviewed', 'path', 'sha256', 'value', 'mirror', 'basis', 'missing'])
def test_adoption_gate(tmp_path, mutation):
    source = pinned(tmp_path)
    item = decision(source)
    attest_decision(source, item)
    sources = ev.reviewed_sources(tmp_path, [source])
    if mutation == 'unreviewed': item['review_status'] = 'unreviewed'
    if mutation in {'path', 'sha256'}: item['evidence_' + mutation] = 'wrong'
    if mutation == 'value': item['selected_weight_t'] = 200
    if mutation == 'mirror': item.update(decision='mirror', selected_weight_t=200)
    if mutation == 'basis': item['weight_basis'] = 'contained_mn'
    if mutation == 'missing': del item['selected_weight_t']
    with pytest.raises(ValueError): ev.load_decisions([item], [diagnostic()], sources, [])


def archived_bundle(tmp_path):
    native, q = api_row(), query()
    native.update(cmdCode='260200', classificationCode='H6', netWgt=1000, isNetWgtEstimated=False)
    q.update(cmdCode='260200', maxRecords=500)
    body = archive.encode({'data': [native], 'count': 1})
    ref = archive.save(tmp_path, 'comtrade', body, url='https://example.test/comtrade', query=q)
    rows = mn.strict_comtrade.normalize(json.loads(body), q, 500)
    for r in rows: r.update(raw_path=ref['path'], retrieved_at=ref['retrieved_at'])
    mn.graphite.enrich(tmp_path, rows, ref)
    path = tmp_path / 'bundle.json'
    path.write_bytes(archive.encode(dict(trade=rows, sources=[ref], acquisition_scope='sample', queries=[])))
    return path


def test_replay_revalidates_raw_and_normalized(tmp_path):
    path = archived_bundle(tmp_path)
    assert mn.replay(path)[0][0]['weight_t'] == 1
    bundle = json.loads(path.read_bytes())
    bundle['trade'][0]['weight_t'] = 2
    path.write_bytes(archive.encode(bundle))
    with pytest.raises(ValueError, match='differs'): mn.replay(path)


def test_collect_missing_key_no_network_and_attempts_all(tmp_path, monkeypatch):
    monkeypatch.delenv('COMTRADE_API_KEY', raising=False)
    monkeypatch.setattr(mn, 'fetch', lambda *a, **k: pytest.fail('No public fallback'))
    rows, queries = mn.collect(tmp_path)
    assert rows == [] and len(queries) == 16
    assert all(q['status'] == 'failed' for q in queries)


def test_query_failure_does_not_stop_others(tmp_path, monkeypatch):
    def fetch(root, hs, year, flow, **kwargs):
        if flow == 'X': raise ValueError('not available')
        return [row(flow='M', reporter='CHN', partner='ZAF', weight=100, sample_reporter=kwargs['reporter'])], {'path': 'data/raw/test.json'}
    monkeypatch.setattr(mn, 'fetch', fetch)
    monkeypatch.setattr(mn.graphite, 'enrich', lambda *a: None)
    monkeypatch.setattr(mn, 'SAMPLE_REPORTERS', [156])
    rows, queries = mn.collect(tmp_path, True)
    assert len(rows) == 1
    assert [q['status'] for q in queries] == ['failed', 'ok']


def test_workflows_manual_read_only_and_discovery_no_secret():
    for name in ('manganese-audit.yml', 'manganese-disclosures.yml'):
        text = (mn.ROOT / '.github/workflows' / name).read_text()
        assert 'workflow_dispatch:' in text and 'contents: read' in text
        assert 'schedule:' not in text and '  push:' not in text and 'pull_request:' not in text
        assert 'git push' not in text and 'pages: write' not in text
        assert 'persist-credentials: false' in text
    text = (mn.ROOT / '.github/workflows/manganese-disclosures.yml').read_text()
    assert 'secrets.' not in text and 'COMTRADE_API_KEY' not in text


def test_committed_reviews_are_empty_not_claimed_human_work():
    assert json.loads((mn.ROOT / 'pipeline/manganese_reviewed_sources.json').read_bytes()) == []
    assert json.loads((mn.ROOT / 'pipeline/manganese_reviews.json').read_bytes()) == []
    assert ev.parse_disclosures((mn.ROOT / 'data/manual/manganese-disclosures.csv').read_bytes(), {}) == []


def test_fetch_retains_rejected_raw(tmp_path, monkeypatch):
    from pipeline.sources import http
    monkeypatch.delenv('COMTRADE_API_KEY', raising=False)
    monkeypatch.setattr(http, 'get', lambda *a, **k: b'{"data": [], "count": 0}')
    with pytest.raises(ValueError) as exc:
        mn.fetch(tmp_path, '260200', 2024, 'X', reporter=36)
    assert exc.value.reason_code == 'empty_response_not_zero_trade'
    assert ev.verify_raw(tmp_path, exc.value.raw_ref) == b'{"data": [], "count": 0}'


def test_query_rejected_raw_tamper_fails_replay(tmp_path):
    path = archived_bundle(tmp_path)
    bundle = json.loads(path.read_bytes())
    ref = archive.save(tmp_path, 'comtrade', b'{"data": []}', url='https://example.test/empty')
    bundle['queries'] = [dict(status='failed', raw=ref)]
    path.write_bytes(archive.encode(bundle))
    (tmp_path / ref['path']).write_bytes(b'changed')
    with pytest.raises(ValueError, match='sha256'): mn.replay(path)


def test_archive_path_pin_cannot_be_relocated_even_with_same_bytes(tmp_path):
    source = pinned(tmp_path)
    original = tmp_path / source['raw']['path']
    other = original.with_name('0' * 64 + '.pdf')
    other.write_bytes(original.read_bytes())
    source['raw']['path'] = other.relative_to(tmp_path).as_posix()
    with pytest.raises(ValueError, match='content-addressed'): ev.reviewed_sources(tmp_path, [source])


def test_explicit_mirror_decision_needs_primary_attestation_and_allowlist(tmp_path):
    source = pinned(tmp_path)
    item = decision(source) | dict(decision='mirror', selected_weight_t=200)
    attest_decision(source, item)
    sources = ev.reviewed_sources(tmp_path, [source])
    assert ev.load_decisions([item], [diagnostic()], sources, ['ZAF'])[0]['selected_weight_t'] == 200
    assert diagnostic()['selected_weight_t'] is None


def usgs_text():
    return ('Data in thousand metric tons, gross weight, unless otherwise specified\n'
            'World Mine Production (manganese content) and Reserves:\n'
            'Mine production Reserves\n2024 2025e\nUnited States — — —\n'
            'Australia e1,600 1,600 999999\nBrazil W NA 999999\nOther countries 100 100 Small\n'
            'World total (rounded) 1,700 1,700 999999\nWorld Resources: not production')


def test_usgs_content_native_units_estimates_and_withheld():
    rows = reference.parse_usgs(usgs_text(), {})
    assert rows[0]['value_t'] == 0
    assert rows[1]['value_t'] == 1600000 and rows[1]['estimate_status'] == 'estimated'
    assert rows[2]['value_t'] is None
    assert rows[-1]['coverage_scope'] == 'world'
    assert all(r['weight_basis'] == 'contained_mn' and r['publishable'] is False for r in rows)
    assert all(r['review_status'] == 'unreviewed_machine_extraction' for r in rows)


@pytest.mark.parametrize('mutation', ['unit', 'basis', 'year', 'duplicate', 'world'])
def test_usgs_changed_table_fails_closed(mutation):
    text = usgs_text()
    if mutation == 'unit': text = text.replace('thousand metric tons', 'metric tons')
    if mutation == 'basis': text = text.replace('(manganese content)', '(gross weight)')
    if mutation == 'year': text = text.replace('2024 2025e', '2025 2026e')
    if mutation == 'duplicate': text = text.replace('Brazil W NA 999999', 'Brazil W NA 999999\nBrazil W NA 999999')
    if mutation == 'world': text = text.replace('World total (rounded) 1,700 1,700 999999\n', '')
    with pytest.raises(ValueError): reference.parse_usgs(text, {})


def test_full_offline_run_does_not_touch_public_and_rejects_bad_review(tmp_path, monkeypatch):
    real_root = mn.ROOT
    root = tmp_path / 'repo'
    (root / 'pipeline').mkdir(parents=True)
    (root / 'data/manual').mkdir(parents=True)
    (root / 'critical-minerals').mkdir()
    public = root / 'critical-minerals/sentinel.json'
    public.write_bytes(b'unchanged public data')
    for name in ('manganese_policy.json', 'manganese_reviewed_sources.json', 'manganese_reviews.json'):
        (root / 'pipeline' / name).write_bytes((real_root / 'pipeline' / name).read_bytes())
    (root / 'data/manual/manganese-disclosures.csv').write_bytes(csv_bytes([]))
    monkeypatch.setattr(mn, 'ROOT', root)
    raw_root = root / '.cache/input'
    raw_root.mkdir(parents=True)
    path = archived_bundle(raw_root)
    output = root / '.cache/result'
    summary, code = mn.run(output, replay_path=path)
    assert code == 0 and summary['adopted_values'] == 0
    assert json.loads((output / 'status.json').read_bytes())['queries_complete'] is False
    assert json.loads((output / 'status.json').read_bytes())['publishable'] is False
    assert public.read_bytes() == b'unchanged public data'
    # An identical replay is repeatable. Existing changed Raw must not be repaired silently.
    assert mn.run(output, replay_path=path)[0] == summary
    b = json.loads(path.read_bytes())
    (output / b['sources'][0]['path']).write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='refusing overwrite'): mn.run(output, replay_path=path)
    assert json.loads((output / 'status.json').read_bytes())['status'] == 'failed'
    assert public.read_bytes() == b'unchanged public data'
    (root / 'pipeline/manganese_reviews.json').write_bytes(archive.encode([{'selected_weight_t': 999}]))
    with pytest.raises(ValueError, match='Missing required'):
        mn.run(root / '.cache/result2', replay_path=path)


def test_public_output_path_rejected():
    for path in (mn.ROOT, mn.ROOT / 'critical-minerals', mn.ROOT / 'critical-minerals/data', mn.ROOT / 'data/raw'):
        with pytest.raises(ValueError, match='Output'): mn.isolated_output(path)


def test_committed_real_trade_replay_and_reference_integrity():
    path = mn.ROOT / 'data/review/manganese-sample/bundle.json'
    rows, bundle = mn.replay(path)
    assert len(rows) == 249
    assert len(bundle['queries']) == 16
    assert sum(q['status'] == 'failed' for q in bundle['queries']) == 5
    assert all(q.get('raw') for q in bundle['queries'])
    assert all(d['selected_weight_t'] is None for d in mn.compare(rows, policy()))
    root = mn.ROOT / 'data/review/manganese-evidence'
    discovered = json.loads((root / 'discover.json').read_bytes())
    for doc in discovered:
        if doc.get('raw'):
            ev.verify_raw(root, doc['raw'])
