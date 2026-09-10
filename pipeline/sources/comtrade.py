"""UN Comtrade adapter: annual exports by reporter, for the export-side HHI.

Two endpoints exist and this adapter uses whichever it is entitled to:

* ``/public/v1/preview/C/A/HS`` is free and needs no key. It caps a response
  at 500 rows, which comfortably covers one commodity code, one year, all
  reporters, exports to world.
* ``/data/v1/get/C/A/HS`` needs a subscription key (free tier available from
  comtradedeveloper.un.org) and lifts that cap. Set ``COMTRADE_API_KEY`` in
  the environment, or as a GitHub Actions secret, and this adapter switches
  to it automatically.

What is fetched, per commodity code and year: flow ``X`` (exports), partner
``0`` (World). The reporter is the supplying country, and its ``primaryValue``
(FOB value in current USD) is the quantity the index is computed over.

Value rather than weight is deliberate: net weight is missing for a large and
non-random share of Comtrade rows, and dropping those reporters would bias the
index far more than the value/weight distinction does. ``netWgt`` is carried
through in the output so the choice can be revisited.
"""

from __future__ import annotations

import logging
import os

from . import http

log = logging.getLogger(__name__)

PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/A/HS"
FULL_URL = "https://comtradeapi.un.org/data/v1/get/C/A/HS"

# Reporter entries that are aggregates, unallocated residuals or otherwise not
# a supplying country. Including them would both double-count and invent
# suppliers. Codes are Comtrade M49-based reporter codes.
NON_COUNTRY_REPORTERS = {
    0,  # World
    97,  # EU (as a reporting bloc)
    899,  # Areas, nes
    837,  # Bunkers
    838,  # Free zones
    839,  # Special categories
    849,  # US Misc. Pacific Isds
    879,  # Western Asia, nes
    568,  # Other Europe, nes
    636,  # Rest of America, nes
    527,  # Oceania, nes
    577,  # Other Africa, nes
    473,  # LAIA, nes
    490,  # Other Asia, nes
    492,  # Europe EFTA, nes
    536,  # Neutral Zone
    637,  # North America and Central America, nes
    290,  # Northern Africa, nes
    471,  # CACM, nes
    121,  # Caribbean, nes
}

NON_COUNTRY_NAME_MARKERS = (
    ", nes",
    "nes)",
    "areas, nes",
    "special categories",
    "free zones",
    "bunkers",
    "world",
    "neutral zone",
)


def _api_key() -> str | None:
    key = os.environ.get("COMTRADE_API_KEY", "").strip()
    return key or None


def _is_country(row: dict) -> bool:
    try:
        code = int(row.get("reporterCode"))
    except (TypeError, ValueError):
        return False
    if code in NON_COUNTRY_REPORTERS:
        return False
    name = str(row.get("reporterDesc") or "").strip().lower()
    if not name:
        return False
    return not any(marker in name for marker in NON_COUNTRY_NAME_MARKERS)


def fetch_year(cmd_code: str, year: int) -> list[dict]:
    """Raw export rows for one HS code and one year, all reporters."""
    key = _api_key()
    params = {
        "reporterCode": "",  # empty means every reporter
        "period": str(year),
        "partnerCode": "0",  # World
        "partner2Code": "0",
        "cmdCode": cmd_code,
        "flowCode": "X",  # exports
        "customsCode": "C00",
        "motCode": "0",
        "includeDesc": "true",
    }
    headers = {}
    if key:
        url = FULL_URL
        headers["Ocp-Apim-Subscription-Key"] = key
    else:
        url = PREVIEW_URL

    payload = http.get_json(url, params=params, headers=headers)

    rows = payload.get("data")
    if rows is None:
        # The API reports problems in-band with a 200 status.
        message = payload.get("errorMessage") or payload.get("message") or payload
        raise http.FetchError(f"Comtrade returned no data array for {cmd_code} {year}: {str(message)[:300]}")

    if not key and len(rows) >= 500:
        log.warning(
            "%s %d hit the 500-row preview cap; set COMTRADE_API_KEY for the "
            "uncapped endpoint. The index for this year may be truncated.",
            cmd_code,
            year,
        )
    return rows


def exports_by_country(
    cmd_codes: list[str], years: list[int]
) -> tuple[dict[int, dict[str, float]], dict[str, str], list[str]]:
    """Aggregate export value by reporter, summed across the given HS codes.

    Returns ``(by_year, iso_codes, notes)``. ``by_year`` maps year to
    ``{country: value_usd}``; ``iso_codes`` maps country name to ISO-3.
    """
    by_year: dict[int, dict[str, float]] = {}
    iso: dict[str, str] = {}
    notes: list[str] = []

    for year in years:
        totals: dict[str, float] = {}
        codes_with_data = 0
        for code in cmd_codes:
            try:
                rows = fetch_year(code, year)
            except http.FetchError as exc:
                notes.append(f"{code} {year}: {exc}")
                log.warning("comtrade %s %d unavailable: %s", code, year, exc)
                continue
            if rows:
                codes_with_data += 1
            for row in rows:
                if not _is_country(row):
                    continue
                name = str(row.get("reporterDesc")).strip()
                try:
                    value = float(row.get("primaryValue") or 0.0)
                except (TypeError, ValueError):
                    continue
                if value <= 0:
                    continue
                totals[name] = totals.get(name, 0.0) + value
                code3 = row.get("reporterISO")
                if code3 and name not in iso:
                    iso[name] = str(code3)
        if totals:
            by_year[year] = totals
            if codes_with_data < len(cmd_codes):
                notes.append(
                    f"{year}: {codes_with_data} of {len(cmd_codes)} commodity codes "
                    "returned data; the export index for this year is partial."
                )

    return by_year, iso, notes
