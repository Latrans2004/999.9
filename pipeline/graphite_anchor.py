"""Diagnose whether USGS mine production can adjudicate a disputed export figure.

Selects nothing. Production is contextual evidence, so this module only narrows
the review queue and names the side each case would favour if, and only if,
specific external evidence is later obtained for it.
"""
from __future__ import annotations

from collections import defaultdict

# A reported export near domestic mine output is consistent with an export
# oriented producer. Inventory draw, timing and re-export push the ratio above
# one, so the band is asymmetric rather than centred on parity.
CONSISTENT_LOW = 0.5
CONSISTENT_HIGH = 1.5

# Below the 25% screen the two trade observations agree and there is nothing to
# adjudicate; graphite.compare already handles that case.
DISPUTE_THRESHOLD = 0.25


def production_consistent(trade_t, production_t):
    if trade_t is None or not production_t:
        return None
    return CONSISTENT_LOW <= trade_t / production_t <= CONSISTENT_HIGH


def classify(reported_t, mirror_t, production_t):
    """Name the review class of one country/year, never a selected weight."""
    if not production_t:
        return 'no_mine_production', None
    if reported_t is None or mirror_t is None:
        return 'incomplete_trade_observation', None
    if max(reported_t, mirror_t) == 0:
        return 'incomplete_trade_observation', None
    if abs(reported_t - mirror_t) / max(reported_t, mirror_t) <= DISPUTE_THRESHOLD:
        return 'no_dispute', None
    own = production_consistent(reported_t, production_t)
    other = production_consistent(mirror_t, production_t)
    if own and not other:
        return 'production_adjudicable', 'reported'
    if other and not own:
        return 'production_adjudicable', 'mirror'
    if not own and not other:
        # Both sides sit outside the band: a re-export hub when both exceed it,
        # a domestic consumption producer when both fall short.
        if min(reported_t, mirror_t) / production_t > CONSISTENT_HIGH:
            return 'reexport_hub', None
        if max(reported_t, mirror_t) / production_t < CONSISTENT_LOW:
            return 'domestic_consumption_producer', None
        return 'production_cannot_adjudicate', None
    return 'production_cannot_adjudicate', None


def audit(decisions, production):
    """Classify every disputed exporter/year against its own mine output."""
    mine = {(r['country'], r['year']): r['production_t'] for r in production
            if r['kind'] == 'country' and r['production_t'] is not None}
    reported, mirrored = defaultdict(lambda: None), defaultdict(lambda: None)
    for row in decisions:
        key = (row['country'], row['year'])
        for store, field in ((reported, 'reported_weight_t'), (mirrored, 'mirror_observed_weight_t')):
            if row[field] is not None:
                store[key] = (store[key] or 0) + row[field]
    results = []
    for key in sorted(set(reported) | set(mirrored) | set(mine)):
        country, year = key
        own, other, produced = reported[key], mirrored[key], mine.get(key)
        review_class, favours = classify(own, other, produced)
        results.append({
            'country': country, 'year': year,
            'mine_production_t': produced,
            'reported_weight_t': own, 'mirror_observed_weight_t': other,
            'review_class': review_class,
            'favours': favours,
            'selected_weight_t': None,
            'note': 'Diagnostic only. Mine output is contextual evidence, never an '
                    'export measurement; adoption still requires HS-specific external '
                    'evidence recorded in graphite_reviews.json.',
        })
    return results


def summarise(results):
    counts = defaultdict(int)
    for row in results:
        counts[row['review_class']] += 1
    return dict(sorted(counts.items()))
