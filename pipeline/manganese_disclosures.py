"""Manually triggered document discovery; no credentials and no adoption."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from . import archive
from .manganese_evidence import required, source_url
from .sources import http

ROOT = Path(__file__).resolve().parents[1]


def discover(root, manifest, get=None):
    get = get or http.get
    results = []
    seen = set()
    for item in manifest:
        record = {'id': item.get('id'), 'source_url': item.get('source_url'),
                  'review_status': 'unreviewed', 'publishable': False}
        try:
            required(item, ('id', 'kind', 'source_url', 'title'))
            if item['id'] in seen:
                raise ValueError('Duplicate document id')
            seen.add(item['id'])
            source_url(item['source_url'])
            if item['kind'] == 'index':
                record['status'] = 'skipped_index'
            elif item['kind'] == 'document':
                required(item, ('format',))
                if item['format'] not in {'pdf', 'html'}:
                    raise ValueError('Unsupported document format')
                body = get(item['source_url'], headers={}, timeout=30, retries=2,
                           use_cache=False, binary=item['format'] == 'pdf')
                ref = archive.save(root, 'external', body, url=item['source_url'], suffix='.' + item['format'])
                record['raw'] = ref
                if item['format'] == 'pdf' and not body.startswith(b'%PDF-'):
                    raise ValueError('Document is not a PDF')
                if not body.strip():
                    raise ValueError('Empty document')
                record['status'] = 'downloaded_unreviewed'
            else:
                raise ValueError('Unknown source kind')
        except Exception as exc:
            record.update(status='failed', error_type=type(exc).__name__)
        results.append(record)
        root.mkdir(parents=True, exist_ok=True)
        (root / 'discover.json').write_bytes(archive.encode(results))
    return results


def main():
    from .manganese import isolated_output
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'pipeline/manganese_sources.json')
    parser.add_argument('--output', type=Path, default=ROOT / '.cache/manganese-discover')
    args = parser.parse_args()
    results = discover(isolated_output(args.output), json.loads(args.manifest.read_bytes()))
    return int(any(r['status'] == 'failed' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
