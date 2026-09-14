import copy
import json
import logging
import pytest
from pipeline import audit_entities, countries, entity_diagnostics, process_trade, strict_comtrade, update_minerals
from pipeline.tests.test_strict_pipeline import (api_row, query, row, CONFIG, ROOT, synthetic_bundle,
                                                 copy_repo, SYNTHETIC_START_YEAR)


@pytest.mark.parametrize('code,name,numeric,key,kind,eligible', [
    ('USA', 'United States', 842, 'USA', 'country', True),
    ('HKG', 'China, Hong Kong SAR', 344, 'HKG', 'territory', True),
    ('ATB', 'Br. Antarctic Terr.', 80, 'CT:80', 'territory', True),
    ('W00', 'World', 0, 'W00', 'aggregate', False),
    ('WORLD', None, None, 'W00', 'aggregate', False),
    ('TOTAL', None, None, 'W00', 'aggregate', False),
    ('_X ', 'Areas, nes', 899, 'CT:899', 'special_area', False),
    ('MCO', 'Europe EU, nes', 492, 'CT:492', 'special_area', False),
    ('ZZZ', 'Unreviewed supplier', 9999, 'CT:9999', 'unknown', False),
])
def test_entity_identity_and_separate_policy(code, name, numeric, key, kind, eligible):
    entity = countries.resolve(name, code=code, numeric_code=numeric)
    assert (entity.key, entity.kind) == (key, kind)
    assert countries.metric_eligibility(entity)[0] is eligible
    assert not hasattr(entity, 'included')


def test_same_iso_different_statistical_areas_and_unknown_names():
    assert countries.resolve(code='A79', numeric_code=473).key == 'CT:473'
    assert countries.resolve(code='A79', numeric_code=636).key == 'CT:636'
    assert countries.resolve('unknown one').key != countries.resolve('unknown two').key
    assert countries.resolve().kind == 'unknown'


def test_unknown_retained_warned_and_other_rows_continue(caplog):
    first = api_row()
    atb = {**first, 'partnerCode': 80, 'partnerISO': 'ATB', 'partnerDesc': 'Br. Antarctic Terr.'}
    unknown = {**first, 'partnerCode': 9999, 'partnerISO': 'ZZZ', 'partnerDesc': 'New area'}
    special = {**first, 'partnerCode': 838, 'partnerISO': 'X2 ', 'partnerDesc': 'Free Zones'}
    caplog.set_level(logging.WARNING)
    normalized = strict_comtrade.normalize({'data': [first, atb, unknown, special]}, {**query(), 'partnerCode': ''}, 500)
    assert len(normalized) == 4
    assert normalized[2]['partner'] == 'CT:9999'
    assert normalized[2]['partner_iso'] == 'ZZZ'
    assert normalized[2]['partner_name'] == 'New area'
    assert 'Unknown Comtrade entity partner CT:9999' in caplog.text
    assert [countries.trade_eligibility(r)[0] for r in normalized] == [True, True, False, False]
    diagnostics = entity_diagnostics.summarize(normalized)
    assert diagnostics['queries'][0]['excluded']['partner:unknown_requires_review']['rows'] == 1


def test_unknown_and_aggregates_cannot_bias_mirrors_or_partner_recovery():
    config = {'stages': {'283691': CONFIG['stages']['283691']}}
    records = [row('ARG', 100), row('CHN', 200, 'M', 'ARG')]
    contamination = [row('CT:9999', 1e9, 'M', 'ARG'), row('W00', 1e9, 'M', 'ARG'),
                     row('ARG', 1e9, partner='CT:9999'), row('ARG', 1e9, partner='CT:838')]
    assert process_trade.build(records, config) == process_trade.build(records + contamination, config)
    records = [row('USA', 0), row('USA', 20, partner='CHN')]
    selected = process_trade.build(records + [row('USA', 1e9, partner='CT:9999')], config)
    assert selected[0]['selected_value'] == 20


