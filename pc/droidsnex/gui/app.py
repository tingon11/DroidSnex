# DroidSnex — interfaccia grafica.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Finestra principale di DroidSnex, con l'impostazione di AndrOsint.

Intestazione (logo, dispositivo, stato) che fa da barra del titolo, colonna dei
comandi a sinistra, al centro le schede Config / Untrusted / Trusted / Mappa,
piede con lo stato.

    python gui.py                         # usa adb e il telefono collegato
    python gui.py --demo 127.0.0.1:8899   # collegati a tools/fake_agent.py, senza telefono
"""
from __future__ import annotations

import argparse
import atexit
import ipaddress
import os
import queue
import re
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from .. import DEFAULT_PORT, __version__
from .. import platform_tools
from ..adb import Adb, AdbError
from ..cli import HERE, find_apk, probe_agent
from ..paths import FROZEN, MANUAL_DIR, manual_path
from ..proc import hidden
from ..export import export_all
from ..geo import DBIP_FILE, GeoDb, download_dbip, public_ip
from .. import risk
from .. import scrcpy as scrcpy_mod
from .. import ipinfo
from .. import apkinfo
from .. import PACKAGE
from ..i18n import LANGUAGES, language, set_language, tr
from ..model import SORT_MODES, Monitor
from ..replay import SPEEDS, Replay
from ..resolve import AsnDb, ReverseDns
from ..settings import Settings
from ..stream import StreamClient
from ..vector import VectorMap, download_10m, load_async
from ..trust import TrustStore
from ..ui import _bytes, _ports, _t
from . import about, frameless, manual, theme, welcome
from .. import terms
from .. import updates
from .. import phoneloc
from .analysis import ANALYSIS_TABS, AnalysisMixin
from .mapview import Link, MapView, _rate
from .ipdetail import IpDetailWindow
from .widgets import GLYPH_REFRESH, Card, StatCard, Table, TabBar, button, caption, confirm, rule, window_buttons

APP_NAME = "DroidSnex"
CREDITS = "Andrea Cumini - andrea@osintinfo.net - www.osintinfo.net"
DEFAULT_SIZE = "1280x800"
MIN_SIZE = (1040, 660)
SIDE_WIDTH = 228
DETAILS_WIDTH = 260
NO_DEVICE = "Nessun dispositivo"
NO_DEVICE_HINT = "Collega il telefono via USB e attiva il Debug USB nelle Opzioni sviluppatore."
WATCHDOG_SEC = 20   # secondi senza PC dopo i quali l'agent sul telefono si ferma da solo
TRUST_FILE = os.path.join(HERE, "trusted.json")
CONFIG_FILE = os.path.join(HERE, "config.json")
DATA_DIR = os.path.join(HERE, "data")
VECTOR_50M = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "vector-50m.json.gz")
SESSIONS_DIR = os.path.join(HERE, "sessions")
TABS = (("config", "Config"), ("untrusted", "Untrusted"), ("trusted", "Trusted"), ("map", "Mappa")) + ANALYSIS_TABS
FLOAT_PAGES = ("map", "graph")       # schede che si possono staccare in una finestra a parte


def _describe_error(e: Exception) -> str:
    """Messaggio leggibile per gli errori di download (HTTP, rete, certificati)."""
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code} {e.reason} · {e.url}"
    if isinstance(e, urllib.error.URLError):
        return f"{tr('rete')}: {e.reason}"
    return f"{type(e).__name__}: {e}" if not str(e) else str(e)


def _kv(label: str, value) -> str:
    """Riga "etichetta   valore" allineata nel pannello dettagli."""
    return f"{label:<13}{value}"


def _ip_key(ip: str) -> tuple[int, int]:
    """Ordinamento numerico degli IP (10.0.0.9 prima di 10.0.0.10), prima IPv4 poi IPv6."""
    try:
        a = ipaddress.ip_address(ip)
        return a.version, int(a)
    except ValueError:
        return 9, 0


class App(AnalysisMixin, ctk.CTk):
    def __init__(self, demo: str | None = None, port: int = DEFAULT_PORT, asn_db: str | None = None,
                 out_dir: str | None = None) -> None:
        theme.apply()
        super().__init__()
        self.title(APP_NAME)
        self.settings = Settings.load(CONFIG_FILE)
        set_language(self.settings.language or "it")
        self.minsize(*MIN_SIZE)
        self.geometry(DEFAULT_SIZE)
        theme.set_icon(self)
        # senza barra del titolo di sistema (Windows): l'intestazione fa da barra
        self.frameless = frameless.make_frameless(self, border_color=theme.BORDER)
        # prima apertura (o termini nuovi): lingua e accettazione dei termini, prima di costruire l'interfaccia
        need_lang = not self.settings.language
        if need_lang or self.settings.terms_accepted != terms.TERMS_VERSION:
            self.withdraw()
            welcome.run(self, self.settings, need_lang,
                        on_accept=lambda: self._after_welcome(demo, port, asn_db, out_dir),
                        on_reject=self.destroy)
            return
        self._init_rest(demo, port, asn_db, out_dir)

    def _after_welcome(self, demo, port, asn_db, out_dir) -> None:
        """Termini accettati: salva, mostra la finestra principale e completa l'avvio."""
        self.settings.save(CONFIG_FILE)
        set_language(self.settings.language)
        self.deiconify()
        self._init_rest(demo, port, asn_db, out_dir)

    def _init_rest(self, demo: str | None, port: int, asn_db: str | None, out_dir: str | None) -> None:
        self.fonts = theme.Fonts()
        theme.style_tables(self)

        self.demo = demo
        self.port = port
        self.out_dir = os.path.abspath(out_dir or os.path.join(HERE, "captures"))
        self.adb: Adb | None = None
        self.client: StreamClient | None = None
        self.ui_queue: queue.Queue = queue.Queue()
        # un errore dentro una callback di Tk finisce nel registro (in rosso), non solo sulla console
        self.report_callback_exception = self._tk_exception
        self.busy = False
        asn_path = asn_db or AsnDb.autodetect([DATA_DIR, HERE, os.path.join(HERE, "data"), os.getcwd()])
        self.rdns = ReverseDns(True)
        self.mon = Monitor(self.rdns, AsnDb(asn_path))
        self.mon.hide_dns = True
        self.sort_mode = SORT_MODES[0]
        self.trust = TrustStore(TRUST_FILE)
        self._log_lines: list[tuple[str, str]] = []
        self._map_trust = "all"           # mappa: tutte / solo fidate / solo non fidate
        self._float_bars: dict = {}            # barre delle finestre staccate (solo Windows senza cornice)
        self._floating: dict[str, bool] = {}   # pannelli staccati in una finestra a parte: map, details, apps
        self.geo = GeoDb()
        self._open_geo()
        self.vector: VectorMap | None = None
        self._map_new_since: set | None = None   # "solo nuove": connessioni già viste quando è stato premuto
        self._map_new_t = ""
        self._load_vector()
        self._cancel = {"db": False, "tiles": False, "adb": False}
        self._init_analysis(DATA_DIR, SESSIONS_DIR)
        self._jobs: set[str] = set()
        # velocità del traffico: totali precedenti e media mobile per punto della mappa
        self._rate_prev: dict[str, tuple[int, int]] = {}
        self._rate_ema: dict[str, tuple[float, float]] = {}
        self._rate_t = time.monotonic()
        self._links: dict[str, Link] = {}
        self._map_sel: str | None = None
        self.tab = ""
        self.monitoring = False
        self._cleanup_done = True
        self._groups_by_dest: dict[str, object] = {}
        self._risk_by_dest: dict[str, risk.Risk] = {}
        self._job_error: dict[str, str] = {}      # ultimo errore di ogni download, mostrato nella sua card
        self.scrcpy = scrcpy_mod.Scrcpy()
        self.cloud = ipinfo.CloudRanges(DATA_DIR)
        self.ipdetail_win: IpDetailWindow | None = None
        self._guard: subprocess.Popen | None = None   # guardiano: pulisce il telefono se questo programma crasha
        self._replay: Replay | None = None       # replay di una sessione salvata (viste al posto del vivo)
        self._live: tuple | None = None           # (monitor, alert) dal vivo, messi da parte durante il replay
        self._replay_dt = 1.0
        self._replay_drag = False
        self._details_dest: str | None = None
        self._details_ip: str | None = None     # IP da mostrare per primo nel Dettaglio IP (linea sulla mappa)
        self._col_sort: dict | None = None
        # Se Python esce senza passare da _on_close (Ctrl+C, eccezione), puliamo comunque il telefono.
        # Se il processo viene ucciso, interviene il watchdog dell'agent.
        atexit.register(self._atexit)

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<F5>", lambda _e: self._run_bg(self._detect))
        self.bind("<Control-f>", lambda _e: self.search.focus_set())
        self.after(250, self._tick)
        self.after(150, self._busy_tick)
        if asn_path:
            self.log(f"db ASN: {os.path.basename(asn_path)}")
        if demo:
            self.after(300, self._connect_demo)
        else:
            self._hint(tr(NO_DEVICE_HINT))
            self.after(300, self._startup_adb)

    # ================================================================ costruzione
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_header()
        rule(self, True).grid(row=1, column=0, sticky="ew")

        body = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0)
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_columnconfigure(2, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self._build_side(body)
        rule(body, False).grid(row=0, column=1, sticky="ns")

        main = ctk.CTkFrame(body, fg_color=theme.BG, corner_radius=0)
        main.grid(row=0, column=2, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        head = ctk.CTkFrame(main, fg_color="transparent", corner_radius=0)
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(14, 0))
        ctk.CTkLabel(head, text="DROIDSNEX / MONITOR", anchor="w", font=self.fonts.caption,
                     text_color=theme.TEXT_FAINT, height=14).pack(anchor="w")
        ctk.CTkLabel(head, text=tr("Destinazioni live"), anchor="w", font=self.fonts.page,
                     text_color=theme.TEXT).pack(anchor="w")
        self.hint_label = ctk.CTkLabel(main, text="", font=self.fonts.small, text_color=theme.WARN,
                                       anchor="w", justify="left")
        self.hint_label.grid(row=1, column=0, sticky="ew", padx=22, pady=(6, 0))
        self.hint_label.grid_remove()

        # contatori
        stats = ctk.CTkFrame(main, fg_color="transparent", corner_radius=0)
        stats.grid(row=2, column=0, sticky="ew", padx=14, pady=(10, 0))
        self.c_conn = StatCard(stats, tr("Connessioni"), self.fonts)
        self.c_dest = StatCard(stats, tr("Destinazioni"), self.fonts)
        self.c_untrusted = StatCard(stats, tr("Non fidate"), self.fonts)
        self.c_trusted = StatCard(stats, tr("Fidate"), self.fonts)
        self.c_rate = StatCard(stats, tr("Traffico al secondo"), self.fonts)
        self.c_rate.value.configure(font=ctk.CTkFont(family=theme.mono_font(), size=15, weight="bold"))
        self.c_untrusted.value.configure(text_color=theme.ERR)
        self.c_trusted.value.configure(text_color=theme.OK)
        for i, c in enumerate((self.c_conn, self.c_dest, self.c_untrusted, self.c_trusted, self.c_rate)):
            c.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else theme.GAP, 0))
            stats.grid_columnconfigure(i, weight=1, uniform="stat")

        content = ctk.CTkFrame(main, fg_color="transparent", corner_radius=0)
        content.grid(row=3, column=0, sticky="nsew", padx=14, pady=(theme.GAP, 12))
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(2, weight=1)
        self._build_tabs(content)
        self._build_details(content)
        self._build_replay_bar(main)
        self._show_tab("untrusted")

        rule(self, True).grid(row=3, column=0, sticky="ew")
        self._build_footer()

    def _build_header(self) -> None:
        """Intestazione: logo, dispositivo, stato. Fa anche da barra del titolo."""
        header = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0, height=50)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(2, weight=1)
        header.grid_rowconfigure(0, weight=1)

        brand = ctk.CTkFrame(header, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="w", padx=(18, 0))
        logo = theme.logo(17)
        if logo is not None:
            name = ctk.CTkLabel(brand, text="", image=logo)
        else:
            name = ctk.CTkLabel(brand, text=APP_NAME.upper(), font=(theme.mono_font(), 15, "bold"))
        name.pack(side="left")
        version = ctk.CTkLabel(brand, text=f"   v{__version__}", font=(theme.mono_font(), 10),
                               text_color=theme.TEXT_DIM)
        version.pack(side="left", pady=(3, 0))
        subtitle = ctk.CTkLabel(brand, text="  ·  network monitor", font=(theme.mono_font(), 10),
                                text_color=theme.TEXT_FAINT)
        subtitle.pack(side="left", pady=(3, 0))

        chip = ctk.CTkFrame(header, fg_color=theme.PANEL, corner_radius=4, border_width=1,
                            border_color=theme.BORDER, height=32)
        chip.grid(row=0, column=1, sticky="w", padx=(20, 0))
        tag = ctk.CTkLabel(chip, text=tr("DISPOSITIVO"), font=self.fonts.caption, text_color=theme.TEXT_FAINT)
        tag.pack(side="left", padx=(10, 6), pady=2)
        self.device_menu = ctk.CTkOptionMenu(
            chip, values=[tr(NO_DEVICE)], width=230, height=24, dynamic_resizing=False,
            fg_color=theme.PANEL, button_color=theme.PANEL, button_hover_color=theme.HOVER,
            font=self.fonts.bold, dropdown_font=self.fonts.body, command=self._on_device_pick)
        self.device_menu.pack(side="left", pady=3)
        has_icons = bool(theme.icon_font())
        ctk.CTkButton(chip, text=GLYPH_REFRESH if has_icons else "↻", width=28, height=24, corner_radius=4,
                      fg_color="transparent", hover_color=theme.HOVER, text_color=theme.TEXT_DIM,
                      font=self.fonts.icon(12), command=lambda: self._run_bg(self._detect)
                      ).pack(side="left", padx=(2, 4))

        spacer = ctk.CTkFrame(header, fg_color="transparent", height=1)
        spacer.grid(row=0, column=2, sticky="ew")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.grid(row=0, column=3, sticky="e", padx=(0, 12))
        self.mode_label = ctk.CTkLabel(right, text="", font=self.fonts.caption, text_color=theme.TEXT_DIM)
        self.mode_label.pack(side="left", padx=(0, 14))
        self.state_dot = ctk.CTkLabel(right, text="●", font=(theme.mono_font(), 12),
                                      text_color=theme.TEXT_FAINT)
        self.state_dot.pack(side="left", padx=(0, 6))
        self.state_label = ctk.CTkLabel(right, text=tr(NO_DEVICE), font=self.fonts.bold,
                                        text_color=theme.TEXT_SOFT)
        self.state_label.pack(side="left")

        if self.frameless:
            window_buttons(self, header, self._on_close).grid(row=0, column=4, sticky="ne", padx=(4, 0))
            for w in (header, brand, name, version, subtitle, spacer, right, tag,
                      self.mode_label, self.state_dot, self.state_label):
                frameless.enable_drag(self, w)

    def _build_side(self, body) -> None:
        """Colonna dei comandi, con lo stesso aspetto della barra laterale di AndrOsint."""
        side = ctk.CTkFrame(body, fg_color=theme.PANEL, corner_radius=0, width=SIDE_WIDTH)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        r = 0

        def section(text, top=16):
            nonlocal r
            caption(side, tr(text), self.fonts).grid(row=r, column=0, sticky="ew", padx=20, pady=(top, 8))
            r += 1

        def place(widget, pady=3):
            nonlocal r
            widget.grid(row=r, column=0, sticky="ew", padx=14, pady=pady)
            r += 1

        section("Monitor")
        # un pulsante solo: Start a monitor fermo, Stop a monitor attivo (vedi _paint_monitor_buttons)
        self.btn_start = button(side, "▶  Start monitor", self._toggle_monitor, primary=True, height=38)
        place(self.btn_start)
        self._mon_btn = None
        self.btn_clear = button(side, "🗑  " + tr("Pulisci tutto"), self._clear_all, danger=True, height=34)
        place(self.btn_clear)
        self.btn_clear.grid_remove()                   # compare solo a monitor fermo (vedi _paint_monitor_buttons)
        self.btn_screen = button(side, "📱  " + tr("Schermo del telefono"), self._open_screen, height=34)

        place(self.btn_screen)
        self.btn_mark = button(side, "🔖  " + tr("Segnalibro"), self._mark_dialog, height=34)
        place(self.btn_mark)
        self.btn_mark.grid_remove()                    # compare solo a monitor attivo (vedi _paint_monitor_buttons)
        note = ctk.CTkLabel(side, text=tr("Start installa l'agent sul telefono, lo avvia e mostra le "
                                          "connessioni. Stop (o chiusura) lo ferma e lo disinstalla."),
                            font=self.fonts.small, text_color=theme.TEXT_DIM, justify="left",
                            anchor="w", wraplength=SIDE_WIDTH - 36)
        place(note, pady=(4, 2))
        section("Dati")
        place(button(side, tr("Esporta CSV · JSON · pcapng"), self._export))
        place(button(side, "▤  " + tr("Report HTML"), lambda: self._report()))
        place(button(side, tr("Apri cartella export"), self._open_out))
        section("Aiuto")
        self.btn_manual = button(side, "📖  " + tr("Manuale"), self._open_manual, height=34)
        place(self.btn_manual)

        section("Opzioni")
        self.sw_dns = ctk.CTkSwitch(side, text=tr("Nascondi query DNS"), font=self.fonts.body,
                                    command=lambda: setattr(self.mon, "hide_dns", bool(self.sw_dns.get())))
        if self.mon.hide_dns:
            self.sw_dns.select()
        place(self.sw_dns, pady=4)
        self.sw_rdns = ctk.CTkSwitch(side, text=tr("Reverse DNS degli IP"), font=self.fonts.body,
                                     command=lambda: setattr(self.rdns, "enabled", bool(self.sw_rdns.get())))
        if self.rdns.enabled:
            self.sw_rdns.select()
        place(self.sw_rdns, pady=4)
        self.pause_var = tk.BooleanVar(value=getattr(self, "pause_var", None) is not None and self.pause_var.get())
        place(ctk.CTkCheckBox(side, text=tr("Pausa vista"), variable=self.pause_var, font=self.fonts.body), pady=4)

        section("Stato")
        box = ctk.CTkFrame(side, fg_color=theme.PANEL_2, corner_radius=4, border_width=1,
                           border_color=theme.BORDER)
        place(box)
        box.grid_columnconfigure(2, weight=1)
        self.status_rows = {}
        for i, key in enumerate(("ADB", "DEVICE", "AGENT", "VPN", "STREAM")):
            dot = ctk.CTkLabel(box, text="●", font=(theme.mono_font(), 11), text_color=theme.TEXT_FAINT, width=12)
            dot.grid(row=i, column=0, padx=(10, 6), pady=(8 if i == 0 else 2, 8 if i == 4 else 2))
            ctk.CTkLabel(box, text=key, font=self.fonts.caption, text_color=theme.TEXT_FAINT, width=52,
                         anchor="w").grid(row=i, column=1, sticky="w")
            val = ctk.CTkLabel(box, text="—", font=self.fonts.small, text_color=theme.TEXT_SOFT, anchor="w")
            val.grid(row=i, column=2, sticky="ew", padx=(0, 8))
            self.status_rows[key] = (dot, val)
        side.grid_rowconfigure(r, weight=1)
        r += 1
        ctk.CTkLabel(side, text=tr("solo metadati · nessun MITM"), font=self.fonts.tiny,
                     text_color=theme.TEXT_FAINT).grid(row=r, column=0, sticky="w", padx=20, pady=12)

    def _build_tabs(self, parent) -> None:
        """Schede: Config / Untrusted / Trusted / Mappa."""
        top = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.tabbar = TabBar(top, self.fonts, [(k, tr(t)) for k, t in TABS], self._show_tab)
        self.tabbar.pack(side="left", anchor="sw")
        self.list_tools = ctk.CTkFrame(top, fg_color="transparent", corner_radius=0)
        self.list_tools.pack(side="right", pady=(0, 4))
        self.search = ctk.CTkEntry(self.list_tools, placeholder_text=tr("Filtra dominio, IP o app") + "   (Ctrl+F)",
                                   height=30, width=200, font=self.fonts.body)
        self.search.pack(side="left")
        ctk.CTkLabel(self.list_tools, text=tr("ORDINA"), font=self.fonts.caption, text_color=theme.TEXT_FAINT).pack(
            side="left", padx=(12, 8))
        self.sort_menu = ctk.CTkOptionMenu(self.list_tools, values=[tr(m) for m in SORT_MODES], width=150, height=30,
                                           font=self.fonts.body, dropdown_font=self.fonts.body,
                                           command=self._set_sort_mode)
        self.sort_menu.set(tr(self.sort_mode))
        self.sort_menu.pack(side="left")
        rule(parent, True).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, theme.GAP))

        self.pages_box = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        self.pages_box.grid(row=2, column=0, sticky="nsew")
        self.pages_box.grid_columnconfigure(0, weight=1)
        self.pages_box.grid_rowconfigure(0, weight=1)
        self.pages = {}

        cols = [("action", "", 98, False, "w"), ("dest", tr("Destinazione"), 230, True, "w"),
                ("ips", tr("IP risolti"), 120, True, "w"), ("ports", tr("Porte"), 60, False, "w"),
                ("app", "App", 160, True, "w"), ("count", tr("Conn"), 44, False, "e"),
                ("bytes", tr("Traffico"), 70, False, "e"),
                ("first", tr("Prima"), 62, False, "center"), ("last", tr("Ultima"), 62, False, "center"),
                ("org", "Org / ASN", 80, True, "w"), ("rep", tr("Rep."), 58, False, "w")]
        self.lists = {}
        for key, title, color, action, hint in (
                ("untrusted", tr("Destinazioni non fidate"), theme.ERR, " ✓ TRUST",
                 tr("clic su ✓ TRUST per spostarla tra le fidate")),
                ("trusted", tr("Destinazioni fidate"), theme.OK, " ✕ UNTRUST",
                 tr("clic su ✕ UNTRUST per riportarla tra le non fidate"))):
            card = Card(self.pages_box, title, self.fonts)
            card.head.winfo_children()[0].configure(fg_color=color)      # barretta nel colore della lista
            count = ctk.CTkLabel(card.head, text="0", font=self.fonts.title, text_color=color)
            count.pack(side="left", padx=(8, 0))
            if key == "trusted":
                ctk.CTkButton(card.head, text=tr("✕ Untrust tutti"), height=20, width=0, corner_radius=3,
                              fg_color="transparent", border_width=1, border_color=theme.ERR,
                              hover_color=theme.HOVER, text_color=theme.ERR, font=self.fonts.small,
                              command=self._untrust_all).pack(side="right", padx=(10, 0))
            ctk.CTkLabel(card.head, text=hint, font=self.fonts.small, text_color=theme.TEXT_DIM).pack(side="right")
            card.body.grid_columnconfigure(0, weight=1)
            card.body.grid_rowconfigure(0, weight=1)
            table = Table(card.body, cols, tags={"row": color, "dns": theme.TEXT_DIM, "rep": theme.WARN})
            for lvl, rc in enumerate(risk.COLORS):
                table.tree.tag_configure(f"risk{lvl}", foreground=rc)
            table.grid(row=0, column=0, sticky="nsew")
            tree = table.tree
            tree.heading("action", text="TRUST" if key == "untrusted" else "UNTRUST")
            for ck, ctitle, *_rest in cols[1:]:          # clic sul titolo: A-Z, poi Z-A
                tree.heading(ck, command=lambda k=key, c=ck: self._sort_by_column(k, c))
            tree.tag_configure("odd", background=theme.PANEL_2)
            tree.bind("<<TreeviewSelect>>", lambda e, k=key: self._on_select(k))
            tree.bind("<ButtonRelease-1>", lambda e, k=key: self._on_click(k, e))
            tree.bind("<Motion>", lambda e, t=tree: t.configure(
                cursor="hand2" if t.identify_column(e.x) == "#1" and t.identify_region(e.x, e.y) == "cell" else ""))
            self.lists[key] = {"tree": tree, "count": count, "action": action, "rows": {},
                               "sort": (self._col_sort or {}).get(key), "titles": {ck: ct for ck, ct, *_r in cols}}
            self.pages[key] = card

        frame = ctk.CTkFrame(self.pages_box, fg_color=theme.PANEL, corner_radius=4, border_width=1,
                             border_color=theme.BORDER)
        self.map = MapView(frame, self.fonts, on_select=self._on_map_select, dark=self.settings.map_dark)
        self.map.vector = self.vector
        self.map.pack(fill="both", expand=True, padx=1, pady=1)
        self.map.set_home(self.settings.home_lat, self.settings.home_lon, self.settings.home_name)
        self.map.on_detach = lambda: self._toggle_float("map")
        self.map.on_home = self._home_from_map
        self.map.heat = self.settings.map_heat
        self.map.heat_btn.configure(text_color=theme.ACCENT if self.map.heat else theme.TEXT_FAINT)
        self.map.on_heat = self._set_map_heat
        self.pages["map"] = frame
        # al posto della mappa quando è in una finestra separata
        hold = ctk.CTkFrame(self.pages_box, fg_color=theme.PANEL, corner_radius=4, border_width=1,
                            border_color=theme.BORDER)
        inner = ctk.CTkFrame(hold, fg_color="transparent")
        inner.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(inner, text="⧉", font=(theme.mono_font(), 28), text_color=theme.ACCENT).pack()
        ctk.CTkLabel(inner, text=tr("Il pannello è in una finestra separata."), font=self.fonts.body,
                     text_color=theme.TEXT_SOFT).pack(pady=(4, 10))
        button(inner, tr("Riaggancia"), lambda: self._toggle_float(self.tab), primary=True).pack()
        self.map_holder = hold
        self.pages["config"] = self._build_config(self.pages_box)
        self._build_analysis_pages()

    # ---------------------------------------------------------------- ordinamento per colonna
    COLUMN_KEYS = {
        "dest": lambda g: g.dest.lower().removeprefix("[dns] "),
        "ips": lambda g: _ip_key(min(g.ips, key=_ip_key)) if g.ips else (9, 0),
        "ports": lambda g: min(g.ports) if g.ports else 0,
        "app": lambda g: g.app.lower(),
        "count": lambda g: g.count,
        "bytes": lambda g: g.bytes,
        "first": lambda g: g.first,
        "last": lambda g: g.last,
        "org": lambda g: (g.org == "", g.org.lower()),
    }

    def _sort_by_column(self, key: str, col: str) -> None:
        """Primo clic: crescente (A-Z, 0-9). Clic sulla stessa colonna: inverte."""
        lst = self.lists[key]
        cur = lst["sort"]
        lst["sort"] = (col, not cur[1]) if cur and cur[0] == col else (col, False)
        self._paint_headings(key)
        self._refresh()

    def _paint_headings(self, key: str) -> None:
        lst = self.lists[key]
        for ck, title in lst["titles"].items():
            if ck == "action":
                continue
            arrow = ""
            if lst["sort"] and lst["sort"][0] == ck:
                arrow = "  ▼" if lst["sort"][1] else "  ▲"
            lst["tree"].heading(ck, text=title.upper() + arrow)

    def _set_sort_mode(self, value: str) -> None:
        """Il menu ORDINA toglie l'ordinamento per colonna."""
        self.sort_mode = next((m for m in SORT_MODES if tr(m) == value), SORT_MODES[0])
        for key, lst in self.lists.items():
            lst["sort"] = None
            self._paint_headings(key)
        self._refresh()

    def _show_tab(self, key: str) -> None:
        self.tab = key
        self.tabbar.select(key)
        fl = self._floating
        for k, page in self.pages.items():
            if k in FLOAT_PAGES and fl.get(k):
                continue                            # è una finestra a parte: resta dov'è
            if k == key:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_remove()
        if key in FLOAT_PAGES and fl.get(key):
            self.map_holder.grid(row=0, column=0, sticky="nsew")
        else:
            self.map_holder.grid_remove()
        if key in ("config", "sessions", "timeline"):
            self.details_col.grid_remove()
            self.list_tools.pack_forget()
            if key == "config":
                self._config_status()
            if key == "sessions":
                self._refresh_sessions()
        else:
            self.details_col.grid()
            self.list_tools.pack(side="right", pady=(0, 4))
        if key == "dns":
            self._dns_shown = -1
        if key == "alerts":
            self._alerts_shown = -1
        # nella Mappa e nel Grafo la colonna di destra mostra l'elenco delle app e i dettagli del punto
        # (i pannelli staccati restano nelle loro finestre)
        if key in ("map", "graph") and not fl.get("apps"):
            self.log_card.grid_remove()
            self.apps_card.grid(row=0, column=0, sticky="nsew", pady=0)
            if not fl.get("details"):
                self.det_card.grid(row=1, column=0, sticky="nsew", pady=(theme.GAP, 0))
        else:
            if not fl.get("apps"):
                self.apps_card.grid_remove()
            if not fl.get("details"):
                self.det_card.grid(row=0, column=0, sticky="nsew", pady=0)
            self.log_card.grid(row=1 if not fl.get("details") else 0, column=0, sticky="nsew",
                               pady=(theme.GAP, 0) if not fl.get("details") else 0)
        self.map.active = key == "map" or bool(fl.get("map"))
        if self.map.active:
            self.after(30, self.map.redraw)

    # ---------------------------------------------------------------- pannelli staccabili
    def _toggle_float(self, name: str) -> None:
        """Stacca il pannello in una finestra a parte (spostabile, ridimensionabile) o lo riaggancia.
        Usa `wm manage`: il pannello resta lo stesso widget, con i suoi dati, solo in un'altra finestra."""
        w = self._float_widget(name)
        if not self._floating.get(name):
            w.grid_forget()
            self.tk.call("wm", "manage", w._w)
            title = {"map": tr("Mappa"), "graph": tr("Grafo"), "details": tr("Dettagli"), "apps": tr("App sulla mappa")}[name]
            self.tk.call("wm", "title", w._w, f"DroidSnex · {title}")
            size = {"map": "1100x700", "graph": "1100x700", "details": "480x640", "apps": "380x600"}[name]
            off = {"map": 40, "graph": 40, "details": 80, "apps": 120}[name]
            self.tk.call("wm", "geometry", w._w, f"{size}+{self.winfo_rootx() + off}+{self.winfo_rooty() + off}")
            self.tk.call("wm", "protocol", w._w, "WM_DELETE_WINDOW",
                         self.register(lambda n=name: self._float_close(n)))
            try:
                if getattr(self, "_droidsnex_icon", None) is not None:
                    self.tk.call("wm", "iconphoto", w._w, self._droidsnex_icon)
            except tk.TclError:
                pass
            self._floating[name] = True
            if self.frameless:
                self._float_bar(name, w, title)
        else:
            bar = self._float_bars.pop(name, None)
            if bar is not None:
                bar.destroy()
            self.tk.call("wm", "forget", w._w)
            self._floating[name] = False
        self._paint_float_buttons()
        self._show_tab(self.tab)
        if name == "map":
            self.after(80, self.map.redraw)
        if name == "graph":
            self.graph.active = True
            self.graph._mark()

    def _float_close(self, name: str) -> None:
        """La X di una finestra staccata: riaggancia il pannello."""
        self._toggle_float(name)

    def _float_widget(self, name: str):
        return {"map": self.pages["map"], "graph": self.pages["graph"],
                "details": self.det_card, "apps": self.apps_card}[name]

    def _float_bar(self, name: str, w, title: str) -> None:
        """Finestra staccata senza barra del titolo, come la principale: intestazione con logo e nome
        (trascinabile, doppio clic massimizza), riduci / massimizza / chiudi (= riaggancia); i bordi
        restano quelli nativi, quindi si ridimensiona dai lati."""
        win = frameless.WmHandle(w)
        bar = ctk.CTkFrame(w, fg_color=theme.BG, corner_radius=0, height=34)
        bar.grid_propagate(False)
        bar.pack_propagate(False)
        logo = theme.logo(12)
        brand = (ctk.CTkLabel(bar, text="", image=logo) if logo is not None else
                 ctk.CTkLabel(bar, text=APP_NAME.upper(), font=(theme.mono_font(), 12, "bold")))
        brand.pack(side="left", padx=(12, 0))
        label = ctk.CTkLabel(bar, text=f"   ·   {title}", font=self.fonts.bold, text_color=theme.TEXT_SOFT)
        label.pack(side="left")
        window_buttons(win, bar, lambda n=name: self._float_close(n)).pack(side="right")
        # riaggancia: rimette il pannello nella finestra principale (come la X)
        ctk.CTkButton(bar, text="⇲  " + tr("Riaggancia"), height=24, width=0, corner_radius=4, fg_color="transparent",
                      hover_color=theme.HOVER, border_width=1, border_color=theme.BORDER_STRONG, text_color=theme.ACCENT,
                      font=self.fonts.small, command=lambda n=name: self._toggle_float(n)).pack(side="right", padx=(0, 8))
        if isinstance(w, Card):
            bar.grid(row=0, column=0, sticky="ew", padx=1, pady=(1, 0))
        else:
            first = w.pack_slaves()
            bar.pack(side="top", fill="x", padx=1, pady=(1, 0), **({"before": first[0]} if first else {}))
        for x in (bar, brand, label):
            frameless.enable_drag(win, x)
        self._float_bars[name] = bar
        self._float_frameless(name, bar, win)

    def _float_frameless(self, name: str, bar, win, n: int = 0) -> None:
        """Toglie la barra del titolo di Windows al pannello staccato. Va fatto quando la sua finestra
        esiste davvero (subito dopo `wm manage` non c'e' ancora): si riprova finche' non e' pronta."""
        if self._float_bars.get(name) is not bar:        # riagganciato nel frattempo
            return
        done = False
        try:
            win.widget.update_idletasks()
            if win.widget.winfo_viewable() and frameless.toplevel_ready(win):
                done = frameless.make_frameless(win, border_color=theme.BORDER)
        except tk.TclError:
            return
        if not done and n < 25:
            self.after(120, lambda: self._float_frameless(name, bar, win, n + 1))

    def _paint_float_buttons(self) -> None:
        for name, btn in (("map", self.map.detach_btn), ("graph", self.graph.detach_btn), ("details", self.det_float_btn),
                          ("apps", self.apps_float_btn)):
            btn.configure(text="⇲" if self._floating.get(name) else "⧉")

    # ---------------------------------------------------------------- config
    def _build_config(self, parent):
        page = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure((0, 1), weight=1, uniform="cfg")
        f = self.fonts

        def note(master, text):
            lab = ctk.CTkLabel(master, text=text, font=f.small, text_color=theme.TEXT_DIM, justify="left",
                               anchor="w", wraplength=440)
            # il testo va a capo sulla larghezza reale del riquadro (mai tagliato)
            def fit(e, w=lab):
                wl = max(120, e.width - 8)
                if w.winfo_exists() and abs(int(w.cget("wraplength")) - wl) > 2:
                    w.configure(wraplength=wl)
            master.bind("<Configure>", fit, add="+")
            return lab

        def field(master, row, label, width=160):
            ctk.CTkLabel(master, text=label, font=f.caption, text_color=theme.TEXT_FAINT, anchor="w").grid(
                row=row, column=0, sticky="w", pady=4, padx=(0, 10))
            e = ctk.CTkEntry(master, width=width, height=30, font=f.mono)
            e.grid(row=row, column=1, sticky="ew", pady=4)
            return e

        # --- adb (Android Platform Tools)
        ad = Card(page, "ADB · Android Platform Tools", self.fonts)
        ad.grid(row=0, column=0, sticky="nsew", padx=(0, theme.GAP // 2), pady=(0, theme.GAP))
        b = ad.body
        b.grid_columnconfigure(0, weight=1)
        note(b, tr("DroidSnex comanda il telefono con adb e usa solo quello nella cartella tools del programma "
                   "(pc/tools/platform-tools), mai l'adb del sistema. Non viene scaricato da solo: premi "
                   "'Scarica / aggiorna da Google' per prendere le Android Platform Tools ufficiali. Niente "
                   "installazione nel sistema e niente modifiche al PATH.")).grid(
            row=0, column=0, sticky="ew")
        self.adb_status = ctk.CTkLabel(b, text="", font=f.mono, text_color=theme.TEXT_SOFT, anchor="w",
                                       justify="left", wraplength=900)
        self.adb_status.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.adb_bar = ctk.CTkProgressBar(b, height=6)
        self.adb_bar.set(0)
        self.adb_bar.grid(row=2, column=0, sticky="ew", pady=4)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        button(row, tr("Scarica / aggiorna da Google"), lambda: self._job("adb", self._download_adb),
               primary=True).pack(side="left")
        button(row, tr("Interrompi"), lambda: self._cancel.__setitem__("adb", True), danger=True).pack(
            side="left", padx=(8, 0))
        button(row, tr("Apri cartella tools"), lambda: self._open_dir(platform_tools.TOOLS_DIR)).pack(
            side="left", padx=(8, 0))

        # --- scrcpy (schermo del telefono)
        sc = Card(page, tr("Schermo del telefono") + " · scrcpy", self.fonts)
        sc.grid(row=0, column=1, sticky="nsew", padx=(theme.GAP // 2, 0), pady=(0, theme.GAP))
        b = sc.body
        b.grid_columnconfigure(0, weight=1)
        note(b, tr("Il pulsante 'Schermo del telefono' mostra e comanda lo schermo con scrcpy (Genymobile, Apache 2.0), "
                   "usato solo dalla cartella pc/tools/scrcpy. Non viene scaricato da solo: premi 'Scarica / aggiorna "
                   "da GitHub' per prendere l'ultima release ufficiale per Windows. Usa l'adb della cartella tools.")).grid(
            row=0, column=0, sticky="ew")
        self.scrcpy_status = ctk.CTkLabel(b, text="", font=f.mono, text_color=theme.TEXT_SOFT, anchor="w",
                                          justify="left", wraplength=440)
        self.scrcpy_status.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.scrcpy_bar = ctk.CTkProgressBar(b, height=6)
        self.scrcpy_bar.set(0)
        self.scrcpy_bar.grid(row=2, column=0, sticky="ew", pady=4)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        button(row, tr("Scarica / aggiorna da GitHub"), lambda: self._job("scrcpy", self._download_scrcpy),
               primary=True).pack(side="left")
        button(row, tr("Interrompi"), lambda: self._cancel.__setitem__("scrcpy", True), danger=True).pack(
            side="left", padx=(8, 0))
        self._cancel.setdefault("scrcpy", False)

        # --- posizione
        pos = Card(page, tr("La tua posizione"), self.fonts)
        pos.grid(row=1, column=0, sticky="nsew", padx=(0, theme.GAP // 2), pady=(0, theme.GAP))
        b = pos.body
        b.grid_columnconfigure(1, weight=1)
        note(b, tr("È il punto da cui partono le linee sulla mappa (il telefono). Il modo più preciso è leggerla "
                   "dal telefono collegato (ultima posizione GPS o di rete, via adb, senza internet) oppure "
                   "sceglierla con il clic destro sulla mappa. Puoi anche inserirla a mano. Il rilevamento "
                   "dall'IP pubblico (chiesto ad api.ipify.org e cercato nel database delle città) è solo "
                   "indicativo: può sbagliare di decine di chilometri.")).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.e_lat = field(b, 1, tr("LATITUDINE"))
        self.e_lon = field(b, 2, tr("LONGITUDINE"))
        self.e_home = field(b, 3, tr("NOME"))
        for e, v in ((self.e_lat, self.settings.home_lat), (self.e_lon, self.settings.home_lon),
                     (self.e_home, self.settings.home_name)):
            if v not in (None, ""):
                e.insert(0, str(v))
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        button(row, tr("Salva posizione"), self._save_home, primary=True).pack(side="left")
        button(row, "⌖  " + tr("Dal telefono (GPS)"), lambda: self._job("home", self._home_from_phone)).pack(
            side="left", padx=(8, 0))
        button(row, tr("Rileva dal mio IP pubblico"), lambda: self._job("home", self._detect_home)).pack(
            side="left", padx=(8, 0))
        self.home_status = note(b, "")
        self.home_status.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        # --- database città
        db = Card(page, tr("Database città degli IP") + " · DB-IP City Lite", self.fonts)
        db.grid(row=1, column=1, sticky="nsew", padx=(theme.GAP // 2, 0), pady=(0, theme.GAP))
        b = db.body
        b.grid_columnconfigure(0, weight=1)
        note(b, tr("Associa ogni IP alla sua città (latitudine e longitudine) per disegnarlo sulla mappa. "
                   "Database gratuito di db-ip.com, licenza CC BY 4.0, aggiornato ogni mese: circa 60 MB da "
                   "scaricare, 130 MB su disco. Va bene anche un GeoLite2-City.mmdb di MaxMind.")).grid(
            row=0, column=0, sticky="ew")
        self.db_status = ctk.CTkLabel(b, text="", font=f.mono, text_color=theme.TEXT_SOFT, anchor="w",
                                      justify="left")
        self.db_status.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.db_bar = ctk.CTkProgressBar(b, height=6)
        self.db_bar.set(0)
        self.db_bar.grid(row=2, column=0, sticky="ew", pady=4)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        button(row, tr("Scarica / aggiorna"), lambda: self._job("db", self._download_db), primary=True).pack(side="left")
        button(row, tr("Scegli file .mmdb…"), self._pick_db).pack(side="left", padx=(8, 0))
        button(row, tr("Interrompi"), lambda: self._cancel.__setitem__("db", True), danger=True).pack(side="left", padx=(8, 0))

        # --- mappa vettoriale a livello città
        mp = Card(page, tr("Mappa vettoriale · livello città"), self.fonts)
        mp.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, theme.GAP))
        b = mp.body
        b.grid_columnconfigure(0, weight=1)
        note(b, tr("La mappa è disegnata dal programma con i dati di Natural Earth (pubblico dominio): nitida a ogni "
                   "zoom, con coste, laghi, fiumi, confini di stati e regioni e i nomi delle città. 'Scarica mappa' "
                   "scarica una volta il livello città (~60 MB, ~10 MB su disco in pc/data); poi funziona senza "
                   "rete.")).grid(row=0, column=0, sticky="ew")
        self.sw_dark = ctk.CTkSwitch(b, text=tr("Mappa scura"), font=f.body, command=self._toggle_dark)
        if self.settings.map_dark:
            self.sw_dark.select()
        self.sw_dark.grid(row=0, column=1, sticky="ne", padx=(10, 0))
        self.tiles_status = ctk.CTkLabel(b, text="", font=f.mono, text_color=theme.TEXT_SOFT, anchor="w",
                                         justify="left", wraplength=900)
        self.tiles_status.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        self.tiles_bar = ctk.CTkProgressBar(b, height=6)
        self.tiles_bar.set(0)
        self.tiles_bar.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        button(row, tr("Scarica mappa"), lambda: self._job("tiles", self._download_vector), primary=True).pack(side="left")
        button(row, tr("Interrompi"), lambda: self._cancel.__setitem__("tiles", True), danger=True).pack(
            side="left", padx=(8, 0))
        button(row, tr("Apri cartella dati"), lambda: self._open_dir(DATA_DIR)).pack(side="left", padx=(8, 0))

        self._build_analysis_config(page, note, 3)

        # --- dettaglio IP: liste cloud + chiavi API
        cl = Card(page, tr("Dettaglio IP") + " · " + tr("range cloud"), self.fonts)
        cl.grid(row=4, column=0, sticky="nsew", padx=(0, theme.GAP // 2), pady=(0, theme.GAP))
        b = cl.body
        b.grid_columnconfigure(0, weight=1)
        note(b, tr("La finestra 'Dettaglio IP' (pulsante nel riquadro Dettagli) raccoglie PTR, domini della sessione, "
                   "RDAP/WHOIS, certificato TLS e, se scaricate da qui, dice se l'IP sta nei range pubblici di AWS, "
                   "Google Cloud, Azure, Cloudflare e Oracle (liste ufficiali, in pc/data/cloud, mai in automatico).")).grid(
            row=0, column=0, sticky="ew")
        self.cloud_status = ctk.CTkLabel(b, text="", font=f.mono, text_color=theme.TEXT_SOFT, anchor="w", justify="left",
                                         wraplength=440)
        self.cloud_status.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.cloud_bar = ctk.CTkProgressBar(b, height=6)
        self.cloud_bar.set(0)
        self.cloud_bar.grid(row=2, column=0, sticky="ew", pady=4)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        button(row, tr("Scarica / aggiorna liste cloud"), lambda: self._job("cloud", self._download_cloud), primary=True).pack(side="left")
        button(row, tr("Interrompi"), lambda: self._cancel.__setitem__("cloud", True), danger=True).pack(side="left", padx=(8, 0))
        self.ip_active_var = tk.BooleanVar(value=self.settings.ip_active)
        ctk.CTkCheckBox(b, text=tr("contatto attivo permesso (certificato TLS: il PC si collega all'IP)"), variable=self.ip_active_var,
                        font=f.small, checkbox_width=16, checkbox_height=16, border_width=1, corner_radius=3,
                        command=self._save_ip_keys).grid(row=4, column=0, sticky="w", pady=(10, 0))
        self._cancel.setdefault("cloud", False)

        ak = Card(page, tr("Dettaglio IP") + " · " + tr("servizi con chiave API"), self.fonts)
        ak.grid(row=4, column=1, sticky="nsew", padx=(theme.GAP // 2, 0), pady=(0, theme.GAP))
        b = ak.body
        b.grid_columnconfigure(1, weight=1)
        note(b, tr("Facoltativi: con la chiave, il Dettaglio IP interroga anche questi servizi (l'IP viene inviato al "
                   "servizio). Senza chiave restano disattivi. Le chiavi sono salvate in pc/config.json.")).grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.key_entries = {}
        for i, (key, name, key_url, signup_url) in enumerate(ipinfo.API_SERVICES, start=1):
            e = field(b, i, name, width=200)
            e.configure(show="•")
            e.insert(0, getattr(self.settings, key, "") or "")
            self.key_entries[key] = e
            links = ctk.CTkFrame(b, fg_color="transparent")
            links.grid(row=i, column=2, sticky="w", padx=(8, 0))
            button(links, tr("Registrati") + " ↗", lambda u=signup_url: self._open_url(u), height=28).pack(side="left")
            button(links, tr("Chiave API") + " ↗", lambda u=key_url: self._open_url(u), height=28).pack(side="left", padx=(6, 0))
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=len(ipinfo.API_SERVICES) + 1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        button(row, tr("Salva chiavi"), self._save_ip_keys, primary=True).pack(side="left")
        self.keys_status = ctk.CTkLabel(row, text="", font=f.small, text_color=theme.TEXT_DIM)
        self.keys_status.pack(side="left", padx=(12, 0))

        # --- agent Android (APK)
        ag = Card(page, tr("Agent Android") + " · APK", self.fonts)
        ag.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(theme.GAP, theme.GAP))
        b = ag.body
        b.grid_columnconfigure(1, weight=1)
        note(b, tr("L'app che Start installa e avvia sul telefono (Stop, la chiusura del programma o un suo crash la fermano "
                   "e la disinstallano). Scegli il file .apk da usare: vuoto = quello predefinito (pc/agent.apk oppure "
                   "l'ultima build in android/app/build/outputs/apk). Qui non si installa niente: succede allo Start.")).grid(
            row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.e_apk = field(b, 1, "APK", width=420)
        self.e_apk.insert(0, self.settings.agent_apk or "")
        self.e_apk.bind("<Return>", lambda _e: self._save_apk())
        links = ctk.CTkFrame(b, fg_color="transparent")
        links.grid(row=1, column=2, sticky="w", padx=(8, 0))
        button(links, tr("Sfoglia…"), self._pick_apk, height=28).pack(side="left")
        button(links, tr("Predefinito"), self._default_apk, height=28).pack(side="left", padx=(6, 0))
        self.apk_status = ctk.CTkLabel(b, text="", font=f.small, text_color=theme.TEXT_DIM, anchor="w", justify="left")
        self.apk_status.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(6, 4))
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        button(row, tr("Salva"), self._save_apk, primary=True).pack(side="left")
        self._apk_status()

        # --- lingua
        lg = Card(page, tr("Lingua") + " · Language", self.fonts)
        lg.grid(row=6, column=0, sticky="nsew", padx=(0, theme.GAP // 2), pady=(0, 0))
        b = lg.body
        self.lang_menu = ctk.CTkOptionMenu(b, values=list(LANGUAGES.values()), width=220, height=30, font=f.body,
                                           dropdown_font=f.body, command=self._set_language)
        self.lang_menu.set(LANGUAGES[language()])
        self.lang_menu.pack(side="left")
        note(b, tr("Lingua dell'interfaccia. Anche l'app sul telefono userà questa lingua (viene passata al prossimo Start).")).pack(
            side="left", padx=(12, 0), fill="x", expand=True)

        # --- aggiornamenti: solo su richiesta, non scarica niente
        up = Card(page, tr("Aggiornamenti"), self.fonts)
        up.grid(row=6, column=1, sticky="nsew", padx=(theme.GAP // 2, 0), pady=(0, 0))
        b = up.body
        b.grid_columnconfigure(1, weight=1)
        note(b, tr("Controlla se è uscita una versione nuova (ora hai la {v}). Il controllo parte solo da questo "
                   "pulsante, legge l'indirizzo qui sotto e non scarica niente: se c'è una versione nuova ti mostra "
                   "il collegamento.", v=__version__)).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.e_update = field(b, 1, tr("Indirizzo"), width=320)
        self.e_update.insert(0, self.settings.update_url or updates.DEFAULT_URL)
        row = ctk.CTkFrame(b, fg_color="transparent")
        row.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        button(row, tr("Controlla aggiornamenti"), self._check_update, primary=True).pack(side="left")
        self.btn_update_open = button(row, tr("Apri la pagina"), lambda: self._open_url(self._update_link))
        self._update_link = ""
        self.update_status = ctk.CTkLabel(b, text="", font=f.small, text_color=theme.TEXT_DIM, anchor="w", justify="left",
                                          wraplength=420)
        self.update_status.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        return page

    # ---------------------------------------------------------------- aggiornamenti
    def _check_update(self) -> None:
        url = self.e_update.get().strip()
        if url != (self.settings.update_url or updates.DEFAULT_URL):
            self.settings.update_url = url
            self.settings.save(CONFIG_FILE)
        self.btn_update_open.pack_forget()
        if not url:
            return self.update_status.configure(
                text=tr("Scrivi l'indirizzo dove vengono pubblicate le versioni (https://…) e riprova."), text_color=theme.WARN)
        self.update_status.configure(text=tr("controllo in corso…"), text_color=theme.TEXT_DIM)

        def done(info: dict | None, err: str = "") -> None:
            if not self.update_status.winfo_exists():
                return
            if info is None:
                return self.update_status.configure(text=tr("controllo non riuscito: {e}", e=err), text_color=theme.ERR)
            if not info["newer"]:
                return self.update_status.configure(
                    text=tr("Hai già l'ultima versione ({v}).", v=__version__), text_color=theme.OK)
            text = tr("È disponibile la versione {new} (tu hai la {v}).", new=info["version"], v=__version__)
            if info["notes"]:
                text += "\n" + info["notes"][:400]
            self.update_status.configure(text=text, text_color=theme.WARN)
            self._update_link = info["url"]
            if info["url"]:
                self.btn_update_open.pack(side="left", padx=(8, 0))
            self.log(text.split("\n")[0], "ok")

        def run() -> None:
            try:
                info = updates.check(url)
            except Exception as e:  # noqa: BLE001
                return self._ui(done, None, _describe_error(e))
            self._ui(done, info)
        threading.Thread(target=run, daemon=True).start()

    # ---------------------------------------------------------------- lingua
    def _set_language(self, name: str) -> None:
        code = next((c for c, n in LANGUAGES.items() if n == name), "it")
        if code == language():
            return
        set_language(code)
        self.settings.language = code
        self.settings.save(CONFIG_FILE)
        self._rebuild()

    def _rebuild(self) -> None:
        """Ricostruisce l'interfaccia nella nuova lingua, senza fermare il monitor né perdere i dati."""
        tab = self.tab
        search = self.search.get()
        self._col_sort = {k: v["sort"] for k, v in self.lists.items()}
        view = (self.map.z, self.map.cx, self.map.cy, self.map._fitted)
        self.map.active = False
        for name, fl in list(self._floating.items()):      # i pannelli staccati tornano nella finestra
            if fl:
                w = self._float_widget(name)
                try:
                    self.tk.call("wm", "forget", w._w)
                except tk.TclError:
                    pass
        self._floating = {}
        self._float_bars = {}
        self._close_screen()
        self._close_ip_detail()
        if self._replay:
            self._exit_replay()
        for w in self.winfo_children():
            w.destroy()
        self._app_boxes = {}
        self._build()
        self.map.z, self.map.cx, self.map.cy, self.map._fitted = view
        if search:
            self.search.insert(0, search)
        for k in self.lists:
            self._paint_headings(k)
        self._show_tab(tab or "untrusted")
        self.console.configure(state="normal")
        for line, kind in self._log_lines[-300:]:
            self.console.insert("end", line + "\n", kind or None)
        self.console.see("end")
        self.console.configure(state="disabled")
        if self.demo:
            self._connect_demo()
        else:
            self._run_bg(self._detect)
        self._refresh()

    def _config_status(self) -> None:
        self._analysis_config_status()
        if "adb" not in self._jobs:
            self._adb_status()
        if "scrcpy" not in self._jobs:
            self._scrcpy_status()
        if "cloud" not in self._jobs:
            self._cloud_status()
        if "db" in self._job_error:
            self.db_status.configure(text=tr("errore: {e}", e=self._job_error["db"]), text_color=theme.ERR)
        elif self.geo.available:
            self.db_status.configure(text=f"{os.path.basename(self.geo.path)}  ·  {self.geo.description()}",
                                     text_color=theme.OK)
        else:
            self.db_status.configure(text=tr("non presente") + (f"  ({self.geo.error})" if self.geo.error else ""),
                                     text_color=theme.WARN)
        if "tiles" not in self._jobs:
            if "tiles" in self._job_error:
                self.tiles_status.configure(text=tr("errore: {e}", e=self._job_error["tiles"]), text_color=theme.ERR)
            elif os.path.isfile(self._vector_10m()):
                self.tiles_status.configure(text=tr("mappa a livello città installata (Natural Earth 1:10m)"),
                                            text_color=theme.OK)
            else:
                self.tiles_status.configure(
                    text=tr("non ancora scaricata: intanto si vede la versione base inclusa (stati e grandi città)"),
                    text_color=theme.WARN)

    def _job(self, name: str, fn) -> None:
        """Download e rilevamenti in un thread a parte (non bloccano adb né l'interfaccia)."""
        if name in self._jobs:
            return self.log(tr("operazione già in corso…"))
        self._jobs.add(name)
        self._cancel[name] = False
        self._job_error.pop(name, None)

        def run():
            try:
                fn()
            except InterruptedError:
                self.log(tr("download interrotto"))
            except Exception as e:  # noqa: BLE001
                self._job_error[name] = _describe_error(e)
                self.log(tr("errore: {e}", e=self._job_error[name]), "err")
            finally:
                self._jobs.discard(name)
                self._ui(self._config_status)
        threading.Thread(target=run, daemon=True).start()

    def _open_geo(self) -> None:
        cands = [self.settings.resolve("geo_db"), os.path.join(DATA_DIR, DBIP_FILE),
                 os.path.join(DATA_DIR, "GeoLite2-City.mmdb"), os.path.join(HERE, "GeoLite2-City.mmdb")]
        path = next((p for p in cands if p and os.path.isfile(p)), None)
        if path:
            self.geo.open(path)

    def _download_db(self) -> None:
        self.log(tr("download di DB-IP City Lite…"))
        last = [0.0]

        def progress(done, total):
            now = time.monotonic()
            if now - last[0] > 0.25 or (total and done >= total):
                last[0] = now
                txt = (tr("scaricati {a} MB di {b} MB", a=f"{done / 1e6:.1f}", b=f"{total / 1e6:.1f}") if total
                       else tr("scaricati {a} MB", a=f"{done / 1e6:.1f}"))
                self._ui(lambda: (self.db_bar.set(done / total if total else 0),
                                  self.db_status.configure(text=txt, text_color=theme.TEXT_SOFT)))
        self.geo.close()                         # su Windows il file in uso non si può sostituire
        try:
            path = download_dbip(DATA_DIR, progress, cancel=lambda: self._cancel["db"])
        except BaseException:
            self._open_geo()                     # download fallito: si riapre quello di prima
            raise
        self._ui(lambda: self.db_status.configure(text=tr("decompresso, apertura…")))
        self.geo.open(path)
        self.settings.geo_db = path
        self.settings.save(CONFIG_FILE)
        self._ui(self.db_bar.set, 1)
        self.log(tr("database città pronto: {d}", d=self.geo.description()), "ok")
        if self.settings.home_lat is None:
            self._detect_home()

    def _pick_db(self) -> None:
        path = filedialog.askopenfilename(title=tr("Database città") + " (.mmdb)", filetypes=[("MaxMind DB", "*.mmdb")])
        if not path:
            return
        if self.geo.open(path):
            self.settings.geo_db = path
            self.settings.save(CONFIG_FILE)
            self.log(tr("database città: {d}", d=self.geo.description()), "ok")
        else:
            self.log(tr("file non valido: {e}", e=self.geo.error), "err")
        self._config_status()

    def _detect_home(self) -> None:
        if not self.geo.available:
            raise RuntimeError(tr("prima scarica il database delle città (DB-IP City Lite)"))
        self._ui(lambda: self.home_status.configure(text=tr("richiesta dell'IP pubblico…"), text_color=theme.TEXT_DIM))
        ip = public_ip()
        place = self.geo.lookup(ip)
        if not place:
            raise RuntimeError(tr("IP pubblico {ip} non trovato nel database", ip=ip))

        def apply():
            for e, v in ((self.e_lat, f"{place.lat:.4f}"), (self.e_lon, f"{place.lon:.4f}"),
                         (self.e_home, place.city or place.name)):
                e.delete(0, "end")
                e.insert(0, v)
            self.settings.home_country = place.country
            self._save_home()
            self.home_status.configure(text=tr("IP pubblico {ip}", ip=ip) + f"  →  {place.name}", text_color=theme.OK)
        self._ui(apply)

    def _home_from_phone(self) -> None:
        """Ultima posizione nota del telefono collegato (GPS / rete), letta con `adb shell dumpsys location`."""
        if self.demo:
            raise RuntimeError(tr("nessun telefono collegato via adb"))
        self._ui(lambda: self.home_status.configure(text=tr("lettura della posizione dal telefono…"),
                                                    text_color=theme.TEXT_DIM))
        if self.adb is None:
            self.adb = Adb()
        if not self.adb.serial:
            ready = [d for d in self.adb.devices() if d.state == "device"]
            if not ready:
                raise RuntimeError(tr("nessun telefono collegato via adb"))
            self.adb.serial = ready[0].serial
        fix = phoneloc.best(self.adb)
        if fix is None:
            raise RuntimeError(tr("il telefono non ha una posizione recente: accendi la localizzazione, apri un'app "
                                  "di mappe finché trova il punto e riprova"))
        how = fix.provider.upper()
        if fix.accuracy is not None:
            how += " · ±" + (f"{fix.accuracy:.0f} m" if fix.accuracy < 1000 else f"{fix.accuracy / 1000:.1f} km")
        if fix.age is not None:
            how += " · " + (tr("{n} s fa", n=int(fix.age)) if fix.age < 90 else tr("{n} min fa", n=int(fix.age / 60))
                            if fix.age < 5400 else tr("{n} ore fa", n=int(fix.age / 3600)))
        self._ui(lambda: self._set_home(fix.lat, fix.lon, tr("posizione dal telefono") + f"  ({how})"))

    def _home_from_map(self, lat: float, lon: float) -> None:
        """Clic destro sulla mappa > "Imposta qui la mia posizione"."""
        self._set_home(lat, lon, tr("posizione scelta sulla mappa"))

    def _set_home(self, lat: float, lon: float, status: str) -> None:
        """Nuova posizione precisa: riempie i campi (nome = città più vicina della mappa), aggiorna lo stato
        di residenza usato dalla scala di rischio e salva."""
        name = self.map.place_near(lat, lon)
        for e, v in ((self.e_lat, f"{lat:.5f}"), (self.e_lon, f"{lon:.5f}"), (self.e_home, name)):
            e.delete(0, "end")
            e.insert(0, v)
        country = self.map.country_at(lat, lon)
        if country:
            self.settings.home_country = country
        self._save_home()
        self.home_status.configure(text=status + f"  →  {lat:.5f}, {lon:.5f}" + (f"  ·  {name}" if name else ""),
                                   text_color=theme.OK)
        self.log(status + f": {lat:.5f}, {lon:.5f}" + (f" · {name}" if name else ""), "ok")

    def _save_home(self) -> None:
        try:
            lat = float(self.e_lat.get().replace(",", ".")) if self.e_lat.get().strip() else None
            lon = float(self.e_lon.get().replace(",", ".")) if self.e_lon.get().strip() else None
            if lat is not None and not -90 <= lat <= 90 or lon is not None and not -180 <= lon <= 180:
                raise ValueError
        except ValueError:
            self.home_status.configure(text=tr("coordinate non valide (es. 45.6495 e 13.7768)"), text_color=theme.ERR)
            return
        self.settings.home_lat, self.settings.home_lon = lat, lon
        self.settings.home_name = self.e_home.get().strip()
        self.settings.save(CONFIG_FILE)
        self.map.set_home(lat, lon, self.settings.home_name)
        self.home_status.configure(text=tr("posizione salvata") if lat is not None else tr("posizione rimossa"),
                                   text_color=theme.OK)

    def _startup_adb(self) -> None:
        """All'avvio: adb si usa solo dalla cartella tools. Se manca NON si scarica da solo:
        si avvisa e si rimanda al pulsante in Config."""
        if platform_tools.local_adb():
            return self._run_bg(self._detect)
        self.log(tr("adb non presente nella cartella tools: scaricalo con 'Scarica / aggiorna da Google' nel tab Config."))
        self._status("ADB", tr("non presente"), theme.ERR)

    def _adb_status(self) -> None:
        def check():
            path = platform_tools.local_adb()
            if not path:
                txt = tr("adb non presente in {p}: premi 'Scarica / aggiorna da Google'", p=platform_tools.local_dir())
                return self._ui(lambda: self.adb_status.configure(text=txt, text_color=theme.ERR))
            ver = platform_tools.adb_version(path)
            txt = f"{tr('scaricato nella cartella tools')}  ·  {ver or '?'}\n{path}"
            self._ui(lambda: self.adb_status.configure(text=txt, text_color=theme.OK if ver else theme.WARN))
        threading.Thread(target=check, daemon=True).start()

    def _open_url(self, url: str) -> None:
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:  # noqa: BLE001
            self.log(tr("errore: {e}", e=e), "err")

    def _save_ip_keys(self) -> None:
        for key, e in self.key_entries.items():
            setattr(self.settings, key, e.get().strip())
        self.settings.ip_active = bool(self.ip_active_var.get())
        self.settings.save(CONFIG_FILE)
        n = sum(1 for key, _e in self.key_entries.items() if getattr(self.settings, key))
        self.keys_status.configure(text=tr("salvato · {n} servizi attivi", n=n), text_color=theme.OK)

    # ---------------------------------------------------------------- agent Android (APK)
    def _apk_path(self) -> str | None:
        """L'APK da usare: quello scelto in Config se esiste, altrimenti il predefinito."""
        chosen = self.settings.resolve("agent_apk")
        if chosen:
            return chosen if os.path.isfile(chosen) else None
        return find_apk(None)

    def _apk_status(self) -> None:
        chosen = (self.settings.agent_apk or "").strip()
        path = self._apk_path()
        if chosen and not path:
            return self.apk_status.configure(text=tr("file non trovato: {p}", p=chosen), text_color=theme.ERR)
        if not path:
            return self.apk_status.configure(
                text=tr("nessun APK: compila l'agent (README > Compilare l'APK) o scegli il file con Sfoglia"), text_color=theme.WARN)
        info = apkinfo.read(path)
        self._apk_info = info
        if info.error:
            return self.apk_status.configure(text=tr("APK non leggibile: {e}", e=info.error) + f"  ·  {path}", text_color=theme.ERR)
        text = f"{os.path.basename(path)}  ·  {tr('versione')} {info.version}  ·  {_bytes(info.size)}  ·  {info.package or '?'}"
        if not chosen:
            text += "  ·  " + tr("(predefinito)")
        if info.package and info.package != PACKAGE:
            text += "\n⚠ " + tr("non è l'agent DroidSnex (atteso {p})", p=PACKAGE)
            self.apk_status.configure(text=text, text_color=theme.WARN)
        else:
            self.apk_status.configure(text=text, text_color=theme.OK)

    def _save_apk(self) -> None:
        self.settings.agent_apk = self.e_apk.get().strip()
        self.settings.save(CONFIG_FILE)          # dentro la cartella del programma -> salvato relativo
        self.e_apk.delete(0, "end")
        self.e_apk.insert(0, self.settings.agent_apk)
        self._apk_status()
        self.log(tr("APK dell'agent: {p}", p=self.settings.agent_apk or tr("predefinito")), "ok")

    def _pick_apk(self) -> None:
        path = filedialog.askopenfilename(title=tr("Seleziona l'APK dell'agent DroidSnex"), filetypes=[("APK", "*.apk")],
                                          initialdir=os.path.dirname(self.settings.resolve("agent_apk")) if self.settings.agent_apk else HERE)
        if path:
            self.e_apk.delete(0, "end")
            self.e_apk.insert(0, path)
            self._save_apk()

    def _default_apk(self) -> None:
        self.e_apk.delete(0, "end")
        self._save_apk()

    def _cloud_status(self) -> None:
        if "cloud" in self._job_error:
            self.cloud_status.configure(text=tr("errore: {e}", e=self._job_error["cloud"]), text_color=theme.ERR)
        elif self.cloud.available:
            self.cloud_status.configure(text=self.cloud.describe(), text_color=theme.OK)
        else:
            self.cloud_status.configure(text=tr("non presenti"), text_color=theme.WARN)

    def _download_cloud(self) -> None:
        self.log(tr("download delle liste dei range cloud…"))
        self._ui(self.cloud_status.configure, text=tr("download…"), text_color=theme.ACCENT)
        n = len(ipinfo.CLOUD_LISTS)
        done = [0]

        def progress(name):
            done[0] += 1
            self._ui(self.cloud_bar.set, (done[0] - 1) / n)
            self._ui(self.cloud_status.configure, text=f"{name}…")
        ok, errors = ipinfo.download_cloud(DATA_DIR, progress, lambda: self._cancel["cloud"])
        self._ui(self.cloud_bar.set, 1)
        self.cloud.load(DATA_DIR)
        if ok:
            self.log(tr("liste cloud: {d}", d=self.cloud.describe()), "ok")
        if errors:
            raise OSError(tr("liste non scaricate") + " → " + "; ".join(f"{k}: {v}" for k, v in errors.items()))

    def _scrcpy_status(self) -> None:
        if "scrcpy" in self._job_error:
            self.scrcpy_status.configure(text=tr("errore: {e}", e=self._job_error["scrcpy"]), text_color=theme.ERR)
        elif self.scrcpy.available:
            self.scrcpy_status.configure(text=f"{scrcpy_mod.describe()}\n{self.scrcpy.path}", text_color=theme.OK)
        else:
            self.scrcpy_status.configure(text=tr("non presente") + f"  ({scrcpy_mod.local_dir()})", text_color=theme.WARN)

    def _download_scrcpy(self) -> None:
        self.log(tr("download di scrcpy dalle release ufficiali su GitHub…"))
        self._close_screen()                     # scrcpy.exe in uso non si può sostituire
        last = [0.0]

        def progress(got, total):
            now = time.monotonic()
            if now - last[0] > 0.2 or (total and got >= total):
                last[0] = now
                txt = tr("scaricati {a} MB di {b} MB", a=f"{got / 1e6:.1f}", b=f"{total / 1e6:.1f}") if total \
                    else tr("scaricati {a} MB", a=f"{got / 1e6:.1f}")
                self._ui(lambda: (self.scrcpy_bar.set(got / total if total else 0),
                                  self.scrcpy_status.configure(text=txt, text_color=theme.TEXT_SOFT)))
        path = scrcpy_mod.download(progress=progress, cancel=lambda: self._cancel["scrcpy"])
        self._ui(self.scrcpy_bar.set, 1)
        self.log(tr("scrcpy pronto: {v}", v=scrcpy_mod.version(path) or path), "ok")

    def _use_new_adb(self) -> None:
        """Dopo un cambio di adb: si ricollega con quello nuovo (se il monitor non è attivo)."""
        if self.client is None and not self.demo:
            self.adb = None
            self._run_bg(self._detect)
        self._config_status()

    def _download_adb(self) -> None:
        url = platform_tools.download_url()
        self.log(tr("download di adb (Android Platform Tools) da {u}…", u=url))
        # un adb avviato dalla cartella tools blocca i suoi file (Windows): lo fermiamo prima
        if self.adb and self.client is None and self.adb.path == platform_tools.local_adb():
            try:
                self.adb.run("kill-server", device=False, check=False, timeout=10)
            except AdbError:
                pass
        last = [0.0]

        def progress(got, total):
            now = time.monotonic()
            if now - last[0] > 0.2 or (total and got >= total):
                last[0] = now
                txt = tr("scaricati {a} MB di {b} MB", a=f"{got / 1e6:.1f}", b=f"{total / 1e6:.1f}") if total \
                    else tr("scaricati {a} MB", a=f"{got / 1e6:.1f}")
                self._ui(lambda: (self.adb_bar.set(got / total if total else 0),
                                  self.adb_status.configure(text=txt, text_color=theme.TEXT_SOFT)))
        path = platform_tools.download(progress=progress, cancel=lambda: self._cancel["adb"])
        ver = platform_tools.adb_version(path)
        self.log(tr("adb pronto: {v}", v=ver or path), "ok")
        self._ui(self._use_new_adb)

    # ---------------------------------------------------------------- mappa vettoriale
    @staticmethod
    def _vector_10m() -> str:
        return os.path.join(DATA_DIR, "vector-10m.json.gz")

    def _load_vector(self) -> None:
        """Carica la mappa vettoriale (alta definizione se scaricata) senza bloccare l'interfaccia."""
        path = self._vector_10m() if os.path.isfile(self._vector_10m()) else VECTOR_50M

        def done(vm: VectorMap) -> None:
            if not vm.ready and path != VECTOR_50M:          # file 10m rovinato: si torna a quello incluso
                return load_async(VECTOR_50M, done)
            self._ui(lambda: self._vector_ready(vm))
        load_async(path, done)

    def _vector_ready(self, vm: VectorMap) -> None:
        if not vm.ready:
            return self.log(tr("mappa vettoriale non disponibile: {e}", e=vm.error), "err")
        self.vector = vm
        self.map.set_vector(vm)

    def _download_vector(self) -> None:
        self.log(tr("download della mappa vettoriale ad alta definizione (Natural Earth 1:10m)…"))
        last = [0.0]

        def progress(what, got, total):
            now = time.monotonic()
            if what == "convert":
                return self._ui(lambda: (self.tiles_bar.set(1), self.tiles_status.configure(
                    text=tr("conversione dei dati… (circa un minuto)"), text_color=theme.TEXT_SOFT)))
            if now - last[0] > 0.3:
                last[0] = now
                txt = f"{what}  ·  {got / 1e6:.1f}" + (f" / {total / 1e6:.1f}" if total else "") + " MB"
                step = int(what.split("/")[0]) - 1
                frac = (step + (got / total if total else 0)) / 6
                self._ui(lambda: (self.tiles_bar.set(frac), self.tiles_status.configure(text=txt, text_color=theme.TEXT_SOFT)))
        download_10m(self._vector_10m(), os.path.join(DATA_DIR, "ne-10m"), progress=progress,
                     cancel=lambda: self._cancel["tiles"])
        self.log(tr("mappa vettoriale ad alta definizione installata"), "ok")
        self._ui(self._load_vector)

    def _set_map_heat(self, on: bool) -> None:
        self.settings.map_heat = on
        self.settings.save(CONFIG_FILE)

    def _toggle_dark(self) -> None:
        self.settings.map_dark = bool(self.sw_dark.get())
        self.settings.save(CONFIG_FILE)
        self.map.dark = self.settings.map_dark
        self.map.redraw()

    def _build_details(self, parent) -> None:
        right = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, width=DETAILS_WIDTH)
        right.grid(row=2, column=1, sticky="ns", padx=(theme.GAP, 0))
        self.details_col = right
        right.grid_propagate(False)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=3)
        right.grid_rowconfigure(1, weight=2)

        det = Card(right, tr("Dettagli"), self.fonts)
        det.grid(row=0, column=0, sticky="nsew")
        self.det_card = det
        self.det_float_btn = det.corner_button("⧉", lambda: self._toggle_float("details"))
        self.det_ip_btn = ctk.CTkButton(det.head, text=tr("Dettaglio IP"), width=0, height=18, corner_radius=3,
                                        fg_color="transparent", border_width=1, border_color=theme.BORDER_STRONG,
                                        hover_color=theme.HOVER, text_color=theme.ACCENT, font=self.fonts.small,
                                        command=self._open_ip_detail)
        self.det_ip_btn.pack(side="right", padx=(0, 6))
        self._details_text = None
        self.details = ctk.CTkTextbox(det.body, font=self.fonts.mono, wrap="word")
        self.details.pack(fill="both", expand=True)
        self._set_details(tr("Seleziona una riga per vedere IP, porte, protocolli, fonte del nome e ultime connessioni."))

        log = Card(right, "Log", self.fonts)
        log.grid(row=1, column=0, sticky="nsew", pady=(theme.GAP, 0))
        self.log_card = log
        self.console = ctk.CTkTextbox(log.body, font=ctk.CTkFont(family=theme.mono_font(), size=10),
                                      text_color=theme.TEXT_SOFT, wrap="word")
        self.console.pack(fill="both", expand=True)
        self.console.tag_config("ok", foreground=theme.OK)
        self.console.tag_config("err", foreground=theme.ERR)
        self.console.configure(state="disabled")
        self._build_app_filter(right)

    def _build_app_filter(self, parent) -> None:
        """Scheda Mappa: elenco delle app, per scegliere di quali mostrare i collegamenti."""
        card = Card(parent, tr("App sulla mappa"), self.fonts)
        self.apps_card = card
        self.apps_float_btn = card.corner_button("⧉", lambda: self._toggle_float("apps"))
        self.apps_count = ctk.CTkLabel(card.head, text="", font=self.fonts.title, text_color=theme.TEXT_DIM)
        self.apps_count.pack(side="left", padx=(8, 0))
        b = card.body
        b.grid_columnconfigure((0, 1), weight=1)
        b.grid_rowconfigure(3, weight=1)
        # fidate / non fidate
        self._trust_names = {"all": tr("Tutte"), "t": tr("Fidate"), "u": tr("Non fidate")}
        self.trust_seg = ctk.CTkSegmentedButton(b, values=list(self._trust_names.values()), height=26,
                                                font=self.fonts.small, command=self._set_map_trust,
                                                selected_color=theme.BTN, selected_hover_color=theme.BTN_HOVER)
        self.trust_seg.set(self._trust_names[self._map_trust])
        self.trust_seg.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, theme.GAP))
        # solo nuove: nasconde le connessioni già viste e da qui in poi mostra solo quelle nuove
        self.btn_new = button(b, "", self._toggle_new_only, height=28)
        self.btn_new.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, theme.GAP))
        self._paint_new_button()
        button(b, tr("Mostra tutte"), lambda: self._set_all_apps(True), height=26).grid(
            row=2, column=0, sticky="ew", padx=(0, 3))
        button(b, tr("Nascondi tutte"), lambda: self._set_all_apps(False), height=26).grid(
            row=2, column=1, sticky="ew", padx=(3, 0))
        self.apps_list = ctk.CTkScrollableFrame(b, fg_color=theme.PANEL_2, corner_radius=4, border_width=1,
                                                border_color=theme.BORDER)
        self.apps_list.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(theme.GAP, 0))
        self._app_boxes: dict[str, tuple] = {}      # app -> (variabile, checkbox)
        if not hasattr(self, "_app_visible"):
            self._app_visible: dict[str, bool] = {}  # scelta dell'utente per ogni app
            self._apps_default = True                # le app nuove: visibili dopo "Mostra tutte", no dopo "Nascondi"

    def _toggle_new_only(self) -> None:
        """Primo clic: nasconde tutte le connessioni attuali, poi compaiono solo quelle nuove. Secondo clic: tutte."""
        if self._map_new_since is None:
            self._map_new_since = {c.key for c in self.mon.snapshot()}
            self._map_new_t = time.strftime("%H:%M:%S")
            self.log(tr("mappa: solo connessioni nuove dalle {t}", t=self._map_new_t))
        else:
            self._map_new_since = None
        self._paint_new_button()
        self._apps_changed()

    def _paint_new_button(self) -> None:
        if self._map_new_since is None:
            self.btn_new.configure(text="✦  " + tr("Solo connessioni nuove"), fg_color=theme.NEUTRAL,
                                   hover_color=theme.NEUTRAL_HOVER, text_color=theme.TEXT)
        else:
            self.btn_new.configure(text="●  " + tr("Nuove dalle {t} · mostra tutte", t=self._map_new_t),
                                   fg_color=theme.BTN, hover_color=theme.BTN_HOVER, text_color=theme.BTN_TEXT)

    def _set_map_trust(self, value: str) -> None:
        """Mappa: tutte le linee, solo le fidate (verdi) o solo le non fidate (rosse)."""
        self._map_trust = next((k for k, v in self._trust_names.items() if v == value), "all")
        self._apps_changed()

    def _app_shown(self, app: str) -> bool:
        return self._app_visible.get(app, self._apps_default)

    def _set_all_apps(self, visible: bool) -> None:
        self._apps_default = visible
        for app, (var, _box) in self._app_boxes.items():
            self._app_visible[app] = visible
            var.set(visible)
        self._apps_changed()

    def _toggle_app(self, app: str) -> None:
        self._app_visible[app] = bool(self._app_boxes[app][0].get())
        self._apps_changed()

    def _apps_changed(self) -> None:
        # niente "picchi" di velocità quando un'app ricompare: si riparte dai totali attuali
        self._rate_prev.clear()
        self._rate_ema.clear()
        self._map_sel = None
        self.map.selected = None
        if not self.pause_var.get():
            self._refresh()

    def _update_app_list(self, per_app: dict[str, int]) -> None:
        """Una casella per app (ordine alfabetico); aggiorna i conteggi delle connessioni."""
        for i, app in enumerate(sorted(per_app)):
            if app not in self._app_boxes:
                var = tk.BooleanVar(value=self._app_shown(app))
                box = ctk.CTkCheckBox(self.apps_list, text=app, variable=var, font=self.fonts.small,
                                      checkbox_width=16, checkbox_height=16, border_width=1, corner_radius=3,
                                      command=lambda a=app: self._toggle_app(a))
                box.bind("<Double-Button-1>", lambda _e, a=app: self._show_app_profile(a))
                self._app_boxes[app] = (var, box)
            var, box = self._app_boxes[app]
            box.configure(text=f"{self.mon.app_label(app)}  ·  {per_app[app]}")
            box.grid(row=i, column=0, sticky="w", padx=6, pady=2)
        shown = sum(1 for a in per_app if self._app_shown(a))
        self.apps_count.configure(text=f"{shown}/{len(per_app)}")

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0, height=26)
        footer.grid(row=4, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_rowconfigure(0, weight=1)
        self.status_label = ctk.CTkLabel(footer, text=tr("Pronto."), font=self.fonts.small,
                                         text_color=theme.TEXT_SOFT, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=(16, 8))
        self.busy_bar = ctk.CTkProgressBar(footer, mode="indeterminate", width=90, height=4)
        self.busy_bar.grid(row=0, column=1, padx=(0, 14))
        self.busy_bar.grid_remove()
        self.info_label = ctk.CTkLabel(footer, text="", font=self.fonts.tiny, text_color=theme.TEXT_DIM)
        self.info_label.grid(row=0, column=2, sticky="e", padx=(0, 16))
        ctk.CTkLabel(footer, text="F5  " + tr("aggiorna dispositivi"), font=self.fonts.tiny,
                     text_color=theme.TEXT_FAINT).grid(row=0, column=3, sticky="e", padx=(0, 16))
        credits = ctk.CTkLabel(footer, text=CREDITS + "  ·  " + tr("Info e licenze"), font=self.fonts.tiny,
                               text_color=theme.TEXT_DIM, cursor="hand2")
        credits.grid(row=0, column=4, sticky="e", padx=(0, 16))
        credits.bind("<Button-1>", lambda _e: about.show(self, self.fonts))

    # ================================================================ helper
    def log(self, msg: str, kind: str = "") -> None:
        """Thread-safe: i messaggi passano da una coda letta dal thread dell'interfaccia."""
        self.ui_queue.put(("log", time.strftime("%H:%M:%S") + "  " + str(msg), kind))

    def _ui(self, fn, *args, **kw) -> None:
        """Esegue fn(*args, **kw) nel thread dell'interfaccia (da usare dai thread di download/adb)."""
        self.ui_queue.put(("call", fn, args, kw))

    def _write_log(self, line: str, kind: str) -> None:
        self._log_lines.append((line, kind))
        del self._log_lines[:-500]
        self.console.configure(state="normal")
        self.console.insert("end", line + "\n", kind or None)
        self.console.see("end")
        self.console.configure(state="disabled")
        self.status_label.configure(text=line.split("  ", 1)[-1],
                                    text_color=theme.ERR if kind == "err" else theme.TEXT_SOFT)

    def _set_details(self, text: str) -> None:
        """Aggiorna il pannello Dettagli. L'aggiornamento live non riporta più lo scroll in cima:
        se il testo è lo stesso non si tocca nulla, se cambia solo nei numeri resta dov'eri."""
        if text == getattr(self, "_details_text", None) and self.details.winfo_exists():
            return
        same_subject = text.split("\n", 1)[0] == (getattr(self, "_details_text", "") or "").split("\n", 1)[0]
        pos = self.details.yview()[0] if same_subject else 0.0
        self._details_text = text
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")
        if pos:
            self.details.yview_moveto(pos)

    def _hint(self, text: str) -> None:
        if text:
            self.hint_label.configure(text=text)
            self.hint_label.grid()
        else:
            self.hint_label.grid_remove()

    def _status(self, key: str, text: str, color: str = theme.TEXT_FAINT) -> None:
        dot, val = self.status_rows[key]
        dot.configure(text_color=color)
        val.configure(text=text)

    def _show_state(self, text: str, color: str) -> None:
        """Stato della connessione nell'intestazione: spia colorata e testo."""
        self.state_dot.configure(text_color=color)
        self.state_label.configure(text=text, text_color=theme.TEXT if color == theme.OK else theme.TEXT_SOFT)

    def _run_bg(self, fn, *args) -> None:
        """Operazioni adb (lente) fuori dal thread dell'interfaccia."""
        if self.busy:
            self.log(tr("operazione già in corso…"))
            return
        self.busy = True

        def wrap():
            try:
                fn(*args)
            except AdbError as e:
                self.log(str(e), "err")
            except Exception as e:  # noqa: BLE001
                self.log(tr("errore: {e}", e=e), "err")
            finally:
                self.busy = False
        threading.Thread(target=wrap, daemon=True).start()

    def _busy_tick(self) -> None:
        if self.busy:
            self.busy_bar.grid()
            self.busy_bar.start()
        else:
            self.busy_bar.stop()
            self.busy_bar.grid_remove()
        self.after(150, self._busy_tick)

    # ================================================================ azioni adb
    def _detect(self) -> None:
        try:
            if self.adb is None:
                self.adb = Adb()
            self._ui(self._status, "ADB", tr("pronto"), theme.OK)
        except AdbError:
            self._ui(self._status, "ADB", tr("non trovato"), theme.ERR)
            raise
        devs = self.adb.devices()
        names = [f"{d.model or d.serial}  ·  {d.serial}" for d in devs] or [tr(NO_DEVICE)]
        self._ui(lambda: (self.device_menu.configure(values=names), self.device_menu.set(names[0])))
        ready = [d for d in devs if d.state == "device"]
        if not ready:
            unauth = any(d.state == "unauthorized" for d in devs)
            self._ui(self._status, "DEVICE", tr("non autorizzato") if unauth else tr("non collegato"),
                     theme.WARN if devs else theme.ERR)
            self._ui(self._show_state, tr("Non autorizzato") if unauth else tr(NO_DEVICE),
                     theme.WARN if devs else theme.TEXT_FAINT)
            self._ui(self._hint, tr("Sblocca il telefono e accetta 'Consentire debug USB?'.") if unauth
                     else tr(NO_DEVICE_HINT))
            self.adb.serial = None
            return
        if self.adb.serial not in [d.serial for d in ready]:
            self.adb.serial = ready[0].serial
        dev = next(d for d in ready if d.serial == self.adb.serial)
        api = self.adb.sdk_int()
        self._ui(self._status, "DEVICE", f"{dev.model or dev.serial} · API {api}", theme.OK)
        self._ui(self._hint, "")
        self._ui(lambda: self.info_label.configure(text=f"{dev.model or ''}  {dev.serial}  ·  Android API {api}"))
        self._ui(self._show_state, tr("Pronto: premi Start"), theme.ACCENT)
        installed = self.adb.is_installed()
        self._ui(self._status, "AGENT", tr("installato") if installed else tr("non installato"),
                 theme.WARN if installed else theme.TEXT_FAINT)
        self.log(tr("dispositivo {serial} {model}", serial=dev.serial, model=dev.model), "ok")

    def _on_device_pick(self, value: str) -> None:
        serial = value.split("·")[-1].strip()
        if self.adb and serial and value != tr(NO_DEVICE):
            self.adb.serial = serial
            self._stop_stream()
            self._run_bg(self._detect)

    def _start(self) -> None:
        """Start: installa l'APK, concede i permessi, avvia la VPN, adb forward, stream live."""
        if self._replay:
            self._exit_replay()
        if self.demo:
            return self._connect_demo()
        if self.monitoring:
            return self.log(tr("il monitor è già attivo"))
        apk = self._apk_path()
        if not apk:
            if self.settings.agent_apk:
                self.log(tr("file non trovato: {p}", p=self.settings.agent_apk), "err")
            apk = filedialog.askopenfilename(title=tr("Seleziona l'APK dell'agent DroidSnex"),
                                             filetypes=[("APK", "*.apk")])
            if not apk:
                return self.log(tr("APK dell'agent non trovato: compilalo (README) o scegli il file nel tab Config"), "err")
        self._run_bg(self._do_start, apk)

    def _do_start(self, apk: str) -> None:
        self._detect()
        if not self.adb or not self.adb.serial:
            return
        self.monitoring = True
        self.device_info = self.adb.identity()
        d = self.device_info
        self.log(tr("telefono: {m} · Android {a} · seriale {s} · Android ID {i}", m=d.get("model", "?"), a=d.get("android", "?"),
                    s=d.get("serial", "?"), i=d.get("android_id") or "-"))
        if d.get("imei") or d.get("wifi_mac"):
            self.log(f"IMEI {d.get('imei') or '-'} · MAC Wi-Fi {d.get('wifi_mac') or '-'}")
        else:
            self.log(tr("IMEI e MAC non leggibili via adb senza root (Android 10+): il telefono viene riconosciuto da seriale e Android ID"))
        self._ui(self._show_state, tr("Installazione…"), theme.WARN)
        self.log(tr("installazione di {apk} sul telefono…", apk=os.path.basename(apk)))
        out = self.adb.install(apk)
        self.log(out.splitlines()[-1] if out else tr("installato"), "ok")
        self._ui(self._status, "AGENT", tr("installato"), theme.OK)
        for w in self.adb.grant_permissions():
            self.log(w, "err")
        self.log(tr("permessi concessi: VPN pre-autorizzata, notifiche, batteria"), "ok")

        self._ui(self._show_state, tr("Avvio della VPN…"), theme.WARN)
        self.adb.start_capture(language())       # l'app sul telefono usa la stessa lingua del PC
        self.adb.forward(self.port, DEFAULT_PORT)
        self.log(f"adb forward tcp:{self.port} tcp:{DEFAULT_PORT}")
        self._start_guard()
        self._ui(self._status, "VPN", tr("attesa consenso…"), theme.WARN)
        t0, hinted = time.time(), False
        while time.time() - t0 < 90 and self.monitoring:
            hello = probe_agent(self.port)
            if hello and hello.get("vpn"):
                self.log(tr("VPN attiva, connessioni in arrivo"), "ok")
                self._ui(self._ensure_stream)
                return
            if not hinted and time.time() - t0 > 4:
                hinted = True
                self.log(tr("Se sul telefono compare 'Richiesta di connessione', sblocca e tocca OK."))
            time.sleep(1.5)
        self._ui(self._status, "VPN", tr("non attiva"), theme.ERR)
        self.log(tr("la VPN non risulta attiva: vedi README > Troubleshooting"), "err")

    def _stop(self) -> None:
        """Stop: chiude lo stream, ferma la VPN e disinstalla l'agent dal telefono."""
        if self.demo:
            self._stop_stream()
            self.monitoring = False
            self._session_end()
            self._show_state(tr("Monitor fermo"), theme.TEXT_FAINT)
            return self.log(tr("monitor fermato (demo)"))
        self._stop_stream()
        self.monitoring = False
        self._session_end()

        def job():
            for line in self._cleanup_phone():
                self.log(line, "ok")
            self._ui(self._show_state, tr("Monitor fermo"), theme.TEXT_FAINT)
            self._ui(self._status, "AGENT", tr("disinstallato"), theme.TEXT_FAINT)
            self._ui(self._status, "VPN", tr("ferma"), theme.TEXT_FAINT)
            self._ui(self._status, "STREAM", "—", theme.TEXT_FAINT)
        self._run_bg(job)

    def _cleanup_phone(self) -> list[str]:
        """Ferma e disinstalla l'agent (anche se il monitor non risulta attivo). Mai eccezioni."""
        self._cleanup_done = True
        if self.demo or not self.adb or not self.adb.serial:
            return []
        try:
            if not self.adb.is_online():
                self._stop_guard(done=False)      # il guardiano continua a provare per un po'
                return [tr("telefono non collegato: l'agent si fermerà da solo (watchdog)")]
        except Exception:  # noqa: BLE001
            self._stop_guard(done=False)
            return []
        out = self.adb.cleanup(self.port)
        try:
            removed = not self.adb.is_installed()
        except Exception:  # noqa: BLE001
            removed = False
        self._stop_guard(done=removed)
        return out

    # ---------------------------------------------------------------- guardiano (crash del PC)
    def _start_guard(self) -> None:
        """Processo a parte (droidsnex/guard.py) che, se questo programma crasha o viene chiuso di colpo,
        ferma e disinstalla l'agent dal telefono. Con Stop/chiusura regolare riceve "bye" e non fa nulla."""
        self._stop_guard(done=True)
        if self.demo or not self.adb or not self.adb.serial:
            return
        os.makedirs(self.out_dir, exist_ok=True)
        logf = os.path.join(self.out_dir, "guard.log")
        args = ["--adb", self.adb.path, "--serial", self.adb.serial, "--port", str(self.port), "--log", logf]
        # da eseguibile (PyInstaller) non esiste "python -m": l'exe stesso, con --guard, fa da guardiano (vedi gui.py)
        cmd = [sys.executable, "--guard", *args] if FROZEN else [sys.executable, "-m", "droidsnex.guard", *args]
        # finestra di console nascosta (Windows) e gruppo di processi a parte, cosi' un Ctrl-C non lo tocca
        kw = hidden(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)) if os.name == "nt" else {"start_new_session": True}
        try:
            self._guard = subprocess.Popen(cmd, cwd=HERE, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, **kw)
            self.log(tr("guardiano avviato (pid {p}): se il programma crasha, l'agent viene fermato e disinstallato", p=self._guard.pid))
        except OSError as e:
            self._guard = None
            self.log(tr("guardiano non avviato: {e}", e=e), "err")

    def _stop_guard(self, done: bool) -> None:
        """`done`=True: il telefono e' gia' pulito, il guardiano esce. False: il guardiano prova lui."""
        g, self._guard = self._guard, None
        if g is None or g.poll() is not None:
            return
        try:
            if done and g.stdin:
                g.stdin.write(b"bye\n")
                g.stdin.flush()
            if g.stdin:
                g.stdin.close()
        except (OSError, ValueError):
            pass

    def _export(self) -> None:
        conns = self.mon.snapshot()
        if not conns:
            return self.log(tr("nessuna connessione da esportare"))
        paths = export_all(conns, self.out_dir, label_for=self.mon.dest_label)
        self.log(tr("esportato:") + " " + ", ".join(os.path.basename(p) for p in paths), "ok")

    def _open_out(self) -> None:
        self._open_dir(self.out_dir)

    def _open_manual(self) -> None:
        """Il manuale docs/manual/<lingua>/MANUAL.md, formattato in una finestra del programma (inglese se la lingua manca)."""
        path = manual_path(language())
        if not path:
            self.log(tr("manuale non trovato: {p}", p=os.path.join(MANUAL_DIR, language(), "MANUAL.md")), "err")
            return
        try:
            manual.open_manual(self, path)
        except Exception as e:  # noqa: BLE001
            self.log(tr("impossibile aprire il manuale: {e}", e=e), "err")

    def _open_dir(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import subprocess
                subprocess.Popen(["xdg-open" if os.uname().sysname != "Darwin" else "open", path])
        except OSError as e:
            self.log(tr("impossibile aprire la cartella: {e}", e=e), "err")

    # ================================================================ stream
    def _connect_demo(self) -> None:
        host, _, port = self.demo.partition(":")
        self.port = int(port or 8899)
        self._status("ADB", tr("modalità demo"), theme.ACCENT)
        self._status("DEVICE", f"{host}:{self.port}", theme.ACCENT)
        self.device_menu.configure(values=[f"Demo  ·  {host}:{self.port}"])
        self.device_menu.set(f"Demo  ·  {host}:{self.port}")
        self.info_label.configure(text=tr("agent simulato"))
        self.device_info = {"serial": "demo", "model": "Demo", "brand": "", "android_id": "demo"}
        self._ensure_stream(host)

    def _ensure_stream(self, host: str = "127.0.0.1") -> None:
        if self.client and self.client.is_alive():
            return
        os.makedirs(self.out_dir, exist_ok=True)
        if self.mon._log is None:   # log grezzo dello stream, come nella versione a riga di comando
            self.mon._log = open(os.path.join(self.out_dir, time.strftime("stream-%Y%m%d-%H%M%S.jsonl")),
                                 "a", encoding="utf-8")

        def on_event(ev):
            ev["_inst"] = self.client.instance or ""
            self.mon.handle(ev)

        def on_status(s, kind=""):
            self.mon.set_status(s)
            self.log(s, kind)

        # watchdog: se questo programma sparisce (chiuso, crash, cavo staccato) per
        # WATCHDOG_SEC secondi, l'agent sul telefono ferma la VPN da solo.
        self.mon.reset()
        self._session_begin()
        self.client = StreamClient(host, self.port, on_event, on_status,
                                   adb=None if self.demo else self.adb, remote_port=DEFAULT_PORT,
                                   watchdog=0 if self.demo else WATCHDOG_SEC)
        self.client.start()
        self.monitoring = True
        self._cleanup_done = False
        self.log(f"stream: {host}:{self.port}")

    def _stop_stream(self) -> None:
        if self.client:
            self.client.stop()
            self.client = None

    # ================================================================ aggiornamento
    def _tick(self) -> None:
        try:
            while True:
                item = self.ui_queue.get_nowait()
                if item[0] == "log":
                    self._write_log(item[1], item[2])
                else:
                    try:
                        item[1](*item[2], **(item[3] if len(item) > 3 else {}))
                    except tk.TclError:
                        pass            # widget di un'interfaccia ricostruita (cambio lingua)
        except queue.Empty:
            pass
        try:
            self._refresh()
        except Exception as e:  # noqa: BLE001
            self._write_log(f"refresh: {e}", "err")
        self.after(1000, self._tick)

    def _paint_monitor_buttons(self) -> None:
        """'Pulisci tutto' si vede solo a monitor fermo e con qualcosa da cancellare (nel replay: esce dal replay);
        'Segnalibro' solo a monitor attivo."""
        on = bool(self.monitoring)
        if on != self._mon_btn:
            self._mon_btn = on
            if on:
                self.btn_start.configure(text="■  Stop monitor", fg_color="transparent", hover_color=theme.HOVER,
                                         border_width=1, border_color=theme.ERR, text_color=theme.ERR)
            else:
                self.btn_start.configure(text="▶  Start monitor", fg_color=theme.BTN, hover_color=theme.BTN_HOVER,
                                         border_width=0, text_color=theme.BTN_TEXT)
        show = not self.monitoring and not self._replay and bool(self.mon.conns or self.mon.dns or self.alerts.items)
        if show != getattr(self, "_clear_shown", None):
            self._clear_shown = show
            if show:
                self.btn_clear.grid()
            else:
                self.btn_clear.grid_remove()
        mark = bool(self.monitoring and self.session)
        if mark != getattr(self, "_mark_shown", None):
            self._mark_shown = mark
            if mark:
                self.btn_mark.grid()
            else:
                self.btn_mark.grid_remove()

    def _mark_dialog(self) -> None:
        """Segnalibro: una nota (es. 'ho aperto Instagram') legata all'istante e, se c'e' il telefono, uno screenshot."""
        if not self.session:
            return self.log(tr("nessuna sessione in corso: avvia il monitor"), "err")
        win = ctk.CTkToplevel(self, fg_color=theme.BG)
        win.title(tr("Segnalibro"))
        win.resizable(False, False)
        win.transient(self)
        f = self.fonts
        box = ctk.CTkFrame(win, fg_color=theme.PANEL, border_width=1, border_color=theme.BORDER, corner_radius=4)
        box.pack(fill="both", expand=True, padx=1, pady=1)
        ctk.CTkLabel(box, text="🔖  " + tr("Segnalibro") + f"  ·  {time.strftime('%H:%M:%S')}", font=f.bold,
                     text_color=theme.TEXT).pack(anchor="w", padx=18, pady=(14, 2))
        ctk.CTkLabel(box, text=tr("Cosa sta succedendo sul telefono in questo momento? (es. 'ho aperto Instagram'). "
                                  "Il segnalibro viene salvato nella sessione con l'orario e uno screenshot del telefono."),
                     font=f.small, text_color=theme.TEXT_DIM, justify="left", wraplength=420).pack(anchor="w", padx=18)
        entry = ctk.CTkEntry(box, width=440, height=32, font=f.body, placeholder_text=tr("nota"))
        entry.pack(padx=18, pady=(10, 4))
        row = ctk.CTkFrame(box, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(6, 14))

        def save(_e=None):
            note = entry.get()
            win.destroy()
            self._add_mark(note)
        button(row, tr("Salva segnalibro"), save, primary=True).pack(side="right")
        button(row, tr("Annulla"), win.destroy).pack(side="right", padx=(0, 8))
        entry.bind("<Return>", save)
        win.bind("<Escape>", lambda _e: win.destroy())
        win.update_idletasks()
        win.geometry(f"+{self.winfo_rootx() + 260}+{self.winfo_rooty() + 180}")
        frameless.style_titlebar(win, theme.BG, theme.TEXT_SOFT, theme.BORDER)
        win.after(80, lambda: (win.deiconify(), win.lift(), entry.focus_set()) if win.winfo_exists() else None)

    def _clear_all(self) -> None:
        if self.monitoring:
            return
        if self._replay:
            return self._exit_replay()
        confirm(self, tr("Pulisci tutto"),
                tr("Cancellare tutte le connessioni, le query DNS, gli alert, la mappa, il grafo e la timeline "
                   "di questa sessione? Le sessioni salvate e l'elenco delle fidate restano."),
                tr("Pulisci"), self._do_clear, self.fonts)

    def _do_clear(self) -> None:
        self.mon.reset()
        self.alerts.reset()
        self.timeline.clear()
        self.graph.clear()
        self._dns_shown = -1
        self._alerts_shown = -1
        self._groups_by_dest, self._risk_by_dest = {}, {}
        self._links, self._link_conns = {}, {}
        self._rate_prev, self._rate_ema = {}, {}
        self._map_sel = None
        self.map.selected = None
        self.map.set_links([], 0, self.geo.available)
        for lst in self.lists.values():
            lst["tree"].delete(*lst["tree"].get_children())
            lst["rows"] = {}
        self.dns_table.tree.delete(*self.dns_table.tree.get_children())
        self.alert_table.tree.delete(*self.alert_table.tree.get_children())
        self._set_details(tr("Seleziona una riga per vedere IP, porte, protocolli, fonte del nome e ultime connessioni."))
        for _var, box in self._app_boxes.values():
            box.destroy()
        self._app_boxes = {}
        self._update_app_list({})
        self.log(tr("tutto il traffico è stato cancellato"))
        self._refresh()

    # ---------------------------------------------------------------- dettaglio IP
    def _connection_record(self, dest: str) -> dict:
        """Il dettaglio del collegamento in forma strutturata (per il salvataggio)."""
        g = self._groups_by_dest.get(dest)
        rows = [x for x in self.mon.snapshot() if self.mon.dest_label(x) == dest]
        rows.sort(key=lambda x: -x.ts)
        rk = self._risk_by_dest.get(dest)
        rep = self.rep.lookup(dest, g.ips if g else (), g.org if g else None)
        rec = {"destination": dest, "trusted": self.trust.is_trusted(dest, g.ips if g else ()),
               "ips": sorted(g.ips) if g else sorted({x.dst_ip for x in rows}),
               "ports": sorted(g.ports) if g else sorted({x.dst_port for x in rows}),
               "protocols": sorted(g.protos) if g else sorted({x.proto for x in rows}),
               "org": (g.org if g else None) or (rows[0].org if rows else None),
               "asn": rows[0].asn if rows else None, "connections": g.count if g else len(rows),
               "open": g.active if g else sum(1 for x in rows if x.closed_ts is None),
               "bytes": g.bytes if g else sum(x.bytes_in + x.bytes_out for x in rows),
               "first_seen": _t(g.first) if g else "", "last_seen": _t(g.last) if g else "",
               "apps": sorted({x.app for x in rows}), "app_labels": {a: self.mon.app_label(a) for a in {x.app for x in rows}},
               "name_sources": sorted({x.host_src for x in rows if x.host_src}),
               "risk": {"level": rk.level, "name": rk.name, "reasons": list(rk.reasons)} if rk else None,
               "reputation": {"category": rep[0], "list": rep[1]} if rep else None,
               "reverse_dns": {ip: self.rdns.get(ip) for ip in (sorted(g.ips) if g else [])},
               "device": dict(self.device_info), "session": self.session.id if self.session else None,
               "last_connections": [x.to_dict() for x in rows[:50]]}
        return rec

    def _tk_exception(self, exc, val, tb) -> None:
        """Errore non gestito in una callback: traceback sulla console e ultima riga nel registro."""
        text = "".join(traceback.format_exception(exc, val, tb))
        print(text, file=sys.stderr)
        self.log(tr("errore interno: {e}", e=_describe_error(val)), "err")

    def _find_detail_dest(self) -> tuple[str | None, object]:
        """La destinazione selezionata, con qualche tolleranza: il nome può essere cambiato nel frattempo
        (reverse DNS arrivato dopo), la selezione può venire dalla mappa, dal tab DNS o da un alert."""
        groups = self._groups_by_dest
        dest = self._details_dest
        if dest and dest in groups:
            return dest, groups[dest]
        if not groups:                                   # vista in pausa o filtro: ricalcolo senza filtro
            groups = {g.dest: g for g in self.mon.groups("dest", self.sort_mode)}
        text = self._details_text or ""
        first = text.split("\n", 1)[0].strip()
        for cand in (dest, first, first[6:] if first.startswith("[dns] ") else None):
            if cand and cand in groups:
                return cand, groups[cand]
        # per IP: quello della linea sulla mappa, poi il primo IP che compare nel testo dei dettagli
        ips = [self._details_ip] if self._details_ip else []
        ips += re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)
        for ip in ips:
            for d, g in groups.items():
                if ip in g.ips:
                    return d, g
        return None, None

    def _open_ip_detail(self) -> None:
        dest, g = self._find_detail_dest()
        if not dest or not g:
            return self.log(tr("seleziona prima una destinazione (riga, linea sulla mappa o nodo del grafo)"), "err")
        self._details_dest = dest
        if self.ipdetail_win is not None:
            try:
                self.ipdetail_win.close()
            except tk.TclError:
                pass
            self.ipdetail_win = None
        try:
            self._open_ip_detail_window(dest, g)
        except Exception as e:  # noqa: BLE001 - l'errore deve arrivare nel registro, non sparire
            traceback.print_exc()
            self.log(tr("Dettaglio IP: {e}", e=_describe_error(e)), "err")

    def _open_ip_detail_window(self, dest: str, g) -> None:
        rows = [x for x in self.mon.snapshot() if self.mon.dest_label(x) == dest]
        ips = sorted(g.ips, key=lambda ip: -sum(1 for x in rows if x.dst_ip == ip))
        if self._details_ip in ips:
            ips.remove(self._details_ip)
            ips.insert(0, self._details_ip)
        sni = next((x.host for x in rows if x.host_src in ("sni", "http", "dns", "rdns") and x.host), None)
        if not sni and not dest.startswith("[dns]") and not ipinfo.is_private(dest) and any(ch.isalpha() for ch in dest):
            sni = dest
        port = next((x.dst_port for x in rows if x.dst_port in (443, 8443)), rows[0].dst_port if rows else 443)
        names: dict[str, set] = {}
        for d in self.mon.dns:
            for a in d.get("answers", []) or []:
                if a in g.ips:
                    names.setdefault(a, set()).add(d.get("qname", ""))
        for x in rows:
            if x.host and x.host_src != "dns-query":
                names.setdefault(x.dst_ip, set()).add(x.host)
        try:
            record = self._connection_record(dest)
        except Exception as e:  # noqa: BLE001 - il dettaglio si apre comunque, senza la parte strutturata
            traceback.print_exc()
            self.log(tr("Dettaglio IP: {e}", e=_describe_error(e)), "err")
            record = {"destination": dest, "ips": sorted(g.ips)}
        self.ipdetail_win = IpDetailWindow(self, dest, record, self._details_text or dest, ips, sni, port, names)
        self.log(tr("Dettaglio IP aperto per {d}", d=dest))

    def _close_ip_detail(self) -> None:
        if self.ipdetail_win is not None:
            self.ipdetail_win.close()
            self.ipdetail_win = None

    # ---------------------------------------------------------------- schermo del telefono
    def _open_screen(self) -> None:
        """Schermo del telefono: avvia (o ferma) scrcpy nella sua finestra, esattamente come AndrOsint."""
        if self.scrcpy.running():
            self.scrcpy.stop()
            self.btn_screen.configure(text="📱  " + tr("Schermo del telefono"))
            return self.log(tr("scrcpy fermato"))
        if not self.scrcpy.available:
            self.log(tr("scrcpy non presente nella cartella tools: scaricalo con 'Scarica / aggiorna da GitHub' nel tab Config."), "err")
            return self._show_tab("config")
        if self.demo or self.adb is None:
            self.log(tr("nessun telefono collegato via adb"), "err")
            return
        self.scrcpy.adb_path = self.adb.path
        serial = self.adb.serial
        if not serial:
            try:
                self.adb.devices()
            except AdbError as e:
                return self.log(str(e), "err")
            serial = self.adb.serial
        try:
            self.scrcpy.start(serial, title=f"Android - {serial}")
        except scrcpy_mod.ScrcpyError as e:
            return self.log(str(e), "err")
        self.btn_screen.configure(text="■  " + tr("Chiudi schermo"))
        self.log(tr("scrcpy avviato per {s}", s=serial))
        self._screen_owned = False
        self.after(500, self._watch_screen)

    def _watch_screen(self) -> None:
        """Appena la finestra di scrcpy esiste la lega a quella di DroidSnex (resta sopra, mai sotto);
        poi si accorge di quando viene chiusa, e del perché."""
        if self.scrcpy.running():
            if not self._screen_owned and os.name == "nt":
                hwnd = self.scrcpy.find_window()
                if hwnd:
                    self._screen_owned = self.scrcpy.set_owner(hwnd, frameless._hwnd(self))
            return self.after(300 if not self._screen_owned else 1000, self._watch_screen)
        try:
            self.btn_screen.configure(text="📱  " + tr("Schermo del telefono"))
        except tk.TclError:
            return
        err = self.scrcpy.last_error()
        if err:
            self.log(tr("scrcpy si è chiuso") + ": " + err.splitlines()[-1][:200], "err")

    def _close_screen(self) -> None:
        self.scrcpy.stop()

    def _toggle_monitor(self) -> None:
        """Il pulsante Start / Stop: uno solo, cambia dicitura con lo stato del monitor."""
        if self.monitoring:
            self._stop()
        else:
            self._start()
        self._paint_monitor_buttons()

    def _refresh(self, force: bool = False) -> None:
        self._paint_monitor_buttons()
        if self._replay:
            self._replay_step()
        c = self.client
        if c and c.connected:
            self._status("STREAM", tr("collegato"), theme.OK)
        elif c:
            self._status("STREAM", tr("riconnessione…"), theme.WARN)
        if c and c.vpn_on is not None:
            self._status("VPN", tr("attiva") if c.vpn_on else tr("ferma"), theme.OK if c.vpn_on else theme.WARN)
            if c.connected:
                self._show_state(tr("Monitor attivo") if c.vpn_on else tr("Cattura ferma"),
                                 theme.OK if c.vpn_on else theme.WARN)
                self.mode_label.configure(text=tr("VPN LOCALE") + f"  ·  USB  ·  WATCHDOG {WATCHDOG_SEC}s"
                                          if not self.demo else "DEMO")
        elif c and not c.connected:
            self._show_state(tr("Riconnessione…"), theme.WARN)

        conns = self.mon.snapshot()
        self.c_conn.set(len(conns))
        if self.pause_var.get() and not force:      # trust/untrust passa anche a vista in pausa
            return
        groups = self.mon.groups("dest", self.sort_mode, self.search.get().strip())
        split = {"untrusted": [], "trusted": []}
        trusted_dest = {}
        for g in groups:
            t = self.trust.is_trusted(g.dest, g.ips)
            trusted_dest[g.dest] = t
            split["trusted" if t else "untrusted"].append(g)
        self.c_dest.set(len(groups))
        self.c_untrusted.set(len(split["untrusted"]))
        self.c_trusted.set(len(split["trusted"]))
        self.tabbar.set_count("untrusted", len(split["untrusted"]), theme.ERR)
        self.tabbar.set_count("trusted", len(split["trusted"]), theme.OK)
        self._groups_by_dest = {g.dest: g for g in groups}
        self._risk_by_dest = {g.dest: self._risk_of(g) for g in split["untrusted"]}
        self._update_map(conns, trusted_dest)
        self._refresh_graph(conns, trusted_dest)
        self._refresh_timeline()
        self._refresh_dns()
        self._refresh_alerts()
        self._session_autosave()

        for key, items in split.items():
            lst = self.lists[key]
            tree = lst["tree"]
            lst["count"].configure(text=str(len(items)))
            if lst["sort"]:
                col, desc = lst["sort"]
                items = sorted(items, key=self.COLUMN_KEYS[col], reverse=desc)
            sel = tree.selection()
            sel_dest = lst["rows"].get(sel[0]) if sel else None
            y = tree.yview()[0]
            self._restoring = True       # la riselezione della riga non deve rifare i dettagli
            tree.delete(*tree.get_children())
            lst["rows"] = {}
            for i, g in enumerate(items[:3000]):
                rep = self.rep.lookup(g.dest, g.ips, g.org)
                if key == "untrusted":
                    tags = [f"risk{self._risk_by_dest[g.dest].level}"]
                else:
                    tags = ["dns" if g.dest.startswith("[dns]") else "rep" if rep else "row"]
                if i % 2:
                    tags.append("odd")
                ips = ", ".join(sorted(g.ips)[:3]) + (" …" if len(g.ips) > 3 else "")
                iid = tree.insert("", "end", tags=tags, values=(
                    lst["action"], ("● " if g.active else "   ") + g.dest, ips, _ports(g), g.app, g.count,
                    _bytes(g.bytes) if g.bytes else "", _t(g.first), _t(g.last), g.org, rep[0] if rep else ""))
                lst["rows"][iid] = g.dest
                if g.dest == sel_dest:
                    tree.selection_set(iid)
            tree.yview_moveto(y)
            self._restoring = False

    # ================================================================ replay
    def _build_replay_bar(self, main) -> None:
        """Barra del replay sotto il contenuto: play/pausa, velocita', orario, cursore con i segnalibri, uscita."""
        f = self.fonts
        bar = ctk.CTkFrame(main, fg_color=theme.PANEL, corner_radius=4, border_width=1, border_color=theme.ACCENT)
        bar.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 12))
        bar.grid_remove()
        bar.grid_columnconfigure(4, weight=1)
        self.replay_bar = bar
        ctk.CTkLabel(bar, text="▶ REPLAY", font=f.caption, text_color=theme.ACCENT).grid(row=0, column=0, padx=(12, 8), pady=8)
        self.replay_play = button(bar, "▶", self._replay_toggle, primary=True, width=40, height=30)
        self.replay_play.grid(row=0, column=1, padx=(0, 4))
        button(bar, "⏮", lambda: self._replay_seek(self._replay.t0 if self._replay else 0), width=36, height=30).grid(row=0, column=2)
        self.replay_speed = ctk.CTkSegmentedButton(bar, values=[f"{x}x" for x in SPEEDS], height=28, font=f.small,
                                                   command=self._replay_set_speed, selected_color=theme.BTN,
                                                   selected_hover_color=theme.BTN_HOVER, width=150)
        self.replay_speed.set("1x")
        self.replay_speed.grid(row=0, column=3, padx=(8, 10))
        self.replay_canvas = tk.Canvas(bar, height=30, bg=theme.PANEL, highlightthickness=0, bd=0, cursor="hand2")
        self.replay_canvas.grid(row=0, column=4, sticky="ew", padx=(0, 10))
        self.replay_canvas.bind("<ButtonPress-1>", self._replay_press)
        self.replay_canvas.bind("<B1-Motion>", self._replay_drag_to)
        self.replay_canvas.bind("<ButtonRelease-1>", self._replay_release)
        self.replay_canvas.bind("<Motion>", self._replay_hover)
        self.replay_canvas.bind("<Button-3>", self._replay_open_shot)
        self.replay_canvas.bind("<Leave>", lambda _e: self._replay_paint())
        self.replay_canvas.bind("<Configure>", lambda _e: self._replay_paint())
        self.replay_time = ctk.CTkLabel(bar, text="", font=f.mono, text_color=theme.TEXT, anchor="e", width=200)
        self.replay_time.grid(row=0, column=5, padx=(0, 10))
        button(bar, "■  " + tr("Esci dal replay"), self._exit_replay, danger=True, height=30).grid(row=0, column=6, padx=(0, 10))
        self.replay_note = ctk.CTkLabel(bar, text="", font=f.small, text_color=theme.TEXT_SOFT, anchor="w", justify="left")
        self.replay_note.grid(row=1, column=0, columnspan=7, sticky="ew", padx=12, pady=(0, 6))
        self.replay_note.grid_remove()

    def _enter_replay(self, session) -> None:
        if self.monitoring:
            return self.log(tr("ferma il monitor prima di rivedere una sessione"), "err")
        if self._replay:
            self._exit_replay(quiet=True)
        rp = Replay(session, self.rdns, self.mon.asn, self.trust, self.geo, self.rep, tr, hide_dns=self.mon.hide_dns)
        if not rp.events:
            return self.log(tr("questa sessione non ha gli eventi registrati (versione precedente): non si può rivedere"), "err")
        self._live = (self.mon, self.alerts)
        self.mon, self.alerts = rp.mon, rp.alerts
        self._replay = rp
        self._reset_views()
        self.timeline.now = lambda: rp.t
        self.replay_bar.grid()
        self.replay_speed.set("1x")
        self.replay_play.configure(text="❚❚")
        rp.playing = True
        self._show_state(tr("Replay") + f"  ·  {session.id}", theme.ACCENT)
        self._status("STREAM", tr("replay"), theme.ACCENT)
        self._replay_paint()
        self.log(tr("replay della sessione {id}: {n} eventi, {d} · play", id=session.id, n=len(rp.events), d=Replay.hms(rp.duration)), "ok")
        if self.tab == "sessions":
            self._show_tab("untrusted")
        self._refresh()

    def _exit_replay(self, quiet: bool = False) -> None:
        rp = self._replay
        if not rp:
            return
        self._replay = None
        if self._live:
            self.mon, self.alerts = self._live
            self._live = None
        self.timeline.now = None
        self.replay_bar.grid_remove()
        self.replay_note.grid_remove()
        self._reset_views()
        self._show_state(tr("Monitor fermo"), theme.TEXT_FAINT)
        self._status("STREAM", "—", theme.TEXT_FAINT)
        if not quiet:
            self.log(tr("replay chiuso: di nuovo in modalità dal vivo"))
            self._refresh()

    def _reset_views(self) -> None:
        """Le viste ripartono da zero (cambio sorgente dei dati o salto indietro nel tempo)."""
        self.timeline.clear()
        self.graph.clear()
        self._graph_t = 0.0
        self._dns_shown = -1
        self._alerts_shown = -1
        self._groups_by_dest, self._risk_by_dest = {}, {}
        self._links, self._link_conns = {}, {}
        self._rate_prev, self._rate_ema = {}, {}
        self._map_sel = None
        self._map_new_since = None
        self.map.selected = None
        self.map.set_links([], 0, self.geo.available)
        for lst in self.lists.values():
            lst["tree"].delete(*lst["tree"].get_children())
            lst["rows"] = {}
        self.dns_table.tree.delete(*self.dns_table.tree.get_children())
        self.alert_table.tree.delete(*self.alert_table.tree.get_children())
        self._details_dest, self._details_ip = None, None
        self._set_details(tr("Seleziona una riga per vedere IP, porte, protocolli, fonte del nome e ultime connessioni."))
        for _var, box in self._app_boxes.values():
            box.destroy()
        self._app_boxes = {}
        self._update_app_list({})
        self._paint_new_button()

    def _replay_step(self) -> None:
        """Ogni secondo (dal _tick): avanza di un secondo reale per la velocita' scelta."""
        rp = self._replay
        if rp.playing and not self._replay_drag:
            before = rp.t
            rp.advance(1.0)
            self._replay_dt = max(0.2, rp.t - before)
            if rp.done:
                self.replay_play.configure(text="▶")
                self.log(tr("replay: fine della sessione"))
            m = rp.mark_at(rp.t, tolerance=self._replay_dt)
            if m is not None and m is not getattr(self, "_replay_last_mark", None):
                self._replay_last_mark = m
                self._replay_show_mark(m)
        for ts, per_app in rp.take_samples():
            self.timeline.add(per_app, ts)
        self._replay_paint()

    def _replay_toggle(self) -> None:
        rp = self._replay
        if not rp:
            return
        if rp.done and not rp.playing:
            self._replay_seek(rp.t0)
        rp.playing = not rp.playing
        self.replay_play.configure(text="❚❚" if rp.playing else "▶")

    def _replay_set_speed(self, value: str) -> None:
        if self._replay:
            self._replay.speed = int(value.rstrip("x"))

    def _replay_seek(self, t: float) -> None:
        rp = self._replay
        if not rp:
            return
        backwards = t < rp.t
        rp.seek(t)
        if backwards:
            self._reset_views()
        else:
            self.timeline.clear()
        for ts, per_app in rp.samples:
            self.timeline.add(per_app, ts)
        self._replay_last_mark = None
        self._replay_paint()
        self._refresh()

    # --- cursore
    def _replay_geom(self) -> tuple[int, int, int]:
        w = max(50, self.replay_canvas.winfo_width())
        return 10, w - 10, 15                     # x sinistra, x destra, y della traccia

    def _replay_x_to_t(self, x: int) -> float:
        rp = self._replay
        x0, x1, _y = self._replay_geom()
        frac = min(1.0, max(0.0, (x - x0) / max(1, x1 - x0)))
        return rp.t0 + frac * rp.duration

    def _replay_t_to_x(self, t: float) -> int:
        rp = self._replay
        x0, x1, _y = self._replay_geom()
        return int(x0 + (x1 - x0) * min(1.0, max(0.0, (t - rp.t0) / max(1e-6, rp.duration))))

    def _replay_press(self, e) -> None:
        if not self._replay:
            return
        self._replay_drag = True
        m = self._replay_mark_near(e.x)
        if m is not None:
            self._replay_show_mark(m)
            self._replay_last_mark = m
            self._replay_seek(m["ts"])
        else:
            self._replay_seek(self._replay_x_to_t(e.x))

    def _replay_drag_to(self, e) -> None:
        if self._replay and self._replay_drag:
            self._replay_seek(self._replay_x_to_t(e.x))

    def _replay_release(self, _e) -> None:
        self._replay_drag = False

    def _replay_mark_near(self, x: int) -> dict | None:
        rp = self._replay
        for m in rp.marks:
            if abs(self._replay_t_to_x(m.get("ts", 0)) - x) <= 6:
                return m
        return None

    def _replay_hover(self, e) -> None:
        if not self._replay:
            return
        m = self._replay_mark_near(e.x)
        self._replay_paint(hover_t=self._replay_x_to_t(e.x), hover_mark=m)

    def _replay_show_mark(self, m: dict) -> None:
        rp = self._replay
        note = m.get("note") or "-"
        text = f"🔖 {Replay.clock(m.get('ts', 0))}  ·  {note}"
        if m.get("shot"):
            text += "  ·  📷 " + tr("screenshot: clic sul segnalibro con il tasto destro per aprirlo")
        self.replay_note.configure(text=text)
        self.replay_note.grid()
        lines = [tr("SEGNALIBRO"), Replay.clock(m.get("ts", 0)), "", note]
        if m.get("shot"):
            lines += ["", "📷 " + os.path.join(self.sessions.device_dir(rp.session.device), m["shot"])]
        self._set_details("\n".join(lines))
        self.log(f"🔖 {Replay.clock(m.get('ts', 0))}  {note}")

    def _replay_open_shot(self, e) -> None:
        m = self._replay_mark_near(e.x) if self._replay else None
        if m and m.get("shot"):
            self._open_dir(os.path.join(self.sessions.device_dir(self._replay.session.device), m["shot"]))

    def _replay_paint(self, hover_t: float | None = None, hover_mark: dict | None = None) -> None:
        rp = self._replay
        c = self.replay_canvas
        if not rp or not c.winfo_exists():
            return
        c.delete("all")
        x0, x1, y = self._replay_geom()
        xt = self._replay_t_to_x(rp.t)
        c.create_line(x0, y, x1, y, fill=theme.BORDER, width=4, capstyle="round")
        c.create_line(x0, y, xt, y, fill=theme.ACCENT, width=4, capstyle="round")
        for m in rp.marks:
            mx = self._replay_t_to_x(m.get("ts", 0))
            col = theme.WARN if m is hover_mark else theme.OK
            c.create_polygon(mx - 5, y + 11, mx + 5, y + 11, mx, y + 4, fill=col, outline="")
        c.create_oval(xt - 6, y - 6, xt + 6, y + 6, fill=theme.TEXT, outline=theme.ACCENT, width=2)
        if hover_t is not None:
            hx = self._replay_t_to_x(hover_t)
            label = Replay.clock(hover_t) + (f"  🔖 {hover_mark.get('note') or ''}" if hover_mark else "")
            c.create_text(min(max(hx, x0 + 40), x1 - 40), y - 11, text=label, fill=theme.TEXT_SOFT,
                          font=(theme.mono_font(), 9), anchor="s")
        self.replay_time.configure(text=f"{Replay.clock(rp.t)}  ·  {Replay.hms(rp.t - rp.t0)} / {Replay.hms(rp.duration)}")

    def _risk_of(self, g) -> risk.Risk:
        """Pericolosità di una destinazione non fidata (vedi risk.py)."""
        countries = []
        if self.geo.available:
            for ip in list(g.ips)[:8]:
                pl = self.geo.lookup(ip)
                countries.append(pl.country if pl else "")
        return risk.assess(g.dest, g.ips, g.org, g.ports, self.rep.lookup(g.dest, g.ips, g.org), countries,
                           self.settings.home_country)

    def _risk_lines(self, dest: str) -> list[str]:
        r = self._risk_by_dest.get(dest)
        if r is None:
            return []
        why = [tr(risk.REASONS[k]) for k in r.reasons] or [tr("nessun segnale sospetto")]
        return [_kv(tr("rischio"), f"{tr(r.name)} ({r.level}/5)")] + [f"  · {w}" for w in why]

    # ================================================================ mappa
    def _update_map(self, conns, trusted_dest: dict) -> None:
        """Una linea per ogni IP di destinazione (nella sua città), con la velocità (byte/s) di ognuna."""
        now = time.monotonic()
        dt = self._replay_dt if self._replay else max(0.2, now - self._rate_t)
        self._rate_t = now
        links: dict[str, Link] = {}
        dests_at: dict[str, dict[str, int]] = {}
        unlocated: set[str] = set()
        totals: dict[str, list[int]] = {}
        apps_at: dict[str, set] = {}
        link_conns: dict[str, list] = {}
        per_app: dict[str, int] = {}
        for c in conns:
            if self.mon.hide_dns and c.dst_port == 53:
                continue
            dest = self.mon.dest_label(c)
            if dest not in trusted_dest:          # escluso dal filtro di ricerca
                continue
            trusted = trusted_dest[dest]
            if self._map_trust == "t" and not trusted or self._map_trust == "u" and trusted:
                continue                          # filtro fidate / non fidate
            if self._map_new_since is not None and c.key in self._map_new_since:
                continue                          # "solo nuove": già vista quando è stato premuto
            per_app[c.app] = per_app.get(c.app, 0) + 1
            if not self._app_shown(c.app):        # app nascosta dall'elenco
                continue
            place = self.geo.lookup(c.dst_ip)
            if place is None:
                unlocated.add(dest)
                continue
            trusted = trusted_dest[dest]
            key = f"{place.lat:.2f},{place.lon:.2f}|{c.dst_ip}|{'t' if trusted else 'u'}"
            link = links.get(key)
            if link is None:
                link = links[key] = Link(key, place.lat, place.lon, place.name, trusted, c.dst_ip, country=place.country)
                dests_at[key] = {}
                totals[key] = [0, 0]
                apps_at[key] = set()
                link_conns[key] = []
            link_conns[key].append(c)
            apps_at[key].add(c.app)
            link.conns += 1
            if not trusted:
                rk = self._risk_by_dest.get(dest)
                if rk and rk.level > link.risk:
                    link.risk, link.risk_text = rk.level, tr(rk.name) + " · " + ", ".join(tr(risk.REASONS[k]) for k in rk.reasons)
            if c.closed_ts is None:
                link.active += 1
            link.total += c.bytes_in + c.bytes_out
            totals[key][0] += c.bytes_out
            totals[key][1] += c.bytes_in
            dests_at[key][dest] = dests_at[key].get(dest, 0) + 1
        rate_out = rate_in = 0.0
        for key, link in links.items():
            link.dests = [d for d, _n in sorted(dests_at[key].items(), key=lambda kv: -kv[1])]
            link.apps = sorted(apps_at[key])
            out, inn = totals[key]
            p_out, p_in = self._rate_prev.get(key, (out, inn))
            r_out, r_in = max(0, out - p_out) / dt, max(0, inn - p_in) / dt
            e_out, e_in = self._rate_ema.get(key, (0.0, 0.0))
            # media mobile: il flusso non "sfarfalla" a ogni aggiornamento
            e_out, e_in = e_out * 0.4 + r_out * 0.6, e_in * 0.4 + r_in * 0.6
            if e_out < 1:
                e_out = 0.0
            if e_in < 1:
                e_in = 0.0
            self._rate_ema[key] = (e_out, e_in)
            self._rate_prev[key] = (out, inn)
            link.rate_out, link.rate_in = e_out, e_in
            rate_out += e_out
            rate_in += e_in
        self.c_rate.set(f"↑{_rate(rate_out)[:-2]} ↓{_rate(rate_in)[:-2]}")
        self._links = links
        self._link_conns = link_conns
        self._update_app_list(per_app)
        self.tabbar.set_count("map", len(links), theme.TEXT_DIM)
        self.map.set_links(list(links.values()), len(unlocated), self.geo.available)
        if per_app and not any(self._app_shown(a) for a in per_app):
            self.map.set_note(tr("Tutte le app sono nascoste: scegline una o più nell'elenco a destra."))
        elif self._map_new_since is not None and not links:
            self.map.set_note(tr("Solo connessioni nuove: nessuna dalle {t}, in attesa…", t=self._map_new_t))
        if (self.tab == "map" or self._floating.get("map")) and self._map_sel in links:
            self._show_map_details(links[self._map_sel])

    def _on_map_select(self, link: Link | None) -> None:
        self._map_sel = link.key if link else None
        if link:                             # la linea cliccata vince sulla riga selezionata in tabella
            self._restoring = True
            for lst in self.lists.values():
                lst["tree"].selection_remove(*lst["tree"].selection())
            self._restoring = False
        if link:
            self._show_map_details(link)

    def _show_map_details(self, link: Link) -> None:
        lines = [link.place, tr("FIDATA") if link.trusted else tr("NON FIDATA"), "",
                 _kv("IP", link.ip), _kv(tr("posizione"), f"{link.lat:.3f}, {link.lon:.3f}"),
                 _kv(tr("connessioni"), f"{link.conns}  ({tr('aperte')} {link.active})"),
                 _kv(tr("traffico"), _bytes(link.total)),
                 _kv(tr("uscita") + " ↑", _rate(link.rate_out)), _kv(tr("entrata") + " ↓", _rate(link.rate_in)), "",
                 f"APP ({len(link.apps)})"] + [f"  {a}" for a in link.apps] + ["",
                 f"{tr('DESTINAZIONI')} ({len(link.dests)})"]
        for d in link.dests[:40]:
            g = self._groups_by_dest.get(d)
            lines.append(f"  {d}")
            if g:
                lines.append(f"     {g.count} conn · {_bytes(g.bytes)} · {', '.join(sorted(g.ips)[:2])}")
        conns = sorted(getattr(self, "_link_conns", {}).get(link.key, []), key=lambda x: -x.ts)
        lines += ["", f"{tr('CONNESSIONI SU QUESTA LINEA')} ({len(conns)})"]
        for x in conns[:30]:
            st = tr("aperta") if x.closed_ts is None else tr("chiusa")
            lines.append(f"{_t(x.ts)} {x.proto} {x.dst_ip}:{x.dst_port} {st}")
            lines.append(f"   {self.mon.dest_label(x)}")
            lines.append(f"   {x.app} · ↑{_bytes(x.bytes_out)} ↓{_bytes(x.bytes_in)}" + (f" ⚠ {x.error}" if x.error else ""))
        # la linea è una destinazione valida per il Dettaglio IP: la prima destinazione nota, con l'IP della linea
        self._details_dest = next((d for d in link.dests if d in self._groups_by_dest), None)
        self._details_ip = link.ip
        self._set_details("\n".join(lines))

    def _on_click(self, key: str, event) -> None:
        """Clic sulla colonna TRUST / UNTRUST: sposta la destinazione nell'altra lista."""
        tree = self.lists[key]["tree"]
        if tree.identify_region(event.x, event.y) != "cell" or tree.identify_column(event.x) != "#1":
            return
        iid = tree.identify_row(event.y)
        dest = self.lists[key]["rows"].get(iid)
        g = self._groups_by_dest.get(dest)
        if not g:
            return
        if key == "untrusted":
            self.trust.trust(g.dest, g.ips)
            self.log(tr("fidata: {d}", d=g.dest), "ok")
        else:
            self.trust.untrust(g.dest, g.ips)
            self.log(tr("non più fidata: {d}", d=g.dest))
        self._refresh(force=True)

    def _untrust_all(self) -> None:
        """Pulsante nel tab Trusted: riporta tutte le destinazioni fidate tra le non fidate, dopo conferma."""
        n = len(self.trust)
        if not n:
            self.log(tr("nessuna destinazione fidata"))
            return

        def do() -> None:
            k = self.trust.clear()
            self.log(tr("tolte tutte le destinazioni fidate ({n})", n=k))
            self._refresh(force=True)

        confirm(self, tr("Untrust tutti"),
                tr("Riportare tutte le {n} destinazioni fidate tra le non fidate? L'elenco salvato in trusted.json "
                   "viene svuotato e non si può annullare.", n=n),
                tr("Untrust tutti"), do, self.fonts, cancel_text=tr("Annulla"))

    def _on_select(self, key: str) -> None:
        if getattr(self, "_restoring", False) or not self.lists[key]["tree"].selection():
            return
        self._map_sel = None                 # la riga scelta in tabella vince sulla linea della mappa
        self.map.selected = None
        other = self.lists["trusted" if key == "untrusted" else "untrusted"]["tree"]
        if self.lists[key]["tree"].selection() and other.selection():
            other.selection_remove(*other.selection())
        self._show_details(key)

    def _show_details(self, key: str = "untrusted") -> None:
        lst = self.lists[key]
        sel = lst["tree"].selection()
        dest = lst["rows"].get(sel[0]) if sel else None
        g = self._groups_by_dest.get(dest)
        if not g:
            return
        self._details_dest, self._details_ip = dest, None
        rows = [x for x in self.mon.snapshot() if self.mon.dest_label(x) == dest]
        rows.sort(key=lambda x: -x.ts)
        trusted = self.trust.is_trusted(g.dest, g.ips)
        lines = [dest, tr("FIDATA") if trusted else tr("NON FIDATA"), ""] + self._risk_lines(dest) + [
                 _kv(tr("connessioni"), f"{g.count}  ({tr('aperte')} {g.active})"), _kv(tr("traffico"), _bytes(g.bytes)),
                 _kv(tr("protocolli"), ", ".join(sorted(g.protos))),
                 _kv(tr("porte"), ", ".join(str(p) for p in sorted(g.ports))),
                 _kv("org", g.org or "-"), "", tr("IP RISOLTI")]
        for ip in sorted(g.ips)[:20]:
            rd = self.rdns.get(ip)
            lines.append(f"  {ip}" + (f"  →  {rd}" if rd and rd != dest else ""))
        srcs = sorted({x.host_src for x in rows if x.host_src})
        lines += ["", _kv(tr("nome da"), ", ".join(srcs) or tr("solo IP")), "", "APP"]
        lines += [f"  {a}" for a in sorted({x.app for x in rows})]
        lines += ["", tr("ULTIME CONNESSIONI")]
        for x in rows[:25]:
            st = tr("aperta") if x.closed_ts is None else _bytes(x.bytes_in + x.bytes_out)
            lines.append(f"{_t(x.ts)} {x.proto} {x.dst_ip}:{x.dst_port} {st}" + (f" ⚠ {x.error}" if x.error else ""))
            lines.append(f"         {x.app}")
        self._set_details("\n".join(lines))

    def _atexit(self) -> None:
        if self.monitoring and not self._cleanup_done and not self.demo:
            try:
                self._cleanup_phone()
            except Exception:  # noqa: BLE001
                pass

    def _on_close(self) -> None:
        """Chiusura: ferma e disinstalla l'agent dal telefono prima di uscire."""
        self._close_screen()
        self._close_ip_detail()
        self._stop_stream()
        if self.monitoring and not self.demo:
            self._show_state(tr("Pulizia del telefono…"), theme.WARN)
            self.update_idletasks()
            t = threading.Thread(target=self._cleanup_phone, daemon=True)
            t.start()
            t.join(12)
        self.monitoring = False
        try:
            self._session_end(wait=True)
        except Exception:  # noqa: BLE001
            pass
        self.rdns.shutdown()
        self.mon.close()
        self.destroy()

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DroidSnex GUI")
    ap.add_argument("--demo", metavar="HOST:PORT", help="collegati a un agent (es. tools/fake_agent.py) senza adb")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help="porta locale per adb forward")
    ap.add_argument("--asn-db", help="db ASN locale (ip2asn-*.tsv[.gz] o .mmdb)")
    ap.add_argument("--out", help="cartella per export e log")
    a = ap.parse_args(argv)
    App(demo=a.demo, port=a.port, asn_db=a.asn_db, out_dir=a.out).mainloop()
    return 0
