# Ayalon Highways × NTA — Traffic Light Assignment Map

An interactive HTML map that displays the **Ayalon Highways right-of-way layer**,
the **NTA right-of-way layer**, and the **metropolitan traffic-lights layer**,
and assigns each traffic light to an authority using the lights layer's own
**Traffic Authority** column, plus a buffer around the NTA right of way to
detect lights that moved from Ayalon Highways to NTA.

## Assignment logic

1. A traffic light whose **Traffic Authority** column is *Ayalon Highways*
   (`נתיבי איילון`) is tagged *Ayalon*; one whose column is *NTA* (`נת"ע`) is
   tagged *NTA*. All other authorities (municipalities, Netivei Israel, …) are
   tagged *other authority*.
2. An *Ayalon* light that falls within the buffer of the **NTA right of way**
   may now be under NTA's authority, so it is tagged **moved Ayalon → NTA**.

This makes it easy to assess how many traffic lights are moving from Ayalon
Highways to NTA. The buffer distance is adjustable live in the app
(5–200 m slider, default 30 m); all counts, colors, the list and the popups
update instantly.

### Results by buffer distance

| Buffer | Ayalon (column) | Moved → NTA | Ayalon (final) | NTA (total) |
|-------:|----------------:|------------:|---------------:|------------:|
|  10 m  | 73 | 0 | 73 | 214 |
|  30 m  | 73 | 0 | 73 | 214 |
|  50 m  | 73 | 0 | 73 | 214 |
| 100 m  | 73 | 1 | 72 | 215 |
| 200 m  | 73 | 1 | 72 | 215 |

## Running

Open `index.html` in a browser — everything (Leaflet, data) is bundled locally,
so no web server or build step is needed. Only the OpenStreetMap basemap tiles
require internet access.

## Project structure

```
index.html                  the interactive map (single page, Leaflet)
assets/vendor/leaflet/      vendored Leaflet 1.9.4 (no CDN dependency)
assets/data/                generated data files (JS globals)
  ayalon.js                 Ayalon right-of-way polygons (display-simplified)
  nta.js                    NTA right-of-way lines (filtered, display-simplified)
  lights.js                 traffic lights + precomputed distances (m) to each layer
  districts.js              district polygons (column "machoz") for the district filter
scripts/prepare_data.py     regenerates assets/data/ from the source layers
scripts/update_sources.py   regenerates the sources (i) dialog from data/sources.csv
data/                       source layers (GeoJSON + shapefiles + CSV)
design/                     the approved visual design
```

## Data pipeline (`scripts/prepare_data.py`)

Requires Python 3 with `shapely` (`pip install shapely`). Run from anywhere:

```
python3 scripts/prepare_data.py
```

What it does:

- **Filter** — the "other traffic authorities" layer (`רשויות תמרור אחרות.geojson`)
  is filtered to NTA only (traffic authority = `נתע`, after value normalization).
- **Value normalization** — authority spellings are unified to one common value:
  `נת"א` / `נת''א` → `נתיבי איילון`, `NTA` → `נת"ע` → `נתע`.
- **Column translation** — Hebrew source columns are translated to English
  property names (Traffic Authority, Road Name, Road Number, City, Status,
  Main Street, Street Name 1–3, Source, Last Updated), which the app uses as
  its field labels.
- **Sources list** — the sources (i) dialog is generated from `data/sources.csv`
  (columns: `layer`, `source`, `retrieved`, `updated`). To update the dates,
  edit the CSV and run `python3 scripts/update_sources.py` (standard library
  only, no GIS packages needed); `prepare_data.py` also runs it automatically.
- **District tagging** — the Districts layer (`data/Districts`, column
  `machoz`) is exported for display, every traffic light is assigned the
  district containing it, and every feature of every layer is tagged with the
  list of districts it intersects, so the app can filter the whole map by
  district with no client-side geometry.
- **Distance precomputation** — every traffic light gets its distance in meters
  to the Ayalon right-of-way polygons (0 if inside) and to the NTA right-of-way
  lines, using a local equal-distance projection. The app compares the NTA
  distance to the chosen buffer to detect moved lights, so re-tagging on slider
  change is instant and needs no client-side geometry library.

## Map features

- Layer toggles for the Ayalon polygons, NTA lines and traffic lights.
- District filter (Districts layer, column `machoz`): a dropdown that filters
  the traffic lights and **all** map layers to the chosen district, highlights
  it and zooms to it; the summary counts follow the filter.
- Buffer-distance slider with live re-tagging and an assignment summary
  (Ayalon per column/final, moved Ayalon → NTA, NTA total, other authority).
- Filter the lights by assignment category.
- Hover any feature for a summary tooltip; click for a full detail card
  (including each light's distance to both right-of-way layers).
- Clickable light list that flies the map to the selected light.
