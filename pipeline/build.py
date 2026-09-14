"""Build the data layer: fetch, compute, write JSON, then render the pages.

    python -m pipeline.build                 # everything
    python -m pipeline.build --only lithium  # one mineral
    python -m pipeline.build --render-only   # re-render pages from existing JSON
    python -m pipeline.build --fixtures      # synthetic data, for layout work

Nothing here writes a number it did not receive from a source. When a source
is unavailable the corresponding section of the output is marked unavailable
and the site renders an empty state, which is the whole reason the site can
ship before the first successful run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path

from . import hhi
from .sources import comtrade, usgs

log = logging.getLogger("orelysis")

REPO_ROOT = Path(__file__).resolve().parents[1]
SECTION_DIR = REPO_ROOT / "critical-minerals"
DATA_DIR = SECTION_DIR / "data"
CATALOG_PATH = DATA_DIR / "catalog.json"

# Comtrade reporting lags roughly a year; USGS mine data lags one to two. The
# window is generous at the back end and the pipeline simply drops years that
# come back empty.
TRADE_YEARS_BACK = 12
PRODUCTION_YEARS_BACK = 12


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def target_years(back: int) -> list[int]:
    this_year = dt.date.today().year
    return list(range(this_year - back, this_year + 1))


def build_mineral(mineral: dict, conventions: dict, *, fixtures: bool = False) -> dict:
    slug = mineral["slug"]
    log.info("building %s", slug)
    top_n = conventions.get("top_n_displayed", 10)

    if fixtures:
        from .fixtures import synthetic

        production_by_year, world_totals, production_notes = synthetic(slug, "production")
        trade_by_year, iso, trade_notes = synthetic(slug, "trade")
    else:
        production_by_year, world_totals, production_notes = usgs.collect(
            mineral.get("usgs_aliases") or [mineral["usgs_commodity"]],
            target_years(PRODUCTION_YEARS_BACK),
        )
        trade_by_year, iso, trade_notes = comtrade.exports_by_country(
            mineral["hs_codes"], target_years(TRADE_YEARS_BACK)
        )

    production_series = hhi.series(production_by_year, universe_totals=world_totals)
    trade_series = hhi.series(trade_by_year, codes=iso if not fixtures else None)

    unit_ja_lookup = {
        "share of reported mine production": "報告された鉱山生産量に占める割合",
        "share of reported export value (USD, FOB)": (
            "報告された輸出額(USドル、FOB)に占める割合"
        ),
    }

    def pack(results, notes, unit, source, stage):
        unit_ja = unit_ja_lookup.get(unit, unit)
        if not results:
            return {
                "available": False,
                "notes": notes,
                "unit": unit,
                "unit_ja": unit_ja,
                "source": source,
                "stage": stage,
            }
        return {
            "available": True,
            "unit": unit,
            "unit_ja": unit_ja,
            "source": source,
            "stage": stage,
            "latest_year": results[-1].year,
            "latest": results[-1].to_dict(top_n=top_n),
            "series": [
                {
                    "year": r.year,
                    "hhi": round(r.hhi, 1),
                    "cr3": round(r.cr3, 2),
                    "reporters": r.reporters,
                    "coverage": None if r.coverage is None else round(r.coverage, 4),
                }
                for r in results
            ],
            "trend": hhi.trend(results),
            "notes": notes,
        }

    return {
        "slug": slug,
        "name": mineral["name"],
        "name_ja": mineral.get("name_ja"),
        "symbol": mineral.get("symbol"),
        "role": mineral.get("role"),
        "role_ja": mineral.get("role_ja"),
        "summary": mineral.get("summary"),
        "summary_ja": mineral.get("summary_ja"),
        "caveats": mineral.get("caveats", []),
        "caveats_ja": mineral.get("caveats_ja", []),
        "hs_codes": mineral["hs_codes"],
        "hs_label": mineral.get("hs_label"),
        "hs_label_ja": mineral.get("hs_label_ja"),
        "usgs_commodity": mineral["usgs_commodity"],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "production": pack(
            production_series,
            production_notes,
            "share of reported mine production",
            "USGS Mineral Commodity Summaries",
            "mine",
        ),
        "trade": pack(
            trade_series,
            trade_notes,
            "share of reported export value (USD, FOB)",
            "UN Comtrade",
            mineral.get("trade_stage", "export"),
        ),
    }


def summarise(mineral_data: dict) -> dict:
    """The compact record the section index page renders a card from."""
    def head(block):
        if not block.get("available"):
            return None
        latest = block["latest"]
        leader = latest["top"][0] if latest["top"] else None
        return {
            "year": latest["year"],
            "hhi": latest["hhi"],
            "band": latest["band"],
            "cr3": latest["cr3"],
            "leader": leader["name"] if leader else None,
            "leader_share": leader["share"] if leader else None,
            "sparkline": [point["hhi"] for point in block["series"]],
            "years": [point["year"] for point in block["series"]],
            "trend": block.get("trend"),
        }

    return {
        "slug": mineral_data["slug"],
        "name": mineral_data["name"],
        "symbol": mineral_data.get("symbol"),
        "role": mineral_data.get("role"),
        "production": head(mineral_data["production"]),
        "trade": head(mineral_data["trade"]),
    }


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    log.info("wrote %s", path.relative_to(REPO_ROOT))


def run(only: list[str] | None = None, *, fixtures: bool = False) -> dict:
    catalog = load_catalog()
    conventions = catalog["conventions"]
    minerals = catalog["minerals"]
    if only:
        wanted = set(only)
        minerals = [m for m in minerals if m["slug"] in wanted]
        if not minerals:
            raise SystemExit(f"no mineral in the catalog matches {only}")

    # Configured minerals use the strict transaction, even through the old entry point.
    if not fixtures:
        strict_config = json.loads((REPO_ROOT / 'pipeline/minerals.json').read_text(encoding='utf-8'))
        strict_slugs = set(strict_config['minerals'])
        for mineral in minerals:
            if mineral['slug'] in strict_slugs:
                from .update_minerals import run as strict_run
                strict_run(REPO_ROOT, mineral['slug'])
        minerals = [m for m in minerals if m['slug'] not in strict_slugs]
        if not minerals:
            return json.loads((DATA_DIR / 'index.json').read_text(encoding='utf-8'))

    summaries = []
    failures = []
    for mineral in minerals:
        try:
            data = build_mineral(mineral, conventions, fixtures=fixtures)
        except Exception as exc:  # a single bad mineral must not sink the run
            log.exception("%s failed", mineral["slug"])
            failures.append({"slug": mineral["slug"], "error": str(exc)})
            continue
        write_json(DATA_DIR / "minerals" / f"{mineral['slug']}.json", data)
        summaries.append(summarise(data))

    index_path = DATA_DIR / "index.json"
    existing = (
        json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    )
    by_slug = {item["slug"]: item for item in existing.get("minerals", [])}
    for summary in summaries:
        by_slug[summary["slug"]] = summary
    ordered = [by_slug[m["slug"]] for m in catalog["minerals"] if m["slug"] in by_slug]

    index = {
        "section": catalog["section"],
        "conventions": conventions,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "fixtures": fixtures,
        "sources": [
            {
                "name": "USGS Mineral Commodity Summaries",
                "url": "https://www.usgs.gov/centers/national-minerals-information-center/mineral-commodity-summaries",
                "used_for": "world mine production by country",
            },
            {
                "name": "UN Comtrade",
                "url": "https://comtradeplus.un.org/",
                "used_for": "annual export value by reporting country",
            },
        ],
        "failures": failures,
        "minerals": ordered,
    }
    write_json(index_path, index)
    return index


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="build only these mineral slugs")
    parser.add_argument("--render-only", action="store_true", help="skip fetching")
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="synthetic data for layout work; never commit the result",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(name)s  %(message)s",
    )

    if not args.render_only:
        index = run(args.only, fixtures=args.fixtures)
        if index["failures"]:
            log.error("%d mineral(s) failed", len(index["failures"]))

    from . import render

    render.render_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
