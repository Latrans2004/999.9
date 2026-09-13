"""Archive official publications; ingest explicitly reviewed country tables."""
import csv
import io
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from . import archive, countries
from .strict_comtrade import number
from .sources import http

FIELDS = {'year', 'country', 'production_t', 'world_total_t', 'edition', 'status', 'source_url'}


def parse_csv(body):
    reader = csv.DictReader(io.StringIO(body.decode('utf-8-sig')))
    if not FIELDS <= set(reader.fieldnames or []):
        raise ValueError('USGS reviewed CSV missing required columns')
    records, seen = [], set()
    for row in reader:
        code = countries.normalize(row['country'])
        year, edition = int(row['year']), int(row['edition'])
        if not code or not 1900 <= year < edition <= 2100:
            raise ValueError('Invalid USGS country/year/edition')
        if row['status'] not in ('reported', 'estimated', 'withheld'):
            raise ValueError('Unknown USGS status')
        url = urlparse(row['source_url'])
        if url.scheme != 'https' or not (url.hostname or '').endswith('.usgs.gov'):
            raise ValueError('USGS record needs an official source URL')
        key = (year, code)
        if key in seen:
            raise ValueError(f'Duplicate production record: {key}; retain revisions in raw, select latest edition explicitly')
        seen.add(key)
        value, world = number(row['production_t']), number(row['world_total_t'])
        if (row['status'] == 'withheld') != (value is None):
            raise ValueError('Missing production must be explicitly withheld')
        records.append({'year': year, 'country': code, 'production_t': value,
                        'world_total_t': world, 'edition': edition,
                        'status': row['status'], 'source_url': row['source_url']})
    if not records:
        raise ValueError('USGS reviewed CSV is empty; transcribe and review official production table')
    return records


def collect(root: Path, config):
    url = config['publication_url']
    body = http.get(url, binary=True, use_cache=False)
    if not body.startswith(b'%PDF'):
        raise ValueError('USGS publication is not a PDF (upstream format/error)')
    publication = archive.save(root, 'usgs', body, url=url, suffix='.pdf', query={'edition': config['edition']})
    if hashlib.sha256(body).hexdigest() != config['publication_sha256']:
        raise ValueError('USGS PDF changed; review production table before updating publication_sha256')
    path = root / config['reviewed_csv']
    if not path.exists():
        raise ValueError(f'Missing reviewed USGS table: {config["reviewed_csv"]}')
    table = path.read_bytes()
    records = parse_csv(table)
    # Reviewed table must name the pinned publication for its newest edition.
    newest = max(r['edition'] for r in records)
    if newest != config['edition'] or any(r['source_url'] != url for r in records if r['edition'] == newest):
        raise ValueError('USGS reviewed table edition/source differs from pinned publication')
    record = archive.save(root, 'usgs', table, url='reviewed:' + config['reviewed_csv'], suffix='.csv')
    return records, [publication, record]
