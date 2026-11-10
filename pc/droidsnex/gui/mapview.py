# DroidSnex — interfaccia grafica.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Mappa del mondo con le connessioni del telefono.

Un piccolo smartphone nella tua posizione, una linea sottile verso la città di
ogni destinazione: verde se fidata, rossa se non fidata. Sulle linee scorrono
degli impulsi con la scia che rappresentano il traffico (verso la destinazione = dati in
uscita, verso il telefono = dati in entrata): numero, grandezza e spessore della linea
crescono con i byte al secondo che stanno passando.

Animazioni: una connessione nuova si annuncia con una scintilla che parte dal telefono e un
lampo ad anelli sulla destinazione; le città con connessioni aperte pulsano; lo zoom è
progressivo e il trascinamento continua per inerzia. A zoom bassi le città vicine sono
raggruppate in un solo punto; un punto con più IP è una pallina con il numero degli IP (clic =
ingrandisci) e dallo zoom SPREAD_Z gli IP si aprono in punti distinti, vicini, sempre più larghi
man mano che si ingrandisce; gli stati si colorano in
base al traffico scambiato (pulsante ◐).

Lo sfondo è la mappa vettoriale Natural Earth; finché si carica, viene disegnato il
contorno degli stati. Rotella = zoom, trascina = sposta, clic su un punto = dettagli.
"""
from __future__ import annotations

import json
import ipaddress
import math
import os
import queue
import threading
import time
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from ..i18n import tr
from ..vector import STYLES, VectorMap
from . import theme
from .. import risk as risk_mod
from .widgets import ScaleRow

TILE = 256
MAX_LAT = 85.05112878
WORLD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "world.json")

SEA = "#080c12"
LAND = "#111821"
LAND_EDGE = "#223040"
GRID = "#0e141c"
PARTICLE_IN = "#e6edf5"      # puntini del traffico in entrata (verso il telefono)
FPS = 30
CLUSTER_PX = 18              # città più vicine di così (a schermo) diventano un punto solo
SPREAD_Z = 4                 # da questo zoom gli IP di uno stesso punto si aprono in punti distinti
BORN_SEC = 1.3               # durata del lampo di una connessione nuova
ZOOM_FRAMES = 7              # fotogrammi dello zoom progressivo
OVERLAY_TAGS = ("link", "pt", "phone", "pp", "tip", "label", "fx")
HEAT_ALPHA = (0, 40, 58, 76, 96, 120)    # opacità degli stati per livello di traffico (0 = niente)


@dataclass
class Link:
    """Una linea sulla mappa: un IP di destinazione, con la sua città e i nomi che ci finiscono."""
    key: str                # "lat,lon|ip|t/u": le linee con lo stesso prefisso vanno nella stessa città
    lat: float
    lon: float
    place: str
    trusted: bool
    ip: str = ""
    dests: list = field(default_factory=list)    # nomi delle destinazioni
    apps: list = field(default_factory=list)     # app che generano i collegamenti
    conns: int = 0
    active: int = 0
    total: int = 0          # byte totali (entrata + uscita)
    rate_out: float = 0.0   # byte/s in uscita (telefono -> destinazione)
    rate_in: float = 0.0    # byte/s in entrata
    risk: int = 0           # pericolosità 0..5 (solo non fidate), vedi risk.py
    risk_text: str = ""
    country: str = ""       # codice ISO dello stato (per la colorazione in base al traffico)


def _mix(c1: str, c2: str, t: float) -> str:
    """Colore intermedio: t=0 -> c1, t=1 -> c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _rgb(c: str) -> tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def heat_levels(volumes: dict[str, float]) -> dict[str, int]:
    """Stato -> livello 1..5 in base ai byte scambiati rispetto al massimo (1% -> 1, 10% -> 2, 100% -> 5)."""
    top = max(volumes.values(), default=0)
    if top <= 0:
        return {}
    return {iso: 1 + min(4, int(4 * (v / top) ** 0.4)) for iso, v in volumes.items() if iso and v > 0}


def spread_sep(z: int) -> float:
    """Distanza a schermo fra gli IP di uno stesso punto: 0 = ancora una pallina sola, poi cresce con lo zoom."""
    return 0.0 if z < SPREAD_Z else min(22.0, 9.0 + 4.0 * (z - SPREAD_Z))


def spread_offsets(n: int, sep: float) -> list[tuple[float, float]]:
    """Dove mettere n punti attorno al centro, vicini ma distinti (distanti circa `sep`): pochi su un
    cerchio, tanti su una spirale a girasole che riempie il disco."""
    if n <= 1 or sep <= 0:
        return [(0.0, 0.0)] * max(n, 0)
    if n <= 8:
        r = max(sep * 0.6, n * sep / (2 * math.pi))
        return [(r * math.cos(-math.pi / 2 + 2 * math.pi * i / n), r * math.sin(-math.pi / 2 + 2 * math.pi * i / n))
                for i in range(n)]
    golden = math.pi * (3 - math.sqrt(5))
    return [(sep * 0.62 * math.sqrt(i + 0.5) * math.cos(i * golden), sep * 0.62 * math.sqrt(i + 0.5) * math.sin(i * golden))
            for i in range(n)]


def cluster_cities(cities: list[tuple[str, float, float, int]], radius: float) -> list[list[str]]:
    """Raggruppa le città vicine a schermo. `cities` = (chiave, x, y, peso): la più pesante fa da centro."""
    out: list[tuple[float, float, list[str]]] = []
    for key, x, y, _w in sorted(cities, key=lambda c: (-c[3], c[0])):
        for cx, cy, keys in out:
            if radius > 0 and math.hypot(cx - x, cy - y) <= radius:
                keys.append(key)
                break
        else:
            out.append((x, y, [key]))
    return [keys for _x, _y, keys in out]


