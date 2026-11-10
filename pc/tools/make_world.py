#!/usr/bin/env python3
"""
Genera droidsnex/gui/assets/world.json: i contorni degli stati, ognuno con il suo codice ISO.
Servono alla mappa per due cose: lo sfondo semplice mentre la mappa vettoriale si carica e la
colorazione degli stati in base al traffico (e alla mappa del report).

Fonte: Natural Earth 1:110m Admin 0 Countries (pubblico dominio, naturalearthdata.com), in GeoJSON:
https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson

    python tools/make_world.py ne_110m_admin_0_countries.geojson
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "droidsnex", "gui", "assets", "world.json")


def main(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    rings, iso, names = [], [], {}
    for feat in data["features"]:
        p = feat["properties"]
        code = p.get("ISO_A2_EH") or p.get("ISO_A2") or ""
        if len(code) != 2 or not code.isalpha():
            code = ""
        if code:
            names[code] = p.get("NAME") or code
        g = feat["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            pts, last = [], None
            for lon, lat in poly[0]:                     # solo il contorno esterno
                q = (round(lon, 1), round(lat, 1))       # 0.1° ~ 11 km: basta a zoom bassi
                if q != last:
                    pts += [q[0], q[1]]
                    last = q
            if len(pts) >= 8:
                rings.append(pts)
                iso.append(code)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"source": "Natural Earth 1:110m (public domain)", "rings": rings, "iso": iso, "names": names},
                  f, separators=(",", ":"), ensure_ascii=False)
    print(f"{OUT}: {len(rings)} contorni, {len(names)} stati, {os.path.getsize(OUT) // 1024} KB")


if __name__ == "__main__":
    main(sys.argv[1])
