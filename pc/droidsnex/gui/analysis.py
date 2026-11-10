"""Le schede di analisi della GUI: Grafo, Timeline, DNS, Alert, Sessioni, profilo app,
più i riquadri di Config per il database ASN e le liste di reputazione.

È un mixin di App (gui/app.py): qui ci sono solo i pezzi nuovi, App li chiama nei
punti giusti (costruzione, cambio scheda, aggiornamento ogni secondo, Start/Stop).
"""
from __future__ import annotations

import base64
import io
import os
import threading
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageTk

from .. import report, reputation, risk
from ..alerts import AlertEngine
from ..geo import DBIP_ASN_FILE, DBIP_ASN_URL, download_dbip
from ..i18n import language, tr
from ..resolve import AsnDb
from ..sessions import Session, SessionStore, compare, device_title
from ..ui import _bytes, _t
from . import theme
from .graphview import KIND_COLOR, KIND_SIZE, Edge, GraphView, Node
from .timeline import TimelineView
from .widgets import Card, Table, button, caption, confirm

ANALYSIS_TABS = (("graph", "Grafo"), ("timeline", "Timeline"), ("dns", "DNS"), ("alerts", "Alert"),
                 ("sessions", "Sessioni"))
DANGEROUS = ("CAMERA", "RECORD_AUDIO", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "ACCESS_BACKGROUND_LOCATION",
             "READ_CONTACTS", "WRITE_CONTACTS", "READ_SMS", "SEND_SMS", "RECEIVE_SMS", "READ_CALL_LOG", "READ_PHONE_STATE",
             "READ_PHONE_NUMBERS", "CALL_PHONE", "BODY_SENSORS", "READ_CALENDAR", "READ_EXTERNAL_STORAGE",
             "READ_MEDIA_IMAGES", "READ_MEDIA_VIDEO", "READ_MEDIA_AUDIO", "BLUETOOTH_CONNECT", "BLUETOOTH_SCAN",
             "NEARBY_WIFI_DEVICES", "SYSTEM_ALERT_WINDOW", "BIND_ACCESSIBILITY_SERVICE", "PACKAGE_USAGE_STATS",
             "QUERY_ALL_PACKAGES", "REQUEST_INSTALL_PACKAGES")
ALERT_KIND_NAMES = {"new_untrusted": "nuova destinazione", "new_country": "nuovo paese", "odd_port": "porta insolita",
                    "reputation": "reputazione", "doh": "DNS cifrato", "anon": "Tor / VPN"}
LEVEL_COLOR = {"info": theme.TEXT_SOFT, "warn": theme.WARN, "err": theme.ERR}


