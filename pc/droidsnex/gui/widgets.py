# DroidSnex — componenti grafici nello stile di AndrOsint.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Riquadri, pulsanti, tabella e pulsanti finestra, con lo stesso aspetto di AndrOsint."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from . import frameless, theme

# glifi di Segoe Fluent Icons / MDL2
GLYPH_REFRESH = ""
GLYPH_MINIMIZE = ""
GLYPH_MAXIMIZE = ""
GLYPH_RESTORE = ""
GLYPH_CLOSE = ""


class Card(ctk.CTkFrame):
    """Riquadro bordato con titolo in maiuscolo e barretta d'accento; il contenuto va in `body`."""

    def __init__(self, parent, title: str, fonts: theme.Fonts) -> None:
        super().__init__(parent, fg_color=theme.PANEL, border_width=1,
                         border_color=theme.BORDER, corner_radius=4)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)       # riga 0: barra della finestra quando il riquadro è staccato
        head = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        head.grid(row=1, column=0, sticky="ew", padx=theme.PAD, pady=(theme.PAD - 2, 0))
        ctk.CTkFrame(head, fg_color=theme.ACCENT, width=2, height=11, corner_radius=0).pack(
            side="left", padx=(0, 7))
        self.title_label = ctk.CTkLabel(head, text=title.upper(), font=fonts.title,
                                        text_color=theme.TEXT_DIM, anchor="w", height=14)
        self.title_label.pack(side="left", fill="x")
        self.head = head
        self.body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.body.grid(row=2, column=0, sticky="nsew", padx=theme.PAD, pady=(theme.GAP, theme.PAD))

    def corner_button(self, text: str, command, tooltip: str = "") -> ctk.CTkButton:
        """Piccolo pulsante in alto a destra del riquadro (es. stacca / riaggancia)."""
        btn = ctk.CTkButton(self.head, text=text, width=22, height=18, corner_radius=3, fg_color="transparent",
                            hover_color=theme.HOVER, text_color=theme.TEXT_DIM, font=(theme.mono_font(), 13),
                            command=command)
        btn.pack(side="right")
        return btn


class StatCard(Card):
    """Card con un numero grande (contatori in alto)."""

    def __init__(self, parent, title: str, fonts: theme.Fonts) -> None:
        super().__init__(parent, title, fonts)
        self.value = ctk.CTkLabel(self.body, text="0", anchor="w", text_color=theme.TEXT,
                                  font=ctk.CTkFont(family=theme.mono_font(), size=22, weight="bold"))
        self.value.pack(fill="x")

    def set(self, v) -> None:
        self.value.configure(text=str(v))


def button(parent, text: str, command, primary: bool = False, width: int = 0, danger: bool = False,
           **kwargs) -> ctk.CTkButton:
    """Pulsante principale (accento), secondario (neutro) o distruttivo (bordo rosso)."""
    if danger:
        kwargs.setdefault("fg_color", "transparent")
        kwargs.setdefault("hover_color", theme.HOVER)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.ERR)
        kwargs.setdefault("text_color", theme.ERR)
    elif not primary:
        kwargs.setdefault("fg_color", theme.NEUTRAL)
        kwargs.setdefault("hover_color", theme.NEUTRAL_HOVER)
        kwargs.setdefault("text_color", theme.TEXT)
    kwargs.setdefault("font", (theme.ui_font(), 12, "bold"))
    kwargs.setdefault("height", 30)
    if width:
        kwargs["width"] = width
    return ctk.CTkButton(parent, text=text, command=command, **kwargs)


def caption(parent, text: str, fonts: theme.Fonts) -> ctk.CTkLabel:
    """Etichetta di sezione in maiuscolo, attenuata (come il titolo della barra laterale)."""
    return ctk.CTkLabel(parent, text=text.upper(), anchor="w", font=fonts.caption,
                        text_color=theme.TEXT_FAINT)


def rule(parent, horizontal: bool) -> ctk.CTkFrame:
    """Filetto di separazione da un pixel."""
    size = {"height": 1} if horizontal else {"width": 1}
    return ctk.CTkFrame(parent, fg_color=theme.BORDER, corner_radius=0, **size)


