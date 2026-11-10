#!/usr/bin/env python3
"""
Agent finto che parla lo stesso protocollo dell'app Android (JSON-lines su TCP).
Serve per provare il programma PC senza telefono:

    python tools/fake_agent.py --port 8899
    python run.py monitor --no-adb --port 8899
"""
import argparse
import base64
import json
import random
import socket
import struct
import threading
import time
import uuid
import zlib

APPS = ["com.whatsapp", "com.instagram.android", "com.google.android.youtube", "com.android.chrome",
        "com.spotify.music", "android.dns", "com.google.android.gms"]
HOSTS = {
    "graph.facebook.com": "157.240.1.1", "i.instagram.com": "157.240.2.174", "www.youtube.com": "142.250.180.14",
    "r3---sn-xyz.googlevideo.com": "173.194.10.8", "spclient.wg.spotify.com": "35.186.224.25",
    "www.google.com": "142.250.180.4", "play.googleapis.com": "142.250.184.10", None: "93.184.216.34",
    "api.telegram.org": "149.154.167.220", "mmx-ds.cdn.whatsapp.net": "31.13.86.51",
    "tracker.adnet.cn": "47.246.23.10", "t.appsflyer.com": "52.56.10.5", "api.mixpanel.com": "35.190.25.25",
    "cdn.yandex.ru": "77.88.55.80", "log.tiktokv.com": "161.117.70.145", "sdk.sentry.io": "34.120.195.249",
}
# connessioni "pesanti" (video, musica): generano molto traffico in entrata
HEAVY = {"r3---sn-xyz.googlevideo.com": 900_000, "www.youtube.com": 120_000, "spclient.wg.spotify.com": 60_000,
         "mmx-ds.cdn.whatsapp.net": 250_000}

LABELS = {"com.whatsapp": ("WhatsApp", "2.24.20.80", (37, 211, 102)), "com.instagram.android": ("Instagram", "350.0", (225, 48, 108)),
          "com.google.android.youtube": ("YouTube", "19.40", (255, 0, 0)), "com.android.chrome": ("Chrome", "130.0", (66, 133, 244)),
          "com.spotify.music": ("Spotify", "8.9.80", (30, 215, 96)), "com.google.android.gms": ("Google Play Services", "24.40", (52, 168, 83))}
PERMS = ["android.permission.INTERNET", "android.permission.ACCESS_NETWORK_STATE", "android.permission.CAMERA",
         "android.permission.READ_CONTACTS", "android.permission.ACCESS_FINE_LOCATION", "android.permission.RECORD_AUDIO",
         "android.permission.READ_SMS", "android.permission.POST_NOTIFICATIONS", "android.permission.WAKE_LOCK"]
DNS_SERVER = "192.168.1.1"


def png_icon(rgb, size=64):
    """PNG quadrato pieno (con un cerchio chiaro al centro), senza librerie: per le icone finte."""
    r, g, b = rgb
    rows = b""
    for y in range(size):
        row = b"\x00"
        for x in range(size):
            inside = (x - size / 2) ** 2 + (y - size / 2) ** 2 < (size * 0.28) ** 2
            row += bytes((255, 255, 255)) if inside else bytes((r, g, b))
        rows += row
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def app_event(pkg):
    label, ver, rgb = LABELS.get(pkg, (pkg, "1.0", (120, 120, 120)))
    perms = [{"name": p, "granted": random.random() < 0.7} for p in random.sample(PERMS, 5)]
    return {"ev": "app", "pkg": pkg, "uid": 10000 + APPS.index(pkg), "label": label, "version": ver, "system": pkg.startswith("com.google"),
            "installed": int(time.time()) - 86400 * 30, "updated": int(time.time()) - 86400 * 3, "target_sdk": 34,
            "perms": perms, "icon": base64.b64encode(png_icon(rgb)).decode()}


history, lock, clients = [], threading.Lock(), []
reported_apps = set()
seq = 0
INSTANCE = uuid.uuid4().hex[:8]


def emit(obj, keep=True):
    global seq
    with lock:
        seq += 1
        obj["seq"] = seq
        line = json.dumps(obj) + "\n"
        if keep:
            history.append((seq, line))
        for c in list(clients):
            try:
                c.sendall(line.encode())
            except OSError:
                clients.remove(c)


live = {}          # id -> [byte_uscita, byte_entrata, velocità_entrata, velocità_uscita]
live_lock = threading.Lock()


