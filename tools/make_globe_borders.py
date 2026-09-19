"""Cut the country borders the globe page draws from Natural Earth.

    python tools/make_globe_borders.py NE_110M.geojson NE_50M.geojson

The inputs are the Admin 0 - Countries GeoJSON files of one Natural Earth
release, as published at

    https://raw.githubusercontent.com/nvkelso/natural-earth-vector/<tag>/geojson/ne_110m_admin_0_countries.geojson
    https://raw.githubusercontent.com/nvkelso/natural-earth-vector/<tag>/geojson/ne_50m_admin_0_countries.geojson

The 110m file is the base. It has no polygon at all for several places that
file trade (Hong Kong, Singapore, Malta and about sixty more), and a share the
globe cannot draw is a share that silently disappears, so every Admin 0 unit
the 50m file has and the 110m file lacks is added from the 50m file. Nothing
else is taken from 50m.

Only ADM0_A3 (the join key) and ADMIN (the English name) are kept. ISO_A3 is
not usable as a key in these files: France and Norway, among others, carry -99.
Coordinates are rounded - two decimals for 110m, three for the small 50m
units so that islands keep a shape - which is far below what a globe at page
size can show.

Natural Earth is in the public domain. The release used is recorded in
assets/geo/NOTICE.txt; re-run this script and update that file together.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT = REPO_ROOT / "assets" / "geo" / "countries.geojson"


def rounded_ring(ring, digits):
    out = []
    for lng, lat, *_ in ring:
        point = [round(lng, digits), round(lat, digits)]
        if not out or out[-1] != point:
            out.append(point)
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def rounded_geometry(geometry, digits):
    if geometry["type"] == "Polygon":
        polygons = [geometry["coordinates"]]
    elif geometry["type"] == "MultiPolygon":
        polygons = geometry["coordinates"]
    else:
        raise ValueError(f"unexpected geometry type {geometry['type']}")
    kept = []
    for polygon in polygons:
        rings = [rounded_ring(ring, digits) for ring in polygon]
        if rings[0] is None:
            continue
        kept.append([r for r in rings if r is not None])
    if not kept:
        return None
    if len(kept) == 1:
        return {"type": "Polygon", "coordinates": kept[0]}
    return {"type": "MultiPolygon", "coordinates": kept}


def slim(feature, digits):
    props = feature["properties"]
    geometry = rounded_geometry(feature["geometry"], digits)
    if geometry is None:
        # Rounding can collapse a speck of an island; keep the unit at the
        # precision the source has rather than drop the country.
        geometry = rounded_geometry(feature["geometry"], 5)
    return {
        "type": "Feature",
        "properties": {"ADM0_A3": props["ADM0_A3"], "ADMIN": props["ADMIN"]},
        "geometry": geometry,
    }


def main(path_110m: str, path_50m: str) -> None:
    base = json.loads(Path(path_110m).read_text(encoding="utf-8"))["features"]
    fine = json.loads(Path(path_50m).read_text(encoding="utf-8"))["features"]
    have = {f["properties"]["ADM0_A3"] for f in base}
    features = [slim(f, 2) for f in base]
    features += [slim(f, 3) for f in fine if f["properties"]["ADM0_A3"] not in have]
    features.sort(key=lambda f: f["properties"]["ADM0_A3"])
    codes = [f["properties"]["ADM0_A3"] for f in features]
    if len(codes) != len(set(codes)):
        raise SystemExit("duplicate ADM0_A3 in the combined borders")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {OUT.relative_to(REPO_ROOT)}: {len(features)} features "
          f"({len(base)} from 110m, {len(features) - len(base)} from 50m), "
          f"{OUT.stat().st_size / 1024:.0f} KiB")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
