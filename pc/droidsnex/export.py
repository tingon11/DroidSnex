"""
Export delle connessioni osservate: CSV, JSON e pcapng (apribile con Wireshark).

Il pcapng NON contiene il traffico reale (l'agent invia solo metadati): per
ogni connessione viene sintetizzato il pacchetto di apertura (TCP SYN, oppure
un datagramma UDP; per il DNS una query vera con il nome cercato) con:
  * timestamp, IP e porte reali della connessione;
  * un commento sul pacchetto con app, UID, host e byte trasferiti;
  * un Name Resolution Block con le coppie IP -> dominio, così Wireshark mostra
    i nomi al posto degli IP (Visualizza > Risoluzione nomi > Risolvi indirizzi di rete).
"""
from __future__ import annotations

import csv
import ipaddress
import json
import os
import struct
import time

from .model import Connection

FIELDS = ["ts_iso", "ts", "app", "uid", "proto", "ipver", "src_ip", "src_port", "dst_ip", "dst_port",
          "host", "host_src", "asn", "org", "bytes_out", "bytes_in", "closed_ts", "error"]


def _iso(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) + f".{int((ts % 1) * 1000):03d}" if ts else ""


def export_all(conns: list[Connection], out_dir: str, label_for=None) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(out_dir, f"droidsnex-{stamp}")
    conns = sorted(conns, key=lambda c: c.ts)
    if label_for:                       # applica eventuali nomi da reverse DNS
        for c in conns:
            label_for(c)
    paths = [write_csv(conns, base + ".csv"), write_json(conns, base + ".json"), write_pcapng(conns, base + ".pcapng")]
    return paths


def write_csv(conns: list[Connection], path: str) -> str:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for c in conns:
            d = c.to_dict()
            d["ts_iso"] = _iso(c.ts)
            w.writerow(d)
    return path


def write_json(conns: list[Connection], path: str) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([c.to_dict() for c in conns], f, indent=1, ensure_ascii=False)
    return path


# ---------------------------------------------------------------------- pcapng

def _pad4(b: bytes) -> bytes:
    return b + b"\x00" * (-len(b) % 4)


def _block(btype: int, body: bytes) -> bytes:
    total = 12 + len(body)
    return struct.pack("<II", btype, total) + body + struct.pack("<I", total)


def _opt(code: int, value: bytes) -> bytes:
    return struct.pack("<HH", code, len(value)) + _pad4(value)


def _opt_end() -> bytes:
    return struct.pack("<HH", 0, 0)


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return ~s & 0xFFFF


def _dns_query(name: str) -> bytes:
    q = b"".join(bytes([len(p)]) + p.encode("ascii", "ignore")[:63] for p in name.strip(".").split(".") if p)
    return struct.pack("!HHHHHH", 0x5D5D, 0x0100, 1, 0, 0, 0) + q + b"\x00" + struct.pack("!HH", 1, 1)


def synth_packet(c: Connection) -> bytes:
    """Ricostruisce il primo pacchetto della connessione (IP grezzo, LINKTYPE_RAW)."""
    src = ipaddress.ip_address(c.src_ip or ("10.215.173.1" if c.ipver == 4 else "fd00::1"))
    dst = ipaddress.ip_address(c.dst_ip)
    if src.version != dst.version:
        src = ipaddress.ip_address("10.215.173.1" if dst.version == 4 else "fd00::1")
    if c.proto == "TCP":
        proto = 6
        l4 = struct.pack("!HHIIBBHHH", c.src_port, c.dst_port, 0, 0, 5 << 4, 0x02, 65535, 0, 0)  # SYN
    else:
        proto = 17
        payload = _dns_query(c.host) if c.dst_port == 53 and c.host else b""
        l4 = struct.pack("!HHHH", c.src_port, c.dst_port, 8 + len(payload), 0) + payload
    if dst.version == 4:
        pseudo = src.packed + dst.packed + struct.pack("!BBH", 0, proto, len(l4))
    else:
        pseudo = src.packed + dst.packed + struct.pack("!I3xB", len(l4), proto)
    csum = _checksum(pseudo + l4)
    off = 16 if proto == 6 else 6
    l4 = l4[:off] + struct.pack("!H", csum) + l4[off + 2:]
    if dst.version == 4:
        hdr = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(l4), 0, 0x4000, 64, proto, 0, src.packed, dst.packed)
        hdr = hdr[:10] + struct.pack("!H", _checksum(hdr)) + hdr[12:]
    else:
        hdr = struct.pack("!IHBB16s16s", 0x60000000, len(l4), proto, 64, src.packed, dst.packed)
    return hdr + l4


def write_pcapng(conns: list[Connection], path: str) -> str:
    with open(path, "wb") as f:
        # Section Header Block
        shb = struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1)
        shb += _opt(4, b"DroidSnex (metadati di connessione, pacchetti sintetici)") + _opt_end()
        f.write(_block(0x0A0D0D0A, shb))
        # Interface Description Block: LINKTYPE_RAW (101) = pacchetti IP senza header L2
        idb = struct.pack("<HHI", 101, 0, 65535) + _opt(2, b"droidsnex-tun") + _opt(9, b"\x06") + _opt_end()
        f.write(_block(1, idb))
        # Name Resolution Block: IP -> nome
        names: dict[str, str] = {}
        for c in conns:
            if c.host and c.dst_ip and c.host_src != "dns-query":
                names.setdefault(c.dst_ip, c.host)
        if names:
            recs = b""
            for ip, name in names.items():
                a = ipaddress.ip_address(ip)
                val = a.packed + name.encode("utf-8", "ignore") + b"\x00"
                recs += struct.pack("<HH", 1 if a.version == 4 else 2, len(val)) + _pad4(val)
            recs += struct.pack("<HH", 0, 0)
            f.write(_block(4, recs + _opt_end()))
        # Enhanced Packet Block per ogni connessione
        for c in conns:
            try:
                pkt = synth_packet(c)
            except ValueError:
                continue
            us = int(c.ts * 1_000_000)
            comment = (f"app={c.app} uid={c.uid} host={c.host or '-'} ({c.host_src or '-'}) "
                       f"out={c.bytes_out}B in={c.bytes_in}B" + (f" org={c.asn} {c.org}" if c.org else "")
                       + (f" err={c.error}" if c.error else "") + " [sintetico DroidSnex]")
            body = struct.pack("<IIIII", 0, us >> 32, us & 0xFFFFFFFF, len(pkt), len(pkt)) + _pad4(pkt)
            body += _opt(1, comment.encode("utf-8")) + _opt_end()
            f.write(_block(6, body))
    return path
