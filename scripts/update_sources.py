# -*- coding: utf-8 -*-
"""Generate assets/data/sources.js from data/sources.csv.

The sources (i) dialog in index.html renders this list. To update it,
edit data/sources.csv (columns: layer, source, retrieved, updated —
saved as UTF-8, Excel-friendly) and run:

    python scripts/update_sources.py

Only the Python standard library is needed. prepare_data.py also runs
this as part of a full rebuild.
"""

import csv
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "sources.csv")
OUT = os.path.join(ROOT, "assets", "data", "sources.js")


def main():
    items = []
    with open(SRC, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            layer = (row.get("layer") or "").strip()
            source = (row.get("source") or "").strip()
            retrieved = (row.get("retrieved") or "").strip()
            updated = (row.get("updated") or "").strip()
            if not layer:
                continue
            text = layer
            if source:
                text += ": " + source
            if retrieved:
                text += ", השכבה נמשכה בתאריך " + retrieved
            if updated:
                text += ", עודכנה בתאריך " + updated + "."
            items.append(text)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("const SOURCES = ")
        json.dump(items, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";\n")
    print("wrote %s (%d sources)" % (os.path.relpath(OUT, ROOT), len(items)))


if __name__ == "__main__":
    main()
