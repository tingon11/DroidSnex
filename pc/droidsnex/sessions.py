"""Sessioni di monitoraggio salvate su disco, per telefono, e confronto fra due sessioni.

Ogni Start registra una sessione: connessioni, query DNS, app viste, alert e i
dati del telefono. Alla fine (Stop o chiusura) viene scritta in
pc/sessions/<telefono>/<data-ora>.json.gz; durante il monitor viene salvata
anche ogni minuto, così non si perde nulla se il programma crasha.

Dalla versione 2 del formato la sessione contiene anche gli eventi ricevuti dal
telefono con l'istante di arrivo ("events") e i segnalibri presi durante il monitor
("marks": istante, nota, screenshot): servono al replay (replay.py). Le sessioni
vecchie, senza eventi, si aprono e si confrontano ma non si possono rivedere.

Il telefono è identificato con quello che adb permette di leggere: seriale,
Android ID, modello e, quando il sistema li espone, IMEI e MAC Wi-Fi.
La cartella del telefono prende il nome dall'IMEI se c'è, altrimenti
dall'Android ID, altrimenti dal seriale.
"""
from __future__ import annotations

import gzip
import json
import os
import re
import time
from dataclasses import dataclass, field

FORMAT = 2


def device_key(dev: dict) -> str:
    for k in ("imei", "android_id", "serial"):
        v = (dev or {}).get(k)
        if v:
            return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(v))[:40]
    return "sconosciuto"


def device_title(dev: dict) -> str:
    """Nome leggibile del telefono: modello + seriale (o IMEI)."""
    dev = dev or {}
    model = " ".join(x for x in (dev.get("brand", "").title(), dev.get("model", "")) if x).strip()
    ident = dev.get("imei") or dev.get("serial") or dev.get("android_id") or "?"
    return f"{model or '?'}  ·  {ident}"


@dataclass
class Session:
    id: str                                  # es. 20261106-224512
    device: dict = field(default_factory=dict)
    started: float = 0.0
    ended: float = 0.0
    demo: bool = False
    conns: list = field(default_factory=list)      # Connection.to_dict() + "dest" (nome mostrato) + "trusted"
    dns: list = field(default_factory=list)
    apps: dict = field(default_factory=dict)       # pkg -> info (senza icona)
    alerts: list = field(default_factory=list)
    events: list = field(default_factory=list)     # eventi registrati (replay), con "_t" = istante di arrivo
    marks: list = field(default_factory=list)      # segnalibri: {ts, note, shot}
    path: str = ""

    @property
    def replayable(self) -> bool:
        return bool(self.events)

    # ------------------------------------------------------------- riassunti
    @property
    def duration(self) -> float:
        return max(0.0, (self.ended or time.time()) - self.started)

    def dests(self) -> dict[str, dict]:
        """dest -> {conns, bytes, apps, ips, org, trusted}"""
        out: dict[str, dict] = {}
        for c in self.conns:
            d = c.get("dest") or c.get("host") or c.get("dst_ip")
            if c.get("host_src") == "dns-query" or c.get("dst_port") == 53:
                continue
            g = out.setdefault(d, {"conns": 0, "bytes": 0, "apps": set(), "ips": set(), "org": "", "trusted": c.get("trusted", False),
                                   "countries": set()})
            g["conns"] += 1
            g["bytes"] += int(c.get("bytes_in") or 0) + int(c.get("bytes_out") or 0)
            g["apps"].add(c.get("app", "?"))
            g["ips"].add(c.get("dst_ip", ""))
            if c.get("org") and not g["org"]:
                g["org"] = f"{c.get('asn', '')} {c['org']}".strip()
            if c.get("country"):
                g["countries"].add(c["country"])
        return out

    def app_names(self) -> set[str]:
        return {c.get("app", "?") for c in self.conns}

    def to_json(self) -> dict:
        return {"format": FORMAT, "id": self.id, "device": self.device, "started": self.started, "ended": self.ended,
                "demo": self.demo, "conns": self.conns, "dns": self.dns, "apps": self.apps, "alerts": self.alerts,
                "events": self.events, "marks": self.marks}

    @classmethod
    def from_json(cls, d: dict, path: str = "") -> "Session":
        s = cls(id=d.get("id", ""), device=d.get("device") or {}, started=d.get("started", 0), ended=d.get("ended", 0),
                demo=d.get("demo", False), conns=d.get("conns") or [], dns=d.get("dns") or [], apps=d.get("apps") or {},
                alerts=d.get("alerts") or [], events=d.get("events") or [], marks=d.get("marks") or [], path=path)
        return s


