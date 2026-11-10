"""Grafo delle connessioni, nello stile del grafo di OSInt Graph (nodi tondi bianchi con
bordo colorato e icona, etichetta sotto, collegamenti curvi, disposizione "organica"
a forze come fcose/CoSE).

    telefono ── app ── organizzazione (ASN) ── destinazione

Tutto disegnato su un Canvas Tk: trascina i nodi, rotella = zoom, trascina lo sfondo = sposta,
clic = evidenzia il nodo e i suoi vicini (gli altri si attenuano), doppio clic su app o
organizzazione = richiude/riapre il ramo. La disposizione gira in un thread a parte
(Fruchterman-Reingold con raffreddamento, distanza ideale 110 come in OSInt Graph) e il
disegno segue a 20 fps finché i nodi si muovono.

Riquadro LAYOUT (come in OSInt Graph): Organico (a forze, predefinito), Circolare, Gerarchico
(albero telefono → app → organizzazione → destinazione), Griglia, e "Riduci incroci": ripete la
disposizione organica con semi diversi e tiene quella con meno archi che si intersecano.
Le icone dei nodi sono disegnate a linee (vettoriali) sul canvas; le icone delle app (PNG
dall'agent) sono ritagliate in un cerchio.
"""
from __future__ import annotations

import base64
import io
import math
import random
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageTk

from ..i18n import tr
from . import theme

IDEAL = 110.0          # distanza ideale fra nodi collegati (fcose: idealEdgeLength 110)
REPULSION = 9000.0     # fcose: nodeRepulsion 9000
GRAVITY = 0.015
EDGE_COLOR = "#94a3b8"
NODE_BG = "#ffffff"
TARGET_BG = "#fef3c7"
TARGET_BORDER = "#b45309"
KIND_COLOR = {"phone": TARGET_BORDER, "app": "#2563eb", "org": "#7c3aed", "dest": "#64748b", "dest_u": "#dc2626",
              "dest_t": "#059669", "country": "#0891b2"}
KIND_SIZE = {"phone": 56, "app": 42, "org": 36, "dest": 24, "country": 32}
LAYOUTS = ("organic", "circle", "tree", "grid")
LEVEL = {"phone": 0, "app": 1, "org": 2, "dest": 3, "country": 3}
TREE_WRAP = 8               # Gerarchico: oltre 8 foglie sotto un nodo vanno a blocchi di righe
UNTANGLE_RUNS = 12          # tentativi di "Riduci incroci"
UNTANGLE_BUDGET = 4.0       # secondi al massimo


def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


@dataclass
class Node:
    id: str
    kind: str
    label: str
    color: str = ""
    icon: str | None = None        # PNG in base64 (dall'agent) oppure None
    glyph: str = ""                # testo dentro il cerchio se non c'è l'icona
    size: int = 30
    parent: str | None = None      # per richiudere i rami
    info: dict = field(default_factory=dict)
    x: float = 0.0
    y: float = 0.0
    fixed: bool = False
    placed: bool = False
    _photo: tuple | None = None    # (dimensione, PhotoImage)


@dataclass
class Edge:
    a: str
    b: str
    weight: float = 1.0            # byte (o connessioni): decide lo spessore
    color: str = EDGE_COLOR
    label: str = ""
    rate_out: float = 0.0          # byte/s da a verso b (dal telefono verso la destinazione)
    rate_in: float = 0.0           # byte/s da b verso a
    active: int = 0                # connessioni ancora aperte che passano di qui


def particles_for(rate: float) -> int:
    """Quanti impulsi su un arco: stessa scala della mappa (logaritmica, al massimo 8)."""
    if rate <= 0:
        return 0
    return max(1, min(8, int(math.log2(1 + rate / 1024)) + 1))


