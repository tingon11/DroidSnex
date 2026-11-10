"""Liste di reputazione (blocklist) locali: tracker, pubblicità e domini malevoli.

Le liste si scaricano SOLO dal tab Config (mai in automatico) e finiscono in
pc/data/reputation/<nome>.txt. Formato "hosts" (0.0.0.0 dominio) o un dominio
per riga; le righe con # sono commenti. Il controllo è sul dominio e sui suoi
genitori (tracker.ads.example.com -> ads.example.com -> example.com).

    rep = Reputation(DATA_DIR)
    rep.lookup("t.appsflyer.com")  ->  ("tracker", "StevenBlack")
"""
from __future__ import annotations

import os
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .geo import USER_AGENT

SUBDIR = "reputation"


@dataclass(frozen=True)
class RepList:
    key: str
    name: str           # come compare in Config
    urls: tuple         # il primo che risponde vince (mirror)
    category: str       # "tracker" | "malware" | "tor"
    license: str

    @property
    def url(self) -> str:
        return self.urls[0]


LISTS = (
    RepList("stevenblack", "StevenBlack hosts (pubblicità + malware)",
            ("https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts",
             "https://cdn.jsdelivr.net/gh/StevenBlack/hosts@master/hosts"), "tracker", "MIT"),
    # il vecchio https://urlhaus.abuse.ch/downloads/hostfile/ risponde 410 Gone: usiamo il filtro
    # urlhaus-filter (dati URLhaus, CC0) in formato hosts, pubblicato su GitLab/GitHub Pages
    RepList("urlhaus", "URLhaus (abuse.ch) · domini malware",
            ("https://malware-filter.gitlab.io/malware-filter/urlhaus-filter-hosts.txt",
             "https://curbengh.github.io/malware-filter/urlhaus-filter-hosts.txt",
             "https://malware-filter.pages.dev/urlhaus-filter-hosts.txt"), "malware", "CC0"),
    RepList("tor", "Tor Project · nodi di uscita Tor (IP)",
            ("https://check.torproject.org/torbulkexitlist",
             "https://check.torproject.org/exit-addresses"), "tor", "pubblico"),
)
SEVERITY = {"malware": 3, "tor": 2, "tracker": 1}
# VPN: non esiste una lista completa; riconosciamo i provider noti dal nome dell'organizzazione
# dell'IP (database ASN). Indicativo: possibili falsi positivi, e le VPN su hosting generici sfuggono.
VPN_ORG = re.compile(r"\b(vpn|nordvpn|nord ?security|mullvad|proton ?(ag|vpn)|surfshark|expressvpn|express ?vpn|"
                     r"private internet access|pia\b|cyberghost|ipvanish|windscribe|hide\.?me|tunnelbear|hotspot ?shield|"
                     r"perfect privacy|ivpn|ovpn|vyprvpn|zenmate|purevpn|torguard|astrill|datacamp|m247|packethub|"
                     r"cdn77|clouvider|hydra|anchorfree|pango|tefincom|kape)\b", re.I)


def vpn_org(org: str | None) -> bool:
    return bool(org) and VPN_ORG.search(org) is not None


def list_dir(data_dir: str) -> str:
    return os.path.join(data_dir, SUBDIR)


def list_path(data_dir: str, lst: RepList) -> str:
    return os.path.join(list_dir(data_dir), f"{lst.key}.txt")


def parse_hosts(text: str):
    """Domini da un file hosts o da un elenco di domini (uno per riga)."""
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if not line:
            continue
        parts = line.split()
        if parts[0] in ("exitaddress",) and len(parts) >= 2:      # formato exit-addresses del Tor Project
            host = parts[1]
        elif parts[0] in ("exitnode", "published", "lastStatus".lower()):
            continue
        else:
            host = parts[1] if len(parts) >= 2 and parts[0] in ("0.0.0.0", "127.0.0.1", "::1", "::") else parts[0]
        if host.startswith("||") or host.startswith("http"):      # righe in formato adblock / URL
            host = host.lstrip("|").split("://", 1)[-1].split("/", 1)[0].split("^", 1)[0]
        if host in ("localhost", "localhost.localdomain", "local", "broadcasthost", "ip6-localhost",
                    "ip6-loopback", "ip6-localnet", "ip6-mcastprefix", "ip6-allnodes", "ip6-allrouters",
                    "ip6-allhosts", "0.0.0.0"):
            continue
        if ("." in host or ":" in host) and " " not in host:
            yield host


class PartialDownload(Exception):
    """Alcune liste sono state scaricate, altre no: `ok` e `errors` (nome lista -> messaggio)."""

    def __init__(self, ok: list[str], errors: dict[str, str]):
        self.ok, self.errors = ok, errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def _fetch(url: str, tmp: str, name: str, progress, cancel, timeout: float) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            if cancel and cancel():
                raise InterruptedError("download interrotto")
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress:
                progress(name, got, total)


