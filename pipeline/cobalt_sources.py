"""Archive primary sources for cobalt cross-checks, without adopting their values."""
import argparse
import hashlib
import json
from pathlib import Path

import requests

from . import archive

ROOT = Path(__file__).resolve().parents[1] / 'data/review/cobalt'
SOURCES = {
    'bgs-2020-2024': 'https://nora.nerc.ac.uk/id/eprint/541620/1/WMP_2020%20to%202024.pdf',
    'glencore-2024': 'https://www.glencore.com/.rest/api/v1/documents/static/437c6cdb-dbfb-4e61-a769-18655951cee2/Glencore+production+report_FY2024.pdf',
    'cmoc-2024-results': 'https://en.cmoc.com/html/2025/News_0324/73.html',
    'drc-ministry-index': 'https://mines.gouv.cd/statistique/pdf',
    'drc-ministry-2024': 'https://mines.gouv.cd/download/3',
    'drc-ministry-2023': 'https://mines.gouv.cd/download/4',
    'nrcan-cobalt': 'https://natural-resources.canada.ca/minerals-mining/mining-data-statistics-analysis/minerals-metals-facts/cobalt-facts',
    'un-hs-conversion': 'https://unstats.un.org/unsd/classifications/Econ/corr-notes/HS2022%20conversion%20to%20earlier%20HS%20versions%20and%20other%20classifications%20%20-%20v.1.0.pdf',
    'un-h4': 'https://comtradeapi.un.org/files/v1/app/reference/H4.json',
    'un-h5': 'https://comtradeapi.un.org/files/v1/app/reference/H5.json',
    'un-h6': 'https://comtradeapi.un.org/files/v1/app/reference/H6.json',
    'un-h6-h5': 'https://unstats.un.org/unsd/classifications/Econ/tables/HS2022toHS2017ConversionAndCorrelationTables.xlsx',
    'un-h6-h4': 'https://unstats.un.org/unsd/classifications/Econ/tables/HS2022toHS2012ConversionAndCorrelationTables.xlsx',
    'un-h5-h4': 'https://unstats.un.org/unsd/classifications/Econ/tables/HS2017toHS2012ConversionAndCorrelationTables.xlsx',
}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--fetch', action='store_true')
    args = parser.parse_args()
    path = ROOT / 'external-sources.json'
    entries = json.loads(path.read_bytes()) if path.exists() else []
    if args.fetch:
        for name, url in SOURCES.items():
            if any(e['id'] == name and e['status'] == 'archived_unreviewed' for e in entries):
                continue
            entry = {'id': name, 'url': url, 'publishable': False}
            try:
                response = requests.get(url, timeout=45)
                entry['http_status'] = response.status_code
                suffix = '.pdf' if response.content.startswith(b'%PDF') else '.html'
                if url.endswith('.json'):
                    suffix = '.json'
                elif url.endswith('.xlsx') and response.content.startswith(b'PK'):
                    suffix = '.xlsx'
                entry['raw'] = archive.save(ROOT, name, response.content, url=url, suffix=suffix)
                entry['status'] = 'archived_unreviewed' if response.status_code == 200 else 'http_error'
            except requests.RequestException as exc:
                entry.update(status='transport_error', error_type=type(exc).__name__)
            entries.append(entry)
            path.write_bytes(archive.encode(entries))
            print(name, entry['status'], flush=True)
    for entry in entries:
        if 'raw' in entry:
            ref = entry['raw']
            if hashlib.sha256((ROOT / ref['path']).read_bytes()).hexdigest() != ref['sha256']:
                raise ValueError('Source bytes changed')
    print('Source archive hashes verified')


if __name__ == '__main__':
    main()