class GraphView(ctk.CTkFrame):
    def __init__(self, parent, fonts: theme.Fonts, on_select: Callable[[Node | None], None] | None = None,
                 on_open: Callable[[Node], None] | None = None):
        super().__init__(parent, fg_color=theme.PANEL, corner_radius=0)
        self.fonts = fonts
        self.on_select, self.on_open = on_select, on_open
        self.nodes: dict[str, Node] = {}
        self.edges: dict[tuple[str, str], Edge] = {}
        self.adj: dict[str, set[str]] = {}
        self.collapsed: set[str] = set()
        self.hidden: set[str] = set()
        self.selected: str | None = None
        self.active = False
        self.scale = 1.0
        self.cx = self.cy = 0.0              # punto del mondo al centro del canvas
        self._lock = threading.Lock()
        self._hot = 0.0                      # "temperatura" del layout: > 0 i nodi si muovono
        self._drag: tuple | None = None
        self._moved = 0
        self._fit_pending = True
        self._dirty = True
        self._items: dict[str, list] = {}
        self._last_draw = 0.0
        self._paths: list[dict] = []         # archi con traffico: punti a schermo e impulsi che li percorrono
        self._rings: list[tuple] = []        # anelli pulsanti dei nodi con connessioni aperte
        self._icon_cache: dict[tuple, ImageTk.PhotoImage] = {}
        self._stats_text = ""
        self.layout = "tree"                 # predefinito: Gerarchico
        self._user_view = False              # True dopo zoom o spostamento a mano (niente piu' adatta automatico)
        self._untangling = False
        self._ly_btns: dict[str, ctk.CTkButton] = {}

        self.canvas = tk.Canvas(self, bg=theme.BG, highlightthickness=0, bd=0, cursor="fleur")
        self.canvas.pack(fill="both", expand=True)
        c = self.canvas
        c.bind("<ButtonPress-1>", self._press)
        c.bind("<B1-Motion>", self._motion)
        c.bind("<ButtonRelease-1>", self._release)
        c.bind("<Double-Button-1>", self._double)
        c.bind("<MouseWheel>", self._wheel)
        c.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.2))
        c.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / 1.2))
        c.bind("<Configure>", lambda _e: self._mark())
        c.bind("<Motion>", self._hover)
        c.bind("<Leave>", lambda _e: (c.delete("tip"), setattr(self, "_tip_id", None)), add="+")
        self._tip_id: str | None = None
        self._build_tools()
        threading.Thread(target=self._layout_loop, daemon=True, name="GraphLayout").start()
        self.after(60, self._frame)

    # ---------------------------------------------------------------- strumenti
    def _build_tools(self) -> None:
        box = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=4, border_width=1, border_color=theme.BORDER)
        box.place(relx=1.0, x=-12, y=12, anchor="ne")
        self.detach_btn = None
        for glyph, cmd, tip in (("+", lambda: self._zoom_center(1.25), "zoom +"), ("−", lambda: self._zoom_center(0.8), "zoom −"),
                                ("⌂", self._fit_auto, "adatta"), ("⟳", self.relayout, "ridisponi")):
            ctk.CTkButton(box, text=glyph, width=28, height=26, corner_radius=3, fg_color="transparent",
                          hover_color=theme.HOVER, text_color=theme.TEXT_SOFT, font=(theme.mono_font(), 14),
                          command=cmd).pack(padx=3, pady=2)
        self.tools = box
        self.legend = ctk.CTkLabel(self, text="", font=self.fonts.small, text_color=theme.TEXT_DIM, justify="left",
                                   fg_color=theme.PANEL, corner_radius=4, padx=10, pady=6)
        self.legend.place(x=12, y=12, anchor="nw")
        self.scale_row = None
        self._build_layout_box()

    def _build_layout_box(self) -> None:
        """Riquadro LAYOUT come in OSInt Graph: 2x2 pulsanti + "Riduci incroci" a tutta larghezza."""
        box = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=4, border_width=1, border_color=theme.BORDER)
        box.place(x=12, rely=1.0, y=-12, anchor="sw")
        ctk.CTkLabel(box, text=tr("Layout").upper(), font=(theme.ui_font(), 11, "bold"), text_color=theme.OK,
                     anchor="w").grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(6, 2))
        names = (("organic", tr("Organico")), ("circle", tr("Circolare")), ("tree", tr("Gerarchico")), ("grid", tr("Griglia")))
        for i, (key, label) in enumerate(names):
            b = ctk.CTkButton(box, text=label, width=96, height=28, corner_radius=4, font=self.fonts.small,
                              fg_color=theme.PANEL_3, hover_color=theme.HOVER, text_color=theme.TEXT,
                              command=lambda k=key: self.set_layout(k))
            b.grid(row=1 + i // 2, column=i % 2, padx=(8 if i % 2 == 0 else 3, 3 if i % 2 == 0 else 8), pady=3, sticky="ew")
            self._ly_btns[key] = b
        self.btn_untangle = ctk.CTkButton(box, text="✂ " + tr("Riduci incroci"), height=28, corner_radius=4,
                                          font=self.fonts.small, fg_color=theme.PANEL_3, hover_color=theme.HOVER,
                                          text_color=theme.TEXT, command=self.untangle)
        self.btn_untangle.grid(row=3, column=0, columnspan=2, padx=8, pady=(3, 8), sticky="ew")
        self.layout_box = box
        self._paint_layout_btns()

    def _paint_layout_btns(self) -> None:
        for k, b in self._ly_btns.items():
            on = k == self.layout
            b.configure(fg_color=theme.OK if on else theme.PANEL_3, text_color="#0b1a12" if on else theme.TEXT,
                        hover_color=theme.OK if on else theme.HOVER)

    def set_scale(self, items, title: str = "") -> None:
        """Seconda riga di legenda con dei pallini colorati (scala di pericolosità)."""
        if self.scale_row is not None:
            return
        from .widgets import ScaleRow
        self.scale_row = ScaleRow(self, self.fonts, items, title)
        self.scale_row.configure(fg_color=theme.PANEL, corner_radius=4)
        self.scale_row.place(x=12, rely=1.0, y=-12, anchor="sw")

    def add_tool(self, glyph: str, command) -> ctk.CTkButton:
        b = ctk.CTkButton(self.tools, text=glyph, width=28, height=26, corner_radius=3, fg_color="transparent",
                          hover_color=theme.HOVER, text_color=theme.ACCENT, font=(theme.mono_font(), 14), command=command)
        b.pack(padx=3, pady=2, before=self.tools.winfo_children()[0])
        return b

    def set_legend(self, text: str) -> None:
        if text != self._stats_text:
            self._stats_text = text
            self.legend.configure(text=text)

    # ---------------------------------------------------------------- dati
    def set_graph(self, nodes: list[Node], edges: list[Edge]) -> None:
        """Sostituisce il grafo conservando le posizioni dei nodi già presenti."""
        with self._lock:
            old = self.nodes
            new: dict[str, Node] = {}
            changed = False
            for n in nodes:
                o = old.get(n.id)
                if o is not None:
                    o.label, o.color, o.size, o.info, o.parent = n.label, n.color, n.size, n.info, n.parent
                    if n.icon and n.icon != o.icon:
                        o.icon, o._photo = n.icon, None
                    o.glyph = n.glyph
                    new[n.id] = o
                else:
                    new[n.id] = n
                    changed = True
            if len(new) != len(old):
                changed = True
            self.nodes = new
            self.edges = {(e.a, e.b): e for e in edges if e.a in new and e.b in new}
            adj: dict[str, set[str]] = {i: set() for i in new}
            for a, b in self.edges:
                adj[a].add(b)
                adj[b].add(a)
            self.adj = adj
            self._place_new()
            self._update_hidden()
            if changed and self.layout != "organic":
                self._apply_static()
                if not self._user_view:          # l'albero cresce: si riadatta, finche' l'utente non zooma/sposta
                    self._fit_pending = True
            elif changed:
                self._hot = max(self._hot, 1.0 if len(old) == 0 else 0.35)
            if self.selected and self.selected not in new:
                self.selected = None
        self._dirty = True

    def _place_new(self) -> None:
        """I nodi nuovi partono vicino a un vicino già disposto (o intorno al centro)."""
        for n in self.nodes.values():
            if n.placed:
                continue
            anchor = next((self.nodes[m] for m in self.adj.get(n.id, ()) if self.nodes[m].placed), None)
            ang = random.random() * 6.283
            if n.kind == "phone":
                n.x, n.y, n.fixed = 0.0, 0.0, True
            elif anchor is not None:
                n.x, n.y = anchor.x + math.cos(ang) * IDEAL * 0.8, anchor.y + math.sin(ang) * IDEAL * 0.8
            else:
                n.x, n.y = math.cos(ang) * IDEAL * 2, math.sin(ang) * IDEAL * 2
            n.placed = True

    def _update_hidden(self) -> None:
        hidden = set()
        for n in self.nodes.values():
            p, hops = n.parent, 0
            while p and hops < 6:
                if p in self.collapsed:
                    hidden.add(n.id)
                    break
                p = self.nodes[p].parent if p in self.nodes else None
                hops += 1
        self.hidden = hidden

    def clear(self) -> None:
        with self._lock:
            self.nodes, self.edges, self.adj = {}, {}, {}
            self.selected = None
        self._fit_pending = True
        self._user_view = False
        self._dirty = True

    # ---------------------------------------------------------------- layout (thread)
    def _layout_loop(self) -> None:
        while True:
            if self._hot <= 0.01 or not self.active:
                time.sleep(0.05)
                continue
            with self._lock:
                self._iterate(self._hot)
                self._hot *= 0.97
                self._dirty = True
            time.sleep(0.01)

    def _iterate(self, temp: float) -> None:
        nodes = [n for n in self.nodes.values() if n.id not in self.hidden]
        if len(nodes) < 2:
            return
        disp = {n.id: [0.0, 0.0] for n in nodes}
        for i, a in enumerate(nodes):          # repulsione fra tutti i nodi (O(n²), n piccolo)
            ax, ay, da = a.x, a.y, disp[a.id]
            for b in nodes[i + 1:]:
                dx, dy = ax - b.x, ay - b.y
                d2 = dx * dx + dy * dy + 0.01
                if d2 > 360000:                 # oltre 600 px la repulsione è trascurabile
                    continue
                f = REPULSION / d2 * ((a.size + b.size) / 60.0)   # i nodi grandi (telefono, app) tengono più spazio
                d = math.sqrt(d2)
                fx, fy = dx / d * f, dy / d * f
                da[0] += fx; da[1] += fy
                db = disp[b.id]
                db[0] -= fx; db[1] -= fy
        for (ia, ib), e in self.edges.items():  # attrazione lungo i collegamenti
            if ia in self.hidden or ib in self.hidden:
                continue
            a, b = self.nodes[ia], self.nodes[ib]
            dx, dy = a.x - b.x, a.y - b.y
            d = math.sqrt(dx * dx + dy * dy) + 0.01
            ideal = IDEAL + (a.size + b.size) * 0.4
            f = (d - ideal) * 0.08
            fx, fy = dx / d * f, dy / d * f
            disp[ia][0] -= fx; disp[ia][1] -= fy
            disp[ib][0] += fx; disp[ib][1] += fy
        step = 12.0 * temp + 0.5
        for n in nodes:
            if n.fixed:
                continue
            vx, vy = disp[n.id]
            vx -= n.x * GRAVITY; vy -= n.y * GRAVITY
            v = math.sqrt(vx * vx + vy * vy)
            if v > step:
                vx, vy = vx / v * step, vy / v * step
            n.x += vx; n.y += vy

    def _fit_auto(self) -> None:
        """⌂: adatta e torna a seguire la crescita del grafo."""
        self._user_view = False
        self.fit()

    def relayout(self) -> None:
        self._user_view = False
        if self.layout != "organic":
            with self._lock:
                self._apply_static()
            self._fit_pending = True
            self._mark()
            return
        with self._lock:
            for n in self.nodes.values():
                if n.kind != "phone":
                    n.fixed = False
                    n.placed = False
            self._place_new()
            self._hot = 1.0
        self._fit_pending = True

    # ---------------------------------------------------------------- layout statici (OSInt Graph: circle, breadthfirst, grid)
    def set_layout(self, kind: str) -> None:
        if kind not in LAYOUTS or self._untangling:
            return
        self.layout = kind
        self._paint_layout_btns()
        self.relayout()

    def _visible(self) -> list[Node]:
        return [n for n in self.nodes.values() if n.id not in self.hidden]

    def _order(self) -> list[Node]:
        """Nodi visibili in ordine di albero (telefono, poi i rami in profondità): tiene vicini i parenti."""
        nodes = {n.id: n for n in self._visible()}
        kids: dict[str | None, list[Node]] = {}
        for n in nodes.values():
            p = n.parent if n.parent in nodes else None
            kids.setdefault(p, []).append(n)
        for lst in kids.values():
            lst.sort(key=lambda n: (LEVEL.get(n.kind, 9), n.label.lower()))
        out: list[Node] = []

        def walk(p):
            for n in kids.get(p, []):
                out.append(n)
                walk(n.id)
        walk(None)
        return out

    def _apply_static(self) -> None:
        """Posiziona tutti i nodi visibili secondo self.layout (con il lock gia' preso). Niente forze."""
        nodes = self._order()
        self._hot = 0.0
        if not nodes:
            return
        for n in nodes:
            n.fixed, n.placed = True, True
        if self.layout == "circle":
            k = len(nodes)
            r = max(IDEAL, IDEAL * k / 6.0)          # circonferenza ~ 110 px a nodo (come cytoscape circle)
            for i, n in enumerate(nodes):
                a = -math.pi / 2 + 2 * math.pi * i / k
                n.x, n.y = r * math.cos(a), r * math.sin(a)
        elif self.layout == "grid":
            k = len(nodes)
            cols = max(1, int(math.ceil(math.sqrt(k))))
            step = IDEAL * 1.1
            for i, n in enumerate(nodes):
                n.x = (i % cols - (cols - 1) / 2) * step
                n.y = (i // cols - (math.ceil(k / cols) - 1) / 2) * step
        elif self.layout == "tree":
            self._tree_layout(nodes)
        self._dirty = True

    def _tree_layout(self, nodes: list[Node]) -> None:
        """Gerarchico (breadthfirst, spacingFactor 1.3): ogni livello su una riga, le foglie spaziate
        uniformemente e ogni padre centrato sopra i suoi figli."""
        ids = {n.id for n in nodes}
        kids: dict[str | None, list[Node]] = {}
        for n in nodes:
            kids.setdefault(n.parent if n.parent in ids else None, []).append(n)
        sx, sy = IDEAL * 1.15, IDEAL * 1.3
        cursor = [0.0]

        def place(n: Node, depth: int) -> None:
            ch = kids.get(n.id, [])
            n.y = depth * sy
            if not ch:
                n.x = cursor[0]
                cursor[0] += sx
                return
            if len(ch) > TREE_WRAP and not any(kids.get(c.id) for c in ch):
                # tante foglie sotto lo stesso padre: a blocchi di righe invece di una riga lunghissima
                cols = max(6, int(math.ceil(math.sqrt(len(ch) * 1.6))))
                bx = sx * 1.35                    # etichette lunghe (domini): un po' piu' di spazio
                x0 = cursor[0]
                for i, c in enumerate(ch):
                    c.x = x0 + (i % cols) * bx
                    c.y = (depth + 1) * sy + (i // cols) * sy * 0.62
                cursor[0] = x0 + min(cols, len(ch)) * bx
                n.x = x0 + (min(cols, len(ch)) - 1) * bx / 2
                return
            for c in ch:
                place(c, depth + 1)
            n.x = (ch[0].x + ch[-1].x) / 2
        roots = kids.get(None, [])
        for r in roots:
            place(r, 0)
            cursor[0] += sx * 0.5
        xs = [n.x for n in nodes]
        off = (min(xs) + max(xs)) / 2
        for n in nodes:
            n.x -= off
            n.y -= sy * 1.5

    # ---------------------------------------------------------------- riduci incroci
    @staticmethod
    def _crosses(p, q) -> bool:
        if p[4] in (q[4], q[5]) or p[5] in (q[4], q[5]):
            return False

        def sgn(ax, ay, bx, by, cx, cy):
            v = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
            return (v > 0) - (v < 0)
        d1 = sgn(p[0], p[1], p[2], p[3], q[0], q[1])
        d2 = sgn(p[0], p[1], p[2], p[3], q[2], q[3])
        d3 = sgn(q[0], q[1], q[2], q[3], p[0], p[1])
        d4 = sgn(q[0], q[1], q[2], q[3], p[2], p[3])
        return d1 != d2 and d3 != d4

    def count_crossings(self) -> int:
        segs = []
        for (a, b) in self.edges:
            if a in self.hidden or b in self.hidden:
                continue
            na, nb = self.nodes[a], self.nodes[b]
            segs.append((na.x, na.y, nb.x, nb.y, a, b))
        c = 0
        for i in range(len(segs)):
            for j in range(i + 1, len(segs)):
                if self._crosses(segs[i], segs[j]):
                    c += 1
        return c

    def untangle(self) -> None:
        """Come in OSInt Graph: piu' disposizioni organiche con semi diversi, si tiene quella con meno incroci."""
        if self._untangling:
            return
        self._untangling = True
        self.layout = "organic"
        self._paint_layout_btns()
        self.btn_untangle.configure(text="✂ …", state="disabled")
        threading.Thread(target=self._untangle_run, daemon=True, name="Untangle").start()

    def _untangle_run(self) -> None:
        best, best_c, k = None, 1 << 30, 0
        t0 = time.monotonic()
        try:
            with self._lock:
                if len(self._visible()) < 3:
                    return
                self._hot = 0.0
                while k < UNTANGLE_RUNS and time.monotonic() - t0 < UNTANGLE_BUDGET:
                    # ogni tentativo riparte dai figli attorno ai padri con angoli casuali (seme diverso)
                    for n in self.nodes.values():
                        if n.kind != "phone":
                            n.fixed, n.placed = False, False
                    self._place_new()
                    temp = 1.0
                    for _ in range(400):
                        self._iterate(temp)
                        temp *= 0.985
                    k += 1
                    c = self.count_crossings()
                    if c < best_c:
                        best_c, best = c, {n.id: (n.x, n.y) for n in self.nodes.values()}
                    if best_c == 0:
                        break
                if best:
                    for nid, (x, y) in best.items():
                        if nid in self.nodes:
                            self.nodes[nid].x, self.nodes[nid].y = x, y
                self._hot = 0.0
                self._dirty = True
        finally:
            self._untangling = False
            self._fit_pending = True

            def done():
                try:
                    self.btn_untangle.configure(text="✂ " + tr("Riduci incroci"), state="normal")
                    self.set_legend_note(tr("{n} incroci dopo {k} tentativi", n=best_c if best else 0, k=k))
                except tk.TclError:
                    pass
            self.after(0, done)

    def set_legend_note(self, text: str) -> None:
        """Riga aggiunta in fondo alla legenda (esito di Riduci incroci); sparisce al prossimo set_legend."""
        self.legend.configure(text=(self._stats_text + "\n" if self._stats_text else "") + text)

    # ---------------------------------------------------------------- vista
    def _to_screen(self, x: float, y: float) -> tuple[float, float]:
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        return (x - self.cx) * self.scale + w / 2, (y - self.cy) * self.scale + h / 2

    def _to_world(self, sx: float, sy: float) -> tuple[float, float]:
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        return (sx - w / 2) / self.scale + self.cx, (sy - h / 2) / self.scale + self.cy

    def fit(self) -> None:
        with self._lock:
            pts = [(n.x, n.y) for n in self.nodes.values() if n.id not in self.hidden]
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if not pts or w < 10:
            return
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.cx, self.cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        span_x, span_y = max(xs) - min(xs) + 160, max(ys) - min(ys) + 160
        self.scale = max(0.15, min(1.6, min(w / span_x, h / span_y)))
        self._fit_pending = False
        self._mark()

    def _zoom_center(self, f: float) -> None:
        self._zoom_at(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, f)

    def _zoom_at(self, sx: float, sy: float, f: float) -> None:
        self._user_view = True
        wx, wy = self._to_world(sx, sy)
        self.scale = max(0.1, min(4.0, self.scale * f))
        nx, ny = self._to_world(sx, sy)
        self.cx += wx - nx
        self.cy += wy - ny
        self._mark()

    def _wheel(self, e) -> None:
        self._zoom_at(e.x, e.y, 1.2 if e.delta > 0 else 1 / 1.2)

    def _mark(self) -> None:
        self._dirty = True

    # ---------------------------------------------------------------- mouse
    def _node_at(self, sx: float, sy: float) -> Node | None:
        best, bd = None, 1e9
        with self._lock:
            for n in self.nodes.values():
                if n.id in self.hidden:
                    continue
                x, y = self._to_screen(n.x, n.y)
                r = n.size * self.scale / 2 + 4
                d = (x - sx) ** 2 + (y - sy) ** 2
                if d <= r * r and d < bd:
                    best, bd = n, d
        return best

    def _press(self, e) -> None:
        n = self._node_at(e.x, e.y)
        self._drag = ("node", n, e.x, e.y) if n else ("pan", None, e.x, e.y)
        self._moved = 0

    def _motion(self, e) -> None:
        if not self._drag:
            return
        kind, n, lx, ly = self._drag
        dx, dy = e.x - lx, e.y - ly
        self._moved += abs(dx) + abs(dy)
        self._drag = (kind, n, e.x, e.y)
        if kind == "node":
            with self._lock:
                n.x += dx / self.scale
                n.y += dy / self.scale
                n.fixed = True
                self._hot = max(self._hot, 0.25)
        else:
            self.cx -= dx / self.scale
            self._user_view = True
            self.cy -= dy / self.scale
        self._mark()

    def _release(self, e) -> None:
        if not self._drag:
            return
        kind, n, _x, _y = self._drag
        self._drag = None
        if self._moved > 4:
            return
        self.selected = n.id if n else None
        self._mark()
        if self.on_select:
            self.on_select(n)

    def _double(self, e) -> None:
        n = self._node_at(e.x, e.y)
        if not n:
            return
        if n.kind in ("app", "org"):
            with self._lock:
                if n.id in self.collapsed:
                    self.collapsed.discard(n.id)
                else:
                    self.collapsed.add(n.id)
                self._update_hidden()
                self._hot = max(self._hot, 0.4)
            self._mark()
        if self.on_open:
            self.on_open(n)

    def _hover(self, e) -> None:
        if self._drag:
            return
        n = self._node_at(e.x, e.y)
        c = self.canvas
        c.configure(cursor="hand2" if n else "fleur")
        tip = n.id if n else None
        if tip == self._tip_id and c.find_withtag("tip"):
            return
        self._tip_id = tip
        c.delete("tip")
        if n is None:
            return
        # nome completo (le etichette lunghe o sovrapposte sono abbreviate o nascoste)
        x, y = self._to_screen(n.x, n.y)
        r = n.size * self.scale / 2
        t = c.create_text(x, y - r - 12, text=n.label, anchor="s", fill=theme.TEXT,
                          font=(theme.ui_font(), 10, "bold"), tags=("tip",))
        x0, y0, x1, y1 = c.bbox(t)
        dx = max(0, 8 - x0) - max(0, x1 + 8 - c.winfo_width())
        dy = (r * 2 + 30 + (y1 - y0)) if y0 < 8 else 0          # in alto non ci sta: sotto il nodo
        if dx or dy:
            c.move(t, dx, dy)
            x0, y0, x1, y1 = c.bbox(t)
        box = c.create_rectangle(x0 - 7, y0 - 4, x1 + 7, y1 + 4, fill=theme.PANEL,
                                 outline=n.color or KIND_COLOR.get(n.kind, EDGE_COLOR), tags=("tip",))
        c.tag_lower(box, t)

    # ---------------------------------------------------------------- disegno
    def _frame(self) -> None:
        try:
            if self.active and self.winfo_exists():
                if self._fit_pending and self.nodes and self.canvas.winfo_width() > 10:
                    self.fit()
                if self._dirty:
                    self._dirty = False
                    self.redraw()
                elif (self._paths or self._rings) and not self._drag:
                    self._position_particles()
        except tk.TclError:
            return
        self.after(33 if self.active and (self._paths or self._rings) else 50, self._frame)

    # ---------------------------------------------------------------- traffico animato (come sulla mappa)
    @staticmethod
    def _curve(x1, y1, cx, cy, x2, y2) -> list[tuple[float, float]]:
        """I punti della linea "smooth" di Tk fra tre punti: retta, arco di parabola, retta."""
        if (cx, cy) == ((x1 + x2) / 2, (y1 + y2) / 2):
            return [(x1, y1), (x2, y2)]
        ax, ay, bx, by = (x1 + cx) / 2, (y1 + cy) / 2, (cx + x2) / 2, (cy + y2) / 2
        pts = [(x1, y1)]
        for i in range(9):
            t = i / 8
            u = 1 - t
            pts.append((u * u * ax + 2 * u * t * cx + t * t * bx, u * u * ay + 2 * u * t * cy + t * t * by))
        pts.append((x2, y2))
        return pts

    def _add_particles(self, e: Edge, pts: list, color: str) -> None:
        """Impulsi del traffico su un arco (creati qui, mossi da _frame): una testa e due puntini di scia."""
        if len(self._paths) >= 160:
            return
        c = self.canvas
        cum, acc = [0.0], 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            acc += math.hypot(x1 - x0, y1 - y0)
            cum.append(acc)
        if acc < 12:
            return
        k = max(0.7, min(self.scale, 1.4))
        items = []
        for direction, rate, col in ((1, e.rate_out, _mix(color, "#ffffff", 0.35)), (-1, e.rate_in, theme.TEXT)):
            n = particles_for(rate)
            size = (1.6 + min(1.8, math.log10(1 + rate / 4096))) * k
            for i in range(n):
                dots = tuple(c.create_oval(-9, -9, -9, -9, fill=_mix(col, theme.BG, fade), outline="")
                             for fade in (0.72, 0.45, 0.0))            # la testa per ultima: sta sopra
                items.append((dots, direction, i / n, size))
        if items:
            self._paths.append({"pts": pts, "len": cum, "items": items})

    def _position_particles(self) -> None:
        now = time.monotonic()
        c = self.canvas
        for p in self._paths:
            pts, cum = p["pts"], p["len"]
            total = cum[-1]
            period = max(1.0, min(5.0, total / 110.0))     # velocità costante a schermo, giro fra 1 e 5 s
            for dots, direction, phase, size in p["items"]:
                t = (phase + now / period) % 1.0
                gap = min(0.04, (size * 2.2) / total)
                for j, item in enumerate(dots):            # scia lontana, scia vicina, testa
                    tt = t - (2 - j) * gap
                    if tt < 0:
                        c.coords(item, -9, -9, -9, -9)
                        continue
                    d = (1.0 - tt if direction < 0 else tt) * total
                    lo, hi = 0, len(cum) - 1
                    while lo < hi - 1:
                        mid = (lo + hi) // 2
                        if cum[mid] <= d:
                            lo = mid
                        else:
                            hi = mid
                    f = (d - cum[lo]) / ((cum[hi] - cum[lo]) or 1)
                    x = pts[lo][0] + (pts[hi][0] - pts[lo][0]) * f
                    y = pts[lo][1] + (pts[hi][1] - pts[lo][1]) * f
                    sz = size * (0.5, 0.75, 1.0)[j]
                    c.coords(item, x - sz, y - sz, x + sz, y + sz)
        for it, x, y, r, col, period in self._rings:
            f = (now / period) % 1.0
            rr = r + 9 * f
            c.coords(it, x - rr, y - rr, x + rr, y + rr)
            c.itemconfigure(it, outline=_mix(col, theme.BG, 0.25 + 0.75 * f))

    def _photo(self, n: Node, px: int) -> ImageTk.PhotoImage | None:
        if not n.icon:
            return None
        key = (n.id, px)
        img = self._icon_cache.get(key)
        if img is None:
            try:
                im = Image.open(io.BytesIO(base64.b64decode(n.icon))).convert("RGBA")
                im = im.resize((px * 4, px * 4), Image.LANCZOS)
                mask = Image.new("L", im.size, 0)
                ImageDraw.Draw(mask).ellipse((0, 0, im.size[0] - 1, im.size[1] - 1), fill=255)
                im.putalpha(ImageChops.multiply(im.getchannel("A"), mask))
                im = im.resize((px, px), Image.LANCZOS)          # supersampling: bordo del cerchio liscio
                img = ImageTk.PhotoImage(im)
            except Exception:  # noqa: BLE001 - icona non valida
                n.icon = None
                return None
            if len(self._icon_cache) > 400:
                self._icon_cache.clear()
            self._icon_cache[key] = img
        return img

    def _draw_glyph(self, kind: str, x: float, y: float, r: float, ink: str) -> None:
        """Icone a linee sottili (stile lineare, vettoriale): telefono, organizzazione (palazzo), destinazione (globo)."""
        c = self.canvas
        lw = max(1.0, r / 14)
        if kind == "phone":
            w, h = r * 0.62, r * 1.08
            c.create_rectangle(x - w / 2, y - h / 2, x + w / 2, y + h / 2, outline=ink, width=lw * 1.2)
            c.create_line(x - w * 0.18, y - h / 2 + lw * 2.2, x + w * 0.18, y - h / 2 + lw * 2.2, fill=ink, width=lw, capstyle="round")
            c.create_oval(x - lw, y + h / 2 - lw * 3.6, x + lw, y + h / 2 - lw * 1.6, outline=ink, fill=ink)
        elif kind == "org":
            w, h = r * 1.0, r * 1.0
            x0, y0 = x - w / 2, y - h / 2
            c.create_rectangle(x0, y0, x0 + w * 0.62, y0 + h, outline=ink, width=lw)
            c.create_rectangle(x0 + w * 0.62, y0 + h * 0.35, x0 + w, y0 + h, outline=ink, width=lw)
            for row in range(3):
                yy = y0 + h * (0.2 + row * 0.25)
                for col in range(2):
                    xx = x0 + w * (0.14 + col * 0.26)
                    c.create_line(xx, yy, xx + w * 0.1, yy, fill=ink, width=lw * 1.3)
            c.create_line(x0 + w * 0.31 - lw, y0 + h, x0 + w * 0.31 - lw, y0 + h * 0.8, fill=ink, width=lw)
        else:  # dest / country: globo
            rr = r * 0.55
            c.create_oval(x - rr, y - rr, x + rr, y + rr, outline=ink, width=lw)
            c.create_oval(x - rr * 0.42, y - rr, x + rr * 0.42, y + rr, outline=ink, width=lw * 0.8)
            c.create_line(x - rr, y, x + rr, y, fill=ink, width=lw * 0.8)
            c.create_line(x - rr * 0.86, y - rr * 0.5, x + rr * 0.86, y - rr * 0.5, fill=ink, width=lw * 0.6)
            c.create_line(x - rr * 0.86, y + rr * 0.5, x + rr * 0.86, y + rr * 0.5, fill=ink, width=lw * 0.6)

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        self._paths, self._rings = [], []
        live: dict[str, int] = {}
        with self._lock:
            nodes = {k: v for k, v in self.nodes.items() if k not in self.hidden}
            edges = list(self.edges.values())
            pos = {k: self._to_screen(n.x, n.y) for k, n in nodes.items()}
        sel = self.selected if self.selected in nodes else None
        focus = ({sel} | self.adj.get(sel, set())) if sel else None
        s = self.scale
        wmax = max((e.weight for e in edges), default=1.0) or 1.0
        for e in edges:
            if e.a not in pos or e.b not in pos:
                continue
            (x1, y1), (x2, y2) = pos[e.a], pos[e.b]
            dim = focus is not None and not (e.a in focus and e.b in focus and (e.a == sel or e.b == sel))
            col = _mix(e.color, theme.BG, 0.75 if dim else 0.25)
            w = 0.6 + 1.6 * math.log1p(e.weight) / math.log1p(wmax)      # linee fini
            # curva leggera (bezier) come in OSInt Graph
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            dx, dy = x2 - x1, y2 - y1
            d = math.hypot(dx, dy) or 1
            if self.layout == "organic":
                ox, oy = -dy / d * min(28, d * 0.12), dx / d * min(28, d * 0.12)
            else:
                ox = oy = 0.0                    # layout statici: linee dritte, piu' pulite
            c.create_line(x1, y1, mx + ox, my + oy, x2, y2, smooth=True, width=max(0.8, w * s), fill=col, capstyle="round")
            if e.active:
                live[e.b] = live.get(e.b, 0) + e.active
            if not dim and (e.rate_out > 0 or e.rate_in > 0):
                self._add_particles(e, self._curve(x1, y1, mx + ox, my + oy, x2, y2), e.color)
            if e.label and s > 0.7 and not dim:
                c.create_text(mx + ox, my + oy, text=e.label, font=(theme.ui_font(), 8), fill=theme.TEXT_DIM)
        font_px = max(7, int(10 * min(s, 1.3)))
        labels = []                      # (priorita', nodo, x, y sotto il cerchio, attenuata)
        for k, n in nodes.items():
            x, y = pos[k]
            r = n.size * s / 2
            dim = focus is not None and k not in focus
            border = n.color or KIND_COLOR.get(n.kind, EDGE_COLOR)
            bg = TARGET_BG if n.kind == "phone" else NODE_BG
            if dim:
                border, bg = _mix(border, theme.BG, 0.7), _mix(bg, theme.BG, 0.8)
            bw = (2.5 if n.kind == "phone" else 1.5) * max(0.6, min(s, 1.5))
            if k == sel:
                c.create_oval(x - r - 5, y - r - 5, x + r + 5, y + r + 5, outline=theme.ACCENT, width=2, dash=(3, 3))
            if n.kind == "dest" and live.get(k) and not dim and len(self._rings) < 80:
                ring = c.create_oval(x - r - 2, y - r - 2, x + r + 2, y + r + 2, outline=border, width=1)
                self._rings.append((ring, x, y, r + 1, border, 1.8 + (hash(k) % 7) / 10))
            c.create_oval(x - r, y - r, x + r, y + r, fill=bg, outline=border, width=bw)
            if k in self.collapsed:
                c.create_oval(x - r - 3, y - r - 3, x + r + 3, y + r + 3, outline=border, width=1)
            px = int(r * 1.3)
            photo = self._photo(n, px) if px >= 8 else None
            ink = _mix(border, "#000000", 0.2) if not dim else border
            if photo is not None and not dim:
                c.create_image(x, y, image=photo)
            elif n.kind in ("phone", "org", "dest", "country") and r >= 5:
                self._draw_glyph(n.kind, x, y, r, ink)
            elif n.glyph:
                c.create_text(x, y, text=n.glyph, font=(theme.ui_font(), max(6, int(r * 0.75)), "bold"), fill=ink)
            prio = 0 if n.kind == "phone" else 1 if k == sel else 2 if n.kind == "app" else 3 if n.kind == "org" else 4
            if not (prio == 4 and s < 0.22):
                labels.append((prio, -len(self.adj.get(k, ())), n, x, y + r + 5, dim))
        # etichette: prima le piu' importanti; una che finirebbe sopra un'altra viene abbreviata e, se non
        # basta, nascosta (il nome completo compare passando sopra il nodo con il mouse)
        placed: list[tuple[float, float, float, float]] = []
        labels.sort(key=lambda t: t[:2])
        for prio, _deg, n, x, y, dim in labels:
            px = font_px + (2 if n.kind == "phone" else 0)
            fnt = (theme.ui_font(), px, "bold")
            full = n.label if len(n.label) <= 22 else n.label[:21] + "…"
            for label in dict.fromkeys((full, full if len(full) <= 12 else full[:11] + "…")):
                half = len(label) * px * 0.36 + 3
                box = (x - half, y, x + half, y + px * 1.5)
                if prio <= 1 or not any(box[0] < q[2] and box[2] > q[0] and box[1] < q[3] and box[3] > q[1] for q in placed):
                    break
            else:
                continue
            placed.append(box)
            col = theme.TEXT if not dim else theme.TEXT_FAINT
            if n.kind == "phone":
                col = TARGET_BORDER if not dim else theme.TEXT_FAINT
            for ox, oy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
                c.create_text(x + ox, y + oy, text=label, font=fnt, fill=theme.BG, anchor="n")
            c.create_text(x, y, text=label, font=fnt, fill=col, anchor="n")
        self._tip_id = None
        self._position_particles()
        self._last_draw = time.monotonic()
