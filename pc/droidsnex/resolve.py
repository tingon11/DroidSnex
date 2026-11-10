"""Arricchimento degli indirizzi: reverse DNS (asincrono, con cache) e ASN/organizzazione da db locale."""
from __future__ import annotations

import bisect
import gzip
import ipaddress
import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor


class ReverseDns:
    """Reverse DNS non bloccante: la prima richiesta ritorna None e avvia la risoluzione in background."""

    def __init__(self, enabled: bool = True, workers: int = 8):
        self.enabled = enabled
        self._cache: dict[str, str | None] = {}
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rdns") if enabled else None

    def get(self, ip: str) -> str | None:
        if not self.enabled:
            return None
        with self._lock:
            if ip in self._cache:
                return self._cache[ip]
            if ip in self._pending:
                return None
            self._pending.add(ip)
        self._pool.submit(self._resolve, ip)
        return None

    def _resolve(self, ip: str):
        name = None
        try:
            addr = ipaddress.ip_address(ip)
            if not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast):
                name = socket.gethostbyaddr(ip)[0].lower()
        except (OSError, ValueError):
            pass
        with self._lock:
            self._cache[ip] = name
            self._pending.discard(ip)

    def shutdown(self):
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)


class AsnDb:
    """
    Database ASN locale, facoltativo. Formati supportati:
      * ip2asn-combined.tsv / ip2asn-v4.tsv (anche .gz) da https://iptoasn.com
        colonne: range_start  range_end  AS_number  country_code  AS_description
      * GeoLite2-ASN.mmdb (MaxMind) o dbip-asn-lite.mmdb (DB-IP), letti senza moduli esterni.
    Se il file manca o non è leggibile, lookup() ritorna sempre None (degradazione).
    """

    def __init__(self, path: str | None):
        self.path = path
        self.available = False
        self.error: str | None = None
        self._starts4: list[int] = []
        self._rows4: list[tuple[int, int, str, str]] = []
        self._starts6: list[int] = []
        self._rows6: list[tuple[int, int, str, str]] = []
        self._mmdb = None
        self._cache: dict[str, tuple[str, str] | None] = {}
        if path:
            self._load(path)

    def close(self) -> None:
        """Chiude il file .mmdb (su Windows un file aperto non si può sostituire)."""
        if self._mmdb is not None:
            try:
                self._mmdb.close()
            except Exception:  # noqa: BLE001
                pass
            self._mmdb = None
        self.available = bool(self._rows4 or self._rows6)
        self._cache.clear()

    @staticmethod
    def autodetect(base_dirs: list[str]) -> str | None:
        names = ["ip2asn-combined.tsv.gz", "ip2asn-combined.tsv", "ip2asn-v4.tsv.gz", "ip2asn-v4.tsv",
                 "GeoLite2-ASN.mmdb", "dbip-asn-lite.mmdb"]
        for d in base_dirs:
            for n in names:
                p = os.path.join(d, n)
                if os.path.isfile(p):
                    return p
        return None

    def _load(self, path: str):
        try:
            if path.endswith(".mmdb"):
                from .geo import MmdbReader         # lettore .mmdb in Python puro
                self._mmdb = MmdbReader(path)
                self.available = True
                return
            opener = gzip.open if path.endswith(".gz") else open
            rows4, rows6 = [], []
            with opener(path, "rt", encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < 5 or parts[2] == "0":      # AS 0 = non annunciato
                        continue
                    try:
                        a, b = ipaddress.ip_address(parts[0]), ipaddress.ip_address(parts[1])
                    except ValueError:
                        continue
                    row = (int(a), int(b), f"AS{parts[2]}", f"{parts[4]} ({parts[3]})")
                    (rows4 if a.version == 4 else rows6).append(row)
            rows4.sort(); rows6.sort()
            self._rows4, self._starts4 = rows4, [r[0] for r in rows4]
            self._rows6, self._starts6 = rows6, [r[0] for r in rows6]
            self.available = bool(rows4 or rows6)
        except (OSError, ValueError) as e:
            self.error = str(e)

    def lookup(self, ip: str) -> tuple[str, str] | None:
        """Ritorna (ASN, organizzazione) oppure None."""
        if not self.available:
            return None
        if ip in self._cache:
            return self._cache[ip]
        res = None
        try:
            if self._mmdb is not None:
                r = self._mmdb.get(ip)
                if r:
                    res = (f"AS{r.get('autonomous_system_number')}", r.get("autonomous_system_organization", ""))
            else:
                addr = ipaddress.ip_address(ip)
                starts, rows = (self._starts4, self._rows4) if addr.version == 4 else (self._starts6, self._rows6)
                n = int(addr)
                i = bisect.bisect_right(starts, n) - 1
                if i >= 0 and rows[i][0] <= n <= rows[i][1]:
                    res = (rows[i][2], rows[i][3])
        except ValueError:
            pass
        self._cache[ip] = res
        return res
