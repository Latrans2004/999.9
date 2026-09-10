"""Concentration metrics.

The one piece of this pipeline that must be exactly right, kept free of any
knowledge of where the numbers came from. Everything here operates on a plain
mapping of ``{producer: quantity}`` and returns plain data.

Convention: HHI is reported on the 0-10,000 scale used by the US DOJ/FTC
merger guidelines, i.e. the sum of squared percentage shares. A monopoly
scores 10,000; ten equal suppliers score 1,000.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Iterable, Mapping, Sequence

# US DOJ/FTC 2023 Merger Guidelines bands, applied here to supplier countries
# rather than to firms. See methodology.html for why that substitution is a
# loose analogy rather than an equivalence.
UNCONCENTRATED_MAX = 1000.0
MODERATE_MAX = 1800.0


def band(hhi: float) -> str:
    if hhi < UNCONCENTRATED_MAX:
        return "unconcentrated"
    if hhi < MODERATE_MAX:
        return "moderate"
    return "high"


BAND_LABELS = {
    "unconcentrated": "Unconcentrated",
    "moderate": "Moderately concentrated",
    "high": "Highly concentrated",
}


@dataclass
class Share:
    name: str
    code: str | None
    quantity: float
    share: float  # percent, 0-100

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "code": self.code,
            "quantity": round(self.quantity, 4),
            "share": round(self.share, 4),
        }


@dataclass
class Concentration:
    """The full result of one HHI computation for one year."""

    year: int
    hhi: float
    band: str
    cr1: float
    cr3: float
    cr5: float
    effective_suppliers: float
    total: float
    reporters: int
    coverage: float | None  # 0-1, or None when the universe size is unknown
    top: list[Share] = field(default_factory=list)

    def to_dict(self, top_n: int | None = None) -> dict:
        top = self.top if top_n is None else self.top[:top_n]
        return {
            "year": self.year,
            "hhi": round(self.hhi, 1),
            "band": self.band,
            "cr1": round(self.cr1, 2),
            "cr3": round(self.cr3, 2),
            "cr5": round(self.cr5, 2),
            "effective_suppliers": round(self.effective_suppliers, 2),
            "total": round(self.total, 4),
            "reporters": self.reporters,
            "coverage": None if self.coverage is None else round(self.coverage, 4),
            "top": [s.to_dict() for s in top],
        }


def _clean(quantities: Mapping[str, float]) -> dict[str, float]:
    """Drop non-positive and non-finite entries.

    Zero and negative values are dropped rather than clamped: a negative
    quantity in a trade dataset means a revision or a re-export adjustment,
    not a supplier, and squaring it would inflate the index.
    """
    out: dict[str, float] = {}
    for name, qty in quantities.items():
        try:
            value = float(qty)
        except (TypeError, ValueError):
            continue
        if value != value or value in (float("inf"), float("-inf")):
            continue
        if value <= 0:
            continue
        out[name] = out.get(name, 0.0) + value
    return out


def concentration(
    year: int,
    quantities: Mapping[str, float],
    *,
    codes: Mapping[str, str] | None = None,
    universe_total: float | None = None,
) -> Concentration | None:
    """Compute the concentration profile of one year of supply.

    ``quantities`` maps a producer name to a quantity in any single unit;
    only the ratios matter. ``universe_total`` is the known world total when
    the caller has one that exceeds the sum of the reported entries (USGS, for
    instance, publishes a world total alongside country figures it withholds).
    When supplied, the residual is *not* treated as a supplier: it is reported
    as a coverage shortfall so a reader can see how much of the picture is
    missing, and the index is computed over the reported portion only.
    """
    cleaned = _clean(quantities)
    if not cleaned:
        return None

    reported_total = sum(cleaned.values())
    ordered = sorted(cleaned.items(), key=lambda kv: (-kv[1], kv[0]))

    shares: list[Share] = []
    for name, qty in ordered:
        shares.append(
            Share(
                name=name,
                code=(codes or {}).get(name),
                quantity=qty,
                share=qty / reported_total * 100.0,
            )
        )

    hhi = sum(s.share**2 for s in shares)

    def cr(n: int) -> float:
        return sum(s.share for s in shares[:n])

    coverage: float | None = None
    if universe_total and universe_total > 0:
        coverage = min(1.0, reported_total / universe_total)

    return Concentration(
        year=year,
        hhi=hhi,
        band=band(hhi),
        cr1=cr(1),
        cr3=cr(3),
        cr5=cr(5),
        effective_suppliers=(10000.0 / hhi) if hhi > 0 else 0.0,
        total=reported_total,
        reporters=len(shares),
        coverage=coverage,
        top=shares,
    )


def series(
    by_year: Mapping[int, Mapping[str, float]],
    *,
    codes: Mapping[str, str] | None = None,
    universe_totals: Mapping[int, float] | None = None,
) -> list[Concentration]:
    """Compute one Concentration per year, oldest first."""
    results = []
    for year in sorted(by_year):
        result = concentration(
            year,
            by_year[year],
            codes=codes,
            universe_total=(universe_totals or {}).get(year),
        )
        if result is not None:
            results.append(result)
    return results


def trend(results: Sequence[Concentration], window: int = 5) -> dict | None:
    """Change in HHI over the trailing ``window`` years of the series."""
    if len(results) < 2:
        return None
    latest = results[-1]
    earliest = results[max(0, len(results) - window)]
    if earliest.year == latest.year:
        return None
    change = latest.hhi - earliest.hhi
    return {
        "from_year": earliest.year,
        "to_year": latest.year,
        "from_hhi": round(earliest.hhi, 1),
        "to_hhi": round(latest.hhi, 1),
        "change": round(change, 1),
        "direction": "up" if change > 0 else ("down" if change < 0 else "flat"),
    }


def dumps(results: Iterable[Concentration], top_n: int | None = None) -> list[dict]:
    return [r.to_dict(top_n=top_n) for r in results]


__all__ = [
    "Concentration",
    "Share",
    "band",
    "BAND_LABELS",
    "concentration",
    "series",
    "trend",
    "dumps",
    "asdict",
]
