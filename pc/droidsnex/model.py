"""Modello dati: connessioni osservate e aggregazione per destinazione/app."""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field

from .resolve import AsnDb, ReverseDns


@dataclass
class Connection:
    key: str
    id: int
    ts: float
    app: str
    uid: int
    proto: str
    ipver: int
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    host: str | None = None
    host_src: str | None = None      # sni | http | dns | dns-query | rdns
    closed_ts: float | None = None
    bytes_out: int = 0
    bytes_in: int = 0
    error: str | None = None
    asn: str | None = None
    org: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Group:
    dest: str
    app: str
    count: int = 0
    first: float = 0.0
    last: float = 0.0
    ips: set = field(default_factory=set)
    ports: set = field(default_factory=set)
    protos: set = field(default_factory=set)
    org: str = ""
    bytes: int = 0
    active: int = 0


GROUP_MODES = ("dest+app", "dest", "app")
RECORDED = ("conn", "update", "close", "bytes", "dns", "app")   # eventi salvati per il replay
SORT_MODES = ("ultima vista", "n. connessioni", "prima vista", "destinazione", "traffico")


class Monitor:
    """Riceve gli eventi dallo stream e mantiene lo stato. Thread-safe."""

    def __init__(self, rdns: ReverseDns, asn: AsnDb, hide_dns: bool = False, log_path: str | None = None):
        self.rdns, self.asn = rdns, asn
        self.hide_dns = hide_dns
        self.conns: dict[str, Connection] = {}
        self.lock = threading.Lock()
        self.status = "avvio..."
        self.status_ts = time.time()
        self.events = 0
        self.vpn_on: bool | None = None
        self._log = open(log_path, "a", encoding="utf-8") if log_path else None
        self.dns: list[dict] = []                 # query DNS con risposta (evento "dns" dell'agent)
        self.apps: dict[str, dict] = {}           # pacchetto -> nome, versione, icona (base64), permessi
        self.dns_servers: set[str] = set()
        # callback (fuori dal lock) per gli alert: (connessione, prima_volta)
        self.on_conn = None
        self.on_app = None
        self._pending: list = []
        self._prev_totals: dict[str, tuple[int, int]] = {}
        # registrazione: se e' una lista, ogni evento utile al replay viene aggiunto con l'istante
        # di ricezione ("_t"); la sessione la salva su disco (vedi sessions.py / replay.py)
        self.record: list[dict] | None = None

    # ------------------------------------------------------------------ eventi
    def set_status(self, s: str, kind: str = ""):
        self.status, self.status_ts = s, time.time()

    def handle(self, ev: dict):
        kind = ev.get("ev")
        inst = ev.get("_inst", "")
        if self._log:
            # log grezzo di tutto lo stream: utile per rianalisi successive
            self._log.write(json.dumps({k: v for k, v in ev.items() if k != "_inst"}) + "\n")
            self._log.flush()
        if self.record is not None and kind in RECORDED:
            rec = {k: v for k, v in ev.items() if k not in ("_inst", "seq", "icon")}
            rec["_t"] = time.time()
            if inst:
                rec["_i"] = inst          # istanza dello stream: gli id delle connessioni ripartono a ogni riconnessione
            self.record.append(rec)
        with self.lock:
            self.events += 1
            if kind == "conn":
                k = f"{inst}:{ev['id']}"
                c = Connection(
                    key=k, id=ev["id"], ts=ev.get("ts_ms", ev.get("ts", time.time()) * 1000) / 1000.0,
                    app=ev.get("app") or "unknown", uid=ev.get("uid", -1), proto=ev.get("proto", "?"),
                    ipver=ev.get("ipver", 4), src_ip=ev.get("src_ip", ""), src_port=ev.get("src_port", 0),
                    dst_ip=ev.get("dst_ip", ""), dst_port=ev.get("dst_port", 0),
                    host=ev.get("host"), host_src=ev.get("host_src"),
                )
                a = self.asn.lookup(c.dst_ip)
                if a:
                    c.asn, c.org = a
                self.conns[k] = c
                self._pending.append((c, True))
            elif kind == "update":
                c = self.conns.get(f"{inst}:{ev.get('id')}")
                if c and ev.get("host"):
                    c.host, c.host_src = ev["host"], ev.get("host_src")
                    self._pending.append((c, False))
            elif kind == "dns":
                d = {k: v for k, v in ev.items() if k not in ("ev", "seq", "_inst")}
                d.setdefault("ts", time.time())
                self.dns.append(d)
                if ev.get("server"):
                    self.dns_servers.add(ev["server"])
                if len(self.dns) > 5000:
                    del self.dns[:500]
            elif kind == "app":
                pkg = ev.get("pkg")
                if pkg:
                    self.apps[pkg] = {k: v for k, v in ev.items() if k not in ("ev", "seq", "_inst")}
                    if self.on_app:
                        self._pending.append((pkg, None))
            elif kind == "close":
                c = self.conns.get(f"{inst}:{ev.get('id')}")
                if c:
                    c.closed_ts = ev.get("ts", time.time())
                    c.bytes_out, c.bytes_in = ev.get("bytes_out", 0), ev.get("bytes_in", 0)
                    c.error = ev.get("error")
            elif kind == "bytes":
                # contatori live delle connessioni aperte: [[id, byte_uscita, byte_entrata], ...]
                for item in ev.get("flows", ()):
                    try:
                        fid, out, inb = item[0], int(item[1]), int(item[2])
                    except (TypeError, ValueError, IndexError):
                        continue
                    c = self.conns.get(f"{inst}:{fid}")
                    if c and c.closed_ts is None:
                        c.bytes_out, c.bytes_in = out, inb
            elif kind in ("status", "ping"):
                self.vpn_on = ev.get("vpn", self.vpn_on)
        # alert e profili app: fuori dal lock, così le callback possono leggere lo stato
        if self._pending:
            pending, self._pending = self._pending, []
            for item, first in pending:
                try:
                    if first is None:
                        self.on_app(item)
                    elif self.on_conn:
                        self.on_conn(item, first)
                except Exception:  # noqa: BLE001 - un alert rotto non deve fermare lo stream
                    pass

    def app_label(self, pkg: str) -> str:
        """Nome leggibile dell'app se l'agent l'ha mandato, altrimenti il pacchetto."""
        info = self.apps.get(pkg)
        return (info or {}).get("label") or pkg

    def rates_per_app(self) -> dict[str, tuple[int, int]]:
        """Byte (entrata, uscita) trasferiti dall'ultima chiamata, per app. Da chiamare ogni secondo."""
        out: dict[str, list[int]] = {}
        with self.lock:
            seen = set()
            for k, c in self.conns.items():
                seen.add(k)
                prev = self._prev_totals.get(k, (0, 0))
                din, dout = c.bytes_in - prev[0], c.bytes_out - prev[1]
                self._prev_totals[k] = (c.bytes_in, c.bytes_out)
                if din > 0 or dout > 0:
                    acc = out.setdefault(c.app, [0, 0])
                    acc[0] += max(din, 0)
                    acc[1] += max(dout, 0)
            if len(self._prev_totals) > len(seen) + 1000:
                self._prev_totals = {k: v for k, v in self._prev_totals.items() if k in seen}
        return {a: (v[0], v[1]) for a, v in out.items()}

    def reset(self) -> None:
        """Nuova sessione: azzera tutto (tranne il log grezzo)."""
        with self.lock:
            self.conns.clear()
            self.dns.clear()
            self.apps.clear()
            self.dns_servers.clear()
            self._prev_totals.clear()
            self.events = 0

    def close(self):
        if self._log:
            self._log.close()

    # ------------------------------------------------------------------ viste
    def dest_label(self, c: Connection) -> str:
        """Nome della destinazione: SNI/HTTP/DNS dal telefono, altrimenti reverse DNS, altrimenti l'IP."""
        if c.host:
            # Per le query DNS il "nome" è quello cercato, non il server: lo marchiamo
            return f"[dns] {c.host}" if c.host_src == "dns-query" else c.host
        name = self.rdns.get(c.dst_ip)
        if name:
            c.host, c.host_src = name, "rdns"
            return name
        return c.dst_ip

    def snapshot(self) -> list[Connection]:
        with self.lock:
            return list(self.conns.values())

    def groups(self, mode: str = "dest+app", sort: str = "ultima vista", filt: str = "") -> list[Group]:
        out: dict[tuple, Group] = {}
        filt = filt.lower()
        for c in self.snapshot():
            if self.hide_dns and c.dst_port == 53:
                continue
            dest = self.dest_label(c)
            if filt and filt not in dest.lower() and filt not in c.app.lower() and filt not in c.dst_ip:
                continue
            key = (dest, c.app) if mode == "dest+app" else (dest, "") if mode == "dest" else ("", c.app)
            g = out.get(key)
            if g is None:
                g = out[key] = Group(dest=key[0], app=key[1], first=c.ts, last=c.ts)
            g.count += 1
            g.first = min(g.first, c.ts)
            g.last = max(g.last, c.closed_ts or c.ts, c.ts)
            g.ips.add(c.dst_ip)
            g.ports.add(c.dst_port)
            g.protos.add(c.proto)
            g.bytes += c.bytes_in + c.bytes_out
            if c.closed_ts is None:
                g.active += 1
            if c.org and not g.org:
                g.org = f"{c.asn} {c.org}"
            if mode == "app":
                g.dest = f"{len(g.ips)} IP"
            if mode == "dest":
                apps = g.__dict__.setdefault("_apps", set())
                apps.add(c.app)
                g.app = ", ".join(sorted(apps))
        keyf = {
            "ultima vista": lambda g: -g.last,
            "n. connessioni": lambda g: -g.count,
            "prima vista": lambda g: g.first,
            "destinazione": lambda g: (g.dest, g.app),
            "traffico": lambda g: -g.bytes,
        }[sort]
        return sorted(out.values(), key=keyf)