class Table(ctk.CTkFrame):
    """Tabella ttk con barra di scorrimento; le colonne elastiche riempiono la larghezza.

    `columns`: lista di (chiave, titolo, larghezza, si_allarga, allineamento).
    """

    def __init__(self, parent, columns, tags: dict[str, str] | None = None) -> None:
        super().__init__(parent, fg_color=theme.PANEL, border_width=1,
                         border_color=theme.BORDER, corner_radius=4)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        scale = theme.scaling(self)
        self._columns = [(key, int(width * scale), stretch) for key, _t, width, stretch, _a in columns]
        self._min_width = int(40 * scale)
        self._fitted_width = 0
        self.tree = ttk.Treeview(self, columns=[c[0] for c in columns], show="headings",
                                 selectmode="browse")
        for key, title, width, _stretch, anchor in columns:
            self.tree.heading(key, text=title.upper(), anchor=anchor)
            self.tree.column(key, width=int(width * scale), minwidth=self._min_width, anchor=anchor,
                             stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(1, 0), pady=1)
        self.tree.bind("<Configure>", self._fit, add="+")
        bar = ctk.CTkScrollbar(self, command=self.tree.yview)
        bar.grid(row=0, column=1, sticky="ns", padx=(0, 1), pady=1)
        self.tree.configure(yscrollcommand=bar.set)
        for name, color in (tags or {}).items():
            self.tree.tag_configure(name, foreground=color)

    def _fit(self, event) -> None:
        if event.width == self._fitted_width or event.width < 50:
            return
        self._fitted_width = event.width
        fixed = sum(w for _k, w, s in self._columns if not s)
        flexible = sum(w for _k, w, s in self._columns if s)
        if flexible <= 0:
            return
        factor = max(0.0, event.width - fixed) / flexible
        for key, width, stretch in self._columns:
            if stretch:
                self.tree.column(key, width=max(self._min_width, int(width * factor)))


class TabBar(ctk.CTkFrame):
    """Schede orizzontali con lo stesso aspetto della navigazione di AndrOsint:
    scheda attiva su fondo d'accento con barretta sotto, le altre attenuate.

    `items`: lista di (chiave, etichetta). Il conteggio accanto all'etichetta si
    aggiorna con set_count(chiave, n, colore).
    """

    def __init__(self, parent, fonts: theme.Fonts, items: list[tuple[str, str]],
                 on_select: Callable[[str], None]) -> None:
        super().__init__(parent, fg_color="transparent", corner_radius=0)
        self._fonts = fonts
        self._on_select = on_select
        self._tabs: dict[str, dict] = {}
        self.current = ""
        for key, label in items:
            box = ctk.CTkFrame(self, fg_color="transparent", corner_radius=4, width=10, height=34)
            box.pack(side="left", padx=(0, 2))
            inner = ctk.CTkFrame(box, fg_color="transparent", corner_radius=0, width=10, height=10)
            inner.pack(fill="both", expand=True, padx=12, pady=(5, 0))
            text = ctk.CTkLabel(inner, text=label, font=fonts.body, text_color=theme.TEXT_DIM, height=22)
            text.pack(side="left")
            count = ctk.CTkLabel(inner, text="", font=fonts.title, text_color=theme.TEXT_FAINT, height=22)
            count.pack(side="left", padx=(6, 0))
            bar = ctk.CTkFrame(box, fg_color="transparent", width=1, height=2, corner_radius=0)
            bar.pack(fill="x", side="bottom")
            self._tabs[key] = {"box": box, "text": text, "count": count, "bar": bar, "hover": False,
                               "color": None}
            for w in (box, inner, text, count):
                w.bind("<Button-1>", lambda _e, k=key: self._on_select(k))
                w.bind("<Enter>", lambda _e, k=key: self._hover(k, True))
                w.bind("<Leave>", lambda _e, k=key: self._hover(k, False))
                w.configure(cursor="hand2")

    def select(self, key: str) -> None:
        previous, self.current = self.current, key
        if previous in self._tabs:
            self._paint(previous)
        self._paint(key)

    def set_count(self, key: str, value, color: str | None = None) -> None:
        tab = self._tabs[key]
        tab["color"] = color
        tab["count"].configure(text=str(value), text_color=color or theme.TEXT_FAINT)

    def _hover(self, key: str, on: bool) -> None:
        self._tabs[key]["hover"] = on
        self._paint(key)

    def _paint(self, key: str) -> None:
        tab = self._tabs[key]
        if key == self.current:
            tab["box"].configure(fg_color=theme.ACCENT_BG)
            tab["bar"].configure(fg_color=theme.ACCENT)
            tab["text"].configure(text_color=theme.TEXT, font=self._fonts.bold)
        else:
            tab["box"].configure(fg_color=theme.HOVER if tab["hover"] else "transparent")
            tab["bar"].configure(fg_color="transparent")
            tab["text"].configure(text_color=theme.TEXT_SOFT if tab["hover"] else theme.TEXT_DIM,
                                  font=self._fonts.body)


