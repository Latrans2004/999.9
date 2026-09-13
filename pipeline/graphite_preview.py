"""Render an isolated review site with mine metrics and withheld trade headline."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import shutil
import subprocess
import sys

from .graphite import ROOT, put
from .update_minerals import pack
from .build import summarise


def render(audit, destination):
    if not destination.resolve().is_relative_to(ROOT / '.cache'):
        raise ValueError('Preview must stay under .cache')
    records = json.loads((audit / 'production.json').read_bytes())
    values, world = defaultdict(dict), {}
    for row in records:
        if row['kind'] == 'world':
            world[row['year']] = row['production_t']
        elif row['kind'] == 'country' and row['production_t'] is not None:
            values[row['year']][row['country']] = row['production_t']
    for name in ('pipeline', 'assets'):
        shutil.copytree(ROOT / name, destination / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(ROOT / 'site.json', destination / 'site.json')
    shutil.copytree(ROOT / 'critical-minerals/data', destination / 'critical-minerals/data', dirs_exist_ok=True)
    catalog = json.loads((ROOT / 'critical-minerals/data/catalog.json').read_bytes())
    entry = next(e for e in catalog['minerals'] if e['slug'] == 'natural-graphite')
    entry['summary'] = 'Natural graphite mine production. Synthetic graphite and total battery anode supply are outside this series.'
    entry['summary_ja'] = '天然黒鉛の鉱山生産量を対象とします。人造黒鉛や電池用負極材全体の供給量は含みません。'
    entry['caveats'] = ['Natural graphite covers multiple grades and uses, not just battery materials.',
                         'Trade concentration is withheld pending mirror reconciliation and coverage review.']
    entry['caveats_ja'] = ['天然黒鉛には電池用途以外の品種・用途も含まれます。',
                            '貿易指標はミラー照合とカバレッジの確認が終わるまで保留しています。']
    entry['production'] = pack(values, 'USGS Mineral Commodity Summaries (fixed 2019-2026 editions)',
                               'share of identified natural graphite mine production',
                               '天然黒鉛の国別鉱山生産量に占める割合', 'mine', world)
    entry['production']['notes'] = ['USGS estimates retained; Other excluded from country HHI; world totals rounded.',
                                    'Historical editions differ; annual changes can include revisions. Review preview only.']
    entry['trade'] = {'available': False, 'source': 'UN Comtrade',
                      'unit': 'natural graphite trade', 'stage': 'raw',
                      'notes': ['Mirror discrepancies and population coverage remain under review.']}
    put(destination, 'critical-minerals/data/minerals/natural-graphite.json', entry)
    index = json.loads((destination / 'critical-minerals/data/index.json').read_bytes())
    index['minerals'] = [summarise(entry) if r['slug'] == entry['slug'] else r for r in index['minerals']]
    put(destination, 'critical-minerals/data/index.json', index)
    subprocess.run([sys.executable, '-m', 'pipeline.render'], cwd=destination, check=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', type=Path, default=ROOT / '.cache/graphite-audit')
    args = parser.parse_args()
    render(args.audit, ROOT / '.cache/graphite-preview')
