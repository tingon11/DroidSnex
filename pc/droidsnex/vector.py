"""Mappa vettoriale: il mondo disegnato dal programma, nitido a ogni zoom.

Invece di ingrandire immagini già pronte (che a zoom alti diventano sgranate),
la mappa viene disegnata dai dati geografici di Natural Earth (pubblico dominio,
naturalearthdata.com): terre emerse, laghi, fiumi, confini di stato e di
regione, città. Ogni tile 256x256 è disegnata al momento per lo zoom richiesto,
a risoluzione doppia e poi ridotta (bordi lisci, senza scalini).

Due livelli di dettaglio:
  1:50m  incluso nel programma (assets/vector-50m.json.gz, ~1 MB), buono fino allo zoom 7-8
  1:10m  da scaricare in Config (~60 MB di GeoJSON, ~10 MB convertiti), buono fino allo zoom 10-11

Formato del file convertito (.json.gz): coordinate intere = gradi * q.
  land, lakes:   poligoni già tagliati in celle di `cell` gradi (pezzi piccoli = disegno veloce)
  coast, borders, states, rivers:   linee spezzate in tratti da al massimo 200 punti
  places:        [nome, lat, lon, zoom minimo]
"""
from __future__ import annotations

import gzip
import json
import math
import os
import threading
import urllib.request
from array import array
from typing import Callable

from PIL import Image, ImageChops, ImageDraw

from .geo import USER_AGENT

NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/{name}.geojson"
LAYER_FILES = {
    "land": "ne_{s}_land",
    "lakes": "ne_{s}_lakes",
    "borders": "ne_{s}_admin_0_boundary_lines_land",
    "states": "ne_{s}_admin_1_states_provinces_lines",
    "rivers": "ne_{s}_rivers_lake_centerlines",
    "places": "ne_{s}_populated_places_simple",
}
POLY_LAYERS = ("land", "lakes")
LINE_LAYERS = ("coast", "borders", "states", "rivers")
TILE = 256
SS = 2                   # sovracampionamento: disegno a 512 px e riduco a 256
MAX_LAT = 85.05112878
# livelli di semplificazione: (zoom fino a cui si usa, zoom di riferimento per la tolleranza)
LODS = ((2, 2), (4, 4), (6, 6), (99, 99))

# colori: scuro (come l'interfaccia) e chiaro
STYLES = {
    "dark": {"sea": "#070b11", "land": "#121a24", "coast": "#2a3a4c", "lake": "#0a1018", "river": "#13263a",
             "border": "#3b4d61", "state": "#1f2b38", "place": "#7d8a98", "dot": "#55626f", "grid": "#0c121a"},
    "light": {"sea": "#c9d6e3", "land": "#f2efe9", "coast": "#9fb3c8", "lake": "#c9d6e3", "river": "#a9c1d9",
              "border": "#9a8fa8", "state": "#d2cbd9", "place": "#4a5560", "dot": "#6b7682", "grid": "#d6e0ea"},
}


# ---------------------------------------------------------------------------- conversione

def _clip(ring: list, x0: int, y0: int, x1: int, y1: int) -> list:
    """Sutherland-Hodgman: ritaglia un poligono (lista di (x, y)) su un rettangolo."""
    def edge(pts, inside, cross):
        out = []
        n = len(pts)
        for i in range(n):
            cur, prev = pts[i], pts[i - 1]
            ci, pi = inside(cur), inside(prev)
            if ci:
                if not pi:
                    out.append(cross(prev, cur))
                out.append(cur)
            elif pi:
                out.append(cross(prev, cur))
        return out

    def at_x(x):
        return lambda a, b: (x, round(a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0])))

    def at_y(y):
        return lambda a, b: (round(a[0] + (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1])), y)

    pts = ring
    for inside, cross in ((lambda p: p[0] >= x0, at_x(x0)), (lambda p: p[0] <= x1, at_x(x1)),
                          (lambda p: p[1] >= y0, at_y(y0)), (lambda p: p[1] <= y1, at_y(y1))):
        if not pts:
            break
        pts = edge(pts, inside, cross)
    return pts


def _quant(coords, q: int) -> list:
    out, last = [], None
    for c in coords:
        p = (round(c[0] * q), round(c[1] * q))
        if p != last:
            out.append(p)
            last = p
    return out


def _flat(pts) -> list:
    return [v for p in pts for v in p]