def download_one(data_dir: str, lst: RepList, progress=None, cancel=None, timeout: float = 60) -> str:
    """Scarica una lista provando i suoi mirror in ordine. Ritorna il percorso scritto."""
    dest = list_path(data_dir, lst)
    tmp = dest + ".part"
    errors = []
    for url in lst.urls:
        try:
            _fetch(url, tmp, lst.name, progress, cancel, timeout)
            n = sum(1 for _ in parse_hosts(open(tmp, encoding="utf-8", errors="replace").read()))
            if n < (20 if lst.category == "tor" else 100):
                raise ValueError(f"lista troppo corta ({n} voci)")
            os.replace(tmp, dest)
            return dest
        except InterruptedError:
            _rm(tmp)
            raise
        except Exception as e:  # noqa: BLE001 - si prova il mirror seguente
            _rm(tmp)
            errors.append(f"{_short_error(e)} · {url}")
    raise OSError("  /  ".join(errors))


def download(data_dir: str, progress: Callable[[str, int, int], None] | None = None,
             cancel: Callable[[], bool] | None = None, lists=LISTS, timeout: float = 60) -> list[str]:
    """Scarica tutte le liste in data_dir/reputation. Ritorna i percorsi scritti; se qualcuna fallisce
    le altre restano scaricate e viene sollevata PartialDownload con il dettaglio."""
    os.makedirs(list_dir(data_dir), exist_ok=True)
    ok, errors = [], {}
    for lst in lists:
        try:
            ok.append(download_one(data_dir, lst, progress, cancel, timeout))
        except InterruptedError:
            raise
        except Exception as e:  # noqa: BLE001
            errors[lst.name.split(" ")[0]] = str(e)
    if errors:
        raise PartialDownload(ok, errors)
    return ok


def _rm(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _short_error(e: Exception) -> str:
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code} {e.reason}"
    if isinstance(e, urllib.error.URLError):
        return f"rete: {e.reason}"
    return str(e) or type(e).__name__


class Reputation:
    """Le liste caricate in memoria: dominio -> (categoria, nome lista)."""

    def __init__(self, data_dir: str | None = None):
        self.data_dir = data_dir
        self._hosts: dict[str, tuple[str, str]] = {}
        self._cache: dict[str, tuple[str, str] | None] = {}
        self.loaded: dict[str, tuple[int, float]] = {}      # key -> (voci, mtime)
        if data_dir:
            self.load(data_dir)

    @property
    def available(self) -> bool:
        return bool(self._hosts)

    def load(self, data_dir: str) -> None:
        self.data_dir = data_dir
        hosts: dict[str, tuple[str, str]] = {}
        loaded = {}
        for lst in LISTS:
            p = list_path(data_dir, lst)
            if not os.path.isfile(p):
                continue
            n = 0
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    for h in parse_hosts(f.read()):
                        n += 1
                        old = hosts.get(h)
                        if old is None or SEVERITY[lst.category] > SEVERITY[old[0]]:
                            hosts[h] = (lst.category, lst.name.split(" ")[0])
            except OSError:
                continue
            loaded[lst.key] = (n, os.path.getmtime(p))
        self._hosts, self.loaded, self._cache = hosts, loaded, {}

    def lookup(self, host: str | None, ips=(), org: str | None = None) -> tuple[str, str] | None:
        """(categoria, lista) se il dominio o un suo genitore è in lista, se un IP è un nodo Tor
        o se l'organizzazione è un provider VPN noto; altrimenti None."""
        res = self._lookup_host(host) if host else None
        if not res:
            for ip in ips:
                res = self._hosts.get(ip)
                if res:
                    break
        if not res and vpn_org(org):
            res = ("vpn", "ASN")
        return res

    def _lookup_host(self, host: str) -> tuple[str, str] | None:
        if not self._hosts:
            return None
        h = host.lower().rstrip(".")
        if h.startswith("[dns] "):
            h = h[6:]
        if h in self._cache:
            return self._cache[h]
        res = self._hosts.get(h)
        parts = h.split(".")
        if not res and not parts[-1].isdigit():
            for i in range(1, len(parts) - 1):
                res = self._hosts.get(".".join(parts[i:]))
                if res:
                    break
        if len(self._cache) > 50_000:
            self._cache.clear()
        self._cache[h] = res
        return res

    def describe(self) -> str:
        if not self.loaded:
            return ""
        parts = []
        for lst in LISTS:
            if lst.key in self.loaded:
                n, mtime = self.loaded[lst.key]
                parts.append(f"{lst.name.split(' ')[0]} {n:,} · {time.strftime('%Y-%m-%d', time.localtime(mtime))}")
        return "  ·  ".join(parts).replace(",", ".")