def generator(rate):
    cid = 0
    while True:
        time.sleep(random.expovariate(rate))
        with live_lock:
            open_ids = list(live)
        if open_ids and random.random() < 0.4:
            fid = open_ids[0] if random.random() < 0.7 else random.choice(open_ids)
            with live_lock:
                out, inb, *_ = live.pop(fid)
            emit({"ev": "close", "id": fid, "ts": int(time.time()), "bytes_out": out, "bytes_in": inb,
                  "duration_ms": random.randint(50, 60000)})
            continue
        cid += 1
        app = random.choice(APPS)
        host = random.choice(list(HOSTS))
        dns = app == "android.dns"
        now = time.time()
        if app != "android.dns" and app not in reported_apps:
            reported_apps.add(app)
            emit(app_event(app))
        if dns and host:
            # la risposta DNS completa (evento "dns"): a volte un CNAME, a volte NXDOMAIN
            nx = random.random() < 0.08
            emit({"ev": "dns", "ts": int(now), "app": random.choice(APPS[:-2]), "uid": 10001, "qname": host,
                  "qtype": random.choice(["A", "A", "A", "AAAA", "HTTPS"]), "rcode": 3 if nx else 0,
                  "answers": [] if nx else [HOSTS[host]], "cnames": [] if random.random() < 0.6 else [f"edge.{host}"],
                  "server": DNS_SERVER, "rtt_ms": random.randint(8, 120), "ttl": random.choice([60, 300, 3600]), "conn": cid})
        if not dns and random.random() < 0.03:
            # DNS-over-HTTPS: resolver pubblico contattato sulla 443 (scavalca il DNS di sistema)
            emit({"ev": "conn", "id": cid, "ts": int(now), "ts_ms": int(now * 1000), "app": "com.android.chrome", "uid": 10003,
                  "proto": "TCP", "ipver": 4, "src_ip": "10.215.173.1", "src_port": random.randint(30000, 60000),
                  "dst_ip": "8.8.8.8", "dst_port": 443, "host": "dns.google", "host_src": "sni"})
            with live_lock:
                live[cid] = [300, 900, 400, 200]
            continue
        if not dns and random.random() < 0.04:
            host = "tracker.adnet.cn"
        known = host is not None and (dns or random.random() < 0.5)
        emit({"ev": "conn", "id": cid, "ts": int(now), "ts_ms": int(now * 1000), "app": app,
              "uid": 10000 + APPS.index(app), "proto": "UDP" if dns or random.random() < 0.1 else "TCP", "ipver": 4,
              "src_ip": "10.215.173.1", "src_port": random.randint(30000, 60000),
              "dst_ip": "192.168.1.1" if dns else HOSTS[host], "dst_port": 53 if dns else random.choice([443, 443, 80, 5222]),
              "host": host if known else None,
              "host_src": ("dns-query" if dns else "dns") if known else None})
        if not dns and host and random.random() < 0.5:
            emit({"ev": "update", "id": cid, "ts": int(now), "host": host, "host_src": "sni"})
        heavy = HEAVY.get(host, 0)
        rin = heavy * random.uniform(0.3, 1.5) if heavy else random.choice([0, 200, 2_000, 15_000])
        rout = random.choice([0, 100, 800, 6_000, 40_000]) if not dns else 60
        with live_lock:
            live[cid] = [random.randint(80, 600), random.randint(0, 4000), rin, rout]


def traffic():
    """Ogni secondo: contatori di byte delle connessioni aperte (come l'evento 'bytes' dell'agent)."""
    while True:
        time.sleep(1)
        flows = []
        with live_lock:
            for fid, v in live.items():
                if v[2] or v[3]:
                    v[0] += int(v[3] * random.uniform(0.2, 1.2))
                    v[1] += int(v[2] * random.uniform(0.2, 1.2))
                    flows.append([fid, v[0], v[1]])
        if flows:
            emit({"ev": "bytes", "ts": int(time.time()), "flows": flows}, keep=False)


def serve(conn):
    conn.settimeout(0.7)
    since = 0
    try:
        since = json.loads(conn.makefile().readline() or "{}").get("seq", 0)
    except (OSError, ValueError):
        pass
    conn.settimeout(None)
    with lock:
        backlog = [l for s, l in history if s > since]
        hello = {"ev": "hello", "agent": "droidsnex-fake", "version": 1, "instance": INSTANCE,
                 "last_seq": seq, "replay": len(backlog), "vpn": True}
        conn.sendall((json.dumps(hello) + "\n" + "".join(backlog)).encode())
        clients.append(conn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--rate", type=float, default=3.0, help="connessioni al secondo (media)")
    a = ap.parse_args()
    threading.Thread(target=generator, args=(a.rate,), daemon=True).start()
    threading.Thread(target=traffic, daemon=True).start()
    srv = socket.create_server(("127.0.0.1", a.port))
    print(f"fake agent su 127.0.0.1:{a.port}")
    while True:
        c, _ = srv.accept()
        threading.Thread(target=serve, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
