"""Render the static pages from the JSON in critical-minerals/data/.

Network-free and fast: run it on its own whenever a template or a copy change
needs to reach the site, without refetching anything.

    python -m pipeline.render

Pages are generated for every mineral in the catalog whether or not data
exists for it, so the URLs are stable from the first commit and a missing
dataset shows as an empty state rather than a 404.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import i18n
from .hhi import BAND_LABELS

log = logging.getLogger("999.9.render")

REPO_ROOT = Path(__file__).resolve().parents[1]
SECTION_DIR = REPO_ROOT / "critical-minerals"
DATA_DIR = SECTION_DIR / "data"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
CONFIG_PATH = REPO_ROOT / "site.json"

DEFAULT_CONFIG = {
    "repo_url": "https://github.com/OWNER/999.9",
    "site_base": "/",
}

# Mirrors pipeline/build.py's unit_ja_lookup, for the "no data yet" shape
# that render.py builds directly (build.py's pack() never runs for a
# mineral the pipeline has not fetched yet).
PLACEHOLDER_UNIT_JA = {
    "share of mine production": "鉱山生産量に占める割合",
    "share of export value": "輸出額に占める割合",
}


def config() -> dict:
    merged = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        merged.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    return merged


def safe_json(payload) -> str:
    """JSON for embedding in a <script type="application/json"> block.

    HTML entities are not decoded inside a script element, so the payload must
    not be HTML-escaped by the template engine - it is marked safe instead, and
    the three characters that could close the element early are escaped as
    JSON unicode sequences, which JSON.parse handles natively.
    """
    text = json.dumps(payload, ensure_ascii=False)
    return (
        text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )


def trend_phrase(trend: dict | None) -> str:
    if not trend:
        return ""
    change = trend["change"]
    span = trend["to_year"] - trend["from_year"]
    if abs(change) < 25:
        return f"Broadly flat since {trend['from_year']}"
    direction = "up" if change > 0 else "down"
    return f"{direction.capitalize()} {abs(change):,.0f} over {span} years"


def human_time(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        stamp = dt.datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return stamp.strftime("%d %B %Y, %H:%M UTC")


def environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals["band_labels"] = BAND_LABELS
    env.globals["trend_phrase"] = trend_phrase
    env.globals["trend_phrase_ja"] = i18n.trend_phrase_ja
    env.globals["coverage_notice_ja"] = i18n.coverage_notice_ja
    env.globals["no_data_notice_ja"] = i18n.no_data_notice_ja
    return env


def load_index() -> dict:
    path = DATA_DIR / "index.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def load_catalog() -> dict:
    return json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))


def load_mineral(slug: str) -> dict | None:
    path = DATA_DIR / "minerals" / f"{slug}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def empty_block(source: str, stage: str, unit: str) -> dict:
    return {
        "available": False,
        "notes": [],
        "source": source,
        "stage": stage,
        "unit": unit,
        "unit_ja": PLACEHOLDER_UNIT_JA.get(unit, unit),
        "series": [],
    }


def placeholder_mineral(entry: dict) -> dict:
    """A mineral record for a catalog entry the pipeline has not built yet."""
    return {
        "slug": entry["slug"],
        "name": entry["name"],
        "name_ja": entry.get("name_ja"),
        "symbol": entry.get("symbol"),
        "role": entry.get("role"),
        "role_ja": entry.get("role_ja"),
        "summary": entry.get("summary"),
        "summary_ja": entry.get("summary_ja"),
        "caveats": entry.get("caveats", []),
        "caveats_ja": entry.get("caveats_ja", []),
        "hs_codes": entry.get("hs_codes", []),
        "hs_label": entry.get("hs_label"),
        "hs_label_ja": entry.get("hs_label_ja"),
        "production": empty_block(
            "USGS Mineral Commodity Summaries", "mine", "share of mine production"
        ),
        "trade": empty_block("UN Comtrade", "export", "share of export value"),
    }


def write(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    log.info("rendered %s", path.relative_to(REPO_ROOT))


def render_all() -> None:
    env = environment()
    settings = config()
    catalog = load_catalog()
    index = load_index()
    summaries = {item["slug"]: item for item in index.get("minerals", [])}
    fixtures = bool(index.get("fixtures"))
    generated_at = human_time(index.get("generated_at"))
    generated_at_ja = i18n.human_time_ja(index.get("generated_at"))

    base = {
        "repo_url": settings["repo_url"],
        "generated_at": generated_at,
        "fixtures": fixtures,
        "i18n_json": safe_json(i18n.STRINGS_JA),
        "rebuilt_notice_ja": i18n.rebuilt_notice_ja(generated_at_ja or None),
    }

    entries = catalog["minerals"]

    # ------------------------------------------------------------ hub page
    write(
        REPO_ROOT / "index.html",
        env.get_template("hub.html").render(
            root="", page="hub", mineral_count=len(entries), **base
        ),
    )

    # --------------------------------------------------------- 404, at root
    write(
        REPO_ROOT / "404.html",
        env.get_template("404.html").render(
            root=settings["site_base"], page="404", **base
        ),
    )

    # -------------------------------------------------------- section index
    cards = []
    spark_payload = []
    has_any_data = False
    for entry in entries:
        summary = summaries.get(entry["slug"], {})
        # Prefer the mine-side figure as the headline; fall back to trade.
        headline, headline_source = None, None
        if summary.get("production"):
            headline, headline_source = summary["production"], "Mine"
        elif summary.get("trade"):
            headline, headline_source = summary["trade"], "Export"
        if headline:
            has_any_data = True
            spark_payload.append(
                {"slug": entry["slug"], "sparkline": headline.get("sparkline")}
            )
        cards.append(
            {
                "slug": entry["slug"],
                "name": entry["name"],
                "name_ja": entry.get("name_ja"),
                "symbol": entry.get("symbol"),
                "role": entry.get("role"),
                "role_ja": entry.get("role_ja"),
                "headline": headline,
                "headline_source": headline_source,
            }
        )

    write(
        SECTION_DIR / "index.html",
        env.get_template("section.html").render(
            root="../",
            page="section",
            section=catalog["section"],
            minerals=cards,
            has_any_data=has_any_data,
            page_data=safe_json({"minerals": spark_payload}),
            **base,
        ),
    )

    # ------------------------------------------------------- standing pages
    for name, page in (("methodology", "methodology"), ("about", "about")):
        write(
            SECTION_DIR / f"{name}.html",
            env.get_template(f"{name}.html").render(root="../", page=page, **base),
        )

    # -------------------------------------------------------- mineral pages
    for position, entry in enumerate(entries):
        data = load_mineral(entry["slug"]) or placeholder_mineral(entry)
        notes = []
        for block in ("production", "trade"):
            for note in data.get(block, {}).get("notes") or []:
                if note and note not in notes:
                    notes.append(note)
        write(
            SECTION_DIR / "minerals" / f"{entry['slug']}.html",
            env.get_template("mineral.html").render(
                root="../../",
                page="mineral",
                mineral=data,
                notes=notes,
                previous=entries[position - 1] if position > 0 else None,
                next=entries[position + 1] if position + 1 < len(entries) else None,
                page_data=safe_json(data),
                **base,
            ),
        )

    log.info("rendered %d pages", len(entries) + 5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    render_all()
