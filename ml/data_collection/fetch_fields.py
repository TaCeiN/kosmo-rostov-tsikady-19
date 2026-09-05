#!/usr/bin/env python3
"""Контуры сельхозполей из OpenStreetMap через Overpass API.

    python data_collection/fetch_fields.py --bbox 46.0,38.5 48.5,42.5 \
        --limit 500 --out fields.geojson

bbox задаётся как «юг,запад север,восток». По умолчанию — Ростовская область,
тот же регион, где лежат полигоны организаторов (см. RECIPE.md).

Берутся замкнутые контуры landuse=farmland с площадью в разумных пределах:
слишком мелкие дают шумный средний NDVI по пикселям, слишком крупные почти
наверняка объединяют несколько полей с разными культурами.
"""

from __future__ import annotations

import argparse
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OVERPASS = "https://overpass-api.de/api/interpreter"
MIN_HA, MAX_HA = 10.0, 400.0


def query(bbox: tuple[float, float, float, float], timeout: int = 180) -> dict:
    s, w, n, e = bbox
    q = f"""
    [out:json][timeout:{timeout}];
    (
      way["landuse"="farmland"]({s},{w},{n},{e});
      relation["landuse"="farmland"]({s},{w},{n},{e});
    );
    out geom;
    """
    req = Request(OVERPASS, data=urlencode({"data": q}).encode(),
                  headers={"User-Agent": "ndvi-hackathon/1.0"})
    with urlopen(req, timeout=timeout + 30) as r:
        return json.loads(r.read())


def ring_area_ha(coords: list[tuple[float, float]]) -> float:
    """Площадь замкнутого контура в гектарах (плоское приближение, для фильтра хватает)."""
    if len(coords) < 4:
        return 0.0
    lat0 = sum(c[1] for c in coords) / len(coords)
    import math
    kx = 111_320 * math.cos(math.radians(lat0))
    ky = 110_540
    s = 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        s += (x1 * kx) * (y2 * ky) - (x2 * kx) * (y1 * ky)
    return abs(s) / 2 / 10_000


def to_features(data: dict, limit: int) -> list[dict]:
    feats = []
    for el in data.get("elements", []):
        geom = el.get("geometry")
        if not geom:
            continue
        coords = [(p["lon"], p["lat"]) for p in geom]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        area = ring_area_ha(coords)
        if not (MIN_HA <= area <= MAX_HA):
            continue
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [coords]},
            "properties": {"osm_id": el["id"], "area_ha": round(area, 1),
                           "anon_polygon_id": f"EXT-{el['id']}",
                           "crop_type": el.get("tags", {}).get("crop", "неизвестно")},
        })
        if len(feats) >= limit:
            break
    return feats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", nargs=2, default=["46.0,38.5", "48.5,42.5"],
                    help="'юг,запад' 'север,восток'; по умолчанию Ростовская область")
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--out", default="fields.geojson")
    a = ap.parse_args()

    (s, w), (n, e) = ([float(x) for x in part.split(",")] for part in a.bbox)
    print(f"запрос Overpass по bbox {s},{w} .. {n},{e}")
    t0 = time.time()
    data = query((s, w, n, e))
    feats = to_features(data, a.limit)
    print(f"получено объектов: {len(data.get('elements', []))}, "
          f"после фильтра по площади {MIN_HA}-{MAX_HA} га: {len(feats)} ({time.time()-t0:.0f}s)")

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)
    print(f"записано в {a.out}")
    if feats:
        areas = sorted(x["properties"]["area_ha"] for x in feats)
        print(f"площади, га: медиана {areas[len(areas)//2]}, "
              f"мин {areas[0]}, макс {areas[-1]}")


if __name__ == "__main__":
    main()
