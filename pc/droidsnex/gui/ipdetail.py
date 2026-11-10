"""Finestra "Dettaglio IP": per una destinazione selezionata raccoglie, in un thread a parte,
PTR, domini della sessione, range cloud, RDAP/WHOIS, certificato TLS (contatto attivo) e i
servizi con chiave API configurati; il dettaglio del collegamento sta sopra. "Salva dettaglio"
scrive collegamento + IP in un .json e in un .txt leggibile."""
from __future__ import annotations

import json
import os
import re
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog

import customtkinter as ctk

from .. import ipinfo
from ..i18n import tr
from . import frameless, theme
from .widgets import button, window_buttons

SECTION_TITLES = {"dns_names": "DOMINI VISTI SU QUESTO IP", "ptr": "PTR (reverse DNS)", "cloud": "CLOUD",
                  "rdap": "RDAP / WHOIS", "tls": "CERTIFICATO TLS (contatto attivo)", "virustotal": "VIRUSTOTAL",
                  "abuseipdb": "ABUSEIPDB", "shodan": "SHODAN", "ipinfo": "IPINFO.IO"}
ORDER = ("dns_names", "ptr", "cloud", "rdap", "tls", "virustotal", "abuseipdb", "shodan", "ipinfo")


def _kv(k: str, v) -> str:
    return f"{k:<14}{v if v not in (None, '') else '-'}"


def render(section: str, res) -> list[str]:
    """Righe leggibili di una sezione."""
    if isinstance(res, dict) and res.get("error"):
        return [f"  ⚠ {res['error']}"]
    if section == "dns_names":
        return [f"  {n}" for n in res] if res else [f"  {tr('nessun nome visto in questa sessione')}"]
    if section == "ptr":
        return [f"  {res or tr('nessun record PTR')}"]
    if section == "cloud":
        if not res:
            return [f"  {tr('non in un range cloud noto')}"]
        prov, svc, reg, cidr = res
        return [f"  {prov}" + (f" · {svc}" if svc else "") + (f" · {reg}" if reg else "") + f"  ({cidr})"]
    if section == "rdap":
        lines = [_kv(tr("blocco"), res.get("name")), _kv("handle", res.get("handle")),
                 _kv("range", f"{res.get('start')} – {res.get('end')}"), _kv(tr("paese"), res.get("country")),
                 _kv(tr("titolare"), res.get("registrant")), _kv("abuse", res.get("abuse")), _kv(tr("fonte"), res.get("source"))]
        if res.get("cidrs"):
            lines.append(_kv("cidr", ", ".join(res["cidrs"][:4])))
        lines += [f"  {r}" for r in res.get("remarks", [])[:4]]
        return ["  " + x for x in lines]
    if section == "tls":
        lines = [_kv("SNI", res.get("sni") or tr("nessuno")), _kv(tr("porta"), res.get("port")),
                 _kv(tr("protocollo"), f"{res.get('protocol', '')} · {res.get('cipher', '')} · {res.get('ms', 0)} ms"),
                 _kv("CN", res.get("cn")), _kv(tr("emittente"), res.get("issuer_org") or res.get("issuer")),
                 _kv(tr("validità"), f"{res.get('not_before', '')} → {res.get('not_after', '')}"
                     + ("  ⚠ " + tr("SCADUTO") if res.get("expired") else "")),
                 _kv("SHA-256", (res.get("sha256") or "")[:32] + "…")]
        san = res.get("san") or []
        lines.append(_kv("SAN", f"{len(san)}"))
        lines += [f"    {s}" for s in san[:25]] + ([f"    … {tr('altri')} {len(san) - 25}"] if len(san) > 25 else [])
        return ["  " + x for x in lines]
    if section == "virustotal":
        verdict = f"{res.get('malicious', 0)} malicious · {res.get('suspicious', 0)} suspicious · {res.get('harmless', 0)} harmless"
        return ["  " + x for x in [_kv(tr("verdetto"), verdict), _kv(tr("reputazione"), res.get("reputation")),
                                   _kv("AS owner", res.get("as_owner")), _kv(tr("rete"), res.get("network")),
                                   _kv("tag", ", ".join(res.get("tags", []))), _kv("url", res.get("url"))]]
    if section == "abuseipdb":
        return ["  " + x for x in [_kv(tr("punteggio"), f"{res.get('score')}%  ·  {res.get('reports')} {tr('segnalazioni')}"),
                                   _kv(tr("ultima"), res.get("last")), _kv("ISP", res.get("isp")), _kv(tr("uso"), res.get("usage")),
                                   _kv(tr("dominio"), res.get("domain")), _kv("Tor", tr("sì") if res.get("tor") else tr("no")),
                                   _kv("url", res.get("url"))]]
    if section == "shodan":
        return ["  " + x for x in [_kv(tr("porte"), ", ".join(str(p) for p in res.get("ports", [])) or "-"),
                                   _kv("hostnames", ", ".join(res.get("hostnames", []))), _kv("org", res.get("org")),
                                   _kv("OS", res.get("os")), _kv("vulns", res.get("vulns")), _kv("tag", ", ".join(res.get("tags", []))),
                                   _kv(tr("ultima"), res.get("last")), _kv("url", res.get("url"))]]
    if section == "ipinfo":
        flags = [k for k in ("vpn", "proxy", "tor", "hosting", "anycast") if res.get(k)]
        return ["  " + x for x in [_kv("hostname", res.get("hostname")), _kv("org", res.get("org")),
                                   _kv(tr("luogo"), ", ".join(x for x in (res.get("city"), res.get("region"), res.get("country")) if x)),
                                   _kv("flag", ", ".join(flags) or "-"), _kv("url", res.get("url"))]]
    return [f"  {res}"]


