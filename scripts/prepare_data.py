# -*- coding: utf-8 -*-
"""Prepare web data for the Ayalon Highways / NTA traffic-lights map.

Reads the source layers under data/, then:
  1. Filters the "other traffic authorities" right-of-way layer to NTA only
     (traffic authority == "נתע").
  2. Normalizes authority values to a common form and translates property
     names from Hebrew source columns to English.
  3. Computes, for every traffic light, its distance in meters to the Ayalon
     right-of-way polygons and to the NTA right-of-way lines. The web app tags
     lights by comparing these distances to a user-chosen buffer, so tagging
     is instant client-side without a geometry library.

Outputs JS data files under assets/data/ (plain `const` globals so the map
works when opened directly from the filesystem, no web server needed).
"""

import json
import math
import os

from shapely.geometry import shape
from shapely.ops import transform, unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "assets", "data")

AYALON_SRC = os.path.join(DATA, "נתיבי איילון.geojson")
NTA_SRC = os.path.join(DATA, "רשויות תמרור אחרות.geojson")
LIGHTS_SRC = os.path.join(DATA, "רמזורים במטרופולין.geojson")

# Distances beyond this are irrelevant for any sensible buffer.
MAX_DIST_M = 1000.0

# Common-value normalization (per project instructions).
VALUE_NORM = {
    'נת"א': "נתיבי איילון",
    "נת''א": "נתיבי איילון",
    'נת"ע': "נתע",
    "נת''ע": "נתע",
    "NTA": "נתע",
}


def norm_value(v):
    if v is None:
        return ""
    v = str(v).strip()
    seen = set()
    while v in VALUE_NORM and v not in seen:
        seen.add(v)
        v = VALUE_NORM[v]
    return v


def clean(v):
    v = "" if v is None else str(v).strip()
    return v


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def local_projection(lon0, lat0):
    """Equirectangular projection to meters around (lon0, lat0).

    The study area spans well under one degree of latitude, so the distance
    error versus a true TM projection is negligible at buffer scales.
    """
    r = 6371008.8
    k = math.pi / 180.0
    coslat = math.cos(lat0 * k)

    def project(x, y, z=None):
        return ((x - lon0) * k * r * coslat, (y - lat0) * k * r)

    return project


def round_coords(obj, ndigits=6):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(obj[0], ndigits), round(obj[1], ndigits)]
        return [round_coords(c, ndigits) for c in obj]
    return obj


def write_js(name, var, payload):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("const %s = " % var)
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print("wrote %s (%.1f KB)" % (os.path.relpath(path, ROOT),
                                  os.path.getsize(path) / 1024))


def geom_display(geom, tolerance_m, project_inv_scale):
    """Slightly simplify a geometry for display only (analysis uses full)."""
    simplified = geom.simplify(tolerance_m * project_inv_scale,
                               preserve_topology=True)
    return round_coords(json.loads(json.dumps(simplified.__geo_interface__)))


def main():
    ayalon = load(AYALON_SRC)
    others = load(NTA_SRC)
    lights = load(LIGHTS_SRC)

    # --- filter NTA features -------------------------------------------------
    nta_feats = [
        f for f in others["features"]
        if f.get("geometry") and norm_value(f["properties"].get("TRAFAUTH")) == "נתע"
    ]
    print("NTA features after filter:", len(nta_feats))

    # --- projection centered on the traffic lights ---------------------------
    pts = [f["geometry"]["coordinates"] for f in lights["features"]]
    lon0 = sum(p[0] for p in pts) / len(pts)
    lat0 = sum(p[1] for p in pts) / len(pts)
    project = local_projection(lon0, lat0)
    deg_per_m = 1.0 / (6371008.8 * math.pi / 180.0)

    ayalon_geoms = [transform(project, shape(f["geometry"]))
                    for f in ayalon["features"]]
    nta_geoms = [transform(project, shape(f["geometry"])) for f in nta_feats]
    ayalon_union = unary_union(ayalon_geoms)
    nta_union = unary_union(nta_geoms)

    # --- traffic lights with distances ---------------------------------------
    out_lights = []
    for f in lights["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        pt = transform(project, shape(f["geometry"]))
        d_a = ayalon_union.distance(pt)
        d_n = nta_union.distance(pt)
        streets = [clean(p.get(k)) for k in ("stree_1", "stree_2", "street_3")]
        out_lights.append({
            "id": clean(p.get("OBJECTID")),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "authority": norm_value(p.get("Current_au")),
            "name": clean(p.get("name")),
            "city": clean(p.get("City")),
            "status": clean(p.get("Status")),
            "mainStreet": clean(p.get("main_stree")),
            "streets": [s for s in streets if s],
            "source": clean(p.get("Source")),
            "updated": clean(p.get("Date")),
            "dA": round(d_a, 1) if d_a <= MAX_DIST_M else None,
            "dN": round(d_n, 1) if d_n <= MAX_DIST_M else None,
        })
    write_js("lights.js", "TRAFFIC_LIGHTS", out_lights)

    # --- Ayalon polygons (display) -------------------------------------------
    ayalon_out = {"type": "FeatureCollection", "features": []}
    for f in ayalon["features"]:
        p = f["properties"]
        geom = shape(f["geometry"])
        ayalon_out["features"].append({
            "type": "Feature",
            "properties": {
                "authority": norm_value(p.get("שם_רש")),
                "roadName": clean(p.get("road_rashu")),
                "source": clean(p.get("source")),
                "updated": clean(p.get("date")),
            },
            "geometry": geom_display(geom, 1.0, deg_per_m),
        })
    write_js("ayalon.js", "AYALON_GEOJSON", ayalon_out)

    # --- NTA lines (display) -------------------------------------------------
    nta_out = {"type": "FeatureCollection", "features": []}
    for f in nta_feats:
        p = f["properties"]
        geom = shape(f["geometry"])
        nta_out["features"].append({
            "type": "Feature",
            "properties": {
                "authority": norm_value(p.get("TRAFAUTH")),
                "roadName": clean(p.get("ROADNAME")),
                "roadNumber": clean(p.get("ROADNUMBER")),
                "source": clean(p.get("Source")),
                "updated": clean(p.get("Date")),
            },
            "geometry": geom_display(geom, 1.0, deg_per_m),
        })
    write_js("nta.js", "NTA_GEOJSON", nta_out)

    # --- sanity summary at the default 30 m buffer ---------------------------
    buf = 30.0
    in_a = [l for l in out_lights if l["dA"] is not None and l["dA"] <= buf]
    in_n = [l for l in out_lights if l["dN"] is not None and l["dN"] <= buf]
    both = [l for l in in_a if l["dN"] is not None and l["dN"] <= buf]
    print("--- summary @ %gm buffer ---" % buf)
    print("Ayalon (initial tag): %d" % len(in_a))
    print("moved Ayalon -> NTA:  %d" % len(both))
    print("Ayalon (final):       %d" % (len(in_a) - len(both)))
    print("NTA (total):          %d" % len(in_n))
    print("untagged:             %d" % (len(out_lights) - len(in_a) - len(in_n) + len(both)))


if __name__ == "__main__":
    main()