def confirm(root, title: str, text: str, ok_text: str, on_ok: Callable[[], None], fonts: theme.Fonts,
            cancel_text: str = "Annulla", danger: bool = True) -> ctk.CTkToplevel:
    """Finestra di conferma nel tema del programma (modale). `on_ok` viene chiamata solo con OK."""
    win = ctk.CTkToplevel(root)
    win.title(title)
    win.resizable(False, False)
    win.transient(root)
    box = ctk.CTkFrame(win, fg_color=theme.PANEL, border_width=1, border_color=theme.BORDER, corner_radius=4)
    box.pack(fill="both", expand=True, padx=10, pady=10)
    ctk.CTkLabel(box, text=title.upper(), font=fonts.title, text_color=theme.ERR if danger else theme.TEXT_DIM,
                 anchor="w").pack(fill="x", padx=18, pady=(16, 6))
    ctk.CTkLabel(box, text=text, font=fonts.body, text_color=theme.TEXT, justify="left", anchor="w",
                 wraplength=380).pack(fill="x", padx=18, pady=(0, 16))
    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack(fill="x", padx=18, pady=(0, 16))

    def close() -> None:
        try:
            win.grab_release()
        except tk.TclError:
            pass
        win.destroy()

    def ok() -> None:
        close()
        on_ok()

    button(row, ok_text, ok, danger=danger, primary=not danger).pack(side="right")
    button(row, cancel_text, close).pack(side="right", padx=(0, 8))
    win.protocol("WM_DELETE_WINDOW", close)
    win.bind("<Escape>", lambda _e: close())
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = root.winfo_rootx() + (root.winfo_width() - w) // 2
    y = root.winfo_rooty() + (root.winfo_height() - h) // 3
    win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
    frameless.style_titlebar(win, theme.BG, theme.TEXT_SOFT, theme.BORDER)
    win.after(50, lambda: (win.lift(), win.focus_force(), win.grab_set()) if win.winfo_exists() else None)
    return win


def window_buttons(root, master, on_close: Callable[[], None]) -> ctk.CTkFrame:
    """Riduci / massimizza / chiudi, disegnati nell'intestazione (finestra senza barra)."""
    family = theme.icon_font()
    glyphs = (GLYPH_MINIMIZE, GLYPH_MAXIMIZE, GLYPH_CLOSE) if family else ("—", "□", "✕")
    restore = GLYPH_RESTORE if family else "❐"
    font = ctk.CTkFont(family=family or theme.ui_font(), size=10 if family else 13)
    box = ctk.CTkFrame(master, fg_color="transparent", corner_radius=0)
    buttons = []
    for glyph, command, hover in (
        (glyphs[0], root.iconify, theme.HOVER),
        (glyphs[1], lambda: frameless.toggle_maximize(root), theme.HOVER),
        (glyphs[2], on_close, theme.CLOSE_HOVER),
    ):
        item = ctk.CTkButton(box, text=glyph, command=command, width=46, height=34, corner_radius=0,
                             fg_color="transparent", hover_color=hover, text_color=theme.TEXT_DIM,
                             font=font)
        item.pack(side="left")
        buttons.append(item)

    def sync(event=None) -> None:
        if event is not None and event.widget is not getattr(root, "widget", root):
            return
        try:
            glyph = restore if root.state() == "zoomed" else glyphs[1]
            if buttons[1].winfo_exists() and buttons[1].cget("text") != glyph:
                buttons[1].configure(text=glyph)
        except tk.TclError:
            pass

    root.bind("<Configure>", sync, add="+")
    sync()
    return box


class ScaleRow(ctk.CTkFrame):
    """Legenda a colori: una fila di "● nome" colorati (scala di pericolosità)."""

    def __init__(self, parent, fonts, items, title: str = "") -> None:
        super().__init__(parent, fg_color="transparent")
        if title:
            ctk.CTkLabel(self, text=title, font=fonts.tiny, text_color=theme.TEXT_DIM).pack(side="left", padx=(8, 6), pady=3)
        for i, (color, text) in enumerate(items):
            ctk.CTkLabel(self, text=f"● {text}", font=fonts.tiny, text_color=color).pack(
                side="left", padx=(0, 8 if i == len(items) - 1 else 5), pady=3)
