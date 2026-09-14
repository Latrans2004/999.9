import copy
import json
from pathlib import Path

import pytest

from pipeline import cobalt_collect as c


def example():
    root = Path(__file__).resolve().parents[2] / 'data/review/cobalt'
    entries = json.loads((root / 'a0-probe.json').read_bytes())
    entry = next(e for e in entries if e.get('rows') == 1)
    body = json.loads((root / entry['raw']['path']).read_bytes())
    return body, entry['query']


@pytest.mark.parametrize('mutation', ['count', 'error', 'period', 'reporter', 'duplicate', 'negative', 'classification'])
def test_rejects_bad_observation(mutation):
    body, query = example()
    if mutation == 'count':
        body['count'] += 1
    elif mutation == 'error':
        body['errorMessage'] = 'upstream failed'
    elif mutation == 'duplicate':
        body['data'].append(copy.deepcopy(body['data'][0]))
        body['count'] += 1
    else:
        field, value = {'period': ('period', 1900), 'reporter': ('reporterCode', 999),
                        'negative': ('netWgt', -1), 'classification': ('classificationCode', 'S4')}[mutation]
        body['data'][0][field] = value
    with pytest.raises(ValueError):
        c.diagnose(json.dumps(body), query)


def test_empty_is_not_zero_and_estimation_flags_survive():
    diagnostic, rows = c.diagnose('{"count":0,"data":[]}', c.plan()[0])
    assert diagnostic == {'status': 'empty', 'rows': 0} and rows == []
    body, query = example()
    diagnostic, rows = c.diagnose(json.dumps(body), query)
    assert diagnostic['status'] == 'observed'
    assert rows[0]['isNetWgtEstimated'] == body['data'][0]['isNetWgtEstimated']
    assert rows[0]['publishable'] is False


def test_retry_after_is_not_shortened():
    assert c.retry_delay('120', 0) == 120
    assert c.retry_delay(None, 2) == 12


def test_no_secret_means_no_network(tmp_path, monkeypatch):
    monkeypatch.delenv('COMTRADE_API_KEY', raising=False)
    with pytest.raises(ValueError, match='Missing Actions secret'):
        c.collect(tmp_path)