URL_RE = re.compile(r"https?://[^\s<>\"']+")


class IpDetailWindow(ctk.CTkToplevel):
    def __init__(self, app, dest: str, record: dict, conn_text: str, ips: list[str], sni: str | None, port: int,
                 dns_names: dict):
        super().__init__(app, fg_color=theme.BG)
        self.app, self.dest, self.record, self.conn_text = app, dest, record, conn_text
        self.ips, self.sni, self.port, self.dns_names = ips, sni, port, dns_names
        self.results: dict[str, dict] = {}
        self.sections: dict[str, object] = {}
        self._cancel = False
        self._thread: threading.Thread | None = None
        self.title(f"DroidSnex · {tr('Dettaglio IP')} · {dest}")
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.close)
        try:
            if getattr(app, "_droidsnex_icon", None) is not None:
                self.iconphoto(False, app._droidsnex_icon)
        except tk.TclError:
            pass
        self._build()
        self.geometry(f"760x820+{app.winfo_rootx() + 120}+{app.winfo_rooty() + 30}")
        self.update_idletasks()
        self._frameless_done = False
        self.bind("<Map>", self._on_map, add="+")
        self.after(60, self._raise)
        self.after(100, self.start)

    def _on_map(self, event=None) -> None:
        """Senza barra del titolo, come la finestra principale: va fatto quando la finestra e' davvero
        sullo schermo (prima, su Windows, la cornice nativa non esiste ancora e l'aggancio non prende)."""
        if event is not None and event.widget is not self:
            return
        if self._frameless_done or not self.app.frameless:
            return
        if frameless.make_frameless(self, border_color=theme.BORDER):
            self._frameless_done = True

    def _raise(self) -> None:
        """Su Windows CTkToplevel nasconde e rimostra la finestra appena creata: la si porta davanti."""
        try:
            self.deiconify()
            self.update_idletasks()
            self._on_map()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass
        if not self._frameless_done and self.app.frameless:
            self.after(150, self._raise_retry)

    def _raise_retry(self, n: int = 0) -> None:
        if not self.winfo_exists() or self._frameless_done:
            return
        self._on_map()
        if not self._frameless_done and n < 10:
            self.after(150, lambda: self._raise_retry(n + 1))

    # ------------------------------------------------------------------ interfaccia
    def _build(self) -> None:
        f = self.app.fonts
        bar = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0, height=34)
        bar.pack(side="top", fill="x", padx=1, pady=(1, 0))
        bar.pack_propagate(False)
        logo = theme.logo(12)
        brand = (ctk.CTkLabel(bar, text="", image=logo) if logo is not None else
                 ctk.CTkLabel(bar, text="DROIDSNEX", font=(theme.mono_font(), 12, "bold")))
        brand.pack(side="left", padx=(12, 0))
        label = ctk.CTkLabel(bar, text=f"   ·   {tr('Dettaglio IP')}   ·   {self.dest}", font=f.bold, text_color=theme.TEXT_SOFT)
        label.pack(side="left")
        window_buttons(self, bar, self.close).pack(side="right")
        for x in (bar, brand, label):
            frameless.enable_drag(self, x)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(side="top", fill="x", padx=14, pady=(8, 4))
        ctk.CTkLabel(top, text="IP", font=f.caption, text_color=theme.TEXT_FAINT).pack(side="left")
        self.ip_var = tk.StringVar(value=self.ips[0] if self.ips else "")
        self.ip_menu = ctk.CTkOptionMenu(top, values=self.ips or ["-"], variable=self.ip_var, width=200, height=28,
                                         font=f.mono, command=lambda _v: self.start())
        self.ip_menu.pack(side="left", padx=(8, 14))
        self.active_var = tk.BooleanVar(value=bool(getattr(self.app.settings, "ip_active", True)))
        ctk.CTkCheckBox(top, text=tr("contatto attivo (certificato TLS)"), variable=self.active_var, font=f.small,
                        checkbox_width=16, checkbox_height=16, border_width=1, corner_radius=3).pack(side="left")
        button(top, "⟳  " + tr("Aggiorna"), self.start).pack(side="right")
        button(top, "💾  " + tr("Salva dettaglio"), self.save, primary=True).pack(side="right", padx=(0, 8))
        self.status = ctk.CTkLabel(self, text="", font=f.small, text_color=theme.TEXT_DIM, anchor="w")
        self.status.pack(side="top", fill="x", padx=14)
        ctk.CTkLabel(self, text=tr("PTR, domini, liste cloud e RDAP sono passivi (nessun contatto con l'IP). Il certificato TLS "
                                   "è un contatto attivo: il PC si collega all'IP. I servizi con chiave API inviano l'IP al servizio."),
                     font=f.tiny, text_color=theme.TEXT_FAINT, anchor="w", justify="left", wraplength=720).pack(
            side="top", fill="x", padx=14, pady=(2, 4))
        self.text = ctk.CTkTextbox(self, font=f.mono, wrap="none")
        self.text.pack(side="top", fill="both", expand=True, padx=14, pady=(0, 12))
        self.text.tag_config("h", foreground=theme.ACCENT)
        self.text.tag_config("warn", foreground=theme.WARN)
        self.text.tag_config("dim", foreground=theme.TEXT_DIM)
        self.text.tag_config("link", foreground=theme.ACCENT, underline=True)
        self.text.tag_bind("link", "<Enter>", lambda _e: self.text._textbox.configure(cursor="hand2"))
        self.text.tag_bind("link", "<Leave>", lambda _e: self.text._textbox.configure(cursor=""))
        self.text.tag_bind("link", "<Button-1>", self._click_link)

    # ------------------------------------------------------------------ raccolta
    def start(self) -> None:
        ip = self.ip_var.get()
        if not ip or ip == "-":
            return
        self._cancel = True                       # ferma la raccolta precedente (se ancora in corso)
        self.sections = {}
        self._cancel = False
        self.status.configure(text=tr("raccolta in corso…"), text_color=theme.ACCENT)
        self._redraw()
        keys = {k: getattr(self.app.settings, k, "") for k, *_rest in ipinfo.API_SERVICES}
        names = sorted(self.dns_names.get(ip, set()))
        cloud = self.app.cloud
        active = self.active_var.get()
        gen = object()
        self._gen = gen

        def emit(section, res):
            if self._gen is gen and not self._cancel:
                self.app._ui(self._got, section, res)

        def job():
            full = ipinfo.collect(ip, self.sni, self.port, names, cloud, keys, emit, active=active,
                                  cancel=lambda: self._cancel or self._gen is not gen)
            if self._gen is gen:
                self.results[ip] = full
                self.app._ui(self._done)
        self._thread = threading.Thread(target=job, daemon=True)
        self._thread.start()

    def _got(self, section: str, res) -> None:
        self.sections[section] = res
        self._redraw()

    def _done(self) -> None:
        if not self.winfo_exists():
            return
        self.status.configure(text=tr("raccolta completata") + f"  ·  {time.strftime('%H:%M:%S')}", text_color=theme.OK)

    def _redraw(self) -> None:
        if not self.winfo_exists():
            return
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", f"{tr('DETTAGLIO IP')}  {self.ip_var.get()}\n", "h")
        for sec in ORDER:
            if sec not in self.sections:
                continue
            t.insert("end", f"\n{tr(SECTION_TITLES[sec])}\n", "h")
            for line in render(sec, self.sections[sec]):
                self._insert_line(line, "warn" if line.strip().startswith("⚠") else "")
        t.insert("end", "\n" + "─" * 60 + "\n\n", "dim")
        t.insert("end", tr("COLLEGAMENTO") + "\n", "h")
        for line in self.conn_text.rstrip().splitlines():
            self._insert_line(line, "")
        t.configure(state="disabled")

    def _insert_line(self, line: str, tag: str) -> None:
        """Inserisce una riga; gli indirizzi http(s) diventano link cliccabili (si aprono nel browser)."""
        t = self.text
        pos = 0
        for m in URL_RE.finditer(line):
            url = m.group(0).rstrip(".,;)")
            t.insert("end", line[pos:m.start()], tag)
            t.insert("end", url, ("link",))
            pos = m.start() + len(url)
        t.insert("end", line[pos:] + "\n", tag)

    def _click_link(self, event) -> None:
        """Apre nel browser predefinito l'indirizzo sotto il puntatore."""
        tb = self.text._textbox
        index = tb.index(f"@{event.x},{event.y}")
        rng = tb.tag_prevrange("link", index + "+1c")
        if not rng or tb.compare(index, ">=", rng[1]):
            return
        url = tb.get(rng[0], rng[1])
        try:
            webbrowser.open(url)
            self.app.log(tr("apro {u}", u=url))
        except Exception as e:  # noqa: BLE001 - browser non disponibile
            self.app.log(tr("errore: {e}", e=e), "err")

    # ------------------------------------------------------------------ salvataggio
    def save(self) -> None:
        ip = self.ip_var.get()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", self.dest)[:60]
        stamp = time.strftime("%Y%m%d-%H%M%S")
        initial = f"dettaglio-{safe}-{stamp}.json"
        path = filedialog.asksaveasfilename(parent=self, title=tr("Salva dettaglio"), defaultextension=".json",
                                            initialfile=initial, initialdir=self.app.out_dir,
                                            filetypes=[("JSON", "*.json"), ("Testo", "*.txt")])
        if not path:
            return
        base = path[:-5] if path.lower().endswith(".json") else path[:-4] if path.lower().endswith(".txt") else path
        data = {"saved": time.strftime("%Y-%m-%d %H:%M:%S"), "destination": self.dest, "connection": self.record,
                "ip_detail": {ip: (self.results.get(ip) or dict(self.sections, ip=ip, partial=True))},
                "ip_detail_other": {k: v for k, v in self.results.items() if k != ip}}
        try:
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write(f"DroidSnex · {tr('Dettaglio IP')} · {self.dest} · {data['saved']}\n\n")
                f.write(self.text.get("1.0", "end"))
        except OSError as e:
            self.status.configure(text=tr("errore: {e}", e=e), text_color=theme.ERR)
            return
        self.status.configure(text=tr("salvato: {p}", p=os.path.basename(base) + ".json / .txt"), text_color=theme.OK)
        self.app.log(tr("dettaglio salvato in {p}", p=base + ".json"), "ok")

    def close(self) -> None:
        self._cancel = True
        try:
            self.destroy()
        except tk.TclError:
            pass
        if getattr(self.app, "ipdetail_win", None) is self:
            self.app.ipdetail_win = None
