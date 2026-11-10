# DroidSnex — finestra "Informazioni e licenze".  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Informazioni sul programma, licenza e attribuzioni obbligatorie dei dati di terze parti.

    about.show(root, fonts)

I testi completi stanno in LICENSE, NOTICE e THIRD_PARTY_NOTICES.md nella
cartella principale del progetto; qui ci sono le attribuzioni che le licenze
chiedono di mostrare all'utente (in particolare DB-IP, CC BY 4.0).
"""
from __future__ import annotations

import os
import tkinter as tk
import webbrowser

import customtkinter as ctk

from .. import __version__
from .. import terms
from ..i18n import language, tr
from ..paths import BUNDLE_DIR
from . import frameless, theme, welcome
from .widgets import button, caption, rule, window_buttons

APP_NAME = "DroidSnex"
AUTHOR = "Andrea Cumini"
CONTACT = "andrea@osintinfo.net  ·  www.osintinfo.net"
LICENSE_NAME = "GNU GPL v3 (GPL-3.0-or-later)"

# cartella principale del progetto (quella con LICENSE): .../DroidSnex/pc/droidsnex/gui -> .../DroidSnex
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_CANDIDATES = [os.path.normpath(os.path.join(_HERE, *[".."] * n)) for n in (3, 2)] + [BUNDLE_DIR]

# (titolo, testo, link): attribuzioni da mostrare nel programma
ATTRIBUTIONS = [
    ("DB-IP", "IP Geolocation by DB-IP  ·  DB-IP City Lite / ASN Lite, CC BY 4.0",
     "https://db-ip.com"),
    ("Natural Earth", "Made with Natural Earth  ·  pubblico dominio",
     "https://www.naturalearthdata.com"),
    ("Android Platform-Tools", "adb di Google, scaricato da dl.google.com, termini dell'Android SDK",
     "https://developer.android.com/studio/terms"),
    ("CustomTkinter", "MIT  ·  © 2023 Tom Schimansky",
     "https://github.com/TomSchimansky/CustomTkinter"),
    ("Pillow", "MIT-CMU (HPND)  ·  © Secret Labs AB, Fredrik Lundh, Jeffrey A. Clark e contributori",
     "https://python-pillow.org"),
    ("Kotlin", "Kotlin standard library nell'app Android, Apache-2.0  ·  © JetBrains",
     "https://kotlinlang.org"),
    ("Panchang", "carattere del logo, Indian Type Foundry / Fontshare (file non inclusi)",
     "https://www.fontshare.com/fonts/panchang"),
]


def project_file(name: str) -> str | None:
    """Percorso di LICENSE / NOTICE / THIRD_PARTY_NOTICES.md, se c'è."""
    for root in ROOT_CANDIDATES:
        path = os.path.join(root, name)
        if os.path.isfile(path):
            return path
    return None


def _open(target: str) -> None:
    """Apre un link nel browser o un file con il programma predefinito."""
    try:
        if target.startswith("http"):
            webbrowser.open(target)
        elif hasattr(os, "startfile"):
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            webbrowser.open("file://" + target)
    except OSError:
        pass


def _link(parent, text: str, url: str, fonts: theme.Fonts) -> ctk.CTkLabel:
    lab = ctk.CTkLabel(parent, text=text, font=fonts.small, text_color=theme.ACCENT, anchor="w", cursor="hand2",
                       height=18)
    lab.bind("<Button-1>", lambda _e: _open(url))
    return lab


