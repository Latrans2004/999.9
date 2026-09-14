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

log = logging.getLogger("orelysis.render")

REPO_ROOT = Path(__file__).resolve().parents[1]
SECTION_DIR = REPO_ROOT / "critical-minerals"
DATA_DIR = SECTION_DIR / "data"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
CONFIG_PATH = REPO_ROOT / "site.json"
MINERALS_PATH = REPO_ROOT / "pipeline" / "minerals.json"

# The two series pipeline/update_minerals.py derives itself instead of reading
# from a stage policy, in the order the tabs present them: the published
# headline first because it is the figure the rest of the site quotes, mine
# production last because it is the only one that is not a trade measurement.
# Everything between them comes from minerals.json, in the order written there.
DERIVED_SERIES = ("headline_usd", "mine_li_t")

# A stage whose concentration record is keyed "<stage>_<something>" is the same
# stage counted from the other side of the same transaction. The base series is
# the stage's own filing; the suffix names whose declaration the other one is.
BASE_SIDE = "world_export"

# The selected_source values carry more detail than a reader can hold at a
# glance, so the badge groups them. The data is not changed: the full value
# stays in trade.json and trade.csv, and the badge's title attribute quotes it.
SOURCE_GROUPS = {
    "reported": "reported",
    "reported_partner_sum": "partner_sum",
    "mirror_missing_report": "mirror",
    "mirror_underreported": "mirror",
    "mirror_lower_bound": "mirror",
    "reported_china_import": "mirror",
    "estimated_anchor_price": "estimated",
    "legacy_usgs_export_proxy": "estimated",
}

# not_applicable and no_adjustment are the answers "the question does not
# arise" and "nothing was corrected". Neither is a finding, and badging them
# would bury the three that are.
SHOWN_VERIFICATION = ("unverified", "externally_confirmed", "externally_conflicting")

DEFAULT_CONFIG = {
    "repo_url": "https://github.com/OWNER/orelysis",
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
    env.globals["stage_coverage_ja"] = i18n.stage_coverage_ja
    env.globals["provisional_legend_ja"] = i18n.provisional_legend_ja
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
        "headline_hs_codes": entry.get("headline_hs_codes", []),
        "hs_label": entry.get("hs_label"),
        "hs_label_ja": entry.get("hs_label_ja"),
        "production": empty_block(
            "USGS Mineral Commodity Summaries", "mine", "share of mine production"
        ),
        "trade": empty_block("UN Comtrade", "export", "share of export value"),
    }


def read_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def stage_settings(slug: str) -> dict:
    """The mineral's stage policies, or an empty mapping when it has none.

    Seven of the eight minerals are not configured in minerals.json at all, and
    a mineral without stages simply renders the page it renders today.
    """
    configured = read_json(MINERALS_PATH) or {}
    return configured.get("minerals", {}).get(slug, {})


def split_series_key(hs_code: str, stage_codes) -> tuple[str, str]:
    '''Split a concentration key into the stage it measures and the side it is filed from.

    "253090" is the stage\'s own filing and "253090_china_import" is the same
    stage counted from the importer\'s declarations. The suffix is read from
    the data rather than listed here, so a second side needs no code change -
    only a "side.<suffix>" entry in pipeline/i18n.py to give it a name.
    '''
    for code in stage_codes:
        if hs_code == code:
            return code, BASE_SIDE
        if hs_code.startswith(code + "_"):
            return code, hs_code[len(code) + 1:]
    return hs_code, BASE_SIDE


def badge(key: str, raw: str | None) -> dict:
    """One badge: a grouped label in both languages, with the raw value kept."""
    return {
        "key": key,
        "label": i18n.label_en(key),
        "label_ja": i18n.label_ja(key),
        "raw": raw,
    }


def stage_rows(record: dict, provenance: dict, evidence_index: dict) -> list[dict]:
    """The country rows of one stage-year, with their provenance badges attached.

    concentration.json names countries by ISO3 and carries no provenance; the
    per-country selection lives in trade.json. The two are joined here rather
    than in the data layer so that neither file has to change and no number is
    copied into a second place.
    """
    rows = []
    for entry in record["top"]:
        country = entry["name"]
        selection = provenance.get((record["hs_code"], record["year"], country), {})
        source_group = SOURCE_GROUPS.get(selection.get("selected_source"))
        status = selection.get("verification_status")
        note = evidence_index.get((record["hs_code"], record["year"], country))
        rows.append(
            {
                "country": country,
                "share": entry["share"],
                "quantity": entry["quantity"],
                "source": badge("source." + source_group, selection.get("selected_source"))
                if source_group
                else None,
                "verification": badge("verification." + status, status)
                if status in SHOWN_VERIFICATION
                else None,
                "evidence": note["id"] if note else None,
            }
        )
    return rows