class AnalysisMixin:
    """Metodi aggiunti ad App. Usa: self.mon, self.trust, self.geo, self.fonts, self.pages_box, self.tabbar,
    self.log, self._ui, self._job, DATA_DIR/SESSIONS_DIR (attributi di modulo di app.py passati nel costruttore)."""

    # ================================================================ inizializzazione
    def _init_analysis(self, data_dir: str, sessions_dir: str) -> None:
        self.data_dir = data_dir
        self.rep = reputation.Reputation(data_dir)
        self.alerts = AlertEngine(self.trust, self.geo, self.rep, tr)
        self.mon.on_conn = self._on_conn_alert
        self.mon.on_app = self._on_app_info
        self.sessions = SessionStore(sessions_dir)
        self.session: Session | None = None
        self.device_info: dict = {}
        self._session_saved = 0.0
        self._graph_t = 0.0
        self._graph_flow: tuple[dict, dict] = ({}, {})
        self._dns_shown = 0
        self._alerts_shown = 0
        self._icons: dict[tuple, ImageTk.PhotoImage] = {}
        self._graph_sel: str | None = None
        self._sess_sel: list[str] = []
        if self.rep.available:
            self.log(tr("liste di reputazione: {d}", d=self.rep.describe()))

    def _asn_path(self) -> str:
        return os.path.join(self.data_dir, DBIP_ASN_FILE)

    # ================================================================ costruzione schede
    def _build_analysis_pages(self) -> None:
        f = self.fonts
        # --- grafo
        frame = ctk.CTkFrame(self.pages_box, fg_color=theme.PANEL, corner_radius=4, border_width=1,
                             border_color=theme.BORDER)
        self.graph = GraphView(frame, f, on_select=self._on_graph_select, on_open=self._on_graph_open)
        self.graph.pack(fill="both", expand=True, padx=1, pady=1)
        self.graph.detach_btn = self.graph.add_tool("⧉", lambda: self._toggle_float("graph"))
        self.pages["graph"] = frame
        # --- timeline
        frame = ctk.CTkFrame(self.pages_box, fg_color=theme.PANEL, corner_radius=4, border_width=1,
                             border_color=theme.BORDER)
        self.timeline = TimelineView(frame, f, label_of=self.mon.app_label)
        self.timeline.pack(fill="both", expand=True, padx=1, pady=1)
        self.pages["timeline"] = frame
        # --- DNS
        card = Card(self.pages_box, tr("Query DNS"), f)
        self.dns_count = ctk.CTkLabel(card.head, text="0", font=f.title, text_color=theme.ACCENT)
        self.dns_count.pack(side="left", padx=(8, 0))
        self.dns_note = ctk.CTkLabel(card.head, text="", font=f.small, text_color=theme.TEXT_DIM)
        self.dns_note.pack(side="right")
        card.body.grid_columnconfigure(0, weight=1)
        card.body.grid_rowconfigure(1, weight=1)
        self.doh_label = ctk.CTkLabel(card.body, text="", font=f.small, text_color=theme.WARN, anchor="w", justify="left")
        self.doh_label.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        cols = [("time", tr("Ora"), 62, False, "center"), ("app", "App", 150, True, "w"), ("qname", tr("Dominio"), 220, True, "w"),
                ("qtype", tr("Tipo"), 50, False, "center"), ("answers", tr("Risposte"), 200, True, "w"),
                ("cname", "CNAME", 150, True, "w"), ("server", "Server", 100, False, "w"),
                ("rcode", tr("Esito"), 70, False, "center"), ("rtt", "ms", 44, False, "e"), ("rep", tr("Rep."), 70, False, "w")]
        self.dns_table = Table(card.body, cols, tags={"row": theme.TEXT, "err": theme.ERR, "warn": theme.WARN,
                                                      "odd": theme.TEXT})
        self.dns_table.grid(row=1, column=0, sticky="nsew")
        self.dns_table.tree.bind("<<TreeviewSelect>>", lambda _e: self._dns_details())
        self.pages["dns"] = card
        # --- alert
        card = Card(self.pages_box, "Alert", f)
        self.alert_count = ctk.CTkLabel(card.head, text="0", font=f.title, text_color=theme.WARN)
        self.alert_count.pack(side="left", padx=(8, 0))
        ctk.CTkButton(card.head, text=tr("Svuota"), height=20, width=0, corner_radius=3, fg_color="transparent",
                      border_width=1, border_color=theme.BORDER_STRONG, hover_color=theme.HOVER, text_color=theme.TEXT_SOFT,
                      font=f.small, command=self._clear_alerts).pack(side="right", padx=(10, 0))
        ctk.CTkLabel(card.head, text=tr("nuove destinazioni non fidate · nuovi paesi · porte insolite · tracker/malware · Tor/VPN · DNS cifrato"),
                     font=f.small, text_color=theme.TEXT_DIM).pack(side="right")
        card.body.grid_columnconfigure(0, weight=1)
        card.body.grid_rowconfigure(0, weight=1)
        cols = [("time", tr("Ora"), 62, False, "center"), ("level", "", 24, False, "center"),
                ("kind", tr("Tipo"), 120, False, "w"), ("app", "App", 150, True, "w"),
                ("dest", tr("Destinazione"), 220, True, "w"), ("ip", "IP", 120, False, "w"),
                ("port", tr("Porta"), 50, False, "e"), ("text", tr("Dettaglio"), 320, True, "w")]
        self.alert_table = Table(card.body, cols, tags={"info": theme.TEXT_SOFT, "warn": theme.WARN, "err": theme.ERR})
        self.alert_table.grid(row=0, column=0, sticky="nsew")
        self.alert_table.tree.bind("<<TreeviewSelect>>", lambda _e: self._alert_details())
        self.pages["alerts"] = card
        # --- sessioni
        self.pages["sessions"] = self._build_sessions_page()

    # ================================================================ config
    def _build_analysis_config(self, page, note, row: int) -> int:
        f = self.fonts
        asn = Card(page, tr("Organizzazioni degli IP") + " · DB-IP ASN Lite", f)
        asn.grid(row=row, column=0, sticky="nsew", padx=(0, theme.GAP // 2), pady=(0, theme.GAP))
        b = asn.body
        b.grid_columnconfigure(0, weight=1)
        note(b, tr("Associa ogni IP al suo sistema autonomo (ASN) e all'organizzazione che lo gestisce: Google, Meta, "
                   "Amazon, un hoster sconosciuto… È la base del tab Grafo. Database gratuito di db-ip.com "
                   "(CC BY 4.0, mensile, ~8 MB). Va bene anche un GeoLite2-ASN.mmdb o un ip2asn-combined.tsv.gz "
                   "copiato in pc/data.")).grid(row=0, column=0, sticky="ew")
        self.asn_status = ctk.CTkLabel(b, text="", font=f.mono, text_color=theme.TEXT_SOFT, anchor="w", justify="left")
        self.asn_status.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.asn_bar = ctk.CTkProgressBar(b, height=6)
        self.asn_bar.set(0)
        self.asn_bar.grid(row=2, column=0, sticky="ew", pady=4)
        r = ctk.CTkFrame(b, fg_color="transparent")
        r.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        button(r, tr("Scarica / aggiorna"), lambda: self._job("asn", self._download_asn), primary=True).pack(side="left")
        button(r, tr("Interrompi"), lambda: self._cancel.__setitem__("asn", True), danger=True).pack(side="left", padx=(8, 0))

        rep = Card(page, tr("Liste di reputazione") + " · tracker e malware", f)
        rep.grid(row=row, column=1, sticky="nsew", padx=(theme.GAP // 2, 0), pady=(0, theme.GAP))
        b = rep.body
        b.grid_columnconfigure(0, weight=1)
        names = "  ·  ".join(f"{lst.name} ({lst.license})" for lst in reputation.LISTS)
        note(b, tr("Blocklist pubbliche confrontate con domini e IP contattati: le destinazioni in lista hanno il badge "
                   "'tracker', 'malware' o 'tor' nelle tabelle e generano un alert. Le VPN vengono riconosciute dal nome "
                   "dell'organizzazione nel db ASN (badge 'vpn', indicativo). Si scaricano solo da qui (mai in "
                   "automatico) in pc/data/reputation. Liste: {names}", names=names)).grid(row=0, column=0, sticky="ew")
        self.rep_status = ctk.CTkLabel(b, text="", font=f.mono, text_color=theme.TEXT_SOFT, anchor="w", justify="left")
        self.rep_status.grid(row=1, column=0, sticky="ew", pady=(8, 4))
        self.rep_bar = ctk.CTkProgressBar(b, height=6)
        self.rep_bar.set(0)
        self.rep_bar.grid(row=2, column=0, sticky="ew", pady=4)
        r = ctk.CTkFrame(b, fg_color="transparent")
        r.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        button(r, tr("Scarica / aggiorna liste"), lambda: self._job("rep", self._download_rep), primary=True).pack(side="left")
        button(r, tr("Interrompi"), lambda: self._cancel.__setitem__("rep", True), danger=True).pack(side="left", padx=(8, 0))
        self._cancel.setdefault("asn", False)
        self._cancel.setdefault("rep", False)
        return row + 1

    def _analysis_config_status(self) -> None:
        err = getattr(self, "_job_error", {})
        if "asn" not in self._jobs:
            db = self.mon.asn
            if "asn" in err:
                self.asn_status.configure(text=tr("errore: {e}", e=err["asn"]), text_color=theme.ERR)
                self.asn_bar.set(0)
            elif db.available:
                self.asn_status.configure(text=f"{os.path.basename(db.path)}  ·  " + tr("pronto"), text_color=theme.OK)
            else:
                self.asn_status.configure(text=tr("non presente") + (f"  ({db.error})" if db.error else ""), text_color=theme.WARN)
        if "rep" not in self._jobs:
            if "rep" in err:
                self.rep_status.configure(text=tr("errore: {e}", e=err["rep"]), text_color=theme.ERR)
                self.rep_bar.set(0)
            elif self.rep.available:
                self.rep_status.configure(text=self.rep.describe(), text_color=theme.OK)
            else:
                self.rep_status.configure(text=tr("non presenti"), text_color=theme.WARN)

    def _download_asn(self) -> None:
        self.log(tr("download di DB-IP ASN Lite…"))
        self._ui(self.asn_status.configure, text=tr("download…"), text_color=theme.ACCENT)

        def progress(done, total):
            self._ui(self.asn_bar.set, done / total if total else 0)
            self._ui(self.asn_status.configure, text=f"{done / 1e6:.1f} / {total / 1e6:.1f} MB" if total else f"{done / 1e6:.1f} MB")
        # su Windows il file in uso non si può sostituire: si chiude il db attuale prima del download
        old = self.mon.asn
        old_path = old.path if old.available else None
        with self.mon.lock:
            self.mon.asn = AsnDb(None)
        old.close()
        try:
            path = download_dbip(self.data_dir, progress, lambda: self._cancel["asn"], url_template=DBIP_ASN_URL,
                                 filename=DBIP_ASN_FILE)
        except BaseException:
            if old_path and os.path.isfile(old_path):
                self._use_asn(old_path)             # download fallito: si riapre quello di prima
            raise
        self._ui(self.asn_bar.set, 1)
        self._use_asn(path)
        self.log(tr("database ASN pronto: {d}", d=os.path.basename(path)), "ok")

    def _use_asn(self, path: str) -> None:
        db = AsnDb(path)
        with self.mon.lock:
            self.mon.asn = db
            for c in self.mon.conns.values():
                a = db.lookup(c.dst_ip)
                if a:
                    c.asn, c.org = a

    def _download_rep(self) -> None:
        self.log(tr("download delle liste di reputazione…"))
        self._ui(self.rep_status.configure, text=tr("download…"), text_color=theme.ACCENT)

        def progress(name, done, total):
            self._ui(self.rep_bar.set, done / total if total else 0.5)
            self._ui(self.rep_status.configure, text=f"{name}: {done / 1e6:.1f} MB")
        partial = None
        try:
            reputation.download(self.data_dir, progress, lambda: self._cancel["rep"])
        except reputation.PartialDownload as e:
            partial = e
        self._ui(self.rep_bar.set, 1)
        self.rep.load(self.data_dir)
        self.alerts.seen_rep.clear()
        for c in self.mon.snapshot():                 # rivaluta quello che c'è già
            self._on_conn_alert(c, False)
        if self.rep.describe():
            self.log(tr("liste di reputazione: {d}", d=self.rep.describe()), "ok")
        if partial:
            raise OSError(tr("liste non scaricate") + " → " + str(partial))

    # ================================================================ alert
    def _on_conn_alert(self, c, first: bool) -> None:
        dest = self.mon.dest_label(c)
        new = self.alerts.check(c, dest, first)
        for a in new:
            if a.level != "info":                 # le nuove destinazioni sono tante: solo nel tab Alert
                self._ui(self.log, f"⚠ {tr(ALERT_KIND_NAMES[a.kind])}: {a.dest} ({self.mon.app_label(a.app)}) · {a.text}",
                         "err" if a.level == "err" else "")

    def _clear_alerts(self) -> None:
        self.alerts.items.clear()
        self.alerts.unread = 0
        self._alerts_shown = -1

    def _refresh_alerts(self) -> None:
        items = self.alerts.items
        self.tabbar.set_count("alerts", len(items), theme.ERR if self.alerts.counts["err"] else
                              theme.WARN if self.alerts.counts["warn"] else theme.TEXT_DIM)
        self.alert_count.configure(text=str(len(items)))
        if self.tab != "alerts" or len(items) == self._alerts_shown:
            return
        tree = self.alert_table.tree
        sel = tree.selection()
        tree.delete(*tree.get_children())
        for a in reversed(items[-2000:]):
            tree.insert("", "end", tags=[a.level], values=(
                _t(a.ts), {"info": "·", "warn": "▲", "err": "✖"}[a.level], tr(ALERT_KIND_NAMES[a.kind]),
                self.mon.app_label(a.app), a.dest, a.ip, a.port, a.text))
        self._alerts_shown = len(items)
        self.alerts.unread = 0
        if sel:
            try:
                tree.selection_set(sel)
            except tk.TclError:
                pass

    def _alert_details(self) -> None:
        tree = self.alert_table.tree
        sel = tree.selection()
        if not sel:
            return
        v = tree.item(sel[0], "values")
        dest = v[4]
        self._select_dest_details(dest, v[7])

    def _select_dest_details(self, dest: str, extra: str = "") -> None:
        """Dettagli di una destinazione (come dal tab Untrusted) + una riga in più."""
        g = self._groups_by_dest.get(dest)
        if not g:
            return self._set_details(f"{dest}\n{extra}")
        self._details_dest, self._details_ip = dest, None
        rows = [x for x in self.mon.snapshot() if self.mon.dest_label(x) == dest]
        rows.sort(key=lambda x: -x.ts)
        lines = [dest, extra, "", f"{tr('connessioni'):<13}{g.count}", f"{tr('traffico'):<13}{_bytes(g.bytes)}",
                 f"{'org':<13}{g.org or '-'}", "", "APP"] + [f"  {self.mon.app_label(a)}" for a in sorted({x.app for x in rows})]
        rep = self.rep.lookup(dest, g.ips, g.org)
        if rep:
            lines[2:2] = [f"{tr('reputazione'):<13}{rep[0]} ({rep[1]})"]
        lines[2:2] = self._risk_lines(dest)
        lines += ["", tr("ULTIME CONNESSIONI")]
        for x in rows[:20]:
            lines.append(f"{_t(x.ts)} {x.proto} {x.dst_ip}:{x.dst_port}  {self.mon.app_label(x.app)}")
        self._set_details("\n".join(lines))

    # ================================================================ DNS
    def _refresh_dns(self) -> None:
        n = len(self.mon.dns)
        self.tabbar.set_count("dns", n, theme.TEXT_DIM)
        if self.tab != "dns":
            return
        self.dns_count.configure(text=str(n))
        doh = sorted({(a.app, a.dest) for a in self.alerts.items if a.kind == "doh"})
        if doh:
            self.doh_label.configure(text="⚠ " + tr("DNS cifrato rilevato (DoH/DoT): queste app risolvono i nomi fuori dal DNS di sistema e qui non compaiono") + "\n   "
                                     + "  ·  ".join(f"{self.mon.app_label(a)} → {d}" for a, d in doh[:6]))
        else:
            self.doh_label.configure(text="")
        servers = ", ".join(sorted(self.mon.dns_servers)[:3])
        self.dns_note.configure(text=(tr("server") + f": {servers}") if servers else "")
        if n == self._dns_shown:
            return
        tree = self.dns_table.tree
        filt = self.search.get().strip().lower()
        y = tree.yview()[0]
        tree.delete(*tree.get_children())
        shown = 0
        for d in reversed(self.mon.dns):
            if filt and filt not in d.get("qname", "").lower() and filt not in d.get("app", "").lower():
                continue
            rep = self.rep.lookup(d.get("qname"))
            rcode = d.get("rcode", 0)
            tag = "err" if rcode else ("warn" if rep else "row")
            esito = {0: "OK", 2: "SERVFAIL", 3: "NXDOMAIN", 5: "REFUSED"}.get(rcode, f"rcode {rcode}")
            tree.insert("", "end", tags=[tag], values=(
                _t(d.get("ts", 0)), self.mon.app_label(d.get("app", "?")), d.get("qname", ""), d.get("qtype", ""),
                ", ".join(d.get("answers") or [])[:80], ", ".join(d.get("cnames") or [])[:60], d.get("server", ""),
                esito, d.get("rtt_ms", "") if d.get("rtt_ms", -1) >= 0 else "", rep[0] if rep else ""))
            shown += 1
            if shown >= 3000:
                break
        tree.yview_moveto(y)
        self._dns_shown = n

    def _dns_details(self) -> None:
        tree = self.dns_table.tree
        sel = tree.selection()
        if not sel:
            return
        v = tree.item(sel[0], "values")
        qname = v[2]
        hits = [d for d in self.mon.dns if d.get("qname") == qname]
        ips = sorted({ip for d in hits for ip in (d.get("answers") or [])})
        apps = sorted({d.get("app", "?") for d in hits})
        lines = [qname, "", f"{tr('query'):<13}{len(hits)}", f"{tr('app'):<13}{', '.join(self.mon.app_label(a) for a in apps)}",
                 f"{tr('server'):<13}{', '.join(sorted({d.get('server', '') for d in hits}))}", "", tr("IP RISOLTI")]
        for ip in ips[:30]:
            a = self.mon.asn.lookup(ip)
            lines.append(f"  {ip}" + (f"  {a[0]} {a[1]}" if a else ""))
        used = {c.dst_ip for c in self.mon.snapshot()}
        never = [ip for ip in ips if ip not in used]
        if never:
            lines += ["", tr("risolti ma mai contattati") + f" ({len(never)})"] + [f"  {ip}" for ip in never[:15]]
        rep = self.rep.lookup(qname)
        if rep:
            lines[1:1] = [f"{tr('reputazione'):<13}{rep[0]} ({rep[1]})"]
        # per il Dettaglio IP: la destinazione con questo nome, altrimenti quella che usa uno degli IP risolti
        self._details_dest = qname if qname in self._groups_by_dest else next(
            (d for d, g in self._groups_by_dest.items() if g.ips & set(ips)), None)
        self._details_ip = next((ip for ip in ips if ip in used), None)
        self._set_details("\n".join(lines))

    # ================================================================ grafo
    def _refresh_graph(self, conns, trusted_dest: dict) -> None:
        now = time.monotonic()
        active = self.tab == "graph" or self._floating.get("graph")
        self.graph.active = bool(active)
        if not active or now - self._graph_t < 2.0:
            return
        dt = max(0.2, now - self._graph_t)
        self._graph_t = now
        flow: dict[tuple[str, str], list[int]] = {}      # arco -> [byte usciti, byte entrati, connessioni aperte]
        dev = self.device_info
        phone_label = (dev.get("model") or tr("Telefono")) if not self.demo else "Demo"
        nodes: dict[str, Node] = {"phone": Node("phone", "phone", phone_label, glyph="📱", size=KIND_SIZE["phone"],
                                                 info=dev)}
        edges: dict[tuple[str, str], Edge] = {}
        app_bytes: dict[str, int] = {}
        org_of: dict[str, str] = {}
        dest_bytes: dict[str, int] = {}
        dest_apps: dict[str, set] = {}
        dest_meta: dict[str, dict] = {}
        for c in conns:
            if c.dst_port == 53 or c.host_src == "dns-query":
                continue
            if not self._app_shown(c.app):
                continue
            dest = self.mon.dest_label(c)
            trusted = trusted_dest.get(dest, self.trust.is_trusted(dest, (c.dst_ip,)))
            if self._map_trust == "t" and not trusted or self._map_trust == "u" and trusted:
                continue
            if self._map_new_since is not None and c.key in self._map_new_since:
                continue
            b = c.bytes_in + c.bytes_out
            app_id = f"app:{c.app}"
            if app_id not in nodes:
                info = self.mon.apps.get(c.app) or {}
                label = info.get("label") or c.app
                nodes[app_id] = Node(app_id, "app", label, icon=info.get("icon"), glyph=label[:1].upper(),
                                     size=KIND_SIZE["app"], parent="phone", info={"pkg": c.app})
                edges[("phone", app_id)] = Edge("phone", app_id, 1, color=KIND_COLOR["app"])
            edges[("phone", app_id)].weight += 1
            app_bytes[c.app] = app_bytes.get(c.app, 0) + b
            org_name = c.org or tr("organizzazione sconosciuta")
            org_id = f"org:{org_name}"
            if org_id not in nodes:
                nodes[org_id] = Node(org_id, "org", org_name[:40], glyph="AS", size=KIND_SIZE["org"], parent=app_id,
                                     info={"asn": c.asn or "", "org": org_name})
            e = edges.setdefault((app_id, org_id), Edge(app_id, org_id, 0, color=KIND_COLOR["org"]))
            e.weight += b + 1
            did = f"dest:{dest}"
            if did not in nodes:
                rk = self._risk_by_dest.get(dest)
                dcol = KIND_COLOR["dest_t"] if trusted else risk.color_of(rk.level if rk else 0)
                nodes[did] = Node(did, "dest", dest, color=dcol,
                                  size=KIND_SIZE["dest"], parent=org_id, info={"dest": dest, "trusted": trusted, "org": c.org})
                org_of[did] = org_id
                dest_meta[did] = {"ips": set(), "conns": 0}
            dest_meta[did]["ips"].add(c.dst_ip)
            dest_meta[did]["conns"] += 1
            e = edges.setdefault((org_id, did), Edge(org_id, did, 0, color=nodes[did].color))
            e.weight += b + 1
            dest_bytes[did] = dest_bytes.get(did, 0) + b
            for key in (("phone", app_id), (app_id, org_id), (org_id, did)):
                f = flow.setdefault(key, [0, 0, 0])
                f[0] += c.bytes_out
                f[1] += c.bytes_in
                f[2] += c.closed_ts is None
            dest_apps.setdefault(did, set()).add(c.app)
        for did, bb in dest_bytes.items():
            n = nodes[did]
            n.size = KIND_SIZE["dest"] + min(14, int(2 * (len(str(bb)) - 3))) if bb > 1000 else KIND_SIZE["dest"]
            n.info.update(dest_meta[did])
            n.info["apps"] = sorted(dest_apps[did])
            n.info["bytes"] = bb
            rep = self.rep.lookup(n.label, dest_meta[did]["ips"], n.info.get("org"))
            if rep:
                n.info["rep"] = rep
            rk = self._risk_by_dest.get(n.label)
            if rk:
                n.info["risk"] = rk.level
        for app, bb in app_bytes.items():
            nodes[f"app:{app}"].info["bytes"] = bb
        # velocità (byte/s) di ogni arco, con media mobile come sulla mappa: muove gli impulsi animati
        prev, ema = self._graph_flow
        new_prev, new_ema = {}, {}
        for key, (out, inn, live) in flow.items():
            p_out, p_in = prev.get(key, (out, inn))
            e_out, e_in = ema.get(key, (0.0, 0.0))
            e_out = e_out * 0.4 + max(0, out - p_out) / dt * 0.6
            e_in = e_in * 0.4 + max(0, inn - p_in) / dt * 0.6
            e = edges[key]
            e.rate_out, e.rate_in, e.active = (e_out if e_out >= 1 else 0.0), (e_in if e_in >= 1 else 0.0), live
            new_prev[key], new_ema[key] = (out, inn), (e.rate_out, e.rate_in)
        self._graph_flow = (new_prev, new_ema)
        self.graph.set_graph(list(nodes.values()), list(edges.values()))
        self.graph.set_scale([(c, tr(n)) for c, n in zip(risk.COLORS, risk.NAMES)], tr("pericolosità:"))
        n_app = sum(1 for n in nodes.values() if n.kind == "app")
        n_org = sum(1 for n in nodes.values() if n.kind == "org")
        n_dest = sum(1 for n in nodes.values() if n.kind == "dest")
        asn_note = "" if self.mon.asn.available else "\n" + tr("db ASN assente: scaricalo da Config per vedere le organizzazioni")
        self.graph.set_legend(f"{n_app} app · {n_org} {tr('organizzazioni')} · {n_dest} {tr('destinazioni')}\n"
                              + tr("clic = evidenzia · doppio clic = richiudi il ramo / profilo app · trascina i nodi")
                              + "\n" + tr("puntini colorati = uscita · bianchi = entrata")
                              + asn_note)
        self.tabbar.set_count("graph", n_dest, theme.TEXT_DIM)

    def _on_graph_select(self, node: Node | None) -> None:
        self._graph_sel = node.id if node else None
        if not node:
            return
        if node.kind == "dest":
            info = node.info
            extra = (tr("FIDATA") if info.get("trusted") else tr("NON FIDATA"))
            if info.get("rep"):
                extra += f"  ·  {info['rep'][0]} ({info['rep'][1]})"
            self._select_dest_details(node.label, extra)
        elif node.kind == "app":
            self._set_details(self._app_summary(node.info.get("pkg", "")))
        elif node.kind == "org":
            org = node.info.get("org", "")
            rows = [c for c in self.mon.snapshot() if (c.org or tr("organizzazione sconosciuta")) == org]
            dests = {}
            for c in rows:
                d = self.mon.dest_label(c)
                dests[d] = dests.get(d, 0) + 1
            lines = [org, node.info.get("asn", ""), "", f"{tr('connessioni'):<13}{len(rows)}",
                     f"{tr('traffico'):<13}{_bytes(sum(c.bytes_in + c.bytes_out for c in rows))}",
                     f"{tr('ip'):<13}{len({c.dst_ip for c in rows})}", "", f"APP ({len({c.app for c in rows})})"]
            lines += [f"  {self.mon.app_label(a)}" for a in sorted({c.app for c in rows})]
            lines += ["", f"{tr('DESTINAZIONI')} ({len(dests)})"] + [f"  {d}  ·  {n}" for d, n in
                                                                     sorted(dests.items(), key=lambda kv: -kv[1])[:40]]
            self._set_details("\n".join(lines))
        else:
            self._set_details(self._device_summary())

    def _on_graph_open(self, node: Node) -> None:
        if node.kind == "app":
            self._show_app_profile(node.info.get("pkg", ""))

    # ================================================================ timeline
    def _refresh_timeline(self) -> None:
        if not self._replay:                       # nel replay i campioni arrivano dagli eventi registrati
            self.timeline.add(self.mon.rates_per_app())
        self.timeline.active = self.tab == "timeline"

    # ================================================================ profilo app
    def _app_icon(self, pkg: str, px: int) -> ImageTk.PhotoImage | None:
        info = self.mon.apps.get(pkg) or {}
        if not info.get("icon"):
            return None
        key = (pkg, px)
        if key not in self._icons:
            try:
                im = Image.open(io.BytesIO(base64.b64decode(info["icon"]))).convert("RGBA").resize((px, px), Image.LANCZOS)
                self._icons[key] = ImageTk.PhotoImage(im)
            except Exception:  # noqa: BLE001
                return None
        return self._icons[key]

    def _on_app_info(self, pkg: str) -> None:
        self._ui(self._apps_relabel)

    def _apps_relabel(self) -> None:
        """Le caselle dell'elenco app mostrano il nome leggibile appena arriva dall'agent."""
        for app, (var, box) in self._app_boxes.items():
            label = self.mon.app_label(app)
            txt = box.cget("text")
            n = txt.rsplit("·", 1)[-1].strip() if "·" in txt else ""
            box.configure(text=f"{label}  ·  {n}" if n else label)

    def _app_summary(self, pkg: str) -> str:
        info = self.mon.apps.get(pkg) or {}
        rows = [c for c in self.mon.snapshot() if c.app == pkg and c.dst_port != 53]
        dests: dict[str, int] = {}
        for c in rows:
            d = self.mon.dest_label(c)
            dests[d] = dests.get(d, 0) + 1
        untr = sum(1 for d in dests if not self.trust.is_trusted(d, ()))
        lines = [info.get("label") or pkg, pkg, "",
                 f"{tr('versione'):<13}{info.get('version') or '-'}",
                 f"{tr('sistema'):<13}{tr('sì') if info.get('system') else tr('no')}",
                 f"{tr('connessioni'):<13}{len(rows)}",
                 f"{tr('traffico'):<13}{_bytes(sum(c.bytes_in + c.bytes_out for c in rows))}",
                 f"{tr('destinazioni'):<13}{len(dests)}  ({tr('non fidate')} {untr})", "",
                 tr("doppio clic sul nodo (o sull'app nell'elenco) per il profilo completo"), "",
                 f"{tr('DESTINAZIONI')} ({len(dests)})"]
        lines += [f"  {d}  ·  {n}" for d, n in sorted(dests.items(), key=lambda kv: -kv[1])[:40]]
        return "\n".join(lines)

    def _show_app_profile(self, pkg: str) -> None:
        """Scheda dell'app (finestra): icona, nome, versione, permessi, destinazioni."""
        if not pkg:
            return
        info = self.mon.apps.get(pkg) or {}
        f = self.fonts
        win = ctk.CTkToplevel(self)
        win.title(f"{info.get('label') or pkg} · DroidSnex")
        win.geometry(f"720x640+{self.winfo_rootx() + 120}+{self.winfo_rooty() + 60}")
        win.transient(self)
        box = ctk.CTkFrame(win, fg_color=theme.PANEL, border_width=1, border_color=theme.BORDER, corner_radius=4)
        box.pack(fill="both", expand=True, padx=10, pady=10)
        head = ctk.CTkFrame(box, fg_color="transparent")
        head.pack(fill="x", padx=18, pady=(16, 8))
        icon = self._app_icon(pkg, 56)
        if icon is not None:
            ctk.CTkLabel(head, text="", image=icon, width=56).pack(side="left", padx=(0, 14))
        else:
            ctk.CTkLabel(head, text=(info.get("label") or pkg)[:1].upper(), width=56, height=56, corner_radius=28,
                         fg_color=theme.ACCENT_BG, text_color=theme.ACCENT, font=(theme.ui_font(), 24, "bold")).pack(
                side="left", padx=(0, 14))
        tcol = ctk.CTkFrame(head, fg_color="transparent")
        tcol.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(tcol, text=info.get("label") or pkg, font=(theme.ui_font(), 18, "bold"), text_color=theme.TEXT,
                     anchor="w").pack(fill="x")
        sub = [pkg, f"v{info['version']}" if info.get("version") else "", tr("app di sistema") if info.get("system") else "",
               f"SDK {info['target_sdk']}" if info.get("target_sdk") else ""]
        ctk.CTkLabel(tcol, text="  ·  ".join(x for x in sub if x), font=f.caption, text_color=theme.TEXT_DIM, anchor="w").pack(fill="x")
        if info.get("installed"):
            ctk.CTkLabel(tcol, text=tr("installata") + f" {time.strftime('%Y-%m-%d', time.localtime(info['installed']))}"
                         + (f"  ·  {tr('aggiornata')} {time.strftime('%Y-%m-%d', time.localtime(info['updated']))}" if info.get("updated") else ""),
                         font=f.caption, text_color=theme.TEXT_DIM, anchor="w").pack(fill="x")
        rows = [c for c in self.mon.snapshot() if c.app == pkg and c.dst_port != 53]
        dests: dict[str, dict] = {}
        for c in rows:
            d = self.mon.dest_label(c)
            g = dests.setdefault(d, {"n": 0, "b": 0, "ips": set(), "org": c.org or ""})
            g["n"] += 1
            g["b"] += c.bytes_in + c.bytes_out
            g["ips"].add(c.dst_ip)
        stats = ctk.CTkFrame(box, fg_color="transparent")
        stats.pack(fill="x", padx=18, pady=(0, 8))
        untr = sum(1 for d in dests if not self.trust.is_trusted(d, ()))
        for label, val, col in ((tr("CONNESSIONI"), len(rows), theme.TEXT), (tr("DESTINAZIONI"), len(dests), theme.TEXT),
                                (tr("NON FIDATE"), untr, theme.ERR), (tr("TRAFFICO"), _bytes(sum(c.bytes_in + c.bytes_out for c in rows)), theme.TEXT)):
            cell = ctk.CTkFrame(stats, fg_color=theme.PANEL_2, corner_radius=4, border_width=1, border_color=theme.BORDER)
            cell.pack(side="left", fill="x", expand=True, padx=(0, 6))
            ctk.CTkLabel(cell, text=label, font=f.caption, text_color=theme.TEXT_FAINT).pack(anchor="w", padx=10, pady=(6, 0))
            ctk.CTkLabel(cell, text=str(val), font=(theme.mono_font(), 16, "bold"), text_color=col).pack(anchor="w", padx=10, pady=(0, 6))
        body = ctk.CTkFrame(box, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(1, weight=1)
        caption(body, tr("Destinazioni"), f).grid(row=0, column=0, sticky="w", pady=(0, 4))
        caption(body, tr("Permessi") + (f"  ({len(info.get('perms') or [])})" if info.get("perms") else ""), f).grid(
            row=0, column=1, sticky="w", padx=(10, 0), pady=(0, 4))
        cols = [("dest", tr("Destinazione"), 200, True, "w"), ("n", tr("Conn"), 44, False, "e"), ("b", tr("Traffico"), 70, False, "e"),
                ("org", "Org", 110, True, "w"), ("t", "", 30, False, "center")]
        tbl = Table(body, cols, tags={"t": theme.OK, "u": theme.ERR})
        tbl.grid(row=1, column=0, sticky="nsew")
        for d, g in sorted(dests.items(), key=lambda kv: -kv[1]["b"]):
            trusted = self.trust.is_trusted(d, g["ips"])
            tbl.tree.insert("", "end", tags=["t" if trusted else "u"], values=(d, g["n"], _bytes(g["b"]), g["org"], "✓" if trusted else "✕"))
        perms = ctk.CTkTextbox(body, font=f.mono, wrap="none")
        perms.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        perms.tag_config("danger", foreground=theme.WARN)
        perms.tag_config("off", foreground=theme.TEXT_FAINT)
        plist = info.get("perms") or []
        if not plist:
            perms.insert("end", tr("(non ancora ricevuti dall'agent)") if info else tr("(l'agent non ha mandato la scheda di questa app)"))
        for p in sorted(plist, key=lambda p: (not p.get("granted"), p.get("name", ""))):
            name = p.get("name", "")
            short = name.rsplit(".", 1)[-1]
            danger = short in DANGEROUS
            mark = "✓ " if p.get("granted") else "· "
            perms.insert("end", f"{mark}{short}\n", ("danger",) if danger and p.get("granted") else () if p.get("granted") else ("off",))
        perms.configure(state="disabled")
        foot = ctk.CTkFrame(box, fg_color="transparent")
        foot.pack(fill="x", padx=18, pady=(0, 14))
        ctk.CTkLabel(foot, text=tr("✓ = permesso concesso · in giallo i permessi sensibili"), font=f.small,
                     text_color=theme.TEXT_DIM).pack(side="left")
        button(foot, tr("Chiudi"), win.destroy, primary=True).pack(side="right")
        win.bind("<Escape>", lambda _e: win.destroy())
        win.after(50, lambda: (win.lift(), win.focus_force()) if win.winfo_exists() else None)

    # ================================================================ sessioni
    def _device_summary(self) -> str:
        d = self.device_info
        if not d:
            return tr("Telefono") + "\n\n" + tr("(dati del dispositivo non ancora letti: premi Start)")
        lines = [device_title(d), "", f"{'modello':<13}{d.get('manufacturer', '')} {d.get('model', '')}",
                 f"{'Android':<13}{d.get('android', '?')} (SDK {d.get('sdk', '?')})", f"{'seriale':<13}{d.get('serial', '-')}",
                 f"{'Android ID':<13}{d.get('android_id') or '-'}", f"{'IMEI':<13}{d.get('imei') or tr('non leggibile senza root')}",
                 f"{'MAC Wi-Fi':<13}{d.get('wifi_mac') or tr('non leggibile senza root')}",
                 f"{'MAC BT':<13}{d.get('bt_mac') or '-'}"]
        return "\n".join(lines)

    def _session_begin(self) -> None:
        self.session = Session(id=time.strftime("%Y%m%d-%H%M%S"), device=dict(self.device_info), started=time.time(),
                               demo=bool(self.demo))
        self.mon.record = self.session.events          # registrazione sempre attiva (per il replay)
        self._mark_n = 0
        self.alerts.reset()
        self.timeline.clear()
        self.graph.clear()
        self._dns_shown = -1
        self._alerts_shown = -1
        self._session_saved = time.time()
        self.log(tr("sessione {id} avviata", id=self.session.id))

    def _session_snapshot(self) -> Session | None:
        s = self.session
        if not s:
            return None
        conns = []
        for c in self.mon.snapshot():
            d = c.to_dict()
            d["dest"] = self.mon.dest_label(c)
            d["trusted"] = self.trust.is_trusted(d["dest"], (c.dst_ip,))
            p = self.geo.lookup(c.dst_ip)
            if p:
                d["country"], d["city"] = p.country, p.city
            conns.append(d)
        s.conns = conns
        with self.mon.lock:
            s.dns = list(self.mon.dns)
            s.apps = {k: {kk: vv for kk, vv in v.items() if kk != "icon"} for k, v in self.mon.apps.items()}
        s.alerts = [a.to_dict() for a in self.alerts.items]
        s.device = dict(self.device_info) or s.device
        return s

    # ---------------------------------------------------------------- segnalibri
    def _add_mark(self, note: str) -> None:
        """Segnalibro nella sessione in corso: istante, nota e (se c'e' un telefono) screenshot via adb."""
        s = self.session
        if not s:
            return self.log(tr("nessuna sessione in corso: avvia il monitor"), "err")
        self._mark_n = getattr(self, "_mark_n", 0) + 1
        mark = {"ts": time.time(), "note": note.strip(), "shot": None}
        s.marks.append(mark)
        self.log(tr("segnalibro {n} alle {t}: {note}", n=self._mark_n, t=_t(mark["ts"]), note=mark["note"] or "-"), "ok")
        if self.demo or not self.adb or not self.adb.serial:
            return
        n = self._mark_n

        def shot():
            d = self.sessions.device_dir(s.device)
            name = f"{s.id}-mark-{n}.png"
            try:
                os.makedirs(d, exist_ok=True)
                self.adb.screencap(os.path.join(d, name))
                mark["shot"] = name
                self._ui(self.log, tr("screenshot del segnalibro {n} salvato: {p}", n=n, p=name))
            except Exception as e:  # noqa: BLE001 - lo screenshot e' un di piu'
                self._ui(self.log, tr("screenshot del segnalibro non riuscito: {e}", e=e), "err")
        threading.Thread(target=shot, daemon=True).start()

    def _session_autosave(self) -> None:
        if self.session and time.time() - self._session_saved > 60 and self.mon.events:
            self._session_saved = time.time()
            s = self._session_snapshot()
            threading.Thread(target=lambda: self._session_write(s), daemon=True).start()

    def _session_write(self, s: Session) -> None:
        try:
            self.sessions.save(s)
        except OSError as e:
            self._ui(self.log, tr("sessione non salvata: {e}", e=e), "err")

    def _session_end(self, wait: bool = False) -> None:
        s = self._session_snapshot()
        self.session = None
        self.mon.record = None
        if not s or not s.conns:
            return
        s.ended = time.time()
        if wait:
            self._session_write(s)
        else:
            threading.Thread(target=lambda: self._session_write(s), daemon=True).start()
        self.log(tr("sessione salvata: {n} connessioni", n=len(s.conns)), "ok")
        self._ui(self._refresh_sessions)

    def _build_sessions_page(self):
        f = self.fonts
        page = ctk.CTkFrame(self.pages_box, fg_color="transparent", corner_radius=0)
        page.grid_columnconfigure(0, weight=2)
        page.grid_columnconfigure(1, weight=3)
        page.grid_rowconfigure(0, weight=1)
        left = Card(page, tr("Telefoni e sessioni"), f)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, theme.GAP // 2))
        left.body.grid_columnconfigure(0, weight=1)
        left.body.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left.body, text=tr("Ogni Start registra una sessione (connessioni, DNS, app, alert e tutti gli eventi con l'orario) "
                                        "in pc/sessions/<telefono>. Rivedi la fa scorrere come dal vivo (play, velocità, cursore, "
                                        "segnalibri). Seleziona due sessioni dello stesso telefono e premi Confronta."),
                     font=f.small, text_color=theme.TEXT_DIM, justify="left", anchor="w", wraplength=460).grid(
            row=0, column=0, sticky="ew", pady=(0, 6))
        self.sess_tree = ttk_tree = tk.ttk.Treeview(left.body, columns=("when", "dur", "conns", "untr", "alerts", "rep"),
                                                     show="tree headings", selectmode="extended")
        for col, title, w, anchor in (("#0", tr("Telefono / sessione"), 230, "w"), ("when", tr("Inizio"), 120, "w"),
                                      ("dur", tr("Durata"), 60, "e"), ("conns", tr("Conn"), 60, "e"),
                                      ("untr", tr("Non fid."), 60, "e"), ("alerts", "Alert", 50, "e"),
                                      ("rep", tr("Replay"), 60, "center")):
            ttk_tree.heading(col, text=title.upper(), anchor=anchor)
            ttk_tree.column(col, width=w, anchor=anchor, stretch=col in ("#0",))
        ttk_tree.grid(row=1, column=0, sticky="nsew")
        ttk_tree.tag_configure("dev", foreground=theme.ACCENT)
        ttk_tree.tag_configure("sess", foreground=theme.TEXT)
        ttk_tree.bind("<<TreeviewSelect>>", lambda _e: self._sessions_selected())
        row = ctk.CTkFrame(left.body, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        button(row, tr("Confronta"), self._compare_sessions, primary=True).pack(side="left")
        button(row, tr("Apri"), self._open_session).pack(side="left", padx=(8, 0))
        button(row, "▶  " + tr("Rivedi"), self._replay_session).pack(side="left", padx=(8, 0))
        button(row, tr("Report"), self._report_selected).pack(side="left", padx=(8, 0))
        button(row, tr("Elimina"), self._delete_session, danger=True).pack(side="left", padx=(8, 0))
        button(row, tr("Apri cartella"), lambda: self._open_dir(self.sessions.root)).pack(side="right")
        button(row, "⟳", self._refresh_sessions, width=34).pack(side="right", padx=(0, 8))
        right = Card(page, tr("Confronto / dettaglio"), f)
        right.grid(row=0, column=1, sticky="nsew", padx=(theme.GAP // 2, 0))
        right.body.grid_columnconfigure(0, weight=1)
        right.body.grid_rowconfigure(0, weight=1)
        self.sess_text = ctk.CTkTextbox(right.body, font=f.mono, wrap="none")
        self.sess_text.grid(row=0, column=0, sticky="nsew")
        for tag, col in (("h", theme.ACCENT), ("new", theme.ERR), ("gone", theme.TEXT_DIM), ("ok", theme.OK), ("warn", theme.WARN)):
            self.sess_text.tag_config(tag, foreground=col)
        self._sess_rows: dict[str, dict] = {}
        self._sessions_loaded = False
        return page

    def _refresh_sessions(self) -> None:
        tree = self.sess_tree
        tree.delete(*tree.get_children())
        self._sess_rows = {}
        devices = self.sessions.devices()
        for dev in devices:
            did = tree.insert("", "end", text=device_title(dev["device"]), open=True, tags=["dev"],
                              values=("", "", "", "", "", ""))
            for s in dev["sessions"]:
                iid = tree.insert(did, "end", text=("  demo · " if s["demo"] else "  ") + s["id"], tags=["sess"], values=(
                    time.strftime("%Y-%m-%d %H:%M", time.localtime(s["started"])), f"{s['duration'] / 60:.0f} min",
                    s["conns"], s["untrusted"], s["alerts"],
                    ("▶ " + (f"🔖{s['marks']}" if s.get("marks") else "")) if s.get("replay") else "—"))
                self._sess_rows[iid] = s
        self.tabbar.set_count("sessions", sum(len(d["sessions"]) for d in devices), theme.TEXT_DIM)
        self._sessions_loaded = True

    def _sessions_selected(self) -> None:
        self._sess_sel = [i for i in self.sess_tree.selection() if i in self._sess_rows]
        if len(self._sess_sel) == 1:
            self._open_session()

    def _sess_write(self, lines: list[tuple[str, str]]) -> None:
        t = self.sess_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        for text, tag in lines:
            t.insert("end", text + "\n", (tag,) if tag else ())
        t.configure(state="disabled")

    def _open_session(self) -> None:
        if not self._sess_sel:
            return
        meta = self._sess_rows[self._sess_sel[-1]]
        try:
            s = self.sessions.load(meta["path"])
        except (OSError, ValueError) as e:
            return self.log(tr("sessione non leggibile: {e}", e=e), "err")
        dests = s.dests()
        lines = [(f"{tr('SESSIONE')} {s.id}  ·  {device_title(s.device)}", "h"),
                 (f"{tr('inizio'):<14}{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(s.started))}", ""),
                 (f"{tr('durata'):<14}{s.duration / 60:.0f} min", ""),
                 (f"{tr('connessioni'):<14}{len(s.conns)}   {tr('destinazioni')} {len(dests)}   {tr('non fidate')} "
                  f"{sum(1 for g in dests.values() if not g['trusted'])}", ""),
                 (f"{'DNS':<14}{len(s.dns)}   alert {len(s.alerts)}   app {len(s.app_names())}", ""),
                 (f"{tr('replay'):<14}" + (tr("{n} eventi registrati · premi Rivedi", n=len(s.events)) if s.replayable
                                           else tr("non disponibile (sessione registrata senza eventi)")), "" if s.replayable else "warn"),
                 ("", ""), (tr("TELEFONO"), "h")]
        d = s.device
        for k, label in (("model", "modello"), ("android", "Android"), ("serial", "seriale"), ("android_id", "Android ID"),
                         ("imei", "IMEI"), ("wifi_mac", "MAC Wi-Fi")):
            lines.append((f"{label:<14}{d.get(k) or '-'}", ""))
        lines += [("", ""), (f"{tr('DESTINAZIONI')} ({len(dests)})", "h")]
        for dd, g in sorted(dests.items(), key=lambda kv: -kv[1]["bytes"])[:200]:
            lines.append((f"{'✓' if g['trusted'] else '✕'} {dd[:40]:<40} {g['conns']:>5}  {_bytes(g['bytes']):>9}  {', '.join(sorted(g['apps']))[:40]}",
                          "ok" if g["trusted"] else "new"))
        if s.marks:
            lines += [("", ""), (f"{tr('SEGNALIBRI')} ({len(s.marks)})", "h")]
            for i, m in enumerate(s.marks, start=1):
                lines.append((f"{_t(m.get('ts', 0))}  🔖 {i}  {m.get('note') or '-'}" + ("  📷 " + m["shot"] if m.get("shot") else ""), "ok"))
        if s.alerts:
            lines += [("", ""), (f"ALERT ({len(s.alerts)})", "h")]
            for a in s.alerts[:100]:
                lines.append((f"{_t(a['ts'])} {tr(ALERT_KIND_NAMES.get(a['kind'], a['kind'])):<18} {a['dest']:<36} {a['text']}", "warn"))
        self._sess_write(lines)

    # ---------------------------------------------------------------- report HTML
    def _report(self, session: Session | None = None) -> None:
        """Report HTML della sessione (quella in corso, quella in replay o quella passata): un file solo in
        captures/, aperto subito nel browser. Da lì si stampa o si salva in PDF."""
        s = session
        if s is None and getattr(self, "_replay", None):
            s = self._replay.session
        if s is None and self.session:
            s = self._session_snapshot()
        if s is None or not s.conns:
            return self.log(tr("report: nessuna sessione con connessioni (avvia il monitor o scegli una sessione salvata)"), "err")
        st = self.settings
        try:
            path = report.write(s, self.out_dir, tr=tr, rep=self.rep, geo=self.geo if self.geo.available else None,
                                home=(st.home_lat, st.home_lon, st.home_name), home_country=st.home_country,
                                shots_dir=self.sessions.device_dir(s.device), lang=language())
        except Exception as e:  # noqa: BLE001
            return self.log(tr("report non riuscito: {e}", e=e), "err")
        self.log(tr("report salvato: {p}", p=path), "ok")
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                import webbrowser
                webbrowser.open("file://" + path)
        except OSError as e:
            self.log(tr("impossibile aprire il report: {e}", e=e), "err")

    def _report_selected(self) -> None:
        if not self._sess_sel:
            return self.log(tr("scegli una sessione dall'elenco"), "err")
        try:
            s = self.sessions.load(self._sess_rows[self._sess_sel[-1]]["path"])
        except (OSError, ValueError) as e:
            return self.log(tr("sessione non leggibile: {e}", e=e), "err")
        self._report(s)

    def _replay_session(self) -> None:
        """Rivedi: apre la sessione selezionata nel replay (barra in basso, viste come dal vivo)."""
        if not self._sess_sel:
            return self.log(tr("seleziona una sessione da rivedere"))
        meta = self._sess_rows[self._sess_sel[-1]]
        if not meta.get("replay"):
            return self.log(tr("questa sessione non ha gli eventi registrati (versione precedente): non si può rivedere"), "err")
        try:
            s = self.sessions.load(meta["path"])
        except (OSError, ValueError) as e:
            return self.log(tr("sessione non leggibile: {e}", e=e), "err")
        self._enter_replay(s)

    def _compare_sessions(self) -> None:
        if len(self._sess_sel) != 2:
            return self.log(tr("seleziona due sessioni (Ctrl+clic) da confrontare"))
        a, b = (self._sess_rows[i] for i in self._sess_sel)
        if a["started"] > b["started"]:
            a, b = b, a
        try:
            sa, sb = self.sessions.load(a["path"]), self.sessions.load(b["path"])
        except (OSError, ValueError) as e:
            return self.log(tr("sessione non leggibile: {e}", e=e), "err")
        same = (sa.device.get("imei") and sa.device.get("imei") == sb.device.get("imei")) or \
               (sa.device.get("android_id") and sa.device.get("android_id") == sb.device.get("android_id")) or \
               (sa.device.get("serial") and sa.device.get("serial") == sb.device.get("serial"))
        r = compare(sa, sb)
        lines = [(f"{tr('CONFRONTO')}  {sa.id}  →  {sb.id}", "h"), (device_title(sa.device), ""),
                 ("" if same else "⚠ " + tr("le due sessioni sono di telefoni diversi"), "warn"), ("", ""),
                 (f"{tr('destinazioni in comune'):<28}{r['common']}", ""),
                 (f"{tr('nuove destinazioni'):<28}{len(r['new_dests'])}", "new"),
                 (f"{tr('destinazioni scomparse'):<28}{len(r['gone_dests'])}", "gone"),
                 (f"{tr('nuove app'):<28}{', '.join(sb.apps.get(x, {}).get('label') or x for x in r['new_apps']) or '-'}", "new"),
                 (f"{tr('app scomparse'):<28}{', '.join(r['gone_apps']) or '-'}", "gone"),
                 (f"{tr('nuove organizzazioni'):<28}{', '.join(r['new_orgs'][:12]) or '-'}", ""),
                 (f"{tr('nuovi paesi'):<28}{', '.join(r['new_countries']) or '-'}", "warn" if r["new_countries"] else ""),
                 ("", ""), (f"{tr('NUOVE DESTINAZIONI')} ({len(r['new_dests'])})", "h")]
        for d, g in r["new_dests"][:150]:
            lines.append((f"{'✓' if g['trusted'] else '✕'} {d[:40]:<40} {g['conns']:>5}  {_bytes(g['bytes']):>9}  {', '.join(sorted(g['apps']))[:40]}"
                          + (f"  {g['org']}" if g["org"] else ""), "ok" if g["trusted"] else "new"))
        lines += [("", ""), (f"{tr('DESTINAZIONI SCOMPARSE')} ({len(r['gone_dests'])})", "h")]
        for d, g in r["gone_dests"][:100]:
            lines.append((f"  {d[:40]:<40} {g['conns']:>5}  {_bytes(g['bytes']):>9}  {', '.join(sorted(g['apps']))[:40]}", "gone"))
        lines += [("", ""), (f"{tr('CAMBIATE')} ({len(r['changed'])})", "h")]
        for d, x, y in r["changed"][:100]:
            apps_new = sorted(y["apps"] - x["apps"])
            lines.append((f"  {d[:40]:<40} {x['conns']:>4} → {y['conns']:<4}" + (f"  +app {', '.join(apps_new)}" if apps_new else "")
                          + ("" if x["trusted"] == y["trusted"] else f"  {tr('fidata')}: {x['trusted']} → {y['trusted']}"), ""))
        self._sess_write(lines)

    def _delete_session(self) -> None:
        if not self._sess_sel:
            return
        paths = [self._sess_rows[i]["path"] for i in self._sess_sel]

        def do():
            for p in paths:
                try:
                    self.sessions.delete(p)
                except OSError as e:
                    self.log(tr("errore: {e}", e=e), "err")
            self._refresh_sessions()
        confirm(self, tr("Elimina sessioni"), tr("Eliminare {n} sessioni salvate? Non si può annullare.", n=len(paths)),
                tr("Elimina"), do, self.fonts, cancel_text=tr("Annulla"))
