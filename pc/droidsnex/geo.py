"""Geolocalizzazione degli IP con un database locale (DB-IP City Lite o GeoLite2-City, formato .mmdb).

Il lettore del formato MaxMind DB è scritto qui in Python puro (nessuna
dipendenza): il file viene aperto con mmap, quindi anche un database da
130 MB non viene caricato tutto in memoria. Formato:
https://maxmind.github.io/MaxMind-DB/

    db = GeoDb("data/dbip-city-lite.mmdb")
    db.lookup("8.8.8.8")  ->  Place(lat=37.4, lon=-122.1, city="Mountain View", country="US")

Il download del database DB-IP City Lite (licenza CC BY 4.0, aggiornato ogni
mese) è in `download_dbip()`.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import ipaddress
import mmap
import os
import struct
import urllib.request
from dataclasses import dataclass
from typing import Callable

USER_AGENT = "DroidSnex/1.0 (+https://www.osintinfo.net)"
DBIP_URL = "https://download.db-ip.com/free/dbip-city-lite-{month}.mmdb.gz"
DBIP_FILE = "dbip-city-lite.mmdb"
DBIP_ASN_URL = "https://download.db-ip.com/free/dbip-asn-lite-{month}.mmdb.gz"
DBIP_ASN_FILE = "dbip-asn-lite.mmdb"
PUBLIC_IP_URL = "https://api.ipify.org"
METADATA_MARKER = b"\xab\xcd\xefMaxMind.com"


class MmdbError(ValueError):
    pass


class MmdbReader:
    """Lettore minimale del formato MaxMind DB (.mmdb), sola lettura."""

    def __init__(self, path: str):
        self._file = open(path, "rb")
        try:
            self._buf = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError as e:          # file vuoto
            self._file.close()
            raise MmdbError("file vuoto") from e
        # i metadati stanno in fondo, dopo il marcatore
        start = self._buf.rfind(METADATA_MARKER, max(0, len(self._buf) - 128 * 1024))
        if start < 0:
            self.close()
            raise MmdbError("non è un file MaxMind DB (.mmdb)")
        md = start + len(METADATA_MARKER)
        self.metadata, _ = self._decode(md, base=md)     # i puntatori dei metadati partono da qui
        self.node_count = int(self.metadata["node_count"])
        self.record_size = int(self.metadata["record_size"])
        self.ip_version = int(self.metadata.get("ip_version", 6))
        if self.record_size not in (24, 28, 32):
            self.close()
            raise MmdbError(f"record_size {self.record_size} non supportato")
        self._node_bytes = self.record_size * 2 // 8
        self._tree_size = self._node_bytes * self.node_count
        self._data = self._tree_size + 16           # inizio della sezione dati
        # nei database IPv6 gli IPv4 stanno sotto ::/96: troviamo una volta sola quel nodo
        self._ipv4_start = 0
        if self.ip_version == 6:
            node = 0
            for _ in range(96):
                if node >= self.node_count:
                    break
                node = self._record(node, 0)
            self._ipv4_start = node

    def close(self) -> None:
        try:
            self._buf.close()
        except (AttributeError, ValueError):
            pass
        self._file.close()

    # ------------------------------------------------------------------ albero
    def _record(self, node: int, bit: int) -> int:
        off = node * self._node_bytes
        b = self._buf
        if self.record_size == 24:
            o = off + bit * 3
            return (b[o] << 16) | (b[o + 1] << 8) | b[o + 2]
        if self.record_size == 28:
            if bit == 0:
                return ((b[off + 3] & 0xF0) << 20) | (b[off] << 16) | (b[off + 1] << 8) | b[off + 2]
            return ((b[off + 3] & 0x0F) << 24) | (b[off + 4] << 16) | (b[off + 5] << 8) | b[off + 6]
        o = off + bit * 4
        return struct.unpack_from(">I", b, o)[0]

    def get(self, ip: str):
        """Il record associato all'IP (un dict), oppure None."""
        addr = ipaddress.ip_address(ip)
        if addr.version == 6 and self.ip_version == 4:
            return None
        packed = addr.packed
        node = self._ipv4_start if addr.version == 4 and self.ip_version == 6 else 0
        bits = len(packed) * 8
        i = 0
        while i < bits and node < self.node_count:
            bit = (packed[i >> 3] >> (7 - (i & 7))) & 1
            node = self._record(node, bit)
            i += 1
        if node == self.node_count:            # nessun dato per questo indirizzo
            return None
        if node < self.node_count:
            raise MmdbError("albero di ricerca non valido")
        offset = node - self.node_count - 16
        value, _ = self._decode(self._data + offset, base=self._data)
        return value

    # ------------------------------------------------------------------ dati
    def _decode(self, off: int, base: int):
        """Decodifica il campo che inizia a `off`; ritorna (valore, offset successivo)."""
        b = self._buf
        ctrl = b[off]
        off += 1
        kind = ctrl >> 5
        if kind == 1:                           # puntatore
            ss = (ctrl >> 3) & 3
            v = ctrl & 7
            if ss == 0:
                ptr = (v << 8) | b[off]
            elif ss == 1:
                ptr = ((v << 16) | (b[off] << 8) | b[off + 1]) + 2048
            elif ss == 2:
                ptr = ((v << 24) | (b[off] << 16) | (b[off + 1] << 8) | b[off + 2]) + 526336
            else:
                ptr = struct.unpack_from(">I", b, off)[0]
            value, _ = self._decode(base + ptr, base)
            return value, off + ss + 1
        if kind == 0:                           # tipo esteso
            kind = 7 + b[off]
            off += 1
        size = ctrl & 0x1F
        if size >= 29:
            n = size - 28
            extra = int.from_bytes(b[off:off + n], "big")
            off += n
            size = {29: 29, 30: 285, 31: 65821}[ctrl & 0x1F] + extra
        if kind == 2:                           # stringa UTF-8
            return b[off:off + size].decode("utf-8", "replace"), off + size
        if kind == 3:                           # double
            return struct.unpack_from(">d", b, off)[0], off + 8
        if kind == 4:                           # byte
            return bytes(b[off:off + size]), off + size
        if kind in (5, 6, 9, 10):               # interi senza segno
            return int.from_bytes(b[off:off + size], "big"), off + size
        if kind == 8:                           # int32
            v = int.from_bytes(b[off:off + size], "big")
            if size == 4 and v & 0x80000000:
                v -= 1 << 32
            return v, off + size
        if kind == 7:                           # mappa
            out = {}
            for _ in range(size):
                k, off = self._decode(off, base)
                v, off = self._decode(off, base)
                out[k] = v
            return out, off
        if kind == 11:                          # array
            out = []
            for _ in range(size):
                v, off = self._decode(off, base)
                out.append(v)
            return out, off
        if kind == 14:                          # booleano: il valore è nella dimensione
            return bool(size), off
        if kind == 15:                          # float
            return struct.unpack_from(">f", b, off)[0], off + 4
        if kind in (12, 13):                    # contenitore / fine dati
            return None, off
        raise MmdbError(f"tipo di dato {kind} sconosciuto")


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    city: str = ""
    country: str = ""

    @property
    def name(self) -> str:
        return ", ".join(x for x in (self.city, self.country) if x) or f"{self.lat:.2f}, {self.lon:.2f}"