def _rate(b: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if b < 1024 or unit == "GB/s":
            return f"{b:.0f} {unit}" if unit == "B/s" else f"{b:.1f} {unit}"
        b /= 1024
    return ""


def line_width(rate: float) -> float:
    """1 px a riposo, fino a 5 px con qualche MB/s: scala logaritmica."""
    if rate <= 0:
        return 1.0
    return round(min(5.0, 1.0 + 1.4 * math.log10(1 + rate / 2048)), 1)


def particles_for(rate: float) -> int:
    if rate <= 0:
        return 0
    return max(1, min(8, int(math.log2(1 + rate / 1024)) + 1))


def project(lat: float, lon: float, z: int) -> tuple[float, float]:
    """Lat/lon -> pixel del mondo Web Mercator a zoom z (il mondo è largo 256*2^z)."""
    n = TILE * (1 << z)
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    s = math.sin(math.radians(lat))
    x = (lon + 180.0) / 360.0 * n
    y = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * n
    return x, y


def unproject(x: float, y: float, z: int) -> tuple[float, float]:
    n = TILE * (1 << z)
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lat, lon


def great_circle(lat1, lon1, lat2, lon2, steps: int = 48) -> list[tuple[float, float]]:
    """Punti lungo l'arco di cerchio massimo (la rotta più breve), longitudini 'srotolate'."""
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 +
                                math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
    if d < 1e-6:
        return [(lat1, lon1), (lat2, lon2)]
    steps = max(4, min(steps, int(math.degrees(d) / 2) + 4))
    out, prev = [], None
    for i in range(steps + 1):
        f = i / steps
        a = math.sin((1 - f) * d) / math.sin(d)
        b = math.sin(f * d) / math.sin(d)
        x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
        y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
        zz = a * math.sin(p1) + b * math.sin(p2)
        lat = math.degrees(math.atan2(zz, math.hypot(x, y)))
        lon = math.degrees(math.atan2(y, x))
        if prev is not None:                       # niente salti a ±180°
            while lon - prev > 180:
                lon -= 360
            while lon - prev < -180:
                lon += 360
        out.append((lat, lon))
        prev = lon
    return out


def _ip_sort(ip: str):
    try:
        a = ipaddress.ip_address(ip)
        return (a.version, int(a))
    except ValueError:
        return (9, 0)


def offset_path(pts: list, gap: float) -> list:
    """Sposta la linea di lato (a sinistra se gap > 0): parte dal telefono, si allarga a metà
    e torna a coincidere alla destinazione: le linee verso la stessa città si aprono a ventaglio lungo il
    percorso ma partono e arrivano nello stesso punto."""
    n = len(pts)
    if n < 2:
        return pts
    out = []
    for i, (x, y) in enumerate(pts):
        a, b = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        t = i / (n - 1)
        f = gap * 2.5 * math.sin(math.pi * t)          # 0 alle due estremità: stesso punto finale
        out.append((x - dy / d * f, y + dx / d * f))
    return out


class MapView(ctk.CTkFrame):
    def __init__(self, master, fonts: theme.Fonts,
                 on_select: Callable[[Link | None], None] | None = None, dark: bool = True):
        super().__init__(master, fg_color=SEA, corner_radius=0)
        self.fonts = fonts
        self.dark = dark
        self.on_home = None                       # callback(lat, lon): "Imposta qui la mia posizione" (clic destro)
        self.vector: VectorMap | None = None      # mappa vettoriale (Natural Earth), quando è caricata
        self._vq: queue.LifoQueue = queue.LifoQueue()   # tile da disegnare (l'ultima chiesta per prima)
        self._vdone: queue.Queue = queue.Queue()
        self._vpending: set = set()
        self._vpil: OrderedDict = OrderedDict()   # tile vettoriali già disegnate (PIL), per gli zoom vicini
        self._vredraw = None
        threading.Thread(target=self._vworker, daemon=True, name="vector-tiles").start()
        self.on_select = on_select
        self.on_detach: Callable[[], None] | None = None      # pulsante "stacca / riaggancia"
        self.canvas = tk.Canvas(self, bg=SEA, highlightthickness=0, bd=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)

        self.z = 2
        self.cx, self.cy = project(25, 10, self.z)
        self.home: tuple[float, float] | None = None
        self.home_name = ""
        self.links: list[Link] = []
        self.selected: str | None = None
        self.unlocated = 0
        self.geo_ok = False
        self.active = False                       # animazione solo quando il tab è visibile
        self._tiles: OrderedDict = OrderedDict()  # (z,x,y,dark) -> PhotoImage | None
        self._world, self._world_iso = self._load_world()
        self._world_px: dict[int, list] = {}
        self._paths: list[dict] = []              # percorsi a schermo per i puntini
        self._drag: tuple[int, int] | None = None
        self._moved = 0
        self._drag_acc = 0                        # px trascinati dall'ultimo ridisegno
        self._vel: list[tuple[float, int, int]] = []   # ultimi punti del trascinamento (per l'inerzia)
        self._glide: list | None = None           # [vx, vy, istante, fotogrammi]: scorrimento per inerzia
        self._zoom: dict | None = None            # zoom progressivo in corso
        self._zoom_img = None
        self.heat = True                          # stati colorati in base al traffico
        self.on_heat: Callable[[bool], None] | None = None
        self._heat: dict[str, int] = {}           # stato ISO -> livello 1..5
        self._heat_img = None
        self._heat_pil = None
        self._known: set[str] = set()             # linee già viste (le nuove lampeggiano)
        self._born: dict[str, float] = {}         # linea -> istante della comparsa
        self._fx: list[dict] = []                 # lampi delle connessioni nuove
        self._rings: list[tuple] = []             # anelli pulsanti (città attive, telefono)
        self._fitted = False
        self._sig = None

        c = self.canvas
        c.bind("<Configure>", lambda e: self.redraw())
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Button-3>", self._context)
        c.bind("<MouseWheel>", lambda e: self.zoom_at(1 if e.delta > 0 else -1, e.x, e.y))
        c.bind("<Button-4>", lambda e: self.zoom_at(1, e.x, e.y))      # Linux
        c.bind("<Button-5>", lambda e: self.zoom_at(-1, e.x, e.y))
        c.bind("<Double-Button-1>", lambda e: self.zoom_at(1, e.x, e.y))
        # punti e linee sono cliccabili: passando sopra compare il riepilogo
        c.bind("<Motion>", self._hover)
        c.bind("<Leave>", lambda e: c.delete("tip"))
        self._build_overlay()
        self.after(1000 // FPS, self._animate)

    # ------------------------------------------------------------------ interfaccia
    def _build_overlay(self) -> None:
        f = self.fonts
        self.legend = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=4, border_width=1,
                                   border_color=theme.BORDER)
        self.legend.place(x=12, y=12)
        row = ctk.CTkFrame(self.legend, fg_color="transparent")
        row.pack(anchor="w", padx=10, pady=(8, 2))
        self.lg_untrusted = ctk.CTkLabel(row, text="● " + tr("non fidate") + " 0", font=f.bold, text_color=theme.ERR)
        self.lg_untrusted.pack(side="left")
        self.lg_trusted = ctk.CTkLabel(row, text="● " + tr("fidate") + " 0", font=f.bold, text_color=theme.OK)
        self.lg_trusted.pack(side="left", padx=(14, 0))
        ScaleRow(self.legend, f, [(c, tr(n)) for c, n in zip(risk_mod.COLORS, risk_mod.NAMES)],
                 tr("pericolosità:")).pack(anchor="w", padx=2, pady=(0, 2))
        self.lg_rate = ctk.CTkLabel(self.legend, text="↑ 0 B/s   ↓ 0 B/s", font=(theme.mono_font(), 11),
                                    text_color=theme.TEXT, anchor="w")
        self.lg_rate.pack(anchor="w", padx=10)
        ctk.CTkLabel(self.legend, text=tr("puntini colorati = uscita · bianchi = entrata") + "\n"
                     + tr("spessore = byte al secondo") + "\n"
                     + tr("stati più chiari = più traffico · numero = IP nello stesso punto"), font=f.tiny, text_color=theme.TEXT_DIM,
                     justify="left", anchor="w").pack(anchor="w", padx=10, pady=(2, 8))

        tools = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=4, border_width=1, border_color=theme.BORDER)
        tools.place(relx=1.0, x=-12, y=12, anchor="ne")
        # in cima: stacca la mappa in una finestra separata / riagganciala
        self.detach_btn = ctk.CTkButton(tools, text="⧉", width=30, height=28, corner_radius=4, fg_color="transparent",
                                        hover_color=theme.HOVER, text_color=theme.ACCENT, font=(theme.mono_font(), 14),
                                        command=lambda: self.on_detach and self.on_detach())
        self.detach_btn.pack(padx=3, pady=(2, 4))
        for text, cmd in (("+", lambda: self.zoom_at(1)), ("−", lambda: self.zoom_at(-1)),
                          ("⌂", self.center_home), ("◯", self.fit_world)):
            ctk.CTkButton(tools, text=text, width=30, height=28, corner_radius=4, fg_color="transparent",
                          hover_color=theme.HOVER, text_color=theme.TEXT_SOFT, font=(theme.mono_font(), 14),
                          command=cmd).pack(padx=3, pady=2)
        # stati colorati in base al traffico: acceso / spento
        self.heat_btn = ctk.CTkButton(tools, text="◐", width=30, height=28, corner_radius=4, fg_color="transparent",
                                      hover_color=theme.HOVER, font=(theme.mono_font(), 14), command=self.toggle_heat,
                                      text_color=theme.ACCENT if self.heat else theme.TEXT_FAINT)
        self.heat_btn.pack(padx=3, pady=(2, 4))

        self.note = ctk.CTkLabel(self, text="", font=f.small, text_color=theme.WARN, fg_color=theme.PANEL,
                                 corner_radius=4, justify="left", anchor="w")
        self.attrib = ctk.CTkLabel(self, text="", font=f.tiny, text_color=theme.TEXT_DIM, fg_color=SEA)
        self.attrib.place(relx=1.0, rely=1.0, x=-8, y=-4, anchor="se")

    def set_note(self, text: str) -> None:
        if text:
            self.note.configure(text="  " + text + "  ")
            self.note.place(x=12, rely=1.0, y=-12, anchor="sw")
        else:
            self.note.place_forget()

    # ------------------------------------------------------------------ dati
    def set_home(self, lat: float | None, lon: float | None, name: str = "") -> None:
        self.home = (lat, lon) if lat is not None and lon is not None else None
        self.home_name = name
        self._sig = None
        self.redraw()

    def set_links(self, links: list[Link], unlocated: int, geo_ok: bool) -> None:
        self.links, self.unlocated, self.geo_ok = links, unlocated, geo_ok
        # linee mai viste: lampo (non quando ne arrivano molte insieme, es. all'apertura di una sessione)
        now = time.monotonic()
        ids = {x.key.rsplit("|", 1)[0]: x.key for x in links}
        fresh = [i for i in ids if i not in self._known]
        if not links:
            self._known.clear()
            self._born.clear()
        elif len(fresh) <= 12:
            for i in fresh:
                self._born[i] = now
        self._known.update(ids)
        for i in [i for i, t in self._born.items() if now - t > BORN_SEC]:
            del self._born[i]
        vol: dict[str, float] = {}
        for x in links:
            if x.country:
                vol[x.country.upper()] = vol.get(x.country.upper(), 0) + max(1, x.total)
        heat = heat_levels(vol)
        heat_changed = heat != self._heat
        self._heat = heat
        n_u = sum(1 for x in links if not x.trusted)
        out = sum(x.rate_out for x in links)
        inn = sum(x.rate_in for x in links)
        self.lg_untrusted.configure(text=f"● {tr('non fidate')} {n_u}")
        self.lg_trusted.configure(text=f"● {tr('fidate')} {len(links) - n_u}")
        self.lg_rate.configure(text=f"↑ {_rate(out):>10}   ↓ {_rate(inn):>10}")
        notes = []
        if not geo_ok:
            notes.append(tr("Database delle città assente: scarica DB-IP City Lite nel tab Config."))
        if self.home is None:
            notes.append(tr("Imposta la tua posizione nel tab Config (o rilevala dall'IP pubblico)."))
        if unlocated:
            notes.append(tr("{n} destinazioni senza posizione (IP privati o non presenti nel database).", n=unlocated))
        self.set_note("\n  ".join(notes))
        if self.active and not self._zoom:
            if heat_changed and self.heat and not self._drag and not self._glide:
                self.redraw()                      # cambia la colorazione degli stati: anche lo sfondo
            else:
                self._draw_overlay()

    def toggle_heat(self) -> None:
        self.heat = not self.heat
        self.heat_btn.configure(text_color=theme.ACCENT if self.heat else theme.TEXT_FAINT)
        if self.on_heat:
            self.on_heat(self.heat)
        self.redraw()

    # ------------------------------------------------------------------ vista
    @property
    def world(self) -> int:
        return TILE * (1 << self.z)

    def max_zoom(self) -> int:
        if self._vector_on():
            return 11 if self.vector.detail == "1:10m" else 8
        return 7

    def fit_world(self) -> None:
        w = max(self.canvas.winfo_width(), 200)
        z = 1
        while TILE * (1 << (z + 1)) <= w * 1.25 and z < 4:
            z += 1
        self.z = z
        self.cx, self.cy = project(25, 10 if self.home is None else self.home[1], z)
        self.redraw()

    def center_home(self) -> None:
        if self.home:
            self.z = max(self.z, 4)
            self.cx, self.cy = project(*self.home, self.z)
            self.redraw()

    def zoom_at(self, step: int, sx: float | None = None, sy: float | None = None, animate: bool = True) -> None:
        """Zoom di `step` livelli tenendo fermo il punto (sx, sy): progressivo, in pochi fotogrammi."""
        if self._zoom:
            self._zoom_finish()
        nz = max(1, min(self.max_zoom(), self.z + step))
        if nz == self.z:
            return
        self._glide = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        sx = w / 2 if sx is None else sx
        sy = h / 2 if sy is None else sy
        st = self._zoom = {"nz": nz, "sx": sx, "sy": sy, "f": 2.0 ** (nz - self.z), "i": 0, "k": 1.0, "snap": None}
        if not animate or not self.active or w < 50:
            return self._zoom_finish()
        c = self.canvas
        c.delete("tip")
        st["snap"] = self._snapshot() if self._vector_on() else None
        if st["snap"] is not None:
            c.delete("base")
            st["item"] = c.create_image(0, 0, anchor="nw", tags=("zoomfx",))
            c.tag_lower(st["item"])
        self._zoom_step()

    def _snapshot(self):
        """La mappa di sfondo com'è ora sullo schermo (tile già disegnate + colorazione degli stati)."""
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        style = "dark" if self.dark else "light"
        im = Image.new("RGB", (w, h), STYLES[style]["sea"])
        ox, oy = self._offset()
        n = 1 << self.z
        for ty in range(max(0, math.floor(-oy / TILE)), min(n - 1, math.floor((h - oy) / TILE)) + 1):
            for tx in range(math.floor(-ox / TILE), math.floor((w - ox) / TILE) + 1):
                t = self._vpil.get((style, self.z, tx % n, ty))
                if t is not None:
                    im.paste(t, (round(tx * TILE + ox), round(ty * TILE + oy)))
        if self.heat and self._heat_pil is not None and self._heat_pil.size == im.size:
            im.paste(self._heat_pil, (0, 0), self._heat_pil)
        return im

    def _zoom_step(self) -> None:
        st = self._zoom
        if st is None:
            return
        try:
            c = self.canvas
            st["i"] += 1
            t = st["i"] / ZOOM_FRAMES
            k = st["f"] ** (1 - (1 - t) ** 3)              # parte veloce e rallenta
            rel, st["k"] = k / st["k"], k
            sx, sy = st["sx"], st["sy"]
            for tag in OVERLAY_TAGS + (() if st["snap"] is not None else ("base",)):
                c.scale(tag, sx, sy, rel, rel)
            if st["snap"] is not None:
                w, h = st["snap"].size
                frame = st["snap"].transform((w, h), Image.AFFINE, (1 / k, 0, sx - sx / k, 0, 1 / k, sy - sy / k),
                                             resample=Image.BILINEAR, fillcolor=STYLES["dark" if self.dark else "light"]["sea"])
                self._zoom_img = ImageTk.PhotoImage(frame)
                c.itemconfigure(st["item"], image=self._zoom_img)
        except tk.TclError:
            self._zoom = None
            return
        if st["i"] >= ZOOM_FRAMES:
            self._zoom_finish()
        else:
            self.after(15, self._zoom_step)

    def _zoom_finish(self) -> None:
        st, self._zoom = self._zoom, None
        if st is None:
            return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        sx, sy = st["sx"], st["sy"]
        # il punto sotto il cursore resta fermo
        wx, wy = self.cx + sx - w / 2, self.cy + sy - h / 2
        self.z = st["nz"]
        self.cx, self.cy = wx * st["f"] - (sx - w / 2), wy * st["f"] - (sy - h / 2)
        self.canvas.delete("zoomfx")
        self._zoom_img = None
        self.redraw()

    def _clamp(self) -> None:
        h = self.canvas.winfo_height()
        n = self.world
        self.cx %= n
        self.cy = n / 2 if n <= h else max(h / 2, min(n - h / 2, self.cy))

    def _press(self, e) -> None:
        if self._zoom:
            self._zoom_finish()
        if self._glide:
            self._glide = None
            self.redraw()
        self._drag = (e.x, e.y)
        self._moved = 0
        self._drag_acc = 0
        self._vel = [(time.monotonic(), e.x, e.y)]

    def _shift(self, dx: float, dy: float) -> None:
        """Sposta tutto quello che c'è sullo schermo (senza ridisegnare)."""
        self.cx -= dx
        self.cy -= dy
        self.canvas.move("all", dx, dy)
        for p in self._paths:
            p["pts"] = [(x + dx, y + dy) for x, y in p["pts"]]
            p["end"] = (p["end"][0] + dx, p["end"][1] + dy)
        self._rings = [(it, x + dx, y + dy, r, col, per) for it, x, y, r, col, per in self._rings]

    def _motion(self, e) -> None:
        if not self._drag:
            return
        dx, dy = e.x - self._drag[0], e.y - self._drag[1]
        self._drag = (e.x, e.y)
        self._moved += abs(dx) + abs(dy)
        self._drag_acc += abs(dx) + abs(dy)
        self._vel = self._vel[-5:] + [(time.monotonic(), e.x, e.y)]
        self._shift(dx, dy)                    # durante il trascinamento spostiamo e basta...
        if self._drag_acc > 220:               # ...ma ogni tanto si ridisegna: niente bordi vuoti
            self._drag_acc = 0
            self.redraw()

    def _release(self, e) -> None:
        self._drag = None
        if self._moved > 3:
            # inerzia: se il mouse era in movimento al rilascio, la mappa continua e rallenta
            now = time.monotonic()
            recent = [v for v in self._vel if now - v[0] <= 0.12]
            if len(recent) >= 2 and recent[-1][0] - recent[0][0] > 0.01:
                dt = recent[-1][0] - recent[0][0]
                vx, vy = (recent[-1][1] - recent[0][1]) / dt, (recent[-1][2] - recent[0][2]) / dt
                speed = math.hypot(vx, vy)
                if speed > 250:
                    f = min(1.0, 2600 / speed)
                    self._glide = [vx * f, vy * f, now, 0]
                    return
            self.redraw()
            return
        # clic su un gruppo di città: ingrandisci lì
        p = self._nearest_path(e.x, e.y)
        if p is not None and p["cl"]["ball"] and self.z < self.max_zoom():
            # clic sulla pallina con il numero: ingrandisci fin dove gli IP si separano
            self.zoom_at(max(1, min(SPREAD_Z - self.z, self.max_zoom() - self.z)), e.x, e.y)
            return
        # clic senza trascinamento: selezione del punto o della linea più vicina
        hit = self._hit(e.x, e.y)
        self.selected = hit.key if hit else None
        self._draw_overlay()
        if self.on_select:
            self.on_select(hit)

    def _glide_step(self) -> None:
        g = self._glide
        now = time.monotonic()
        dt = min(0.1, now - g[2])
        g[2] = now
        g[3] += 1
        self._shift(g[0] * dt, g[1] * dt)
        decay = math.exp(-4.5 * dt)
        g[0] *= decay
        g[1] *= decay
        if math.hypot(g[0], g[1]) < 40:
            self._glide = None
            self.redraw()
        elif g[3] % 5 == 0:
            self.redraw()

    def _nearest_path(self, x, y, radius: float = 12) -> dict | None:
        best, bd = None, radius
        for p in self._paths:
            px, py = p["end"]
            d = math.hypot(px - x, py - y)
            if d <= bd:
                best, bd = p, d
        return best

    def _nearest(self, x, y, radius: float = 12) -> Link | None:
        p = self._nearest_path(x, y, radius)
        return p["link"] if p else None

    def _hit(self, x, y) -> Link | None:
        """Il punto più vicino (entro 12 px) oppure la linea più vicina (entro qualche px dal tratto)."""
        link = self._nearest(x, y)
        if link:
            return link
        best, bd = None, None
        for p in self._paths:
            pts = p["pts"]
            tol = max(6.0, p.get("lw", 1) / 2 + 4)
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if (x < min(x0, x1) - tol or x > max(x0, x1) + tol or
                        y < min(y0, y1) - tol or y > max(y0, y1) + tol):
                    continue
                dx, dy = x1 - x0, y1 - y0
                L = dx * dx + dy * dy
                t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / L))
                d = math.hypot(x - (x0 + t * dx), y - (y0 + t * dy))
                if d <= tol and (bd is None or d < bd):
                    best, bd = p["link"], d
        return best

    # ------------------------------------------------------------------ disegno
    def redraw(self) -> None:
        try:
            if not self.winfo_exists():              # ridisegno in ritardo dopo un cambio di lingua
                return
        except tk.TclError:
            return
        if not self.winfo_ismapped() and not self.active:
            return
        if self._zoom:                               # zoom in corso: si ridisegna alla fine
            return
        if not self._fitted and self.canvas.winfo_width() > 50:
            self._fitted = True
            return self.fit_world()
        self._clamp()
        self.canvas.delete("all")
        self._draw_base()
        self._draw_overlay()

    def _offset(self) -> tuple[float, float]:
        """Da pixel del mondo a pixel dello schermo: sx = wx + ox."""
        return self.canvas.winfo_width() / 2 - self.cx, self.canvas.winfo_height() / 2 - self.cy

    def _draw_base(self) -> None:
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        ox, oy = self._offset()
        n = 1 << self.z
        vec = self._vector_on()
        self.attrib.configure(text="Natural Earth · IP: DB-IP.com (CC BY 4.0)")
        if vec:
            st = STYLES["dark" if self.dark else "light"]
            c.configure(bg=st["sea"])
            x0, x1 = math.floor(-ox / TILE), math.floor((w - ox) / TILE)
            y0, y1 = max(0, math.floor(-oy / TILE)), min(n - 1, math.floor((h - oy) / TILE))
            for ty in range(y0, y1 + 1):
                for tx in range(x0, x1 + 1):
                    img = self._vtile(self.z, tx % n, ty)
                    if img is not None:
                        c.create_image(tx * TILE + ox, ty * TILE + oy, image=img, anchor="nw", tags=("base",))
            self._draw_heat()
            self._draw_places(st)
            return
        c.configure(bg=SEA)
        # mappa vettoriale ancora in caricamento: contorni semplici degli stati
        W = self.world
        rings = self._world_rings(self.z)
        for k in (-1, 0, 1, 2):
            dx = ox + k * W
            if dx > w or dx + W < 0:
                continue
            for lon in range(-180, 181, 30):           # reticolo leggero
                x = project(0, lon, self.z)[0] + dx
                c.create_line(x, max(oy, 0), x, min(oy + W, h), fill=GRID, tags=("base",))
            for lat in (-60, -30, 0, 30, 60):
                y = project(lat, 0, self.z)[1] + oy
                c.create_line(max(dx, 0), y, min(dx + W, w), y, fill=GRID, tags=("base",))
            for pts in rings:
                c.create_polygon([v + (dx if i % 2 == 0 else oy) for i, v in enumerate(pts)],
                                 fill=LAND, outline=LAND_EDGE, width=1, tags=("base",))
        self._draw_heat()

    def _draw_heat(self) -> None:
        """Stati colorati in base al traffico scambiato: un velo trasparente sopra la mappa (a zoom bassi:
        i contorni sono quelli semplici 1:110m)."""
        if not (self.heat and self._heat) or self.z > 5:
            self._heat_pil = self._heat_img = None
            return
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        ox, oy = self._offset()
        sig = (self.z, round(ox), round(oy), w, h, tuple(sorted(self._heat.items())))
        if sig != getattr(self, "_heat_sig", None) or self._heat_img is None:
            W = self.world
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            r, g, b = _rgb(theme.ACCENT)
            rings = self._world_rings(self.z)
            for k in (-1, 0, 1, 2):
                dx = ox + k * W
                if dx > w or dx + W < 0:
                    continue
                for pts, iso in zip(rings, self._world_iso):
                    lvl = self._heat.get(iso)
                    if lvl:
                        d.polygon([v + (dx if i % 2 == 0 else oy) for i, v in enumerate(pts)],
                                  fill=(r, g, b, HEAT_ALPHA[lvl]), outline=(r, g, b, HEAT_ALPHA[lvl] + 70))
            self._heat_sig, self._heat_pil, self._heat_img = sig, im, ImageTk.PhotoImage(im)
        c.create_image(0, 0, image=self._heat_img, anchor="nw", tags=("base",))

    def _bg(self) -> str:
        """Il colore verso cui sfumano anelli e scie (la terra della mappa)."""
        return STYLES["dark" if self.dark else "light"]["land"] if self._vector_on() else LAND

    def _draw_overlay(self) -> None:
        c = self.canvas
        for tag in OVERLAY_TAGS:
            c.delete(tag)
        self._paths, self._fx, self._rings = [], [], []
        if not self.links and self.home is None:
            return
        ox, oy = self._offset()
        W = self.world
        w = c.winfo_width()
        home = self.home
        bg = self._bg()
        now = time.monotonic()
        k = 0
        if home:
            hx, hy = project(*home, self.z)
            # copia del mondo più vicina al centro dello schermo
            k = round((w / 2 - (hx + ox)) / W)
            hx, hy = hx + ox + k * W, hy + oy

        def screen(lat: float, lon: float) -> tuple[float, float]:
            x, y = project(lat, lon, self.z)
            kk = k if home else round((w / 2 - (x + ox)) / W)
            return x + ox + kk * W, y + oy

        # una linea per IP; le linee verso la stessa città arrivano nello stesso punto e si aprono a
        # ventaglio lungo il percorso (fidate da un lato, non fidate dall'altro). A zoom bassi le città
        # vicine a schermo diventano un punto solo, con il numero di città dentro
        groups: dict[str, list] = {}
        for link in self.links:
            groups.setdefault(link.key.split("|")[0], []).append(link)
        cities = []
        for gkey, members in groups.items():
            x, y = screen(members[0].lat, members[0].lon)
            cities.append((gkey, x, y, sum(m.conns for m in members)))
        radius = CLUSTER_PX if self.z < self.max_zoom() else 0
        cluster_of: dict[str, dict] = {}
        clusters: list[dict] = []
        for keys in cluster_cities(cities, radius):
            members = [m for gk in keys for m in groups[gk]]
            members.sort(key=lambda x: (not x.trusted, _ip_sort(x.ip)))
            head = groups[keys[0]][0]
            cl = {"cities": keys, "members": members, "lat": head.lat, "lon": head.lon, "place": head.place, "geo": None}
            clusters.append(cl)
            n = len(members)
            step = 6.0 if n <= 3 else 4.0 if n <= 8 else max(2.0, 32.0 / n)
            # da lontano una pallina con il numero; ingrandendo gli IP si aprono in punti distinti, sempre più larghi
            sep = spread_sep(self.z)
            cl["spread"] = n > 1 and sep > 0
            cl["ball"] = n > 1 and not cl["spread"]
            offs = spread_offsets(n, sep) if cl["spread"] else [(0.0, 0.0)] * n
            cl["radius"] = max((math.hypot(dx, dy) for dx, dy in offs), default=0.0)
            cl["off"] = {}
            for i, m in enumerate(members):
                cluster_of[m.key] = cl
                m_fan = (i - (n - 1) / 2) * step if n > 1 and not cl["spread"] else 0.0
                cl.setdefault("fan", {})[m.key] = m_fan
                cl["off"][m.key] = offs[i]
        # prima le fidate, poi le non fidate sopra; la selezionata per ultima
        order = sorted(self.links, key=lambda x: (x.key == self.selected, not x.trusted, x.rate_in + x.rate_out))
        for link in order:
            cl = cluster_of[link.key]
            color = theme.OK if link.trusted else risk_mod.color_of(link.risk)
            rate = link.rate_in + link.rate_out
            if home:
                if cl["geo"] is None:
                    cl["geo"] = [screen(lat, lon) for lat, lon in great_circle(home[0], home[1], cl["lat"], cl["lon"])]
                pts = cl["geo"]
                if cl["fan"].get(link.key):
                    pts = offset_path(pts, cl["fan"][link.key])
                dx, dy = cl["off"][link.key]
                if dx or dy:                         # la linea piega verso il suo punto solo nell'ultimo tratto
                    last = len(pts) - 1
                    pts = [(x + dx * (i / last) ** 3, y + dy * (i / last) ** 3) for i, (x, y) in enumerate(pts)]
            else:
                x, y = screen(cl["lat"], cl["lon"])
                pts = [(x + cl["off"][link.key][0], y + cl["off"][link.key][1])]
            end = pts[-1]
            lw = line_width(rate)
            if home and len(pts) > 1:
                flat = [v for q in pts for v in q]
                col = color if rate > 0 or link.key == self.selected else _mix(color, SEA, 0.45)
                if link.key == self.selected:        # linea selezionata: più evidente
                    c.create_line(*flat, fill=_mix(color, "#ffffff", 0.5), width=lw + 3,
                                  smooth=True, capstyle="round", tags=("link",))
                elif rate > 0:                       # traffico in corso: alone attorno alla linea
                    c.create_line(*flat, fill=_mix(color, bg, 0.78), width=lw + 3,
                                  smooth=True, capstyle="round", tags=("link",))
                c.create_line(*flat, fill=col, width=lw, smooth=True, capstyle="round", tags=("link",))
            self._paths.append({"pts": pts, "end": end, "link": link, "color": color, "lw": lw,
                                "len": self._length(pts), "items": [], "cities": cl["cities"], "cl": cl})
        # punti delle destinazioni: da lontano uno solo per città (o gruppo di città) con il numero degli IP,
        # da SPREAD_Z in su un punto per ogni IP, vicini ma distinti
        drawn: set[int] = set()
        for p in self._paths:
            link, (x, y), cl = p["link"], p["end"], p["cl"]
            members = cl["members"]
            first = id(cl) not in drawn
            drawn.add(id(cl))
            many = len(cl["cities"]) > 1
            if cl["spread"]:
                color = p["color"]
                r = 3.5 + min(2.5, math.log2(1 + link.conns) / 3)
                if link.key == self.selected:
                    c.create_oval(x - r - 4, y - r - 4, x + r + 4, y + r + 4, outline=theme.TEXT, width=1, tags=("pt",))
                if link.active and len(self._rings) < 80:
                    ring = c.create_oval(x - r - 2, y - r - 2, x + r + 2, y + r + 2, outline=_mix(color, bg, 0.4),
                                         width=1, tags=("pt",))
                    self._rings.append((ring, x, y, r + 1, color, 1.8 + (hash(link.key) % 7) / 10))
                c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=SEA, width=1, tags=("pt",))
                if link.key == self.selected:
                    c.create_text(x + r + 5, y, text=f"{link.ip} · {link.place}" if link.ip else link.place, anchor="w",
                                  fill=theme.TEXT, font=(theme.mono_font(), 9), tags=("label",))
                if first and self.z >= 4:            # il nome della città una volta sola, sotto il gruppo
                    cx, cy = x - cl["off"][link.key][0], y - cl["off"][link.key][1]
                    c.create_text(cx, cy + cl["radius"] + 9, text=cl["place"] + (f"  +{len(cl['cities']) - 1}" if many else ""),
                                  anchor="n", fill=theme.TEXT_SOFT, font=(theme.mono_font(), 9), tags=("label",))
                continue
            sel = any(m.key == self.selected for m in members)
            if not first:
                if link.key == self.selected:
                    c.create_text(x + 14, y, text=f"{link.ip} · {link.place}" if link.ip else link.place,
                                  anchor="w", fill=theme.TEXT, font=(theme.mono_font(), 9), tags=("label",))
                continue
            ball = cl["ball"]
            conns = sum(m.conns for m in members)
            r = 3 + min(4, math.log2(1 + conns) / 2) + (3.5 if ball else 0)
            if ball and len(members) > 99:
                r += 2
            untrusted = any(not m.trusted for m in members)
            mixed = untrusted and any(m.trusted for m in members)
            color = risk_mod.color_of(max(m.risk for m in members if not m.trusted)) if untrusted else theme.OK
            if sel:
                c.create_oval(x - r - 5, y - r - 5, x + r + 5, y + r + 5, outline=theme.TEXT, width=1, tags=("pt",))
            if any(m.active for m in members) and len(self._rings) < 80:
                # connessioni aperte: un anello che si allarga e sfuma (mosso da _animate)
                ring = c.create_oval(x - r - 3, y - r - 3, x + r + 3, y + r + 3, outline=_mix(color, bg, 0.4),
                                     width=1, tags=("pt",))
                self._rings.append((ring, x, y, r + 2, color, 1.8 + (hash(cl["cities"][0]) % 7) / 10))
            # punto con linee fidate e non fidate: colore del rischio con il bordo verde
            c.create_oval(x - r, y - r, x + r, y + r, fill=color, outline=theme.OK if mixed else SEA,
                          width=2 if mixed else 1, tags=("pt",))
            if ball:                                 # quanti IP ci sono dentro
                c.create_text(x, y, text=str(len(members)), fill="#06090d",
                              font=(theme.mono_font(), 8, "bold"), tags=("pt",))
            if link.key == self.selected:
                c.create_text(x + r + 4, y, text=f"{link.ip} · {link.place}" if link.ip else link.place, anchor="w",
                              fill=theme.TEXT, font=(theme.mono_font(), 9), tags=("label",))
            elif self.z >= 4 and not sel:
                c.create_text(x + r + 4, y, text=cl["place"] + (f"  +{len(cl['cities']) - 1}" if many else ""),
                              anchor="w", fill=theme.TEXT_SOFT, font=(theme.mono_font(), 9), tags=("label",))
        if home:
            sonar = c.create_oval(hx - 16, hy - 16, hx + 16, hy + 16, outline=_mix(theme.ACCENT, bg, 0.5),
                                  width=1, tags=("phone",))
            if any(x.active for x in self.links):
                self._rings.append((sonar, hx, hy, 12, theme.ACCENT, 2.6))
            self._draw_phone(hx, hy)
        # impulsi del traffico (creati qui, mossi da _animate): una testa e due puntini di scia
        for p in self._paths:
            if len(p["pts"]) < 2:
                continue
            link = p["link"]
            for direction, rate, col in ((1, link.rate_out, _mix(p["color"], "#ffffff", 0.35)),
                                         (-1, link.rate_in, PARTICLE_IN)):
                n = particles_for(rate)
                size = 1.6 + min(1.8, math.log10(1 + rate / 4096))
                for i in range(n):
                    items = tuple(c.create_oval(0, 0, 0, 0, fill=_mix(col, bg, fade), outline="", tags=("pp",))
                                  for fade in (0.72, 0.45, 0.0))            # la testa per ultima: sta sopra
                    p["items"].append((items, direction, i / n, size))
            # connessione nuova: scintilla dal telefono alla destinazione e due anelli che si allargano
            born = self._born.get(link.key.rsplit("|", 1)[0])
            if born is not None and now - born < BORN_SEC and len(self._fx) < 24:
                col = p["color"]
                self._fx.append({"born": born, "p": p, "color": col,
                                 "rings": [c.create_oval(0, 0, 0, 0, outline=col, width=2, tags=("fx",)) for _ in (0, 1)],
                                 "spark": c.create_oval(0, 0, 0, 0, fill="#ffffff", outline=col, width=1, tags=("fx",))})
        self._position_particles()
        self._position_fx()

    def _draw_phone(self, x: float, y: float) -> None:
        """Un piccolo smartphone: la tua posizione."""
        c = self.canvas
        w, h, r = 11, 19, 3
        x0, y0, x1, y1 = x - w / 2, y - h / 2, x + w / 2, y + h / 2
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        c.create_polygon(pts, smooth=True, fill=theme.PANEL_2, outline=theme.ACCENT, width=1.5, tags=("phone",))
        c.create_rectangle(x0 + 2, y0 + 3, x1 - 2, y1 - 4, fill=_mix(theme.ACCENT, SEA, 0.35), outline="", tags=("phone",))
        c.create_oval(x - 1, y1 - 3, x + 1, y1 - 1, fill=theme.ACCENT, outline="", tags=("phone",))
        c.create_text(x, y1 + 9, text=self.home_name or tr("telefono"), fill=theme.TEXT, anchor="n",
                      font=(theme.mono_font(), 9, "bold"), tags=("phone",))

    @staticmethod
    def _length(pts) -> list[float]:
        acc, out = 0.0, [0.0]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            acc += math.hypot(x1 - x0, y1 - y0)
            out.append(acc)
        return out

    @staticmethod
    def _at(pts, cum, t) -> tuple[float, float]:
        total = cum[-1]
        if total <= 0:
            return pts[0]
        d = t * total
        lo, hi = 0, len(cum) - 1
        while lo < hi - 1:                         # ricerca binaria del segmento
            mid = (lo + hi) // 2
            if cum[mid] <= d:
                lo = mid
            else:
                hi = mid
        seg = cum[hi] - cum[lo] or 1
        f = (d - cum[lo]) / seg
        (x0, y0), (x1, y1) = pts[lo], pts[hi]
        return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f

    def _position_particles(self) -> None:
        now = time.monotonic()
        c = self.canvas
        for p in self._paths:
            if not p["items"]:
                continue
            total = p["len"][-1]
            if total <= 0:
                continue
            # velocità costante a schermo, ma ogni giro dura tra 1 e 5 s
            period = max(1.0, min(5.0, total / 110.0))
            for items, direction, phase, size in p["items"]:
                t = (phase + now / period) % 1.0
                gap = min(0.04, (size * 2.2) / total)          # distanza tra testa e scia
                for j, item in enumerate(items):               # scia lontana, scia vicina, testa
                    tt = t - (2 - j) * gap
                    if tt < 0:
                        c.coords(item, -9, -9, -9, -9)
                        continue
                    x, y = self._at(p["pts"], p["len"], 1.0 - tt if direction < 0 else tt)
                    sz = size * (0.5, 0.75, 1.0)[j]
                    c.coords(item, x - sz, y - sz, x + sz, y + sz)

    def _position_fx(self) -> None:
        """Lampi delle connessioni nuove e anelli pulsanti delle città con connessioni aperte."""
        now = time.monotonic()
        c = self.canvas
        bg = self._bg()
        for it, x, y, r, col, period in self._rings:
            f = (now / period) % 1.0
            rr = r + 9 * f
            c.coords(it, x - rr, y - rr, x + rr, y + rr)
            c.itemconfigure(it, outline=_mix(col, bg, 0.25 + 0.75 * f))
        if not self._fx:
            return
        alive = []
        for fx in self._fx:
            age = now - fx["born"]
            if age >= BORN_SEC:
                for it in fx["rings"] + [fx["spark"]]:
                    c.delete(it)
                continue
            alive.append(fx)
            p = fx["p"]
            x, y = p["end"]
            travel = 0.55 if len(p["pts"]) > 1 else 0.0          # la scintilla arriva, poi partono gli anelli
            if age < travel:
                sx, sy = self._at(p["pts"], p["len"], (age / travel) ** 0.8)
                c.coords(fx["spark"], sx - 3.5, sy - 3.5, sx + 3.5, sy + 3.5)
            else:
                c.coords(fx["spark"], -9, -9, -9, -9)
            for i, it in enumerate(fx["rings"]):
                f = (age - travel - i * 0.2) / (BORN_SEC - travel - 0.2)
                if f <= 0 or f >= 1:
                    c.coords(it, -9, -9, -9, -9)
                    continue
                rr = 5 + 26 * (1 - (1 - f) ** 2)
                c.coords(it, x - rr, y - rr, x + rr, y + rr)
                c.itemconfigure(it, outline=_mix(fx["color"], bg, f))
        self._fx = alive

    def _animate(self) -> None:
        try:
            if not self._vdone.empty():
                self._vcollect()
            if self.active and not self._zoom:
                if self._glide and not self._drag:
                    self._glide_step()
                if self._paths and not self._drag:
                    self._position_particles()
                    self._position_fx()
        except tk.TclError:
            return
        self.after(1000 // FPS, self._animate)

    # ---------------------------------------------------------------- la tua posizione scelta sulla mappa
    def latlon_at(self, sx: float, sy: float) -> tuple[float, float]:
        """Latitudine e longitudine del punto dello schermo (sx, sy)."""
        n = TILE * (1 << self.z)
        wx = (self.cx + sx - self.canvas.winfo_width() / 2) % n
        wy = min(n - 1, max(0, self.cy + sy - self.canvas.winfo_height() / 2))
        return unproject(wx, wy, self.z)

    def country_at(self, lat: float, lon: float) -> str:
        """Codice ISO dello stato che contiene il punto (contorni 1:110m), "" se è in mare."""
        for ring, iso in zip(self._world, self._world_iso):
            inside = False
            j = len(ring) - 2
            for i in range(0, len(ring) - 1, 2):
                xi, yi, xj, yj = ring[i], ring[i + 1], ring[j], ring[j + 1]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
            if inside:
                return iso
        return ""

    def place_near(self, lat: float, lon: float, max_km: float = 40.0) -> str:
        """Il nome della città più vicina fra quelle della mappa vettoriale ("" se nessuna entro max_km)."""
        if self.vector is None or not getattr(self.vector, "places", None):
            return ""
        x, y = project(lat, lon, 0)
        x, y = x / TILE, y / TILE
        # 1 unità = il giro del mondo all'equatore; alla latitudine del punto vale meno
        unit_km = 40075.0 * max(0.05, math.cos(math.radians(lat)))
        best, best_d = "", max_km / unit_km
        for name, px, py, _mz in self.vector.places:
            d = math.hypot(px - x, py - y)
            if d < best_d:
                best, best_d = name, d
        return best

    def _context(self, e) -> None:
        """Clic destro: "Imposta qui la mia posizione"."""
        if self.on_home is None or self._zoom:
            return
        lat, lon = self.latlon_at(e.x, e.y)
        menu = tk.Menu(self.canvas, tearoff=0, bg=theme.PANEL_2, fg=theme.TEXT, activebackground=theme.ACCENT,
                       activeforeground="#ffffff", bd=0, relief="flat", font=(theme.ui_font(), 10))
        menu.add_command(label="⌖  " + tr("Imposta qui la mia posizione") + f"   ({lat:.4f}, {lon:.4f})",
                         command=lambda: self.on_home(lat, lon))
        try:
            menu.tk_popup(e.x_root, e.y_root)
        finally:
            menu.grab_release()

    def _hover(self, e) -> None:
        c = self.canvas
        if self._drag or self._zoom:
            return
        link = self._hit(e.x, e.y)
        c.delete("tip")
        c.configure(cursor="hand2" if link else "fleur")
        if not link:
            return
        near = self._nearest_path(e.x, e.y)
        if near is not None and near["cl"]["ball"]:
            cl = near["cl"]
            if len(cl["cities"]) > 1:
                names = list(dict.fromkeys(m.place for m in cl["members"]))
                lines = [tr("{n} città vicine · {m} destinazioni", n=len(cl["cities"]), m=len(cl["members"]))]
            else:
                names = [f"{m.ip}  {m.dests[0] if m.dests else ''}".strip() for m in cl["members"]]
                lines = [tr("{m} destinazioni · {place}", m=len(cl["members"]), place=cl["place"])]
            lines += names[:8] + ([tr("… altre {n}", n=len(names) - 8)] if len(names) > 8 else [])
            lines.append(f"↑ {_rate(sum(m.rate_out for m in cl['members']))}  ↓ {_rate(sum(m.rate_in for m in cl['members']))}")
            lines.append(tr("clic per ingrandire"))
            return self._tip(e, lines, theme.ERR if any(not m.trusted for m in cl["members"]) else theme.OK)
        lines = [f"{link.ip} · {link.place}" if link.ip else link.place, (tr("FIDATA") if link.trusted else tr("NON FIDATA"))
                 + f" · {link.conns} conn · {link.active} {tr('aperte')}",
                 f"↑ {_rate(link.rate_out)}  ↓ {_rate(link.rate_in)}"]
        if not link.trusted and link.risk_text:
            lines.append(f"{tr('rischio')}: {link.risk_text}")
        lines += link.dests[:6] + ([tr("… altre {n}", n=len(link.dests) - 6)] if len(link.dests) > 6 else [])
        lines += ["app: " + ", ".join(link.apps[:3]) + (" …" if len(link.apps) > 3 else ""), tr("clic per i dettagli")]
        self._tip(e, lines, theme.OK if link.trusted else theme.ERR)

    def _tip(self, e, lines: list[str], edge: str) -> None:
        c = self.canvas
        x, y = e.x + 14, e.y + 10
        t = c.create_text(x + 8, y + 6, text="\n".join(lines), anchor="nw", fill=theme.TEXT,
                          font=(theme.mono_font(), 9), tags=("tip",))
        x0, y0, x1, y1 = c.bbox(t)
        if x1 + 8 > c.winfo_width():                 # non uscire dal bordo destro
            c.move(t, -(x1 - x0) - 40, 0)
            x0, y0, x1, y1 = c.bbox(t)
        if y1 + 8 > c.winfo_height():
            c.move(t, 0, -(y1 - y0) - 30)
            x0, y0, x1, y1 = c.bbox(t)
        bg = c.create_rectangle(x0 - 8, y0 - 6, x1 + 8, y1 + 6, fill=theme.PANEL, outline=edge, tags=("tip",))
        c.tag_lower(bg, t)

    # ------------------------------------------------------------------ tile e contorni
    def clear_tile_cache(self) -> None:
        self._tiles.clear()

    # ------------------------------------------------------------------ mappa vettoriale
    def _vector_on(self) -> bool:
        """Mappa vettoriale pronta (finché si carica: contorni semplici degli stati)."""
        return self.vector is not None and self.vector.ready

    def set_vector(self, vm: VectorMap | None) -> None:
        self.vector = vm
        self._vpil.clear()
        self._tiles.clear()
        self.redraw()

    def _vworker(self) -> None:
        while True:
            key = self._vq.get()
            style, z, x, y, vm = key
            if vm is not self.vector or z != self.z:   # zoom cambiato nel frattempo: non serve più
                self._vpending.discard(key)
                continue
            try:
                im = vm.render(z, x, y, style)
            except Exception:                           # noqa: BLE001 - una tile rotta non deve fermare il thread
                im = None
            self._vdone.put((key, im))            # raccolte dal thread dell'interfaccia in _animate

    def _vcollect(self) -> None:
        got = False
        while True:
            try:
                key, im = self._vdone.get_nowait()
            except queue.Empty:
                break
            self._vpending.discard(key)
            if im is not None and key[4] is self.vector:
                self._vpil[key[:4]] = im
                while len(self._vpil) > 600:
                    self._vpil.popitem(last=False)
                self._tiles.pop(("v",) + key[:4], None)
                got = True
        if got and self._vredraw is None:
            # più tile arrivano insieme: un solo ridisegno
            self._vredraw = self.after(40, self._vredraw_now)

    def _vredraw_now(self) -> None:
        self._vredraw = None
        self.redraw()

    def _vtile(self, z: int, x: int, y: int):
        style = "dark" if self.dark else "light"
        key = ("v", style, z, x, y)
        if key in self._tiles:
            self._tiles.move_to_end(key)
            return self._tiles[key]
        im = self._vpil.get((style, z, x, y))
        if im is not None:
            img = ImageTk.PhotoImage(im)
            self._tiles[key] = img
            while len(self._tiles) > 400:
                self._tiles.popitem(last=False)
            return img
        job = (style, z, x, y, self.vector)
        if job not in self._vpending:
            self._vpending.add(job)
            self._vq.put(job)
        # intanto: la tile "madre" ingrandita (sfocata per un attimo), se c'è
        for up in range(1, min(z, 4) + 1):
            parent = self._vpil.get((style, z - up, x >> up, y >> up))
            if parent is not None:
                size = TILE >> up
                ox, oy = (x - ((x >> up) << up)) * size, (y - ((y >> up) << up)) * size
                return ImageTk.PhotoImage(parent.crop((ox, oy, ox + size, oy + size)).resize((TILE, TILE), Image.BILINEAR))
        return None

    def _draw_places(self, st: dict) -> None:
        """Nomi delle città: testo vero sul canvas, nitido a ogni zoom; niente sovrapposizioni."""
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        ox, oy = self._offset()
        W = self.world
        placed: list[tuple[float, float, float, float]] = []
        # niente nomi sopra il telefono e sopra i punti delle destinazioni (hanno già la loro etichetta)
        k0 = round((w / 2 - (self.cx % W + ox)) / W) if W else 0
        for lat, lon, wide in ([(self.home[0], self.home[1], 60)] if self.home else []) + \
                [(lk.lat, lk.lon, 90) for lk in self.links]:
            px, py = project(lat, lon, self.z)
            for k in (k0 - 1, k0, k0 + 1):
                sx, sy = px + ox + k * W, py + oy
                placed.append((sx - 14, sy - 14, sx + wide, sy + 22))
        font = (theme.mono_font(), 8 if self.z < 6 else 9)
        cw = 6.2 if self.z < 6 else 7.0
        for k in (-1, 0, 1):
            dx = ox + k * W
            if dx > w or dx + W < 0:
                continue
            x0, x1 = max(0.0, -dx / W), min(1.0, (w - dx) / W)
            y0, y1 = max(0.0, -oy / W), min(1.0, (h - oy) / W)
            for name, px, py in self.vector.places_in(self.z, x0, y0, x1, y1):
                sx, sy = px * W + dx, py * W + oy
                box = (sx - 3, sy - 7, sx + 6 + len(name) * cw, sy + 7)
                if any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in placed):
                    continue
                placed.append(box)
                c.create_oval(sx - 1.5, sy - 1.5, sx + 1.5, sy + 1.5, fill=st["dot"], outline="", tags=("base",))
                c.create_text(sx + 5, sy, text=name, anchor="w", fill=st["place"], font=font, tags=("base",))

    @staticmethod
    def _load_world() -> tuple[list, list]:
        """Contorni degli stati e, per ognuno, il codice ISO dello stato."""
        try:
            with open(WORLD_FILE, encoding="utf-8") as f:
                data = json.load(f)
            rings = data["rings"]
            iso = data.get("iso") or []
            return rings, iso if len(iso) == len(rings) else [""] * len(rings)
        except (OSError, ValueError, KeyError):
            return [], []

    def _world_rings(self, z: int) -> list:
        if z not in self._world_px:
            out = []
            for ring in self._world:
                pts = []
                for i in range(0, len(ring) - 1, 2):
                    x, y = project(ring[i + 1], ring[i], z)
                    pts += [x, y]
                out.append(pts)
            self._world_px[z] = out
        return self._world_px[z]
