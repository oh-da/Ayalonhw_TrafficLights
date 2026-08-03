# -*- coding: utf-8 -*-
"""Prepare web data for the Ayalon Highways / NTA traffic-lights map.

Reads the source layers under data/, then:
  1. Filters the "other traffic authorities" right-of-way layer to NTA only
     (traffic authority == "נתע").
  2. Normalizes authority values to a common form and translates property
     names from Hebrew source columns to English.
  3. Computes, for every traffic light, its distance in meters to the Ayalon
     right-of-way polygons and to the NTA right-of-way lines. The web app
     assigns lights by the lights layer's own Traffic Authority column
     (Ayalon vs NTA); an Ayalon-authority light within a user-chosen buffer
     of the NTA right of way is tagged as moved Ayalon -> NTA. Distances are
     precomputed so tagging is instant client-side without a geometry library.

Outputs JS data files under assets/data/ (plain `const` globals so the map
works when opened directly from the filesystem, no web server needed).
"""

import json
import math
import os

import shapefile
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform, unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "assets", "data")

AYALON_SRC = os.path.join(DATA, "נתיבי איילון.geojson")
NTA_SRC = os.path.join(DATA, "רשויות תמרור אחרות.geojson")

# Traffic lights shapefile (Israel TM Grid, EPSG:2039).
LIGHTS_SRC = os.path.join(DATA, "traffic_lights", "Ramzorim")

# NTA infrastructure shapefiles (Israel TM Grid, EPSG:2039 — units are meters).
LRT_SRC = os.path.join(DATA, "lrt_line", "LRT_LINE")
METRO_SRC = os.path.join(DATA, "metro_line", "METRO_LINE")
DEPO_SRC = os.path.join(DATA, "depo_metro", "DEPO_METRO")

# Fixed buffer sizes around the NTA infrastructure shapes.
LRT_BUFFER_M = 100.0
METRO_BUFFER_M = 50.0
DEPO_BUFFER_M = 500.0

# LRT filter: NTA-operated lines only.
LRT_LINES = ["Red Line", "Purple Line", "Green Line"]

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


def fmt_id(v):
    """Numeric shapefile IDs come back as floats; show whole ones as integers."""
    try:
        f = float(v)
        return str(int(f)) if f == int(f) else clean(v)
    except (TypeError, ValueError):
        return clean(v)


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


def read_shp(path):
    """Read a shapefile as (record dict, shapely geometry) pairs."""
    r = shapefile.Reader(path, encoding="utf-8")
    fields = [f[0] for f in r.fields[1:]]
    return [({k: sr.record[k] for k in fields}, shape(sr.shape.__geo_interface__))
            for sr in r.iterShapeRecords()]


