"""Timeline del traffico: byte al secondo per app nel tempo (aree impilate).

Sopra l'asse l'entrata (↓, dal server al telefono), sotto l'uscita (↑): così si vede
subito chi parla in background a telefono fermo e chi scarica. Le app oltre le prime
dieci finiscono in "altre". Clic su una voce della legenda = nascondi/mostra l'app;
passando il mouse sul grafico si leggono i valori di quell'istante.
"""
from __future__ import annotations

import collections
import time
import tkinter as tk
from typing import Callable

import customtkinter as ctk

from . import theme

PALETTE = ["#7b95dd", "#34d399", "#fbbf24", "#f87171", "#a78bfa", "#38bdf8", "#fb923c", "#e879f9", "#4ade80", "#f472b6",
           "#22d3ee", "#facc15"]
WINDOWS = ((2, "2 min"), (5, "5 min"), (15, "15 min"), (30, "30 min"))
MAX_APPS = 10
KEEP_SEC = 30 * 60 + 5


def _rate(v: float) -> str:
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if v < 1000:
            return f"{v:.0f} {unit}" if unit == "B/s" else f"{v:.1f} {unit}"
        v /= 1000
    return f"{v:.1f} TB/s"


class TimelineView(ctk.CTkFrame):
    def __init__(self, parent, fonts: theme.Fonts, label_of: Callable[[str], str] | None = None):
        super().__init__(parent, fg_color=theme.PANEL, corner_radius=0)
        self.fonts = fonts
        self.label_of = label_of or (lambda a: a)
        self.samples: collections.deque = collections.deque()     # (ts, {app: (in, out)})
        self.window = 5
        self.hidden: set[str] = set()
        self.colors: dict[str, str] = {}
        self.active = False
        self._dirty = True
        self._hover_x: int | None = None
        self._order: list[str] = []
        self._legend_rows: dict[str, tuple] = {}
        self._mode = "both"
        self.now = None                 # orologio alternativo (replay): callable -> istante "adesso"

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(8, 0))
        ctk.CTkLabel(top, text="FINESTRA", font=fonts.caption, text_color=theme.TEXT_FAINT).pack(side="left", padx=(0, 8))
        self.win_seg = ctk.CTkSegmentedButton(top, values=[w[1] for w in WINDOWS], height=26, font=fonts.small,
                                              command=self._set_window, selected_color=theme.BTN,
                                              selected_hover_color=theme.BTN_HOVER)
        self.win_seg.set("5 min")
        self.win_seg.pack(side="left")
        self.mode_names = {"both": "↓ ↑", "in": "↓", "out": "↑"}
        self.mode_seg = ctk.CTkSegmentedButton(top, values=list(self.mode_names.values()), height=26, font=fonts.small,
                                               command=self._set_mode, selected_color=theme.BTN,
                                               selected_hover_color=theme.BTN_HOVER, width=120)
        self.mode_seg.set("↓ ↑")
        self.mode_seg.pack(side="left", padx=(12, 0))
        self.info = ctk.CTkLabel(top, text="", font=fonts.mono, text_color=theme.TEXT_SOFT, anchor="e")
        self.info.pack(side="right")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(6, 10))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(body, bg=theme.BG, highlightthickness=1, highlightbackground=theme.BORDER, bd=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(None))
        self.canvas.bind("<Configure>", lambda _e: self._mark())
        self.legend = ctk.CTkScrollableFrame(body, fg_color=theme.PANEL_2, corner_radius=4, border_width=1,
                                             border_color=theme.BORDER, width=250)
        self.legend.grid(row=0, column=1, sticky="ns", padx=(theme.GAP, 0))
        self.after(500, self._frame)

    # ---------------------------------------------------------------- dati
    def add(self, per_app: dict[str, tuple[int, int]], ts: float | None = None) -> None:
        ts = ts or time.time()
        self.samples.append((ts, per_app))
        while self.samples and ts - self.samples[0][0] > KEEP_SEC:
            self.samples.popleft()
        self._dirty = True

    def clear(self) -> None:
        self.samples.clear()
        self._dirty = True

    def _set_window(self, value: str) -> None:
        self.window = next(w for w, name in WINDOWS if name == value)
        self._dirty = True

    def _set_mode(self, value: str) -> None:
        self._mode = next(k for k, v in self.mode_names.items() if v == value)
        self._dirty = True

    def _mark(self) -> None:
        self._dirty = True

    def _frame(self) -> None:
        try:
            if self.active and self._dirty and self.winfo_exists():
                self._dirty = False
                self.redraw()
        except tk.TclError:
            return
        self.after(1000, self._frame)

    def _color(self, app: str) -> str:
        if app not in self.colors:
            self.colors[app] = PALETTE[len(self.colors) % len(PALETTE)] if app != "altre" else theme.TEXT_FAINT
        return self.colors[app]

    # ---------------------------------------------------------------- mouse
    def _motion(self, e) -> None:
        self._set_hover(e.x)

    def _set_hover(self, x: int | None) -> None:
        if x != self._hover_x:
            self._hover_x = x
            self._dirty = True
            self.redraw()
            self._dirty = False

    def _toggle(self, app: str) -> None:
        if app in self.hidden:
            self.hidden.discard(app)
        else:
            self.hidden.add(app)
        self._dirty = True

    # ---------------------------------------------------------------- disegno
    def _series(self, t_from: float, t_to: float):
        """Campioni nella finestra, già aggregati: [(ts, {app: (in, out)})], app ordinate per traffico."""
        pts = [s for s in self.samples if t_from <= s[0] <= t_to]
        totals: dict[str, int] = {}
        for _ts, d in pts:
            for app, (i, o) in d.items():
                totals[app] = totals.get(app, 0) + i + o
        order = sorted(totals, key=lambda a: -totals[a])
        top = order[:MAX_APPS]
        if len(order) > MAX_APPS:
            top.append("altre")
        rows = []
        for ts, d in pts:
            agg: dict[str, list[int]] = {}
            for app, (i, o) in d.items():
                k = app if app in top else "altre"
                acc = agg.setdefault(k, [0, 0])
                acc[0] += i; acc[1] += o
            rows.append((ts, agg))
        return rows, top, totals

    def redraw(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        now = self.now() if self.now else time.time()     # nel replay: l'istante della sessione
        t_from, t_to = now - self.window * 60, now
        rows, order, totals = self._series(t_from, t_to)
        self._order = order
        self._paint_legend(order, totals)
        shown = [a for a in order if a not in self.hidden]
        pad_l, pad_r, pad_t, pad_b = 78, 14, 14, 24
        gw, gh = w - pad_l - pad_r, h - pad_t - pad_b
        both = self._mode == "both"
        zero_y = pad_t + (gh / 2 if both else gh)
        half = gh / 2 if both else gh
        peak = 1.0
        for _ts, agg in rows:
            tin = sum(agg.get(a, (0, 0))[0] for a in shown)
            tout = sum(agg.get(a, (0, 0))[1] for a in shown)
            if self._mode in ("both", "in"):
                peak = max(peak, tin)
            if self._mode in ("both", "out"):
                peak = max(peak, tout)
        # griglia
        c.create_line(pad_l, zero_y, w - pad_r, zero_y, fill=theme.BORDER_STRONG)
        for frac in (0.5, 1.0):
            yv = peak * frac
            for sign in ((1, -1) if both else ((1,) if self._mode == "in" else (-1,))):
                yy = zero_y - sign * half * frac * 0.92
                c.create_line(pad_l, yy, w - pad_r, yy, fill=theme.BORDER, dash=(2, 4))
                c.create_text(pad_l - 6, yy, text=("↓ " if sign > 0 else "↑ ") + _rate(yv), anchor="e",
                              font=(theme.mono_font(), 8), fill=theme.TEXT_DIM)
        step = 60 if self.window <= 5 else 300 if self.window <= 15 else 600
        t = (int(t_from) // step + 1) * step
        while t < t_to:
            x = pad_l + (t - t_from) / (t_to - t_from) * gw
            c.create_line(x, pad_t, x, h - pad_b, fill=theme.BORDER, dash=(2, 4))
            c.create_text(x, h - pad_b + 4, text=time.strftime("%H:%M", time.localtime(t)), anchor="n",
                          font=(theme.mono_font(), 8), fill=theme.TEXT_DIM)
            t += step
        if not rows:
            c.create_text(w / 2, h / 2, text="in attesa di traffico…", fill=theme.TEXT_FAINT, font=self.fonts.body)
            return
        # aree impilate (entrata sopra, uscita sotto)
        xs = [pad_l + (ts - t_from) / (t_to - t_from) * gw for ts, _a in rows]
        for sign, idx in (((1, 0),) if self._mode == "in" else ((-1, 1),) if self._mode == "out" else ((1, 0), (-1, 1))):
            base = [0.0] * len(rows)
            for app in reversed(shown):          # la più grossa in fondo
                top_vals = []
                for i, (_ts, agg) in enumerate(rows):
                    v = agg.get(app, (0, 0))[idx]
                    base[i] += v
                    top_vals.append(base[i])
                pts = []
                for i, x in enumerate(xs):
                    pts.append((x, zero_y - sign * half * 0.92 * (top_vals[i] / peak)))
                lower = [(x, zero_y - sign * half * 0.92 * ((top_vals[i] - rows[i][1].get(app, (0, 0))[idx]) / peak))
                         for i, x in enumerate(xs)]
                poly = [v for p in pts for v in p] + [v for p in reversed(lower) for v in p]
                if len(poly) >= 6:
                    col = self._color(app)
                    c.create_polygon(poly, fill=col, outline=col, stipple="gray50" if sign < 0 else "", width=1)
        # cursore
        if self._hover_x is not None and pad_l <= self._hover_x <= w - pad_r:
            i = min(range(len(xs)), key=lambda k: abs(xs[k] - self._hover_x))
            ts, agg = rows[i]
            x = xs[i]
            c.create_line(x, pad_t, x, h - pad_b, fill=theme.ACCENT)
            lines = [time.strftime("%H:%M:%S", time.localtime(ts))]
            for app in shown:
                vin, vout = agg.get(app, (0, 0))
                if vin or vout:
                    lines.append(f"{self.label_of(app)[:22]:22} ↓{_rate(vin):>10} ↑{_rate(vout):>10}")
            tx = x + 10 if x < w / 2 else x - 10
            anchor = "nw" if x < w / 2 else "ne"
            tid = c.create_text(tx, pad_t + 4, text="\n".join(lines), anchor=anchor, font=(theme.mono_font(), 9),
                                fill=theme.TEXT)
            bb = c.bbox(tid)
            c.create_rectangle(bb[0] - 6, bb[1] - 4, bb[2] + 6, bb[3] + 4, fill=theme.PANEL, outline=theme.BORDER_STRONG)
            c.tag_raise(tid)
        tot_in = sum(agg.get(a, (0, 0))[0] for _ts, agg in rows for a in shown)
        tot_out = sum(agg.get(a, (0, 0))[1] for _ts, agg in rows for a in shown)
        self.info.configure(text=f"↓ {_bytes(tot_in)}   ↑ {_bytes(tot_out)}   ·   {len(order)} app")

    def _paint_legend(self, order: list[str], totals: dict[str, int]) -> None:
        for app in list(self._legend_rows):
            if app not in order:
                for w in self._legend_rows.pop(app):
                    w.destroy()
        tot_all = sum(totals.values()) or 1
        for i, app in enumerate(order):
            share = (totals.get(app, 0) if app != "altre" else sum(v for a, v in totals.items() if a not in order[:MAX_APPS])) / tot_all
            text = f"{self.label_of(app)[:26]}  ·  {share * 100:.0f}%"
            if app not in self._legend_rows:
                row = ctk.CTkFrame(self.legend, fg_color="transparent", cursor="hand2")
                dot = ctk.CTkLabel(row, text="■", font=(theme.mono_font(), 12), text_color=self._color(app), width=16)
                dot.pack(side="left")
                lab = ctk.CTkLabel(row, text=text, font=self.fonts.small, text_color=theme.TEXT, anchor="w")
                lab.pack(side="left", fill="x", expand=True)
                for wdg in (row, dot, lab):
                    wdg.bind("<Button-1>", lambda _e, a=app: self._toggle(a))
                self._legend_rows[app] = (row, dot, lab)
            row, dot, lab = self._legend_rows[app]
            hidden = app in self.hidden
            lab.configure(text=text, text_color=theme.TEXT_FAINT if hidden else theme.TEXT)
            dot.configure(text_color=theme.TEXT_FAINT if hidden else self._color(app))
            row.pack_forget()
            row.pack(fill="x", padx=4, pady=1)


def _bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1000:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000
    return f"{n:.1f} TB"