class SessionStore:
    def __init__(self, root: str):
        self.root = root

    def device_dir(self, dev: dict) -> str:
        return os.path.join(self.root, device_key(dev))

    def save(self, s: Session) -> str:
        d = self.device_dir(s.device)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{s.id}.json.gz")
        tmp = path + ".part"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(s.to_json(), f, ensure_ascii=False)
        os.replace(tmp, path)
        s.path = path
        return path

    def load(self, path: str) -> Session:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return Session.from_json(json.load(f), path)

    def devices(self) -> list[dict]:
        """[{key, dir, device, sessions: [summary...]}] ordinati per ultima sessione."""
        out = []
        if not os.path.isdir(self.root):
            return out
        for key in os.listdir(self.root):
            d = os.path.join(self.root, key)
            if not os.path.isdir(d):
                continue
            sessions = []
            for name in sorted(os.listdir(d), reverse=True):
                if not name.endswith(".json.gz"):
                    continue
                p = os.path.join(d, name)
                meta = self._summary(p)
                if meta:
                    sessions.append(meta)
            if sessions:
                out.append({"key": key, "dir": d, "device": sessions[0]["device"], "sessions": sessions})
        out.sort(key=lambda x: -(x["sessions"][0]["started"] if x["sessions"] else 0))
        return out

    _cache: dict = {}

    def _summary(self, path: str) -> dict | None:
        try:
            st = os.stat(path)
            key = (path, st.st_mtime, st.st_size)
            if key in self._cache:
                return self._cache[key]
            s = self.load(path)
        except (OSError, ValueError):
            return None
        dests = s.dests()
        meta = {"path": path, "id": s.id, "device": s.device, "started": s.started, "ended": s.ended, "demo": s.demo,
                "duration": s.duration, "conns": len(s.conns), "dests": len(dests),
                "untrusted": sum(1 for g in dests.values() if not g["trusted"]),
                "apps": len(s.app_names()), "alerts": len(s.alerts), "dns": len(s.dns), "size": st.st_size,
                "replay": s.replayable, "events": len(s.events), "marks": len(s.marks)}
        self._cache[key] = meta
        return meta

    def delete(self, path: str) -> None:
        os.remove(path)
        d = os.path.dirname(path)
        if not os.listdir(d):
            os.rmdir(d)


def compare(a: Session, b: Session) -> dict:
    """Cosa è cambiato da a (prima) a b (dopo)."""
    da, db = a.dests(), b.dests()
    apps_a, apps_b = a.app_names(), b.app_names()
    orgs_a = {g["org"] for g in da.values() if g["org"]}
    orgs_b = {g["org"] for g in db.values() if g["org"]}
    cc_a = set().union(*(g["countries"] for g in da.values())) if da else set()
    cc_b = set().union(*(g["countries"] for g in db.values())) if db else set()
    new = sorted(set(db) - set(da), key=lambda d: -db[d]["bytes"])
    gone = sorted(set(da) - set(db), key=lambda d: -da[d]["bytes"])
    common = set(da) & set(db)
    changed = []
    for d in common:
        x, y = da[d], db[d]
        if x["conns"] != y["conns"] or x["apps"] != y["apps"] or x["trusted"] != y["trusted"]:
            changed.append((d, x, y))
    changed.sort(key=lambda t: -abs(t[2]["conns"] - t[1]["conns"]))
    return {
        "new_dests": [(d, db[d]) for d in new], "gone_dests": [(d, da[d]) for d in gone], "changed": changed,
        "new_apps": sorted(apps_b - apps_a), "gone_apps": sorted(apps_a - apps_b),
        "new_orgs": sorted(orgs_b - orgs_a), "new_countries": sorted(cc_b - cc_a),
        "common": len(common),
    }