def stage_panel(records, hs_code, provisional, provenance, evidence_index) -> dict | None:
    """The view model for one series: its years, and its latest year in detail."""
    points = sorted(
        (r for r in records if r["hs_code"] == hs_code), key=lambda r: r["year"]
    )
    if not points:
        return None
    latest = points[-1]
    years = [
        {
            "year": r["year"],
            "hhi": r["hhi"],
            "cr3": r["cr3"],
            "reporters": r["reporters"],
            "coverage_pct": r["coverage_pct"],
            "provisional": r["year"] in provisional,
        }
        for r in points
    ]
    return {
        "id": "stage-" + hs_code,
        "hs_code": hs_code,
        "unit": latest["unit"],
        "years": years,
        "provisional_years": [y["year"] for y in years if y["provisional"]],
        "has_coverage": any(y["coverage_pct"] is not None for y in years),
        "latest": {
            "year": latest["year"],
            "hhi": latest["hhi"],
            "band": latest["band"],
            "cr1": latest["cr1"],
            "cr3": latest["cr3"],
            "effective_suppliers": latest["effective_suppliers"],
            "reporters": latest["reporters"],
            "total": latest["total"],
            "coverage_pct": latest["coverage_pct"],
            "provisional": latest["year"] in provisional,
            "rows": stage_rows(latest, provenance, evidence_index),
        },
    }


def load_stages(slug: str) -> dict | None:
    """Assemble the stage tabs for one mineral, or None when it has no stages.

    Nothing here is written back: the three published files are read as they
    stand and joined into a view model that lives only in the rendered page.
    """
    settings = stage_settings(slug)
    stage_codes = list(settings.get("stages") or {})
    if not stage_codes:
        return None
    concentration = read_json(DATA_DIR / slug / "concentration.json")
    if not concentration:
        return None
    records = concentration["records"]
    metadata = concentration.get("metadata") or {}
    # The published metadata is what the page must agree with; minerals.json is
    # the fallback for a build that predates the metadata field.
    provisional = metadata.get("provisional_years")
    if provisional is None:
        provisional = settings.get("provisional_years") or {}

    evidence = (read_json(DATA_DIR / slug / "evidence.json") or {}).get("entries") or []
    evidence_index, notes = {}, []
    for position, note in enumerate(evidence):
        identifier = f"evidence-{position}"
        notes.append(
            {
                "id": identifier,
                "country": note["country"],
                "hs_code": note["hs_code"],
                "outcome": note["outcome"],
                "years": (
                    str(note["year_from"])
                    if note["year_from"] == note["year_to"]
                    else f"{note['year_from']}\u2013{note['year_to']}"
                ),
                "source_name": note["source_name"],
                "source_url": note.get("source_url"),
                "note": note["note_en"],
                "note_ja": note["note_ja"],
            }
        )
        for year in range(note["year_from"], note["year_to"] + 1):
            evidence_index[(note["hs_code"], year, note["country"])] = notes[-1]

    trade = read_json(DATA_DIR / slug / "trade.json") or {"records": []}
    provenance = {
        (r["hs_code"], r["year"], r["country"]): r for r in trade["records"]
    }

    by_stage: dict[str, list[str]] = {}
    for hs_code in sorted({r["hs_code"] for r in records}):
        stage, side = split_series_key(hs_code, stage_codes)
        by_stage.setdefault(stage, []).append(side)

    head, tail = DERIVED_SERIES[0], DERIVED_SERIES[-1]
    order = [head] + stage_codes + [tail]
    tabs = []
    for stage in order:
        sides = by_stage.get(stage)
        if not sides:
            continue
        # The stage's own filing leads; any mirror side follows in a stable order.
        sides = ([BASE_SIDE] if BASE_SIDE in sides else []) + sorted(
            s for s in sides if s != BASE_SIDE
        )
        label_key = (
            "stage." + stage
            if stage in DERIVED_SERIES
            else "stage." + (settings["stages"][stage].get("policy") or stage)
        )
        panels = []
        for side in sides:
            hs_code = stage if side == BASE_SIDE else f"{stage}_{side}"
            panel = stage_panel(
                records,
                hs_code,
                set(provisional.get(stage) or []),
                provenance,
                evidence_index,
            )
            if panel is None:
                continue
            panel["side_key"] = side
            panel["side_label_key"] = "side." + side
            panel["side_label"] = i18n.label_en("side." + side)
            panel["side_label_ja"] = i18n.label_ja("side." + side)
            panels.append(panel)
        if not panels:
            continue
        tabs.append(
            {
                "key": stage,
                "label_key": label_key,
                # An unnamed stage falls back to its policy, which reads; the HS
                # code it is keyed by does not.
                "label": i18n.label_en(label_key),
                "label_ja": i18n.label_ja(label_key),
                "panels": panels,
            }
        )
    if not tabs:
        return None
    used = {row["evidence"] for tab in tabs for p in tab["panels"] for row in p["latest"]["rows"]}
    return {"tabs": tabs, "notes": [n for n in notes if n["id"] in used]}


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
        # Only a mineral configured with stages in pipeline/minerals.json grows
        # the stage panel; the other seven render exactly the page they do today.
        stages = load_stages(entry["slug"])
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
                stages=stages,
                stage_data=safe_json(stages) if stages else None,
                **base,
            ),
        )

    log.info("rendered %d pages", len(entries) + 5)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    render_all()