def main():
    ayalon = load(AYALON_SRC)
    others = load(NTA_SRC)
    lights = read_shp(LIGHTS_SRC)  # Israel TM Grid points
    print("Traffic lights:", len(lights))

    # --- NTA infrastructure layers (Israel TM Grid, meters) ------------------
    tm_to_wgs = Transformer.from_crs(2039, 4326, always_xy=True)

    def tm_geom_to_wgs(geom, simplify_m):
        g = geom.simplify(simplify_m, preserve_topology=True)
        g = transform(tm_to_wgs.transform, g)
        return round_coords(json.loads(json.dumps(g.__geo_interface__)))

    lrt = [(rec, g) for rec, g in read_shp(LRT_SRC)
           if norm_value(rec.get("COMP")) == "נתע"
           and clean(rec.get("LINE_EG")) in LRT_LINES]
    metro = read_shp(METRO_SRC)  # no filter
    depo = read_shp(DEPO_SRC)
    print("LRT features after filter:", len(lrt))
    print("Metro features:", len(metro))
    print("Depo features:", len(depo))

    def line_layer(pairs, key, props, buffer_m):
        """Feature collections for a line layer + dissolved buffer per group."""
        lines = {"type": "FeatureCollection", "features": [{
            "type": "Feature",
            "properties": {out: clean(rec.get(src)) for out, src in props.items()},
            "geometry": tm_geom_to_wgs(g, 1.0),
        } for rec, g in pairs]}
        buffers = {"type": "FeatureCollection", "features": []}
        for group in dict.fromkeys(clean(rec.get(key)) for rec, _ in pairs):
            buf = unary_union([g.buffer(buffer_m) for rec, g in pairs
                               if clean(rec.get(key)) == group])
            buffers["features"].append({
                "type": "Feature",
                "properties": {"group": group},
                "geometry": tm_geom_to_wgs(buf, 5.0),
            })
        return {"lines": lines, "buffers": buffers, "bufferM": buffer_m}

    write_js("lrt.js", "LRT_DATA", line_layer(
        lrt, "LINE_EG",
        {"name": "NAME", "status": "STATUS", "line": "LINE_EG"}, LRT_BUFFER_M))
    write_js("metro.js", "METRO_DATA", line_layer(
        metro, "NAME", {"name": "NAME"}, METRO_BUFFER_M))

    depo_out = {"type": "FeatureCollection", "features": [], "bufferM": DEPO_BUFFER_M}
    for rec, g in depo:
        depo_out["features"].append({
            "type": "Feature",
            "properties": {"name": clean(rec.get("NAME")),
                           "status": clean(rec.get("STATUS"))},
            "geometry": tm_geom_to_wgs(g, 1.0),
            "buffer": tm_geom_to_wgs(g.buffer(DEPO_BUFFER_M), 5.0),
        })
    write_js("depo.js", "DEPO_DATA", depo_out)

    lrt_union = unary_union([g for _, g in lrt])
    metro_union = unary_union([g for _, g in metro])
    depo_union = unary_union([g for _, g in depo])

    # Per-group unions to name the nearest line for each light.
    def group_unions(pairs, key):
        by = {}
        for rec, g in pairs:
            by.setdefault(clean(rec.get(key)), []).append(g)
        return {k: unary_union(v) for k, v in by.items()}

    lrt_by_line = group_unions(lrt, "LINE_EG")
    metro_by_name = group_unions(metro, "NAME")

    # --- filter NTA features -------------------------------------------------
    nta_feats = [
        f for f in others["features"]
        if f.get("geometry") and norm_value(f["properties"].get("TRAFAUTH")) == "נתע"
    ]
    print("NTA features after filter:", len(nta_feats))

    # --- projection centered on the traffic lights ---------------------------
    lights_ll = [tm_to_wgs.transform(g.x, g.y) for _, g in lights]
    lon0 = sum(p[0] for p in lights_ll) / len(lights_ll)
    lat0 = sum(p[1] for p in lights_ll) / len(lights_ll)
    project = local_projection(lon0, lat0)
    deg_per_m = 1.0 / (6371008.8 * math.pi / 180.0)

    ayalon_geoms = [transform(project, shape(f["geometry"]))
                    for f in ayalon["features"]]
    nta_geoms = [transform(project, shape(f["geometry"])) for f in nta_feats]
    ayalon_union = unary_union(ayalon_geoms)
    nta_union = unary_union(nta_geoms)

    # --- traffic lights with distances ---------------------------------------
    out_lights = []
    for (rec, pt_tm), (lon, lat) in zip(lights, lights_ll):
        pt = transform(project, Point(lon, lat))
        d_a = ayalon_union.distance(pt)
        d_n = nta_union.distance(pt)
        d_l = lrt_union.distance(pt_tm)
        d_m = metro_union.distance(pt_tm)
        d_d = depo_union.distance(pt_tm)
        streets = [clean(rec.get(k)) for k in ("stree_1", "stree_2", "street_3")]
        out_lights.append({
            "id": fmt_id(rec.get("ID")),
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "authority": norm_value(rec.get("Current_au")),
            "name": clean(rec.get("name")),
            "city": clean(rec.get("City")),
            "status": clean(rec.get("Status")),
            "mainStreet": clean(rec.get("main_stree")),
            "streets": [s for s in streets if s],
            "source": clean(rec.get("Source")),
            "updated": clean(rec.get("Date")),
            "dA": round(d_a, 1) if d_a <= MAX_DIST_M else None,
            "dN": round(d_n, 1) if d_n <= MAX_DIST_M else None,
            "dL": round(d_l, 1) if d_l <= MAX_DIST_M else None,
            "dM": round(d_m, 1) if d_m <= MAX_DIST_M else None,
            "dD": round(d_d, 1) if d_d <= MAX_DIST_M else None,
            "nL": (min(lrt_by_line, key=lambda k: lrt_by_line[k].distance(pt_tm))
                   if d_l <= MAX_DIST_M else None),
            "nM": (min(metro_by_name, key=lambda k: metro_by_name[k].distance(pt_tm))
                   if d_m <= MAX_DIST_M else None),
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

    # --- scenario summary ----------------------------------------------------
    ay = [l for l in out_lights if l["authority"] == "נתיבי איילון"]
    nta = [l for l in out_lights if l["authority"] == "נתע"]

    def in_infra(l):
        """Inside the LRT or metro buffer (the "possible situation" trigger)."""
        return ((l["dL"] is not None and l["dL"] <= LRT_BUFFER_M)
                or (l["dM"] is not None and l["dM"] <= METRO_BUFFER_M))

    moved = [l for l in ay if in_infra(l)]
    print("--- current situation (traffic-authority column) ---")
    print("Ayalon:          %d" % len(ay))
    print("NTA:             %d" % len(nta))
    print("other authority: %d" % (len(out_lights) - len(ay) - len(nta)))
    print("--- possible situation (LRT %gm / metro %gm buffers) ---"
          % (LRT_BUFFER_M, METRO_BUFFER_M))
    print("moved Ayalon -> NTA: %d" % len(moved))
    print("  via LRT buffer:    %d" % sum(
        1 for l in moved if l["dL"] is not None and l["dL"] <= LRT_BUFFER_M))
    print("  via metro buffer:  %d" % sum(
        1 for l in moved if l["dM"] is not None and l["dM"] <= METRO_BUFFER_M))
    print("Ayalon (final):      %d" % (len(ay) - len(moved)))
    print("NTA (final):         %d" % (len(nta) + len(moved)))


if __name__ == "__main__":
    main()