def convert(paths: dict[str, str], out_path: str, q: int = 100, cell: int = 10,
            progress: Callable[[str], None] | None = None) -> None:
    """GeoJSON di Natural Earth (un file per layer) -> file compatto per VectorMap."""
    data: dict = {"v": 1, "q": q, "cell": cell, "source": "Natural Earth (public domain)"}
    for layer in ("land", "lakes", "borders", "states", "rivers", "places"):
        if progress:
            progress(layer)
        path = paths.get(layer)
        if not path or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            feats = json.load(f).get("features", [])
        if layer == "places":
            out = []
            for ft in feats:
                p = ft.get("properties") or {}
                g = (ft.get("geometry") or {}).get("coordinates")
                if not g:
                    continue
                mz = p.get("min_zoom") or (p.get("scalerank", 5) / 1.6 + 2)
                out.append([p.get("name") or p.get("nameascii") or "", round(g[1] * q), round(g[0] * q),
                            round(float(mz), 1)])
            data[layer] = out
            continue
        if layer in POLY_LAYERS:
            pieces, coast = [], []
            for ft in feats:
                g = ft.get("geometry") or {}
                if layer == "lakes" and (ft.get("properties") or {}).get("scalerank", 0) > 8:
                    continue
                polys = g.get("coordinates", [])
                if g.get("type") == "Polygon":
                    polys = [polys]
                elif g.get("type") != "MultiPolygon":
                    continue
                for poly in polys:
                    for k, ring in enumerate(poly):
                        r = _quant(ring, q)
                        if len(r) < 4:
                            continue
                        coast.append(r + [r[0]])
                        # i buchi delle terre (es. grandi laghi interni) finiscono tra i laghi
                        target = pieces if (k == 0 or layer == "lakes") else data.setdefault("_holes", [])
                        xs, ys = [p[0] for p in r], [p[1] for p in r]
                        c = cell * q
                        for cx in range(math.floor(min(xs) / c), math.floor(max(xs) / c) + 1):
                            for cy in range(math.floor(min(ys) / c), math.floor(max(ys) / c) + 1):
                                bx, by = cx * c, cy * c
                                if min(xs) >= bx and max(xs) <= bx + c and min(ys) >= by and max(ys) <= by + c:
                                    part = r
                                else:
                                    part = _clip(r, bx, by, bx + c, by + c)
                                if len(part) >= 3:
                                    target.append(_flat(part))
            data[layer] = pieces
            if layer == "land":
                data["coast"] = [_flat(seg) for line in coast for seg in _chunks(line)]
            continue
        lines = []
        for ft in feats:
            g = ft.get("geometry") or {}
            parts = g.get("coordinates", [])
            if g.get("type") == "LineString":
                parts = [parts]
            elif g.get("type") != "MultiLineString":
                continue
            for part in parts:
                r = _quant(part, q)
                if len(r) >= 2:
                    lines += [_flat(seg) for seg in _chunks(r)]
        data[layer] = lines
    data["lakes"] = data.get("lakes", []) + data.pop("_holes", [])
    tmp = out_path + ".part"
    with gzip.open(tmp, "wt", encoding="utf-8", compresslevel=9) as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
    os.replace(tmp, out_path)


def _chunks(pts: list, n: int = 200) -> list:
    out = []
    for i in range(0, len(pts) - 1, n - 1):
        seg = pts[i:i + n]
        if len(seg) >= 2:
            out.append(seg)
    return out


