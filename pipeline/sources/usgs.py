"""USGS adapter: world mine production by country, for the mine-side HHI.

The USGS National Minerals Information Center publishes the Mineral Commodity
Summaries as an annual data release on ScienceBase. The exact file names and
column headings inside that release have changed between editions, so this
adapter *discovers* rather than hardcodes:

1. Search the ScienceBase catalog for the newest "Mineral Commodity Summaries
   ... Data Release" item.
2. Enumerate its attached files and pull the tabular ones (.csv, .xlsx, .zip).
3. Read every table with a tolerant reader that identifies a country column, a
   year (either a year column or wide year-per-column layout) and a production
   column by header pattern rather than by position.
4. Attribute each table to a commodity by the commodity column when one
   exists, otherwise by the file or sheet name.

When that fails for a commodity - and it will, eventually, because upstream
schemas drift - the pipeline falls back to
``critical-minerals/data/manual/world_production.csv``, a hand-maintained file
in this repository with a fixed schema. Nothing is imputed or estimated in
either path.

Run ``python -m pipeline.sources.usgs --inspect`` to print what the discovery
step actually found; that is the fastest way to repair a broken parse.
"""

from __future__ import annotations

import csv
import io
import logging
import os
import re
import zipfile
from pathlib import Path

from . import http

log = logging.getLogger(__name__)

SEARCH_URL = "https://www.sciencebase.gov/catalog/items"
ITEM_URL = "https://www.sciencebase.gov/catalog/item/{id}"

REPO_ROOT = Path(__file__).resolve().parents[2]
MANUAL_CSV = REPO_ROOT / "critical-minerals" / "data" / "manual" / "world_production.csv"

COUNTRY_HEADERS = ("country", "country or locality", "locality", "region", "nation")
PRODUCTION_HEADERS = (
    "production",
    "mine production",
    "prod",
    "quantity",
    "output",
    "value",
)
YEAR_HEADERS = ("year", "yr", "period")
COMMODITY_HEADERS = ("commodity", "mineral", "material")

WORLD_TOTAL_MARKERS = (
    "world total",
    "world total (rounded)",
    "total",
    "world",
    "grand total",
)

# Rows that are footnotes, subtotals or estimation notes rather than producers.
SKIP_ROW_MARKERS = ("other countries", "other", "e ", "estimated", "n/a", "--", "w")

YEAR_RE = re.compile(r"^(19|20)\d{2}$")
NUMERIC_RE = re.compile(r"^-?[\d,\.]+$")


# --------------------------------------------------------------------------
# discovery


def find_latest_data_release() -> dict:
    """Locate the newest MCS data release item on ScienceBase."""
    payload = http.get_json(
        SEARCH_URL,
        params={
            "q": "Mineral Commodity Summaries Data Release",
            "format": "json",
            "max": "30",
            "fields": "title,id,dates,summary",
        },
    )
    items = payload.get("items") or []
    candidates = []
    for item in items:
        title = str(item.get("title") or "")
        match = re.search(r"(20\d{2})", title)
        if "mineral commodity summaries" in title.lower() and match:
            candidates.append((int(match.group(1)), item))
    if not candidates:
        raise http.FetchError(
            "no Mineral Commodity Summaries data release found in the ScienceBase "
            "catalog; check the search endpoint or fall back to the manual CSV"
        )
    candidates.sort(key=lambda pair: -pair[0])
    year, item = candidates[0]
    log.info("using USGS data release: %s (%s)", item.get("title"), item.get("id"))
    return {"year": year, "id": item.get("id"), "title": item.get("title")}


def list_files(item_id: str) -> list[dict]:
    payload = http.get_json(
        ITEM_URL.format(id=item_id), params={"format": "json", "fields": "files,title"}
    )
    files = payload.get("files") or []
    wanted = []
    for entry in files:
        name = str(entry.get("name") or "").lower()
        if name.endswith((".csv", ".xlsx", ".xls", ".zip")):
            wanted.append(entry)
    return wanted


# --------------------------------------------------------------------------
# tolerant table reading


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _to_number(value) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    # USGS marks withheld figures W, estimates e, and not-available NA.
    text = text.replace(",", "").rstrip("e").strip()
    if not NUMERIC_RE.match(text.replace(",", "")):
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number == number else None


