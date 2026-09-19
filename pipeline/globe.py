"""The data behind critical-minerals/globe.html, and the checks that guard it.

The globe shows, for one mineral and one layer at a time, how the published
country shares fall across the map. Nothing here computes a figure the site
does not already publish: every share is copied from a published record (the
mineral JSON, or the concentration file its page is built from) and every
headline figure the globe's info panel quotes is copied from the same place
the mineral page quotes it. Rendering fails, rather than drawing a globe that
disagrees with the rest of the site, when any of five checks does not hold:

1. every country with a share or a no-data mark joins a border polygon;
2. a layer's shares, plus its unattributed remainder, do not exceed 1;
3. the leader, its share, CR3 and (where published) HHI recomputed from the
   shares match the published figures;
4. a layer that is not published carries no number at all, in any file;
5. the mineral list and each mineral's status match the catalog and the
   status the screener shows.

Output, rewritten on every render (stale files are removed, so a mineral that
goes back under review takes its numbers off the site with it):

    critical-minerals/data/globe/index.json     every catalog mineral, its
                                                status and its layers
    critical-minerals/data/globe/<slug>.json    the published layers' shares,
                                                for a mineral that has any

Layer kinds. ``unit`` is always "share"; a layer in any other unit is a build
error until the page learns to draw it.

    mine_production_share   USGS mine production by country
    reserves_share          USGS reserves by country - no pipeline publishes
                            reserves yet; the reader below is the contract a
                            future one fills, and is exercised by the tests
    export_share            UN Comtrade exports by reporter, one layer per
                            published trade stage ("export_share_<stage>")
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import i18n, render

GLOBE_DIR = render.DATA_DIR / "globe"
BORDERS_PATH = render.REPO_ROOT / "assets" / "geo" / "countries.geojson"

UNIT = "share"
KINDS = ("mine_production_share", "reserves_share", "export_share")

# Natural Earth keys a handful of units differently from ISO 3166 alpha-3, and
# the published data is keyed by ISO. Kosovo has no ISO code; XKX is the
# user-assigned code most statistics use.
ISO_TO_ADM0 = {
    "SSD": "SDS",  # South Sudan
    "PSE": "PSX",  # Palestine
    "ESH": "SAH",  # Western Sahara
    "XKX": "KOS",  # Kosovo
}

# Recomputation tolerances. Shares are published to four decimals of a
# percent, CR3 to two and HHI to one, so anything past these is a real
# disagreement rather than rounding.
TOL_SUM = 0.002          # fraction of 1
TOL_SHARE_PP = 0.01      # percentage points
TOL_CR3_PP = 0.02
TOL_HHI = 0.5

# Values a source prints where a number would be, meaning "not disclosed" or
# "not available" rather than zero. A country marked this way is drawn as
# no data, never as 0%.
NO_DATA_STATUSES = {"withheld", "not_available", "na", "not_disclosed", "large"}
NO_DATA_TOKENS = {"W", "NA", "N/A", "XX", "LARGE", "--"}

_ISO3 = re.compile(r"^[A-Z]{3}$")


class GlobeError(Exception):
    """The globe data cannot be built without disagreeing with the site."""


# ------------------------------------------------------------------ helpers

def iso3(entry: dict) -> str:
    """The ISO3 code of a published row: ``code`` in the mineral JSON, and
    ``name`` in concentration.json, which names countries by code."""
    for value in (entry.get("code"), entry.get("country"), entry.get("name")):
        if isinstance(value, str) and _ISO3.match(value):
            return value
    raise GlobeError(f"row has no ISO3 country code: {entry!r}")


def adm0(code: str) -> str:
    return ISO_TO_ADM0.get(code, code)


def load_borders() -> dict[str, str]:
    """ADM0_A3 -> English name for every polygon the page can draw."""
    features = json.loads(BORDERS_PATH.read_text(encoding="utf-8"))["features"]
    return {f["properties"]["ADM0_A3"]: f["properties"]["ADMIN"] for f in features}


def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def full_rows(slug: str, latest: dict, what: str) -> list[dict]:
    """Every country row behind a published latest-year figure.

    The mineral JSON keeps only the largest ten countries. When that is not
    all of them, the complete list is the published concentration record of
    the same year with the same HHI and CR3 - the one the figure was taken
    from. Anything else would be a new calculation, so it is an error.
    """
    top = latest.get("top") or []
    if len(top) >= (latest.get("reporters") or 0):
        return top
    concentration = render.read_json(render.DATA_DIR / slug / "concentration.json") or {}
    matches = []
    for record in concentration.get("records") or []:
        profile = record.get("profile") or record
        if (
            profile.get("year", record.get("year")) == latest["year"]
            and len(profile.get("top") or []) == latest["reporters"]
            and abs((profile.get("hhi") or -1) - latest["hhi"]) < 0.05
            and abs((profile.get("cr3") or -1) - latest["cr3"]) < 0.01
        ):
            matches.append(profile["top"])
    if len(matches) != 1:
        raise GlobeError(
            f"{slug}: the full country list behind the published {what} figure for "
            f"{latest['year']} ({latest['reporters']} countries, HHI {latest['hhi']}) is "
            f"not in the published data (found {len(matches)} matching records). The globe "
            "needs every country's share; publishing it is a pipeline change, not a globe one."
        )
    return matches[0]


def shares(slug: str, rows: list[dict], share_key: str = "share") -> tuple[dict, list]:
    """ADM0-keyed shares (0-1) and the no-data list from published rows.

    A row whose share is not a number (NA, withheld, "Large") is no data, not
    zero.
    """
    values, no_data = {}, []
    for row in rows:
        code = adm0(iso3(row))
        if code in values or code in no_data:
            raise GlobeError(f"{slug}: {code} appears twice in one layer")
        share = row.get(share_key)
        if is_number(share):
            values[code] = round(share / 100, 6)
        else:
            no_data.append(code)
    return values, no_data


def withheld_countries(slug: str, year: int) -> list[str]:
    """Countries the USGS source lists for ``year`` without a figure."""
    production = render.read_json(render.DATA_DIR / slug / "production.json") or {}
    out = []
    for record in production.get("records") or []:
        if record.get("year") != year or record.get("kind", "country") != "country":
            continue
        status = str(record.get("status") or "").lower()
        token = str(record.get("native_token") or "").strip().upper()
        figure = record.get("production_t", 0)
        if status in NO_DATA_STATUSES or token in NO_DATA_TOKENS or (figure is None and token != "—"):
            code = record.get("country")
            if isinstance(code, str) and _ISO3.match(code):
                out.append(adm0(code))
    return sorted(set(out))


def listed_zero(slug: str, year: int) -> list[str]:
    """Countries the USGS table lists for ``year`` with nil output ("—" or 0).

    These are published zeros, drawn as 0%; a country the table does not list
    at all is left without a share rather than given one.
    """
    production = render.read_json(render.DATA_DIR / slug / "production.json") or {}
    out = []
    for record in production.get("records") or []:
        if record.get("year") != year or record.get("kind", "country") != "country":
            continue
        token = str(record.get("native_token") or "").strip()
        if record.get("production_t") == 0 or token == "—":
            code = record.get("country")
            if isinstance(code, str) and _ISO3.match(code):
                out.append(adm0(code))
    return sorted(set(out))


def summary_of(leader: str, leader_share: float, cr3: float, hhi, band) -> dict:
    out = {"leader": adm0(leader), "leader_share": leader_share, "cr3": cr3}
    # HHI is quoted only where the site already publishes it for this layer.
    if is_number(hhi):
        out["hhi"] = hhi
        if band:
            out["band"] = band
    return out


def reviewed(layer_id: str, kind: str, label: str, label_ja: str) -> dict:
    """A layer that exists but is not published: its name and state, no number."""
    return {"id": layer_id, "kind": kind, "status": "under_review",
            "label": label, "label_ja": label_ja, "year": None}


# ------------------------------------------------------------------ layers

def mine_layer(slug: str, data: dict) -> dict | None:
    block = data.get("production") or {}
    label, label_ja = "Mine production", "鉱山生産"
    if block.get("publication_status") == "under_review" or block.get("publishable") is False:
        return reviewed("mine_production_share", "mine_production_share", label, label_ja)
    if not block.get("available"):
        return None
    latest = block["latest"]
    values, no_data = shares(slug, full_rows(slug, latest, "mine production"))
    for code in listed_zero(slug, latest["year"]):
        values.setdefault(code, 0.0)
    no_data = sorted(set(no_data) | {c for c in withheld_countries(slug, latest["year"]) if c not in values})
    world = latest.get("coverage")
    return {
        "id": "mine_production_share",
        "kind": "mine_production_share",
        "status": "published",
        "label": label,
        "label_ja": label_ja,
        "year": latest["year"],
        "source": block.get("source") or "USGS Mineral Commodity Summaries",
        "measure": block.get("unit") or "share of mine production",
        "measure_ja": block.get("unit_ja") or "",
        "unit": UNIT,
        "values": values,
        "no_data": no_data,
        "other_share": 0.0,
        "coverage": round(sum(values.values()), 6),
        "world_coverage": world if is_number(world) else None,
        "provisional": False,
        "summary": summary_of(
            iso3(latest["top"][0]), latest["top"][0]["share"], latest["cr3"],
            latest.get("hhi"), latest.get("band"),
        ),
        "note_en": i18n.globe_share_note_en("mine", world, no_data),
        "note_ja": i18n.globe_share_note_ja("mine", world, no_data),
    }


def reserves_layer(slug: str, data: dict) -> dict | None:
    """Reserves by country, when a pipeline publishes them as ``reserves``.

    Same shape as the production block: ``latest.top`` rows with a percentage
    ``share``, where a row the source prints as NA, W or "Large" carries no
    number and is drawn as no data. HHI is quoted only if the block has one.
    """
    block = data.get("reserves")
    if not block:
        return None
    label, label_ja = "Reserves", "埋蔵量"
    if block.get("publication_status") == "under_review" or block.get("publishable") is False:
        return reviewed("reserves_share", "reserves_share", label, label_ja)
    if not block.get("available"):
        return None
    latest = block["latest"]
    values, no_data = shares(slug, latest["top"])
    numeric = sorted(
        (r for r in latest["top"] if is_number(r.get("share"))), key=lambda r: -r["share"]
    )
    other = latest.get("other_share")
    return {
        "id": "reserves_share",
        "kind": "reserves_share",
        "status": "published",
        "label": label,
        "label_ja": label_ja,
        "year": latest["year"],
        "source": block.get("source") or "USGS Mineral Commodity Summaries",
        "measure": block.get("unit") or "share of reserves",
        "measure_ja": block.get("unit_ja") or "",
        "unit": UNIT,
        "values": values,
        "no_data": sorted(no_data),
        "other_share": other if is_number(other) else 0.0,
        "coverage": round(sum(values.values()), 6),
        "world_coverage": latest.get("coverage") if is_number(latest.get("coverage")) else None,
        "provisional": False,
        "summary": summary_of(
            iso3(numeric[0]), numeric[0]["share"], latest["cr3"],
            latest.get("hhi"), latest.get("band"),
        ),
        "note_en": i18n.globe_share_note_en("reserves", latest.get("coverage"), no_data),
        "note_ja": i18n.globe_share_note_ja("reserves", latest.get("coverage"), no_data),
    }


def export_layers(slug: str, data: dict, stages: dict | None) -> list[dict]:
    """One layer per published trade stage, the stage's own filing only.

    The publication decision comes first, exactly as in the screener: a trade
    block under review yields a named layer with no number, whatever else is
    on disk. A mineral with stage tabs gets a layer per tab (mine production
    has its own layer and is skipped); one without gets its headline.
    """
    trade = data.get("trade") or {}
    if trade.get("publication_status") == "under_review" or trade.get("publishable") is False:
        return [reviewed("export_share_headline", "export_share", "Exports", "輸出")]
    layers = []
    if stages:
        settings = render.stage_settings(slug).get("stages") or {}
        for tab in stages["tabs"]:
            if tab["key"] == render.DERIVED_SERIES[-1]:
                continue
            panel = tab["panels"][0]
            if panel["side_key"] != render.BASE_SIDE:
                continue
            stage = (
                "headline" if tab["key"] == render.DERIVED_SERIES[0]
                else (settings.get(tab["key"], {}).get("policy") or tab["key"])
            )
            latest = panel["latest"]
            rows = [{"code": r["country"], "share": r["share"]} for r in latest["rows"]]
            values, no_data = shares(slug, rows)
            layers.append({
                "id": f"export_share_{stage}",
                "kind": "export_share",
                "stage": stage,
                "status": "published",
                "label": f"Exports · {tab['label']}",
                "label_ja": f"輸出 · {tab['label_ja'] or tab['label']}",
                "year": latest["year"],
                "source": trade.get("source") or "UN Comtrade",
                "measure": i18n.globe_trade_measure_en(panel["unit"]),
                "measure_ja": i18n.globe_trade_measure_ja(panel["unit"]),
                "unit": UNIT,
                "values": values,
                "no_data": no_data,
                "other_share": 0.0,
                "coverage": round(sum(values.values()), 6),
                "world_coverage": None,
                "report_completeness": latest["coverage_pct"],
                "provisional": bool(latest["provisional"]),
                "summary": summary_of(
                    latest["rows"][0]["country"], latest["cr1"], latest["cr3"],
                    latest["hhi"], latest["band"],
                ),
                "note_en": i18n.globe_share_note_en("export", None, no_data),
                "note_ja": i18n.globe_share_note_ja("export", None, no_data),
            })
        return layers
    if trade.get("available"):
        latest = trade["latest"]
        values, no_data = shares(slug, full_rows(slug, latest, "export"))
        layers.append({
            "id": "export_share_headline",
            "kind": "export_share",
            "stage": "headline",
            "status": "published",
            "label": "Exports",
            "label_ja": "輸出",
            "year": latest["year"],
            "source": trade.get("source") or "UN Comtrade",
            "measure": trade.get("unit") or "share of export value",
            "measure_ja": trade.get("unit_ja") or "",
            "unit": UNIT,
            "values": values,
            "no_data": no_data,
            "other_share": 0.0,
            "coverage": round(sum(values.values()), 6),
            "world_coverage": None,
            "provisional": False,
            "summary": summary_of(
                iso3(latest["top"][0]), latest["top"][0]["share"], latest["cr3"],
                latest.get("hhi"), latest.get("band"),
            ),
            "note_en": i18n.globe_share_note_en("export", None, no_data),
            "note_ja": i18n.globe_share_note_ja("export", None, no_data),
        })
    return layers


# ------------------------------------------------------------------ build

def mineral_status(row: dict) -> str:
    """The status the screener shows for this mineral, in three words."""
    if row["mine"] or row["export"]["kind"] in ("value", "stages"):
        return "published"
    if row["export"]["kind"] == "review":
        return "under_review"
    return "pending"


def build(catalog: dict, rows: list[dict]) -> tuple[dict, dict[str, dict]]:
    """The index and the per-mineral files, from the catalog and screener rows."""
    by_slug = {r["slug"]: r for r in rows}
    groups = [
        {"key": key, "label": value.get("label") or key, "label_ja": value.get("label_ja") or ""}
        for key, value in (catalog.get("categories") or {}).items()
    ]
    minerals, files = [], {}
    for entry in catalog["minerals"]:
        slug = entry["slug"]
        row = by_slug[slug]
        data = render.load_mineral(slug)
        layers = []
        if data:
            for layer in (mine_layer(slug, data), reserves_layer(slug, data)):
                if layer:
                    layers.append(layer)
            layers.extend(export_layers(slug, data, render.load_stages(slug)))
        published = [layer for layer in layers if layer["status"] == "published"]
        status = mineral_status(row)
        minerals.append({
            "id": slug,
            "name_en": entry["name"],
            "name_ja": entry.get("name_ja") or "",
            "symbol": entry.get("symbol") or "",
            "group": row["category"]["key"],
            "status": status,
            "selectable": bool(published),
            "page_url": f"minerals/{slug}.html",
            "layers": [
                {key: layer[key] for key in ("id", "kind", "year", "status", "label", "label_ja")}
                for layer in layers
            ],
        })
        if published:
            files[slug] = {
                "id": slug,
                "name_en": entry["name"],
                "name_ja": entry.get("name_ja") or "",
                "layers": published,
            }
    first = next((m for m in minerals if m["selectable"]), None)
    index = {
        "schema": 1,
        "data_generated_at": (render.load_index() or {}).get("generated_at"),
        "scale": {"transform": "sqrt", "max": 0.85},
        "default": {
            "mineral": first["id"] if first else None,
            "layer": next(l["id"] for l in first["layers"] if l["status"] == "published") if first else None,
        },
        "groups": groups,
        "minerals": minerals,
    }
    return index, files


# ------------------------------------------------------------------ checks

def recompute(values: dict) -> dict:
    ordered = sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
    pct = [v * 100 for _, v in ordered]
    return {
        "leader": ordered[0][0] if ordered else None,
        "leader_share": pct[0] if pct else 0.0,
        "cr3": sum(pct[:3]),
        "hhi": sum(p * p for p in pct),
    }


def verify(catalog: dict, rows: list[dict], index: dict, files: dict, borders: dict) -> None:
    """Raise GlobeError listing every failed check; return quietly otherwise."""
    problems = []
    names = {}

    # 5. the list and the statuses follow the catalog and the screener.
    expected = [m["slug"] for m in catalog["minerals"]]
    listed = [m["id"] for m in index["minerals"]]
    if listed != expected:
        problems.append(f"index minerals {listed} do not match the catalog {expected}")
    by_slug = {r["slug"]: r for r in rows}
    for mineral in index["minerals"]:
        row = by_slug.get(mineral["id"])
        if row is None:
            continue
        if mineral["status"] != mineral_status(row):
            problems.append(f"{mineral['id']}: status {mineral['status']} but the screener shows {mineral_status(row)}")
        if mineral["group"] != row["category"]["key"]:
            problems.append(f"{mineral['id']}: group {mineral['group']} is not its catalog category")
        if mineral["status"] == "published" and not mineral["selectable"]:
            problems.append(f"{mineral['id']}: published on the site but has no published globe layer")
        if mineral["status"] != "published" and mineral["selectable"]:
            problems.append(f"{mineral['id']}: {mineral['status']} on the site but selectable on the globe")

    # 4. nothing unpublished carries a number, anywhere.
    for mineral in index["minerals"]:
        for layer in mineral["layers"]:
            if layer["status"] != "published" and layer.get("year") is not None:
                problems.append(f"{mineral['id']}/{layer['id']}: unpublished layer carries a year")
        published_ids = [l["id"] for l in mineral["layers"] if l["status"] == "published"]
        file_ids = [l["id"] for l in (files.get(mineral["id"]) or {}).get("layers", [])]
        if published_ids != file_ids:
            problems.append(f"{mineral['id']}: file layers {file_ids} are not the published layers {published_ids}")
    for slug in files:
        if slug not in listed:
            problems.append(f"{slug}: a globe file exists for a mineral outside the catalog")

    for slug, payload in files.items():
        for layer in payload["layers"]:
            where = f"{slug}/{layer['id']}"
            if layer.get("status") != "published":
                problems.append(f"{where}: unpublished layer written with numbers")
                continue
            if layer.get("unit") != UNIT:
                problems.append(f"{where}: unit {layer.get('unit')!r} is not one the globe can draw")
            if layer.get("kind") not in KINDS:
                problems.append(f"{where}: unknown layer kind {layer.get('kind')!r}")
            values = layer.get("values") or {}
            no_data = layer.get("no_data") or []

            # 1. every country joins a polygon.
            unjoined = sorted(c for c in list(values) + list(no_data) if c not in borders)
            if unjoined:
                problems.append(f"{where}: no border polygon for {', '.join(unjoined)}")
            both = sorted(set(values) & set(no_data))
            if both:
                problems.append(f"{where}: {', '.join(both)} both have a share and are marked no data")
            if any(not is_number(v) or v < 0 for v in values.values()):
                problems.append(f"{where}: a share is negative or not a number")

            # 2. shares plus the unattributed remainder do not exceed the whole.
            total = sum(values.values()) + (layer.get("other_share") or 0.0)
            if total > 1 + TOL_SUM:
                problems.append(f"{where}: shares sum to {total:.4f}, more than 1")

            # 3. the published headline figures follow from the shares.
            if not values:
                problems.append(f"{where}: published layer with no shares")
                continue
            got, published = recompute(values), layer["summary"]
            if got["leader"] != published["leader"]:
                problems.append(f"{where}: leader {got['leader']} from the shares, {published['leader']} published")
            if abs(got["leader_share"] - published["leader_share"]) > TOL_SHARE_PP:
                problems.append(f"{where}: leader share {got['leader_share']:.4f} vs published {published['leader_share']}")
            if abs(got["cr3"] - published["cr3"]) > TOL_CR3_PP:
                problems.append(f"{where}: CR3 {got['cr3']:.3f} vs published {published['cr3']}")
            if "hhi" in published and abs(got["hhi"] - published["hhi"]) > TOL_HHI:
                problems.append(f"{where}: HHI {got['hhi']:.2f} vs published {published['hhi']}")

    if problems:
        raise GlobeError("globe data check failed:\n  " + "\n  ".join(problems))


def check_written(index: dict) -> None:
    """Check 4 on disk: no globe file holds numbers the index says are unpublished."""
    allowed = {m["id"] for m in index["minerals"] if m["selectable"]}
    for path in sorted(GLOBE_DIR.glob("*.json")):
        if path.name == "index.json":
            continue
        if path.stem not in allowed:
            raise GlobeError(f"{path.name}: globe file for a mineral with no published layer")
        payload = json.loads(path.read_text(encoding="utf-8"))
        for layer in payload["layers"]:
            if layer.get("status") != "published":
                raise GlobeError(f"{path.name}: holds unpublished layer {layer.get('id')}")


def dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=False) + "\n"


def write(catalog: dict, rows: list[dict]) -> dict:
    """Build, check, write. Returns the index for the page template."""
    index, files = build(catalog, rows)
    verify(catalog, rows, index, files, load_borders())
    GLOBE_DIR.mkdir(parents=True, exist_ok=True)
    keep = {"index.json"} | {f"{slug}.json" for slug in files}
    for path in GLOBE_DIR.glob("*.json"):
        if path.name not in keep:
            path.unlink()
    (GLOBE_DIR / "index.json").write_text(dump(index), encoding="utf-8", newline="\n")
    for slug, payload in files.items():
        (GLOBE_DIR / f"{slug}.json").write_text(dump(payload), encoding="utf-8", newline="\n")
    check_written(index)
    return index
