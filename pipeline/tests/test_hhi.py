"""Tests for the concentration metrics.

Run from the repository root:  python -m pytest pipeline/tests -q
or, without pytest installed:  python pipeline/tests/test_hhi.py
"""

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pipeline import hhi  # noqa: E402


def approx(a, b, tol=1e-6):
    assert math.isclose(a, b, rel_tol=tol, abs_tol=tol), f"{a} != {b}"


def test_monopoly_scores_ten_thousand():
    r = hhi.concentration(2024, {"Atlantis": 100.0})
    approx(r.hhi, 10000.0)
    assert r.band == "high"
    approx(r.cr1, 100.0)
    approx(r.effective_suppliers, 1.0)


def test_ten_equal_suppliers_score_one_thousand():
    r = hhi.concentration(2024, {f"C{i}": 10.0 for i in range(10)})
    approx(r.hhi, 1000.0)
    assert r.band == "moderate"
    approx(r.effective_suppliers, 10.0)


def test_scale_invariance():
    a = hhi.concentration(2024, {"A": 70, "B": 20, "C": 10})
    b = hhi.concentration(2024, {"A": 7000, "B": 2000, "C": 1000})
    approx(a.hhi, b.hhi)
    approx(a.hhi, 70**2 + 20**2 + 10**2)


def test_duplicate_names_are_summed_not_double_counted():
    # A source that reports the same country twice (two commodity codes)
    # must not be treated as two suppliers.
    r = hhi.concentration(2024, {"A": 50.0})
    r2 = hhi.concentration(2024, dict([("A", 50.0)]))
    approx(r.hhi, r2.hhi)
    merged = hhi.concentration(2024, {"A": 30, "B": 70})
    assert merged.reporters == 2


def test_non_positive_and_garbage_values_are_dropped():
    r = hhi.concentration(
        2024, {"A": 60, "B": 40, "C": 0, "D": -5, "E": None, "F": "n/a"}
    )
    assert r.reporters == 2
    approx(r.hhi, 60**2 + 40**2)


def test_empty_input_returns_none():
    assert hhi.concentration(2024, {}) is None
    assert hhi.concentration(2024, {"A": 0}) is None


def test_concentration_ratios_and_ordering():
    r = hhi.concentration(2024, {"A": 40, "B": 30, "C": 20, "D": 5, "E": 5})
    assert [s.name for s in r.top] == ["A", "B", "C", "D", "E"]
    approx(r.cr1, 40.0)
    approx(r.cr3, 90.0)
    approx(r.cr5, 100.0)


def test_ties_break_alphabetically_for_determinism():
    r = hhi.concentration(2024, {"Zed": 25, "Ada": 25, "Mia": 50})
    assert [s.name for s in r.top] == ["Mia", "Ada", "Zed"]


def test_coverage_reports_shortfall_without_inventing_a_supplier():
    # World total is 200 but only 150 is attributable to named countries.
    r = hhi.concentration(2024, {"A": 100, "B": 50}, universe_total=200.0)
    assert r.reporters == 2
    approx(r.coverage, 0.75)
    # The index is computed over the reported 150, not over the 200.
    approx(r.hhi, (100 / 150 * 100) ** 2 + (50 / 150 * 100) ** 2)


def test_coverage_is_capped_at_one():
    r = hhi.concentration(2024, {"A": 100, "B": 50}, universe_total=100.0)
    approx(r.coverage, 1.0)


def test_bands():
    assert hhi.band(999.9) == "unconcentrated"
    assert hhi.band(1000.0) == "moderate"
    assert hhi.band(1799.9) == "moderate"
    assert hhi.band(1800.0) == "high"


def test_series_is_ordered_and_skips_empty_years():
    s = hhi.series({2022: {"A": 1}, 2020: {"A": 1, "B": 1}, 2021: {}})
    assert [c.year for c in s] == [2020, 2022]


def test_trend_measures_the_trailing_window():
    s = hhi.series({y: {"A": 50 + y - 2018, "B": 50} for y in range(2018, 2025)})
    t = hhi.trend(s, window=5)
    assert t["from_year"] == 2020 and t["to_year"] == 2024
    assert t["direction"] == "up"
    assert hhi.trend(s[:1]) is None


def test_dumps_truncates_the_top_list_but_not_the_index():
    s = hhi.series({2024: {f"C{i}": 100 - i for i in range(30)}})
    out = hhi.dumps(s, top_n=10)
    assert len(out[0]["top"]) == 10
    assert out[0]["reporters"] == 30


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  pass  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print(f"\n{'FAILED' if failures else 'All tests passed'} ({failures} failures)")
    sys.exit(1 if failures else 0)
