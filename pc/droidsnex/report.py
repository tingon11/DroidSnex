# DroidSnex — report della sessione.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Report di una sessione in un unico file HTML, senza dipendenze e senza collegamenti esterni:
si apre con qualunque browser, si può archiviare o allegare e si stampa in PDF dal browser
(Stampa → Salva come PDF: in stampa passa da solo ai colori chiari).

Contiene: riepilogo, telefono, mappa (stati colorati in base al traffico, linee verso le città),
destinazioni non fidate in ordine di pericolosità con i motivi, destinazioni fidate, traffico per
app e per stato, alert, segnalibri con gli screenshot (incorporati nel file).

    path = report.write(session, out_dir, tr=tr, rep=reputation, geo=geodb,
                        home=(lat, lon, nome), home_country="IT", shots_dir=cartella_sessioni)
"""
from __future__ import annotations

import base64
import html
import json
import math
import os
import time
from typing import Callable

from . import __version__, risk

WORLD_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gui", "assets", "world.json")
MAP_W, MAP_H = 1000, 470
LAT_TOP, LAT_BOTTOM = 84.0, -58.0
ALERT_KINDS = {"new_untrusted": "nuova destinazione", "new_country": "nuovo paese", "odd_port": "porta insolita",
               "reputation": "reputazione", "doh": "DNS cifrato", "anon": "Tor / VPN"}


def _e(x) -> str:
    return html.escape(str(x if x is not None else ""))


def _bytes(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _when(ts: float, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    return time.strftime(fmt, time.localtime(ts)) if ts else "-"


def _dur(sec: float) -> str:
    sec = int(max(0, sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h} h {m:02d} min" if h else f"{m} min {s:02d} s"


# ---------------------------------------------------------------------------- dati
def collect(session, rep=None, geo=None, home_country: str = "") -> dict:
    """Aggrega le connessioni della sessione per destinazione, app e stato."""
    dests: dict[str, dict] = {}
    apps: dict[str, dict] = {}
    countries: dict[str, dict] = {}
    places: dict[tuple, dict] = {}
    total_out = total_in = 0
    labels = {pkg: (info.get("label") or pkg) for pkg, info in (session.apps or {}).items()}
    for c in session.conns:
        if c.get("host_src") == "dns-query" or c.get("dst_port") == 53:
            continue
        dest = c.get("dest") or c.get("host") or c.get("dst_ip") or "?"
        out, inn = int(c.get("bytes_out") or 0), int(c.get("bytes_in") or 0)
        total_out += out
        total_in += inn
        app = labels.get(c.get("app"), c.get("app") or "?")
        ts = float(c.get("ts") or 0)
        g = dests.setdefault(dest, {"dest": dest, "conns": 0, "out": 0, "in": 0, "apps": set(), "ips": set(), "ports": set(),
                                    "countries": set(), "org": "", "trusted": bool(c.get("trusted")), "first": ts, "last": ts,
                                    "named": False})
        g["conns"] += 1
        g["out"] += out
        g["in"] += inn
        g["apps"].add(app)
        g["ips"].add(c.get("dst_ip") or "")
        g["ports"].add(int(c.get("dst_port") or 0))
        g["first"] = min(g["first"] or ts, ts) if ts else g["first"]
        g["last"] = max(g["last"], float(c.get("closed_ts") or ts))
        g["named"] = g["named"] or bool(c.get("host"))
        if c.get("org") and not g["org"]:
            g["org"] = f"{c.get('asn') or ''} {c['org']}".strip()
        country = (c.get("country") or "").upper()
        if country:
            g["countries"].add(country)
            k = countries.setdefault(country, {"iso": country, "dests": set(), "conns": 0, "bytes": 0, "untrusted": set()})
            k["dests"].add(dest)
            k["conns"] += 1
            k["bytes"] += out + inn
            if not g["trusted"]:
                k["untrusted"].add(dest)
        a = apps.setdefault(app, {"app": app, "conns": 0, "out": 0, "in": 0, "dests": set(), "untrusted": set()})
        a["conns"] += 1
        a["out"] += out
        a["in"] += inn
        a["dests"].add(dest)
        if not g["trusted"]:
            a["untrusted"].add(dest)
        p = geo.lookup(c.get("dst_ip") or "") if geo is not None else None
        if p is not None:
            pl = places.setdefault((round(p.lat, 1), round(p.lon, 1)), {"lat": p.lat, "lon": p.lon, "name": p.name,
                                                                         "bytes": 0, "untrusted": False, "risk": 0, "dests": set()})
            pl["bytes"] += out + inn
            pl["dests"].add(dest)
            pl["untrusted"] = pl["untrusted"] or not g["trusted"]
    for g in dests.values():
        g["rep"] = rep.lookup(g["dest"], g["ips"], g["org"]) if rep is not None else None
        if g["trusted"]:
            g["risk"] = risk.Risk()
        else:
            g["risk"] = risk.assess(g["dest"], g["ips"], g["org"], g["ports"], g["rep"], g["countries"], home_country,
                                    has_name=g["named"] or None)
    for pl in places.values():
        pl["risk"] = max((dests[d]["risk"].level for d in pl["dests"] if not dests[d]["trusted"]), default=0)
    return {"dests": dests, "apps": apps, "countries": countries, "places": list(places.values()),
            "out": total_out, "in": total_in}


# ---------------------------------------------------------------------------- mappa (SVG)
def _xy(lat: float, lon: float) -> tuple[float, float]:
    x = (lon + 180.0) / 360.0 * MAP_W
    y = (LAT_TOP - max(LAT_BOTTOM, min(LAT_TOP, lat))) / (LAT_TOP - LAT_BOTTOM) * MAP_H
    return round(x, 1), round(y, 1)


def _world() -> tuple[list, list, dict]:
    try:
        with open(WORLD_FILE, encoding="utf-8") as f:
            d = json.load(f)
        rings = d["rings"]
        iso = d.get("iso") or [""] * len(rings)
        return rings, iso, d.get("names") or {}
    except (OSError, ValueError, KeyError):
        return [], [], {}


def map_svg(data: dict, home: tuple | None, tr: Callable) -> str:
    rings, iso, _names = _world()
    if not rings:
        return ""
    vol = {k: v["bytes"] + 1 for k, v in data["countries"].items()}
    top = max(vol.values(), default=0)
    out = [f'<svg class="map" viewBox="0 0 {MAP_W} {MAP_H}" xmlns="http://www.w3.org/2000/svg" role="img">',
           f'<rect width="{MAP_W}" height="{MAP_H}" class="sea"/>']
    for pts, code in zip(rings, iso):
        d = "M" + " L".join(f"{x},{y}" for x, y in (_xy(pts[i + 1], pts[i]) for i in range(0, len(pts) - 1, 2))) + "Z"
        lvl = 1 + min(4, int(4 * (vol[code] / top) ** 0.4)) if top and code in vol else 0
        out.append(f'<path d="{d}" class="land h{lvl}"/>')
    places = sorted(data["places"], key=lambda p: (p["untrusted"], p["bytes"]))
    if home and home[0] is not None and home[1] is not None:
        hx, hy = _xy(home[0], home[1])
        for p in places:
            x, y = _xy(p["lat"], p["lon"])
            if abs(p["lon"] - home[1]) > 180:                 # dall'altra parte: niente linea che attraversa tutta la mappa
                continue
            mx, my = (hx + x) / 2, (hy + y) / 2 - min(90, math.hypot(x - hx, y - hy) * 0.22)
            col = risk.color_of(p["risk"]) if p["untrusted"] else "#34d399"
            out.append(f'<path d="M{hx},{hy} Q{mx:.1f},{my:.1f} {x},{y}" fill="none" stroke="{col}" stroke-width="0.9" opacity="0.75"/>')
    else:
        hx = hy = None
    bmax = max((p["bytes"] for p in places), default=0) or 1
    for p in places:
        x, y = _xy(p["lat"], p["lon"])
        r = 2.2 + 3.5 * math.sqrt(p["bytes"] / bmax)
        col = risk.color_of(p["risk"]) if p["untrusted"] else "#34d399"
        out.append(f'<circle cx="{x}" cy="{y}" r="{r:.1f}" fill="{col}" class="dot"><title>{_e(p["name"])} · '
                   f'{len(p["dests"])} · {_bytes(p["bytes"])}</title></circle>')
    if hx is not None:
        out.append(f'<rect x="{hx - 3.5}" y="{hy - 6}" width="7" height="12" rx="1.6" class="phone"/>')
        out.append(f'<text x="{hx}" y="{hy + 17}" class="home">{_e(home[2] if len(home) > 2 and home[2] else tr("telefono"))}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------------------------------------------------------------------------- HTML
CSS = """
:root{--bg:#07090c;--panel:#0d1117;--panel2:#121821;--border:#1c2530;--text:#d5dde6;--soft:#aab6c3;--dim:#6e7b89;
--accent:#7b95dd;--ok:#34d399;--warn:#fbbf24;--err:#f87171;--sea:#080c12;--land:#141c27;--edge:#263444}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 "Segoe UI",Inter,"Helvetica Neue",Arial,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
header{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;border-bottom:1px solid var(--border);padding-bottom:14px}
h1{font-size:24px;margin:0;letter-spacing:.3px}h1 b{color:var(--accent);font-weight:600}
h2{font-size:13px;letter-spacing:1.4px;text-transform:uppercase;color:var(--accent);margin:34px 0 10px;
border-left:3px solid var(--accent);padding-left:9px}
.meta{color:var(--dim);font-size:12px;text-align:right}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:18px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:10px 12px}
.card small{display:block;color:var(--dim);font-size:10.5px;letter-spacing:1px;text-transform:uppercase}
.card span{font:600 21px/1.3 Consolas,"Cascadia Mono",monospace}
.err{color:var(--err)}.ok{color:var(--ok)}.warn{color:var(--warn)}.dim{color:var(--dim)}
table{width:100%;border-collapse:collapse;background:var(--panel);border:1px solid var(--border);border-radius:6px;font-size:12.5px}
th{font-size:10.5px;letter-spacing:.9px;text-transform:uppercase;color:var(--dim);text-align:left;
padding:7px 9px;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:6px 9px;border-bottom:1px solid var(--border);vertical-align:top;overflow-wrap:anywhere}
tr:last-child td{border-bottom:0}td.n,th.n{text-align:right;white-space:nowrap;font-family:Consolas,"Cascadia Mono",monospace}
td.m{font-family:Consolas,"Cascadia Mono",monospace;font-size:12px}
.chip{display:inline-block;border-radius:10px;padding:1px 8px;font-size:11px;font-weight:600;color:#0a0d12;white-space:nowrap}
.why{color:var(--soft);font-size:11.5px}
.kv{display:grid;grid-template-columns:150px 1fr;gap:3px 14px;background:var(--panel);border:1px solid var(--border);
border-radius:6px;padding:12px 14px}.kv b{color:var(--dim);font-weight:400}
.map{width:100%;height:auto;border:1px solid var(--border);border-radius:6px;display:block}
.sea{fill:var(--sea)}.land{fill:var(--land);stroke:var(--edge);stroke-width:.5}
.h1{fill:#1b2540}.h2{fill:#243257}.h3{fill:#30437a}.h4{fill:#3e569c}.h5{fill:#5069b8}
.dot{stroke:var(--sea);stroke-width:.8}.phone{fill:var(--panel2);stroke:var(--accent);stroke-width:1.4}
.home{fill:var(--text);font:600 11px Consolas,monospace;text-anchor:middle}
.legend{color:var(--dim);font-size:11.5px;margin-top:6px}.legend i{font-style:normal;margin-right:10px}
details{margin-top:8px}summary{cursor:pointer;color:var(--soft);padding:6px 0}
.marks{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px}
.mark{background:var(--panel);border:1px solid var(--border);border-radius:6px;padding:10px}
.mark img{width:100%;border-radius:4px;margin-top:8px;border:1px solid var(--border)}
.mark time{font-family:Consolas,monospace;color:var(--accent)}
footer{margin-top:40px;border-top:1px solid var(--border);padding-top:12px;color:var(--dim);font-size:11.5px}
@media print{:root{--bg:#fff;--panel:#fff;--panel2:#f3f5f8;--border:#c9d1da;--text:#111;--soft:#333;--dim:#555;
--accent:#2f4aa0;--sea:#eef3f8;--land:#fbfbf9;--edge:#aab4c0}
.h1{fill:#dfe6f7}.h2{fill:#c3d0f0}.h3{fill:#a3b6e6}.h4{fill:#8098d8}.h5{fill:#5f7bc8}
main{max-width:none;padding:0}h2{break-after:avoid}tr,.mark,.card{break-inside:avoid}details{display:block}
details>summary{display:none}body{font-size:11px}table{font-size:10.5px}}
"""


def _chip(level: int, tr: Callable) -> str:
    return f'<span class="chip" style="background:{risk.COLORS[level]}">{level} · {_e(tr(risk.NAMES[level]))}</span>'


def _dest_rows(items: list[dict], tr: Callable, with_risk: bool) -> str:
    rows = []
    for g in items:
        ips = sorted(i for i in g["ips"] if i and i != g["dest"])
        ports = sorted(p for p in g["ports"] if p)
        why = ""
        if with_risk:
            reasons = ", ".join(tr(risk.REASONS[k]) for k in g["risk"].reasons)
            why = f'<td>{_chip(g["risk"].level, tr)}<div class="why">{_e(reasons)}</div></td>'
        rows.append(
            f'<tr>{why}<td class="m">{_e(g["dest"])}<div class="why">{_e(", ".join(ips[:4]))}{" …" if len(ips) > 4 else ""}</div></td>'
            f'<td>{_e(", ".join(sorted(g["apps"])))}</td>'
            f'<td>{_e(g["org"] or "-")}<div class="why">{_e(" ".join(sorted(g["countries"])))}</div></td>'
            f'<td class="m">{_e(", ".join(map(str, ports[:6])))}{" …" if len(ports) > 6 else ""}</td>'
            f'<td class="n">{g["conns"]}</td><td class="n">{_bytes(g["out"])}</td><td class="n">{_bytes(g["in"])}</td>'
            f'<td class="n">{_when(g["first"], "%H:%M:%S")}</td><td class="n">{_when(g["last"], "%H:%M:%S")}</td></tr>')
    return "".join(rows)


def _dest_table(items: list[dict], tr: Callable, with_risk: bool) -> str:
    head = (f'<th>{_e(tr("pericolosità"))}</th>' if with_risk else "") + "".join(
        f'<th{" class=n" if n else ""}>{_e(t)}</th>' for t, n in (
            (tr("destinazione"), 0), ("app", 0), (tr("organizzazione"), 0), (tr("porte"), 0), (tr("conn"), 1),
            (tr("inviati"), 1), (tr("ricevuti"), 1), (tr("prima"), 1), (tr("ultima"), 1)))
    return f"<table><thead><tr>{head}</tr></thead><tbody>{_dest_rows(items, tr, with_risk)}</tbody></table>"


def build(session, *, tr: Callable = lambda s, **kw: s.format(**kw) if kw else s, rep=None, geo=None,
          home: tuple | None = None, home_country: str = "", shots_dir: str | None = None, lang: str = "it") -> str:
    """Il report come testo HTML."""
    data = collect(session, rep, geo, home_country)
    dests = data["dests"]
    untrusted = sorted((g for g in dests.values() if not g["trusted"]),
                       key=lambda g: (-g["risk"].level, -(g["out"] + g["in"]), g["dest"]))
    trusted = sorted((g for g in dests.values() if g["trusted"]), key=lambda g: (-(g["out"] + g["in"]), g["dest"]))
    dev = session.device or {}
    model = " ".join(x for x in (str(dev.get("brand") or "").title(), str(dev.get("model") or "")) if x).strip()
    _rings, _iso, names = _world()
    high = sum(1 for g in untrusted if g["risk"].level >= 3)
    o = ['<!DOCTYPE html>', f'<html lang="{_e(lang)}"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width,initial-scale=1">',
         f'<title>DroidSnex · {_e(tr("Report della sessione"))} {_e(session.id)}</title><style>{CSS}</style></head><body><main>',
         f'<header><div><h1>Droid<b>Snex</b> · {_e(tr("Report della sessione"))}</h1>'
         f'<div class="dim">{_e(model or "?")} · {_e(_when(session.started))} · {_e(_dur(session.duration))}'
         + (f' · <span class="warn">{_e(tr("sessione dimostrativa (dati simulati)"))}</span>' if session.demo else "")
         + f'</div></div><div class="meta">{_e(tr("sessione"))} {_e(session.id)}<br>{_e(tr("generato il"))} {_e(_when(time.time()))}'
           f'<br>DroidSnex v{_e(__version__)}</div></header>']
    cards = ((tr("connessioni"), sum(g["conns"] for g in dests.values()), ""), (tr("destinazioni"), len(dests), ""),
             (tr("non fidate"), len(untrusted), "err"), (tr("rischio alto (3-5)"), high, "err" if high else ""),
             (tr("fidate"), len(trusted), "ok"), (tr("stati"), len(data["countries"]), ""),
             (tr("inviati"), _bytes(data["out"]), ""), (tr("ricevuti"), _bytes(data["in"]), ""),
             ("alert", len(session.alerts), "warn" if session.alerts else ""), (tr("segnalibri"), len(session.marks), ""))
    o.append('<div class="cards">' + "".join(
        f'<div class="card"><small>{_e(k)}</small><span class="{c}">{_e(v)}</span></div>' for k, v, c in cards) + "</div>")

    o.append(f'<h2>{_e(tr("Telefono"))}</h2><div class="kv">')
    for key, label in (("model", tr("modello")), ("android", "Android"), ("serial", tr("seriale")), ("android_id", "Android ID"),
                       ("imei", "IMEI"), ("wifi_mac", "MAC Wi-Fi")):
        o.append(f'<b>{_e(label)}</b><span>{_e((model if key == "model" else dev.get(key)) or "-")}</span>')
    o.append(f'<b>{_e(tr("inizio"))}</b><span>{_e(_when(session.started))}</span>'
             f'<b>{_e(tr("fine"))}</b><span>{_e(_when(session.ended) if session.ended else "-")}</span>'
             f'<b>{_e(tr("durata"))}</b><span>{_e(_dur(session.duration))}</span></div>')

    svg = map_svg(data, home, tr)
    if svg and data["countries"]:
        o.append(f'<h2>{_e(tr("Mappa"))}</h2>{svg}<div class="legend"><i class="ok">● {_e(tr("fidate"))}</i>'
                 + "".join(f'<i style="color:{c}">● {_e(tr(n))}</i>' for c, n in zip(risk.COLORS, risk.NAMES))
                 + f'<i>{_e(tr("stati più chiari = più traffico"))}</i></div>')

    o.append(f'<h2>{_e(tr("Destinazioni non fidate"))} ({len(untrusted)})</h2>')
    o.append(_dest_table(untrusted, tr, True) if untrusted else f'<p class="dim">{_e(tr("nessuna"))}</p>')
    if trusted:
        o.append(f'<h2>{_e(tr("Destinazioni fidate"))} ({len(trusted)})</h2>'
                 f'<details{" open" if len(trusted) <= 15 else ""}><summary>{_e(tr("mostra / nascondi"))}</summary>'
                 f'{_dest_table(trusted, tr, False)}</details>')

    o.append(f'<h2>{_e(tr("Traffico per app"))}</h2><table><thead><tr><th>app</th><th class=n>{_e(tr("conn"))}</th>'
             f'<th class=n>{_e(tr("destinazioni"))}</th><th class=n>{_e(tr("non fidate"))}</th><th class=n>{_e(tr("inviati"))}</th>'
             f'<th class=n>{_e(tr("ricevuti"))}</th></tr></thead><tbody>')
    for a in sorted(data["apps"].values(), key=lambda a: -(a["out"] + a["in"])):
        o.append(f'<tr><td>{_e(a["app"])}</td><td class="n">{a["conns"]}</td><td class="n">{len(a["dests"])}</td>'
                 f'<td class="n {"err" if a["untrusted"] else ""}">{len(a["untrusted"])}</td>'
                 f'<td class="n">{_bytes(a["out"])}</td><td class="n">{_bytes(a["in"])}</td></tr>')
    o.append("</tbody></table>")

    if data["countries"]:
        o.append(f'<h2>{_e(tr("Traffico per stato"))}</h2><table><thead><tr><th>{_e(tr("stato"))}</th>'
                 f'<th class=n>{_e(tr("destinazioni"))}</th><th class=n>{_e(tr("non fidate"))}</th><th class=n>{_e(tr("conn"))}</th>'
                 f'<th class=n>{_e(tr("traffico"))}</th></tr></thead><tbody>')
        for k in sorted(data["countries"].values(), key=lambda k: -k["bytes"]):
            o.append(f'<tr><td>{_e(k["iso"])} · {_e(names.get(k["iso"], ""))}</td><td class="n">{len(k["dests"])}</td>'
                     f'<td class="n {"err" if k["untrusted"] else ""}">{len(k["untrusted"])}</td>'
                     f'<td class="n">{k["conns"]}</td><td class="n">{_bytes(k["bytes"])}</td></tr>')
        o.append("</tbody></table>")

    if session.alerts:
        o.append(f'<h2>Alert ({len(session.alerts)})</h2><table><thead><tr><th>{_e(tr("ora"))}</th><th>{_e(tr("tipo"))}</th>'
                 f'<th>app</th><th>{_e(tr("destinazione"))}</th><th>{_e(tr("dettaglio"))}</th></tr></thead><tbody>')
        labels = {pkg: (info.get("label") or pkg) for pkg, info in (session.apps or {}).items()}
        for a in session.alerts[:500]:
            cls = {"err": "err", "warn": "warn"}.get(a.get("level"), "")
            o.append(f'<tr><td class="n">{_when(a.get("ts", 0), "%H:%M:%S")}</td>'
                     f'<td class="{cls}">{_e(tr(ALERT_KINDS.get(a.get("kind"), a.get("kind") or "")))}</td>'
                     f'<td>{_e(labels.get(a.get("app"), a.get("app")))}</td><td class="m">{_e(a.get("dest"))}</td>'
                     f'<td>{_e(a.get("text"))}</td></tr>')
        o.append("</tbody></table>")

    if session.marks:
        o.append(f'<h2>{_e(tr("Segnalibri"))} ({len(session.marks)})</h2><div class="marks">')
        for i, m in enumerate(sorted(session.marks, key=lambda m: m.get("ts", 0)), start=1):
            img = ""
            shot = m.get("shot")
            if shot and shots_dir:
                try:
                    with open(os.path.join(shots_dir, os.path.basename(shot)), "rb") as f:
                        raw = f.read()
                    if len(raw) <= 8 << 20:
                        img = f'<img alt="screenshot {i}" src="data:image/png;base64,{base64.b64encode(raw).decode()}">'
                except OSError:
                    img = ""
            o.append(f'<div class="mark"><time>{_e(_when(m.get("ts", 0), "%H:%M:%S"))}</time> · 🔖 {i}'
                     f'<div>{_e(m.get("note") or "-")}</div>{img}</div>')
        o.append("</div>")

    note = tr("Report generato da DroidSnex sul PC dell'utente: nessun dato è stato inviato all'esterno. "
              "Posizioni, organizzazioni e livelli di pericolosità sono indicativi (database pubblici e liste "
              "di reputazione) e vanno verificati prima di trarne conclusioni.")
    o.append(f"<footer>{_e(note)}</footer>")
    o.append("</main></body></html>")
    return "\n".join(o)


def write(session, out_dir: str, **kw) -> str:
    """Scrive `<out_dir>/droidsnex-report-<sessione>.html` e ne ritorna il percorso."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"droidsnex-report-{session.id or 'session'}.html")
    text = build(session, **kw)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    return path
