"""Deterministic synthetic data, for working on layout without a network.

Never commit the JSON a fixtures run produces. `python -m pipeline.build
--fixtures` writes files that look real and are not; `git checkout
critical-minerals/data` puts the repository back. The pages rendered from
fixture data carry a visible banner (index.json sets `"fixtures": true`) so a
fixture build cannot be mistaken for a real one even if it is deployed by
accident.
"""

from __future__ import annotations

import hashlib
import random

COUNTRIES = [
    ("Australia", "AUS"), ("Chile", "CHL"), ("China", "CHN"),
    ("Argentina", "ARG"), ("Brazil", "BRA"), ("Canada", "CAN"),
    ("Indonesia", "IDN"), ("Peru", "PER"), ("South Africa", "ZAF"),
    ("Zimbabwe", "ZWE"), ("Philippines", "PHL"), ("Russia", "RUS"),
    ("United States", "USA"), ("Mozambique", "MOZ"), ("Gabon", "GAB"),
    ("Madagascar", "MDG"), ("Turkey", "TUR"), ("India", "IND"),
]

YEARS = list(range(2013, 2025))


def _seed(slug: str, kind: str) -> random.Random:
    digest = hashlib.sha256(f"{slug}:{kind}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


def synthetic(slug: str, kind: str):
    """Mirror the return signature of the real source adapters."""
    rng = _seed(slug, kind)
    # A Zipf-ish share profile whose steepness varies by mineral, so the eight
    # cards span the whole HHI range the layout has to cope with.
    steepness = 0.7 + rng.random() * 1.9
    size = rng.randint(7, 14)
    pool = COUNTRIES[:]
    rng.shuffle(pool)
    pool = pool[:size]

    by_year: dict[int, dict[str, float]] = {}
    for index, year in enumerate(YEARS):
        drift = 1.0 + (index - len(YEARS) / 2) * rng.uniform(-0.04, 0.06)
        values = {}
        for rank, (name, _) in enumerate(pool, start=1):
            base = 1000.0 / (rank ** (steepness * max(drift, 0.4)))
            values[name] = round(base * rng.uniform(0.9, 1.1), 2)
        by_year[year] = values

    if kind == "production":
        # A world total slightly above the sum, to exercise coverage display.
        totals = {
            year: sum(values.values()) * rng.uniform(1.02, 1.18)
            for year, values in by_year.items()
        }
        return by_year, totals, ["SYNTHETIC FIXTURE DATA - not a real measurement"]

    iso = {name: code for name, code in pool}
    return by_year, iso, ["SYNTHETIC FIXTURE DATA - not a real measurement"]