def download_10m(out_path: str, work_dir: str, progress: Callable[[str, int, int], None] | None = None,
                 cancel: Callable[[], bool] | None = None, timeout: float = 60) -> None:
    """Scarica i GeoJSON 1:10m di Natural Earth e li converte in `out_path`."""
    os.makedirs(work_dir, exist_ok=True)
    paths = {}
    layers = list(LAYER_FILES)
    for i, layer in enumerate(layers):
        name = LAYER_FILES[layer].format(s="10m")
        dest = os.path.join(work_dir, name + ".geojson")
        paths[layer] = dest
        if os.path.isfile(dest) and os.path.getsize(dest) > 1000:
            continue
        req = urllib.request.Request(NE_URL.format(name=name), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(dest + ".part", "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                if cancel and cancel():
                    raise InterruptedError
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress:
                    progress(f"{i + 1}/{len(layers)} {name}", got, total)
        os.replace(dest + ".part", dest)
    if progress:
        progress("convert", 0, 0)
    convert(paths, out_path, q=1000, cell=5)
    for p in paths.values():                       # i GeoJSON non servono più
        try:
            os.remove(p)
        except OSError:
            pass
    try:
        os.rmdir(work_dir)                         # la cartella di lavoro resta vuota: via anche quella
    except OSError:
        pass


# ---------------------------------------------------------------------------- disegno

def _merc(lat: float, lon: float) -> tuple[float, float]:
    """Gradi -> coordinate Web Mercator normalizzate 0..1."""
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    s = math.sin(math.radians(lat))
    return (lon + 180.0) / 360.0, 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)


class _Feature:
    __slots__ = ("bbox", "lods")

    def __init__(self, bbox, lods):
        self.bbox, self.lods = bbox, lods


class VectorMap:
    """Dati vettoriali caricati in memoria e disegno delle tile."""

    def __init__(self, path: str):
        self.path = path
        self.layers: dict[str, list[_Feature]] = {}
        self.places: list[tuple[str, float, float, float]] = []   # nome, x, y (0..1), zoom minimo
        self.detail = ""
        self.cell = 10                # gradi delle celle in cui sono tagliati i poligoni
        self.ready = False
        self.error = ""

    def load(self) -> "VectorMap":
        try:
            with gzip.open(self.path, "rt", encoding="utf-8") as f:
                data = json.load(f)
            q = data.get("q", 100)
            self.detail = "1:10m" if q >= 1000 else "1:50m"
            self.cell = data.get("cell", 10)
            cell = self.cell * q
            proj: dict[int, tuple[float, float]] = {}
            for layer in POLY_LAYERS + LINE_LAYERS:
                self.layers[layer] = [f for f in (self._feature(r, q, cell if layer in POLY_LAYERS else 0, proj)
                                                  for r in data.get(layer, [])) if f]
            for name, lat, lon, mz in data.get("places", []):
                x, y = _merc(lat / q, lon / q)
                self.places.append((name, x, y, mz))
            self.places.sort(key=lambda p: p[3])
            self.ready = True
        except (OSError, ValueError, KeyError, TypeError, EOFError) as e:
            self.error = str(e)
        return self

    @staticmethod
    def _feature(flat: list, q: int, cell: int, proj: dict) -> _Feature | None:
        n = len(flat) // 2
        if n < 2:
            return None
        xs = array("d")
        ys = array("d")
        keep = bytearray(n)                       # punti sui bordi delle celle: non si tolgono mai
        for i in range(n):
            lon, lat = flat[2 * i], flat[2 * i + 1]
            key = lon * 4_000_000 + lat
            p = proj.get(key)
            if p is None:
                p = proj[key] = _merc(lat / q, lon / q)
            xs.append(p[0])
            ys.append(p[1])
            if cell and (lon % cell == 0 or lat % cell == 0):
                keep[i] = 1
        keep[0] = keep[n - 1] = 1
        bbox = (min(xs), min(ys), max(xs), max(ys))
        lods = []
        prev = None
        for _upto, zref in LODS:
            tol = 0.7 / (TILE * (1 << min(zref, 20)))
            if zref >= 99:
                pts = array("d", (v for i in range(n) for v in (xs[i], ys[i])))
            else:
                if bbox[2] - bbox[0] < tol and bbox[3] - bbox[1] < tol and not cell:
                    lods.append(None)              # troppo piccolo a questo zoom
                    continue
                pts = array("d")
                lx = ly = None
                t2 = tol * tol
                for i in range(n):
                    x, y = xs[i], ys[i]
                    if keep[i] or lx is None or (x - lx) ** 2 + (y - ly) ** 2 >= t2:
                        pts.append(x)
                        pts.append(y)
                        lx, ly = x, y
                if len(pts) < 4 or (cell and len(pts) < 6):
                    lods.append(None)
                    continue
                if prev is not None and len(prev) == len(pts):
                    pts = prev                     # nessuna differenza: condividiamo la memoria
            lods.append(pts)
            prev = pts
        return _Feature(bbox, lods)

    @staticmethod
    def _lod(z: int) -> int:
        for i, (upto, _zref) in enumerate(LODS):
            if z <= upto:
                return i
        return len(LODS) - 1

    def render(self, z: int, tx: int, ty: int, style: str = "dark") -> Image.Image:
        st = STYLES.get(style, STYLES["dark"])
        n = 1 << z
        size = TILE * SS
        scale = TILE * n * SS
        ox, oy = tx * TILE * SS, ty * TILE * SS
        pad = 4 / (TILE * n)
        bx0, by0, bx1, by1 = tx / n - pad, ty / n - pad, (tx + 1) / n + pad, (ty + 1) / n + pad
        img = Image.new("RGB", (size, size), st["sea"])
        d = ImageDraw.Draw(img)
        lod = self._lod(z)

        def feats(layer):
            for f in self.layers.get(layer, ()):
                b = f.bbox
                if b[2] < bx0 or b[0] > bx1 or b[3] < by0 or b[1] > by1:
                    continue
                pts = f.lods[lod]
                if pts is not None:
                    yield [((pts[i] * scale - ox), (pts[i + 1] * scale - oy)) for i in range(0, len(pts), 2)]

        # terre e laghi: prima su una maschera, poi colorati (vedi _seams)
        for layer, color in (("land", st["land"]), ("lakes", st["lake"])):
            mask = Image.new("L", (size, size), 0)
            md = ImageDraw.Draw(mask)
            for p in feats(layer):
                if len(p) >= 3:
                    md.polygon(p, fill=255)
            self._seams(mask, z, tx, ty)
            img.paste(color, (0, 0), mask)
        w1 = SS                                        # 1 px dopo la riduzione
        if z >= 4:
            for p in feats("rivers"):
                d.line(p, fill=st["river"], width=w1)
        if z >= 3:
            for p in feats("states"):
                d.line(p, fill=st["state"], width=w1)
        for p in feats("coast"):
            d.line(p, fill=st["coast"], width=w1)
        bw = w1 if z < 5 else int(SS * 1.5)
        for p in feats("borders"):
            d.line(p, fill=st["border"], width=bw)
        return img.resize((TILE, TILE), Image.LANCZOS)

    def _seams(self, mask: Image.Image, z: int, tx: int, ty: int) -> None:
        """I poligoni sono tagliati in celle: il taglio lascia dei "ponti" larghi zero lungo il bordo della
        cella, che il disegno renderebbe come righine nel mare. Sul bordo teniamo un pixel solo se accanto,
        da almeno un lato, c'è davvero terra (o lago)."""
        size = mask.size[0]
        n = 1 << z
        scale = TILE * n * SS
        lon0, lon1 = tx / n * 360 - 180, (tx + 1) / n * 360 - 180
        lines_x = [round(((lon + 180) / 360) * scale - tx * TILE * SS)
                   for lon in range(math.ceil(lon0 / self.cell) * self.cell, math.floor(lon1) + 1, self.cell)]
        lat_top = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * ty / n))))
        lat_bot = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + 1) / n))))
        lines_y = [round(_merc(lat, 0)[1] * scale - ty * TILE * SS)
                   for lat in range(math.ceil(lat_bot / self.cell) * self.cell, math.floor(lat_top) + 1, self.cell)]
        for vertical, positions in ((True, lines_x), (False, lines_y)):
            for b in positions:
                if b < -1 or b > size:
                    continue

                def strip(a, w):
                    a = max(0, min(size - w, a))
                    return mask.crop((a, 0, a + w, size) if vertical else (0, a, size, a + w))

                sides = []
                if b - 2 >= 0:
                    sides.append(strip(b - 2, 1))
                if b + 2 < size:
                    sides.append(strip(b + 2, 1))
                if not sides:
                    continue
                near = sides[0] if len(sides) == 1 else ImageChops.lighter(*sides)
                a = max(0, min(size - 3, b - 1))
                near = near.resize((3, size) if vertical else (size, 3), Image.NEAREST)
                mask.paste(ImageChops.darker(strip(a, 3), near), (a, 0) if vertical else (0, a))

    def places_in(self, z: int, x0: float, y0: float, x1: float, y1: float, limit: int = 150):
        """Città visibili a questo zoom nel riquadro (coordinate 0..1)."""
        out = []
        for name, x, y, mz in self.places:
            if mz > z + 1.2:
                break
            if x0 <= x <= x1 and y0 <= y <= y1:
                out.append((name, x, y))
                if len(out) >= limit:
                    break
        return out


def load_async(path: str, done: Callable[[VectorMap], None]) -> None:
    def run():
        done(VectorMap(path).load())
    threading.Thread(target=run, daemon=True, name="vector-load").start()
