"""Already published figures must not move when a new year is appended.

``validate_data`` asks whether a change is *plausible* (thresholds on movement
between runs). This module asks a different question: whether anything that was
already published moved *at all*. Extending a series - a new trade year, a
back-filled production edition - is an append, so every key the previous
snapshot carries has to come back byte-identical. Upstream retroactive revisions
are real and legitimate, but they are a human decision, not something a refresh
may absorb silently, so this returns a report instead of applying anything.

Keys absent from the previous snapshot are new and are not inspected here; the
plausibility gates in ``validate_data`` cover those.

    python -m pipeline.invariance --previous data/processed/lithium/snapshot.json \
        --current .cache/candidate.json [--max-year 2024]

Exit status is 1 when a published figure moved, so it can gate a commit.
"""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path

log = logging.getLogger('orelysis.invariance')

# Everything a page or a reader can see for a published year: the index itself,
# the concentration ratios, the reported universe and the completeness note.
CONCENTRATION_FIELDS = ('hhi', 'band', 'cr1', 'cr3', 'cr5', 'effective_suppliers',
                        'total', 'reporters', 'coverage', 'coverage_pct', 'unit')
SHARE_FIELDS = ('quantity', 'share')
PRODUCTION_FIELDS = ('production_t', 'world_total_t', 'edition', 'status', 'source_url')

# Replays of the same bytes through the same code are expected to be exactly
# equal. A tolerance exists only so that a summation-order change inside an
# untouched formula is not reported as a moved figure; every use is recorded.
DEFAULT_RELATIVE_TOLERANCE = 1e-9


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class Report:
    """Differences and tolerated near-misses, in report order."""

    def __init__(self):
        self.differences = []
        self.tolerated = []
        self.checked = {'concentration': 0, 'shares': 0, 'production': 0}

    @property
    def ok(self):
        return not self.differences

    def record(self, kind, key, field, previous, current, relative=None):
        self.differences.append({'kind': kind, 'key': key, 'field': field,
                                 'previous': previous, 'current': current,
                                 'relative_change': relative})

    def tolerate(self, kind, key, field, previous, current, relative):
        entry = {'kind': kind, 'key': key, 'field': field, 'previous': previous,
                 'current': current, 'relative_change': relative}
        self.tolerated.append(entry)
        log.warning('Tolerated %s %s %s: %r -> %r (relative %.3e)',
                    kind, key, field, previous, current, relative)

    def to_dict(self):
        return {'ok': self.ok, 'checked': dict(self.checked),
                'differences': list(self.differences), 'tolerated': list(self.tolerated)}


def _compare(report, kind, key, field, previous, current, tolerance):
    if previous == current:
        return
    if _is_number(previous) and _is_number(current):
        # A previous zero has no relative scale; any move away from it is a move.
        relative = abs(current - previous) / abs(previous) if previous else None
        if relative is not None and relative <= tolerance:
            report.tolerate(kind, key, field, previous, current, relative)
            return
        report.record(kind, key, field, previous, current, relative)
        return
    report.record(kind, key, field, previous, current)


def _shares(record):
    """Country shares of one profile, keyed by the identity the site renders."""
    shares = {}
    for entry in record.get('top') or []:
        key = (entry.get('name'), entry.get('code'))
        if key in shares:
            raise ValueError(f'Duplicate share entity in profile: {key}')
        shares[key] = entry
    return shares


def _index(records, key_fields, label):
    indexed = {}
    for record in records or []:
        key = tuple(record.get(field) for field in key_fields)
        if key in indexed:
            raise ValueError(f'Duplicate {label} key: {key}')
        indexed[key] = record
    return indexed


def _within(key, max_year):
    return max_year is None or key[-1] is None or key[-1] <= max_year