def _match_header(headers: list[str], candidates: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        normalised = _norm(header)
        if normalised in candidates:
            return index
    for index, header in enumerate(headers):
        normalised = _norm(header)
        if any(candidate in normalised for candidate in candidates):
            return index
    return None


def parse_table(rows: list[list], origin: str) -> list[dict]:
    """Turn one table into ``{commodity, country, year, production}`` records.

    Handles both long layout (a year column) and wide layout (one column per
    year). Returns an empty list when the table is not a production table.
    """
    if not rows:
        return []

    # Find the header row: the first row with a country-ish cell in it.
    header_index = None
    for index, row in enumerate(rows[:12]):
        cells = [_norm(cell) for cell in row]
        if _match_header(cells, COUNTRY_HEADERS) is not None:
            header_index = index
            break
    if header_index is None:
        return []

    headers = [str(cell or "").strip() for cell in rows[header_index]]
    country_col = _match_header(headers, COUNTRY_HEADERS)
    if country_col is None:
        return []
    commodity_col = _match_header(headers, COMMODITY_HEADERS)
    year_col = _match_header(headers, YEAR_HEADERS)
    year_columns = [i for i, h in enumerate(headers) if YEAR_RE.match(_norm(h))]

    records: list[dict] = []
    file_commodity = _commodity_from_name(origin)

    for row in rows[header_index + 1 :]:
        if country_col >= len(row):
            continue
        country = str(row[country_col] or "").strip()
        if not country:
            continue
        commodity = (
            str(row[commodity_col]).strip()
            if commodity_col is not None and commodity_col < len(row) and row[commodity_col]
            else file_commodity
        )
        if not commodity:
            continue

        if year_columns:
            for column in year_columns:
                if column >= len(row):
                    continue
                production = _to_number(row[column])
                if production is None:
                    continue
                records.append(
                    {
                        "commodity": commodity,
                        "country": country,
                        "year": int(_norm(headers[column])),
                        "production": production,
                        "origin": origin,
                    }
                )
        elif year_col is not None:
            year = _to_number(row[year_col] if year_col < len(row) else None)
            production_col = _match_header(headers, PRODUCTION_HEADERS)
            if year is None or production_col is None or production_col >= len(row):
                continue
            production = _to_number(row[production_col])
            if production is None:
                continue
            records.append(
                {
                    "commodity": commodity,
                    "country": country,
                    "year": int(year),
                    "production": production,
                    "origin": origin,
                }
            )

    return records


def _commodity_from_name(name: str) -> str:
    stem = Path(name).stem.replace("_", " ").replace("-", " ")
    stem = re.sub(r"\b(mcs|20\d{2}|world|production|data|release|salient)\b", " ", stem, flags=re.I)
    return re.sub(r"\s+", " ", stem).strip()


def _read_csv_bytes(raw: bytes) -> list[list]:
    text = raw.decode("utf-8-sig", errors="replace")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def _read_xlsx_bytes(raw: bytes) -> dict[str, list[list]]:
    try:
        import openpyxl
    except ImportError:  # pragma: no cover
        log.warning("openpyxl is not installed; skipping a spreadsheet")
        return {}
    book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    tables = {}
    for sheet in book.worksheets:
        tables[sheet.title] = [list(row) for row in sheet.iter_rows(values_only=True)]
    book.close()
    return tables


def harvest(item_id: str, max_files: int = 60) -> list[dict]:
    """Download and parse every tabular file attached to a data release."""
    records: list[dict] = []
    for entry in list_files(item_id)[:max_files]:
        name = str(entry.get("name"))
        url = entry.get("url") or entry.get("downloadUri")
        if not url:
            continue
        try:
            raw = http.get(url, binary=True, timeout=180)
        except http.FetchError as exc:
            log.warning("could not download %s: %s", name, exc)
            continue

        lower = name.lower()
        try:
            if lower.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    for member in archive.namelist():
                        member_lower = member.lower()
                        if member_lower.endswith(".csv"):
                            records += parse_table(
                                _read_csv_bytes(archive.read(member)), member
                            )
                        elif member_lower.endswith((".xlsx", ".xls")):
                            for sheet, rows in _read_xlsx_bytes(
                                archive.read(member)
                            ).items():
                                records += parse_table(rows, f"{member}#{sheet}")
            elif lower.endswith(".csv"):
                records += parse_table(_read_csv_bytes(raw), name)
            elif lower.endswith((".xlsx", ".xls")):
                for sheet, rows in _read_xlsx_bytes(raw).items():
                    records += parse_table(rows, f"{name}#{sheet}")
        except (zipfile.BadZipFile, ValueError) as exc:
            log.warning("could not read %s: %s", name, exc)

    log.info("USGS harvest produced %d records", len(records))
    return records


# --------------------------------------------------------------------------
# manual fallback


def read_manual() -> list[dict]:
    """Read the hand-maintained production table, if it has any rows."""
    if not MANUAL_CSV.exists():
        return []
    records = []
    with MANUAL_CSV.open(newline="", encoding="utf-8-sig") as handle:
        lines = [line for line in handle if not line.lstrip().startswith("#")]
    for row in csv.DictReader(lines):
        production = _to_number(row.get("production"))
        year = _to_number(row.get("year"))
        country = (row.get("country") or "").strip()
        commodity = (row.get("commodity") or "").strip()
        if production is None or year is None or not country or not commodity:
            continue
        records.append(
            {
                "commodity": commodity,
                "country": country,
                "year": int(year),
                "production": production,
                "origin": "manual/world_production.csv",
            }
        )
    if records:
        log.info("manual CSV supplied %d records", len(records))
    return records


# --------------------------------------------------------------------------
# selection


def _is_world_total(country: str) -> bool:
    return _norm(country) in WORLD_TOTAL_MARKERS


def _is_skippable(country: str) -> bool:
    normalised = _norm(country)
    return normalised in SKIP_ROW_MARKERS or normalised.startswith("other countries")


def production_for(
    records: list[dict], aliases: list[str], years: list[int]
) -> tuple[dict[int, dict[str, float]], dict[int, float], list[str]]:
    """Filter harvested records down to one commodity.

    Returns ``(by_year, world_totals, notes)``. World-total rows are separated
    out so the caller can report coverage instead of treating the residual as
    an unnamed supplier.
    """
    wanted = {_norm(alias) for alias in aliases}
    by_year: dict[int, dict[str, float]] = {}
    world: dict[int, float] = {}
    notes: list[str] = []
    matched = 0

    for record in records:
        commodity = _norm(record["commodity"])
        if not any(
            commodity == alias or alias in commodity or commodity in alias
            for alias in wanted
        ):
            continue
        year = record["year"]
        if years and year not in years:
            continue
        matched += 1
        country = record["country"].strip()
        if _is_world_total(country):
            world[year] = max(world.get(year, 0.0), record["production"])
            continue
        if _is_skippable(country):
            continue
        bucket = by_year.setdefault(year, {})
        bucket[country] = bucket.get(country, 0.0) + record["production"]

    if matched == 0:
        notes.append(
            "no USGS rows matched this commodity; the mine-side index is "
            "unavailable until the parser or the manual CSV is updated"
        )
    return by_year, world, notes


def collect(aliases: list[str], years: list[int]) -> tuple[dict, dict, list[str]]:
    """Full path: discover, harvest, fall back to the manual CSV, then filter."""
    records: list[dict] = []
    notes: list[str] = []
    try:
        release = find_latest_data_release()
        records = harvest(release["id"])
        notes.append(f"USGS source: {release['title']}")
    except http.FetchError as exc:
        notes.append(f"USGS discovery failed: {exc}")
        log.warning("USGS discovery failed: %s", exc)

    by_year, world, filter_notes = production_for(records, aliases, years)
    if not by_year:
        manual = read_manual()
        if manual:
            by_year, world, filter_notes = production_for(manual, aliases, years)
            if by_year:
                notes.append("mine-side figures came from the manual CSV in this repository")
    return by_year, world, notes + filter_notes


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import collections
    import json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true", help="print what discovery found")
    args = parser.parse_args()

    release = find_latest_data_release()
    print(json.dumps(release, indent=2))
    files = list_files(release["id"])
    print(f"\n{len(files)} tabular files attached:")
    for entry in files[:40]:
        print(f"  {entry.get('name')}  ({entry.get('size')} bytes)")

    if args.inspect:
        records = harvest(release["id"])
        counts = collections.Counter(_norm(r["commodity"]) for r in records)
        print(f"\n{len(records)} records across {len(counts)} commodities:")
        for name, count in counts.most_common(60):
            print(f"  {count:>7}  {name}")
