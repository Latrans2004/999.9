"""Fetch every configured query without publishing; preserve failures and raw observations."""
import json
import logging
import os
from pathlib import Path

from . import archive, countries
from .sources import comtrade, http


def run(root):
    settings = json.loads((root / 'pipeline/minerals.json').read_text())['minerals']['lithium']
    key = os.environ.get('COMTRADE_API_KEY', '').strip()
    if not key:
        raise ValueError('COMTRADE_API_KEY is required for the complete audit')
    report = {'queries': [], 'unmapped': {}}
    for year in range(settings['start_year'], settings['end_year'] + 1):
        for hs in settings['hs_codes']:
            for flow in ('X', 'M'):
                query = dict(period=str(year), cmdCode=hs, flowCode=flow,
                             reporterCode='', partnerCode='', partner2Code='0',
                             customsCode='C00', motCode='0', maxRecords=settings['max_records'],
                             includeDesc='true', breakdownMode='classic')
                item = {'query': query}
                try:
                    body = http.get(comtrade.FULL_URL, params=query,
                                    headers={'Ocp-Apim-Subscription-Key': key}, use_cache=False)
                    item['source'] = archive.save(root, 'comtrade', body, url=comtrade.FULL_URL, query=query)
                    payload = json.loads(body)
                    rows = payload.get('data')
                    if payload.get('errorMessage') or not isinstance(rows, list) or not rows:
                        raise ValueError('Empty/error response')
                    if len(rows) >= settings['max_records'] or int(payload.get('count', len(rows))) != len(rows):
                        raise ValueError('Truncated/count-mismatched response')
                    item['rows'] = len(rows)
                    for row in rows:
                        for dimension in ('reporter', 'partner'):
                            code, name = row.get(dimension+'ISO'), row.get(dimension+'Desc')
                            try:
                                countries.normalize(name, code=code)
                            except ValueError:
                                identity = json.dumps([code, name], ensure_ascii=False)
                                record = report['unmapped'].setdefault(identity, {
                                    'iso': code, 'name': name, 'codes': [], 'dimensions': [], 'rows': 0,
                                    'queries': [], 'value_usd': 0})
                                for field, value in [('codes', row.get(dimension+'Code')),
                                                     ('dimensions', dimension), ('queries', [year, hs, flow])]:
                                    if value not in record[field]: record[field].append(value)
                                record['rows'] += 1
                                record['value_usd'] += row.get('primaryValue') or 0
                    item['status'] = 'ok'
                except Exception as exc:
                    item.update(status='failed', error=str(exc))
                report['queries'].append(item)
                (root / 'entity-audit.json').write_bytes(archive.encode(report))
                logging.info('%s %s %s: %s (%s rows)', year, hs, flow, item['status'], item.get('rows'))
    if any(q['status'] != 'ok' for q in report['queries']):
        raise ValueError('Some queries failed; see entity-audit.json')


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    run(Path(__file__).resolve().parents[1])