class GeoDb:
    """IP -> posizione (città). Se il database manca, lookup() ritorna sempre None."""

    def __init__(self, path: str | None = None):
        self.path = path
        self.error: str | None = None
        self._reader: MmdbReader | None = None
        self._cache: dict[str, Place | None] = {}
        if path:
            self.open(path)

    @property
    def available(self) -> bool:
        return self._reader is not None

    def open(self, path: str) -> bool:
        self.close()
        self.path, self.error = path, None
        try:
            self._reader = MmdbReader(path)
        except (OSError, MmdbError, KeyError) as e:
            self._reader, self.error = None, str(e)
        return self.available

    def close(self) -> None:
        if self._reader:
            self._reader.close()
        self._reader = None
        self._cache.clear()

    def description(self) -> str:
        if not self._reader:
            return "non presente"
        md = self._reader.metadata
        when = _dt.datetime.fromtimestamp(md.get("build_epoch", 0)).strftime("%Y-%m-%d")
        return f"{md.get('database_type', '?')} · {when}"

    def lookup(self, ip: str) -> Place | None:
        if not self._reader or not ip:
            return None
        if ip in self._cache:
            return self._cache[ip]
        place = None
        try:
            a = ipaddress.ip_address(ip)
            if a.is_global:                     # niente LAN, loopback, CGNAT...
                rec = self._reader.get(ip)
                if isinstance(rec, dict):
                    place = _place(rec)
        except (ValueError, MmdbError, IndexError, struct.error):
            place = None
        if len(self._cache) > 50_000:
            self._cache.clear()
        self._cache[ip] = place
        return place


def _place(rec: dict) -> Place | None:
    loc = rec.get("location") or {}
    lat, lon = loc.get("latitude"), loc.get("longitude")
    if lat is None or lon is None:
        return None

    def name(d):
        names = (d or {}).get("names") or {}
        return names.get("it") or names.get("en") or next(iter(names.values()), "")

    country = (rec.get("country") or {}).get("iso_code", "")
    return Place(float(lat), float(lon), name(rec.get("city")), country)


# ---------------------------------------------------------------------- download

def dbip_months(today: _dt.date | None = None) -> list[str]:
    """Il file del mese corrente esce nei primi giorni del mese: proviamo anche i due precedenti."""
    d = today or _dt.date.today()
    out = []
    y, m = d.year, d.month
    for _ in range(3):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out


def download_dbip(dest_dir: str, progress: Callable[[int, int], None] | None = None,
                  cancel: Callable[[], bool] | None = None, url_template: str = DBIP_URL,
                  timeout: float = 30, filename: str = DBIP_FILE) -> str:
    """
    Scarica un database DB-IP Lite (.mmdb.gz: City o ASN), lo decomprime in dest_dir/<filename>
    e ritorna il percorso. `progress(scaricati, totale)` riceve i byte compressi.
    """
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, filename)
    last_error: Exception | None = None
    for month in dbip_months():
        url = url_template.format(month=month)
        try:
            resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}),
                                          timeout=timeout)
        except OSError as e:          # 404 se il file del mese non c'è ancora
            last_error = e
            continue
        total = int(resp.headers.get("Content-Length") or 0)
        tmp_gz, tmp = dest + ".gz.part", dest + ".part"
        try:
            done = 0
            with resp, open(tmp_gz, "wb") as f:
                while True:
                    if cancel and cancel():
                        raise InterruptedError("download interrotto")
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
            with gzip.open(tmp_gz, "rb") as src, open(tmp, "wb") as out:
                while True:
                    chunk = src.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
            MmdbReader(tmp).close()              # verifica che sia leggibile prima di sostituire
            os.replace(tmp, dest)
            return dest
        finally:
            for p in (tmp_gz, tmp):
                try:
                    os.remove(p)
                except OSError:
                    pass
    raise OSError(f"download di DB-IP non riuscito: {last_error}")


def public_ip(timeout: float = 8) -> str:
    """IP pubblico di questo PC (serve solo per stimare la tua posizione)."""
    req = urllib.request.Request(PUBLIC_IP_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ip = r.read(64).decode().strip()
    ipaddress.ip_address(ip)
    return ip