def test_atb_eligible_does_not_force_commodity_inclusion():
    # A recognized territory participates normally in a reported quantity policy.
    config = {'stages': {'283691': {'policy': 'reported'}}}
    records = [row('USA', 40), row('CHN', 35), row('CT:80', 25)]
    selected = process_trade.build(records, config)
    assert process_trade.metrics(selected)[0]['hhi'] == pytest.approx(3450)
    # The actual ATB observations are import mirrors of mixed ore, not reported
    # lithium export totals. Recognition must not manufacture a selected weight.
    ore = {'stages': {'253090': CONFIG['stages']['253090']}}
    result = process_trade.build([row('PER', .01632, 'M', 'CT:80', 184.28, '253090', 2017)], ore)
    assert result[0]['country'] == 'CT:80'
    assert result[0]['mirror_value'] == .01632
    assert result[0]['selected_value'] is None and not result[0]['included']


def test_unknown_bundle_renders_with_visible_diagnostics_and_unchanged_metrics(tmp_path, caplog):
    root = copy_repo(tmp_path)
    bundle = synthetic_bundle()
    assert update_minerals.run(root, bundle=bundle)
    before = json.loads((root/'data/processed/lithium/snapshot.json').read_text(encoding='utf-8'))
    bundle['trade'] += [row('CT:9999', 1e9), row('CHN', 1e9, 'M', 'CT:9999')]
    caplog.set_level(logging.WARNING)
    assert update_minerals.run(root, bundle=bundle)
    after = json.loads((root/'data/processed/lithium/snapshot.json').read_text(encoding='utf-8'))
    assert before['concentration'] == after['concentration']
    assert len(after['trade_rows']) == len(before['trade_rows']) + 2
    assert 'CT:9999' in caplog.text
    assert after['metadata']['unknown_entities'] == ['CT:9999']
    diagnostic = json.loads((root/'critical-minerals/data/lithium/entities.json').read_text(encoding='utf-8'))
    assert diagnostic['entities'][0]['kind'] == 'unknown'
    assert not update_minerals.run(root, bundle=bundle)


def test_replay_cannot_spoof_entity_identity():
    bundle = synthetic_bundle()
    bundle['trade'][0]['reporter_code'] = 80
    settings = copy.deepcopy(CONFIG); settings['start_year'] = SYNTHETIC_START_YEAR
    entry = json.loads((ROOT/'critical-minerals/data/catalog.json').read_text(encoding='utf-8'))['minerals'][0]
    with pytest.raises(ValueError, match='Invalid normalized entity'):
        update_minerals.assemble(bundle, settings, entry)


def test_full_audit_attempts_all_queries_even_after_a_fetch_failure(tmp_path, monkeypatch):
    (tmp_path/'pipeline').mkdir()
    (tmp_path/'pipeline/minerals.json').write_text(json.dumps({'minerals': {'lithium': CONFIG}}))
    monkeypatch.setenv('COMTRADE_API_KEY', 'test-only')
    monkeypatch.setattr(audit_entities.subprocess, 'check_output', lambda *a, **k: 'test-revision')
    calls = []
    def get(url, *, params, **kwargs):
        calls.append(params)
        if len(calls) == 2: raise ValueError('Simulated upstream outage')
        observation = {**api_row(), 'period': params['period'], 'cmdCode': params['cmdCode'],
                       'flowCode': params['flowCode']}
        return json.dumps({'data': [observation], 'count': 1}).encode()
    monkeypatch.setattr(audit_entities.http, 'get', get)
    with pytest.raises(ValueError, match='Some queries failed'):
        audit_entities.run(tmp_path)
    queries = (CONFIG['end_year'] - CONFIG['start_year'] + 1) * len(CONFIG['hs_codes']) * 2
    assert len(calls) == queries
    report = json.loads((tmp_path/'entity-audit.json').read_text(encoding='utf-8'))
    assert sum(q['status'] == 'ok' for q in report['queries']) == queries - 1
    assert report['queries'][1]['error'] == 'Simulated upstream outage'