def compare(previous, current, *, max_year=None, tolerance=DEFAULT_RELATIVE_TOLERANCE):
    """Check that every published key in ``previous`` is unchanged in ``current``.

    ``max_year`` narrows the check to data years at or below a cutoff; by
    default every key the previous snapshot published is checked, which is what
    an append should leave untouched regardless of where the new years sit.
    """
    report = Report()
    if not previous:
        log.info('No previous snapshot; nothing is published yet and nothing can move')
        return report

    old = _index(previous.get('concentration'), ('hs_code', 'year'), 'concentration')
    new = _index(current.get('concentration'), ('hs_code', 'year'), 'concentration')
    for key, before in sorted(old.items(), key=lambda item: (str(item[0][0]), item[0][1])):
        if not _within(key, max_year):
            continue
        name = f'{key[0]} {key[1]}'
        report.checked['concentration'] += 1
        after = new.get(key)
        if after is None:
            report.record('concentration', name, '*', 'published', 'missing')
            continue
        for field in CONCENTRATION_FIELDS:
            _compare(report, 'concentration', name, field, before.get(field), after.get(field), tolerance)
        before_shares, after_shares = _shares(before), _shares(after)
        for entity, share in before_shares.items():
            report.checked['shares'] += 1
            label = f'{name} {entity[0]}'
            if entity not in after_shares:
                report.record('share', label, '*', 'published', 'missing')
                continue
            for field in SHARE_FIELDS:
                _compare(report, 'share', label, field, share.get(field),
                         after_shares[entity].get(field), tolerance)
        for entity in after_shares.keys() - before_shares.keys():
            report.record('share', f'{name} {entity[0]}', '*', 'absent', 'added')

    old_production = _index(previous.get('production'), ('year', 'country'), 'production')
    new_production = _index(current.get('production'), ('year', 'country'), 'production')
    for key, before in sorted(old_production.items()):
        if max_year is not None and key[0] > max_year:
            continue
        name = f'{key[0]} {key[1]}'
        report.checked['production'] += 1
        after = new_production.get(key)
        if after is None:
            report.record('production', name, '*', 'published', 'missing')
            continue
        for field in PRODUCTION_FIELDS:
            _compare(report, 'production', name, field, before.get(field), after.get(field), tolerance)
    return report


def summarise(report, limit=40):
    lines = ['checked: ' + ', '.join(f'{k}={v}' for k, v in sorted(report.checked.items()))]
    if report.tolerated:
        lines.append(f'tolerated within {DEFAULT_RELATIVE_TOLERANCE:g} relative: {len(report.tolerated)}')
        lines += [f'  ~ {e["kind"]} {e["key"]} {e["field"]}: {e["previous"]!r} -> {e["current"]!r}'
                  f' (relative {e["relative_change"]:.3e})' for e in report.tolerated[:limit]]
    if report.ok:
        lines.append('No published figure moved.')
        return '\n'.join(lines)
    lines.append(f'{len(report.differences)} published figure(s) moved:')
    for entry in report.differences[:limit]:
        change = '' if entry['relative_change'] is None else f' (relative {entry["relative_change"]:.3e})'
        lines.append(f'  ! {entry["kind"]} {entry["key"]} {entry["field"]}: '
                     f'{entry["previous"]!r} -> {entry["current"]!r}{change}')
    if len(report.differences) > limit:
        lines.append(f'  ... and {len(report.differences) - limit} more')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous', type=Path, default=Path('data/processed/lithium/snapshot.json'))
    parser.add_argument('--current', type=Path, required=True)
    parser.add_argument('--max-year', type=int, default=None,
                        help='Only check data years at or below this year')
    parser.add_argument('--json', type=Path, help='Write the full report here')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    previous = json.loads(args.previous.read_text(encoding='utf-8')) if args.previous.exists() else None
    current = json.loads(args.current.read_text(encoding='utf-8'))
    report = compare(previous, current, max_year=args.max_year)
    print(summarise(report))
    if args.json:
        args.json.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + '\n',
                             encoding='utf-8')
    return 0 if report.ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