def show(root, fonts: theme.Fonts) -> ctk.CTkToplevel:
    """Finestra nel tema del programma, con la stessa intestazione senza cornice delle finestre staccate
    (Mappa, Grafo) e del Manuale: logo, titolo trascinabile, riduci / massimizza / chiudi."""
    old = getattr(root, "_about_win", None)
    if old is not None and old.winfo_exists():       # una sola: quella già aperta torna davanti
        old.deiconify()
        old.lift()
        old.focus_force()
        return old
    win = ctk.CTkToplevel(root, fg_color=theme.BG)
    root._about_win = win
    win.title(f"{APP_NAME} · " + tr("Informazioni e licenze"))
    try:
        if getattr(root, "_droidsnex_icon", None) is not None:
            win.iconphoto(False, root._droidsnex_icon)
    except tk.TclError:
        pass

    def close() -> None:
        win.destroy()

    bar = ctk.CTkFrame(win, fg_color=theme.BG, corner_radius=0, height=34)
    bar.pack(side="top", fill="x", padx=1, pady=(1, 0))
    bar.pack_propagate(False)
    logo = theme.logo(12)
    brand = (ctk.CTkLabel(bar, text="", image=logo) if logo is not None else
             ctk.CTkLabel(bar, text=APP_NAME.upper(), font=(theme.mono_font(), 12, "bold")))
    brand.pack(side="left", padx=(12, 0))
    label = ctk.CTkLabel(bar, text="   ·   " + tr("Informazioni e licenze"), font=fonts.bold, text_color=theme.TEXT_SOFT)
    label.pack(side="left")
    window_buttons(win, bar, close).pack(side="right")
    for x in (bar, brand, label):
        frameless.enable_drag(win, x)
    box = ctk.CTkFrame(win, fg_color=theme.PANEL, border_width=1, border_color=theme.BORDER, corner_radius=0)
    box.pack(fill="both", expand=True, padx=1, pady=(0, 1))

    ctk.CTkLabel(box, text=f"{APP_NAME}  v{__version__}", font=fonts.page, text_color=theme.TEXT,
                 anchor="w").pack(fill="x", padx=18, pady=(16, 2))
    ctk.CTkLabel(box, text=f"© 2026 {AUTHOR}  ·  {CONTACT}", font=fonts.small, text_color=theme.TEXT_SOFT,
                 anchor="w").pack(fill="x", padx=18)
    ctk.CTkLabel(box, text=tr("Software libero, licenza") + f" {LICENSE_NAME}. "
                 + tr("Senza alcuna garanzia."), font=fonts.small, text_color=theme.TEXT_DIM,
                 anchor="w", justify="left", wraplength=520).pack(fill="x", padx=18, pady=(2, 12))
    rule(box, True).pack(fill="x", padx=18)

    caption(box, tr("Dati e componenti di terze parti"), fonts).pack(fill="x", padx=18, pady=(12, 4))
    body = ctk.CTkScrollableFrame(box, fg_color="transparent", width=520, height=300)
    body.pack(fill="both", expand=True, padx=12)
    body.grid_columnconfigure(0, weight=1)
    for i, (name, text, url) in enumerate(ATTRIBUTIONS):
        ctk.CTkLabel(body, text=name, font=fonts.bold, text_color=theme.TEXT, anchor="w", height=20).grid(
            row=3 * i, column=0, sticky="ew", padx=6, pady=(6, 0))
        ctk.CTkLabel(body, text=text, font=fonts.small, text_color=theme.TEXT_SOFT, anchor="w", justify="left",
                     wraplength=500, height=18).grid(row=3 * i + 1, column=0, sticky="ew", padx=6)
        _link(body, url, url, fonts).grid(row=3 * i + 2, column=0, sticky="ew", padx=6)

    row = ctk.CTkFrame(box, fg_color="transparent")
    row.pack(fill="x", padx=18, pady=(12, 16))

    button(row, tr("Chiudi"), close, primary=True).pack(side="right")
    for name, label in (("THIRD_PARTY_NOTICES.md", tr("Tutte le licenze")), ("LICENSE", "LICENSE")):
        path = project_file(name)
        if path:
            button(row, label, lambda p=path: _open(p)).pack(side="left", padx=(0, 8))
    # termini d'uso ed esclusione di responsabilita' (gli stessi accettati alla prima apertura; TERMS.md)
    button(row, terms.labels(language())[0], lambda: welcome.show_terms(root, fonts)).pack(side="left", padx=(0, 8))

    win.protocol("WM_DELETE_WINDOW", close)
    win.bind("<Escape>", lambda _e: close())
    win.update_idletasks()
    w, h = win.winfo_reqwidth(), win.winfo_reqheight()
    x = root.winfo_rootx() + (root.winfo_width() - w) // 2
    y = root.winfo_rooty() + (root.winfo_height() - h) // 4
    win.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
    state = {"done": False}

    def bare(event=None) -> None:
        """Via la barra del titolo di Windows: va fatto quando la finestra e' davvero sullo schermo."""
        if event is not None and event.widget is not win:
            return
        if state["done"] or not getattr(root, "frameless", False):
            return
        if frameless.make_frameless(win, border_color=theme.BORDER):
            state["done"] = True

    def raise_(n: int = 0) -> None:
        """CTkToplevel su Windows nasconde e rimostra la finestra appena creata: la si porta davanti."""
        if not win.winfo_exists():
            return
        try:
            win.deiconify()
            win.update_idletasks()
            bare()
            win.lift()
            win.focus_force()
        except tk.TclError:
            return
        if n < 10 and not state["done"] and getattr(root, "frameless", False):
            win.after(150, lambda: raise_(n + 1))

    win.bind("<Map>", bare, add="+")
    win.after(60, raise_)
    return win
