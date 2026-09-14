from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from pipeline import build, graphite_usgs, publish_graphite as publisher

ROOT = Path(__file__).resolve().parents[2]


def inputs():
    records = publisher.read(ROOT / 'data/review/natural-graphite/production.json')
    policy = publisher.read(ROOT / publisher.POLICY)
    catalog = publisher.read(ROOT / 'critical-minerals/data/catalog.json')
    entry = next(e for e in catalog['minerals'] if e['slug'] == publisher.SLUG)
    return records, policy, entry


def test_mine_numbers_equal_reviewed_audit_trade_withheld():
    records, policy, entry = inputs()
    site, production, profiles = publisher.assemble(records, policy, entry)
    original = graphite_usgs.profiles(records)
    assert [p['profile'] for p in profiles] == [p['profile'] for p in original]
    assert site['production']['latest']['hhi'] == original[-1]['profile']['hhi']
    assert site['production']['trend'] is None
    assert all(p['publishable'] for p in profiles)
    assert site['trade']['available'] is False
    assert 'latest' not in site['trade']
    assert all(p['verification_status'] == 'not_applicable' for p in production)
    assert any(p['status'] == 'estimated' for p in production)
    assert all(not p['included'] for p in production if p['kind'] != 'country')


@pytest.mark.parametrize('mutation', ['quantity', 'estimate', 'year', 'flag', 'decision', 'trade'])
def test_new_data_or_decisions_need_review(mutation):
    records, policy, entry = inputs()
    if mutation == 'quantity':
        records[0]['production_t'] += 1
    elif mutation == 'estimate':
        records[0]['status'] = 'estimated'
    elif mutation == 'year':
        policy['years'].append(2025)
    elif mutation == 'flag':
        policy['production']['reviewed_flag_years'] = []
    elif mutation == 'decision':
        policy['production']['decision'] = 'pending'
    else:
        policy['trade']['decision'] = 'publish'
    with pytest.raises(ValueError):
        publisher.assemble(records, policy, entry)


def copy_repo(destination):
    for name in ('pipeline', 'assets', 'critical-minerals'):
        shutil.copytree(ROOT / name, destination / name,
                        ignore=shutil.ignore_patterns('__pycache__', '.pytest_cache'))
    shutil.copy2(ROOT / 'site.json', destination / 'site.json')
    shutil.copytree(ROOT / 'data/review/natural-graphite', destination / 'data/review/natural-graphite')


def public_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in (root / 'critical-minerals').rglob('*') if p.is_file()}


def test_replay_transaction_idempotence_and_public_links(tmp_path):
    copy_repo(tmp_path)
    before = public_bytes(tmp_path)
    publisher.run(tmp_path)
    after = public_bytes(tmp_path)
    for name, body in before.items():
        if name.startswith('critical-minerals/data/') and 'natural-graphite' not in name and not name.endswith('/index.json'):
            assert after[name] == body, name
    assert publisher.run(tmp_path) is False
    assert after == public_bytes(tmp_path)
    page = tmp_path / 'critical-minerals/minerals/natural-graphite.html'
    html = page.read_text(encoding='utf-8')
    assert 'Under review' in html and '確認中' in html
    assert '/natural-graphite/trade.json' not in html
    for href in re.findall(r'href="([^"]+)"', html):
        if 'data/natural-graphite/' in href:
            assert (page.parent / href).resolve().is_file(), href
    assert not (tmp_path / publisher.PUBLIC / 'trade.json').exists()
    # A failed staged render must leave all accepted data and pages intact.
    with pytest.raises(subprocess.CalledProcessError):
        publisher.run(tmp_path, render_command=[sys.executable, '-c', 'raise SystemExit(7)'])
    assert after == public_bytes(tmp_path)
    # Tampering with a pinned PDF must also retain the accepted site.
    manifest = publisher.read(tmp_path / 'pipeline/graphite_usgs_sources.json')
    raw = tmp_path / 'data/review/natural-graphite' / manifest[0]['path']
    raw.write_bytes(b'changed PDF')
    with pytest.raises(ValueError):
        publisher.run(tmp_path)
    assert after == public_bytes(tmp_path)


def test_fixtures_rejected_before_replay(tmp_path, monkeypatch):
    publisher.put(tmp_path, 'critical-minerals/data/index.json', {'fixtures': True})
    monkeypatch.setattr(publisher.graphite, 'replay_bundle', lambda *a: pytest.fail('must fail before replay'))
    with pytest.raises(ValueError, match='fixtures'):
        publisher.run(tmp_path)


def test_legacy_build_routes_graphite_to_strict_publisher(monkeypatch):
    calls = []
    monkeypatch.setattr(publisher, 'run', lambda root: calls.append(root))
    monkeypatch.setattr(build, 'build_mineral', lambda *a, **k: pytest.fail('legacy adapter must not run'))
    build.run(['natural-graphite'])
    assert calls == [build.REPO_ROOT]
