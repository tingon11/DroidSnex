"""Dettaglio di un IP: cosa si può sapere di un indirizzo contattato dal telefono.

Passivo (nessun contatto con l'IP):
  * PTR          reverse DNS (chiede al resolver del PC)
  * RDAP/WHOIS   proprietario del blocco, netblock, paese, contatto abuse (rdap.org -> RIR)
  * cloud        range pubblici di AWS, Google Cloud, Azure, Cloudflare, Oracle (liste JSON scaricate da Config)
  * domini       nomi risolti in quell'IP durante la sessione (scheda DNS) e nomi visti nelle connessioni
Attivo (il PC si collega all'IP):
  * certificato  TLS su :443 (o la porta vista), con SNI se noto; nessuna verifica della catena
Servizi con chiave API (facoltativi, in Config): VirusTotal, AbuseIPDB, Shodan, ipinfo.io.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import ssl
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .geo import USER_AGENT

CLOUD_SUBDIR = "cloud"


@dataclass(frozen=True)
class CloudList:
    key: str
    name: str
    url: str
    license: str = ""


CLOUD_LISTS = (
    CloudList("aws", "Amazon Web Services", "https://ip-ranges.amazonaws.com/ip-ranges.json"),
    CloudList("gcp", "Google Cloud", "https://www.gstatic.com/ipranges/cloud.json"),
    CloudList("azure", "Microsoft Azure", "https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519"),
    CloudList("cloudflare", "Cloudflare", "https://www.cloudflare.com/ips-v4"),
    CloudList("oracle", "Oracle Cloud", "https://docs.oracle.com/en-us/iaas/tools/public_ip_ranges.json"),
)
CLOUDFLARE_V6 = "https://www.cloudflare.com/ips-v6"
# (impostazione, nome, pagina della chiave API, pagina di registrazione)
API_SERVICES = (
    ("vt_key", "VirusTotal", "https://www.virustotal.com/gui/my-apikey", "https://www.virustotal.com/gui/join-us"),
    ("abuseipdb_key", "AbuseIPDB", "https://www.abuseipdb.com/account/api", "https://www.abuseipdb.com/register"),
    ("shodan_key", "Shodan", "https://account.shodan.io/", "https://account.shodan.io/register"),
    ("ipinfo_key", "ipinfo.io", "https://ipinfo.io/account/token", "https://ipinfo.io/signup"),
)


def _get(url: str, headers: dict | None = None, timeout: float = 15) -> bytes:
    h = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _json(url: str, headers: dict | None = None, timeout: float = 15) -> dict:
    return json.loads(_get(url, headers, timeout).decode("utf-8", errors="replace"))


# ====================================================================== passivo
def ptr(ip: str, timeout: float = 4) -> str | None:
    old = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return None
    finally:
        socket.setdefaulttimeout(old)


def rdap(ip: str, timeout: float = 15) -> dict:
    """Riassunto RDAP: nome del blocco, range, paese, titolare, abuse. rdap.org rimanda al RIR giusto."""
    data = _json(f"https://rdap.org/ip/{urllib.parse.quote(ip)}", timeout=timeout)
    out = {"name": data.get("name"), "handle": data.get("handle"), "type": data.get("type"),
           "start": data.get("startAddress"), "end": data.get("endAddress"), "country": data.get("country"),
           "registrant": None, "abuse": None, "remarks": [], "source": data.get("port43") or "rdap.org"}
    for net in data.get("cidr0_cidrs", []) or []:
        pfx = net.get("v4prefix") or net.get("v6prefix")
        if pfx:
            out.setdefault("cidrs", []).append(f"{pfx}/{net.get('length')}")
    for ent in data.get("entities", []) or []:
        roles = ent.get("roles", []) or []
        fn, email = _vcard(ent.get("vcardArray"))
        if "abuse" in roles and email and not out["abuse"]:
            out["abuse"] = email
        if any(r in roles for r in ("registrant", "administrative")) and fn and not out["registrant"]:
            out["registrant"] = fn
        for sub in ent.get("entities", []) or []:
            sfn, semail = _vcard(sub.get("vcardArray"))
            if "abuse" in (sub.get("roles") or []) and semail and not out["abuse"]:
                out["abuse"] = semail
    for rem in data.get("remarks", []) or []:
        for line in rem.get("description", []) or []:
            if line and len(out["remarks"]) < 6:
                out["remarks"].append(line)
    return out


def _vcard(vcard) -> tuple[str | None, str | None]:
    fn = email = None
    try:
        for item in vcard[1]:
            if item[0] == "fn" and not fn:
                fn = item[3]
            elif item[0] == "email" and not email:
                email = item[3]
    except (TypeError, IndexError):
        pass
    return fn, email


# ====================================================================== range cloud
def cloud_dir(data_dir: str) -> str:
    return os.path.join(data_dir, CLOUD_SUBDIR)


def cloud_path(data_dir: str, key: str) -> str:
    return os.path.join(cloud_dir(data_dir), f"{key}.json")


def download_cloud(data_dir: str, progress: Callable[[str], None] | None = None,
                   cancel: Callable[[], bool] | None = None, timeout: float = 60) -> tuple[list[str], dict[str, str]]:
    """Scarica le liste dei range cloud in data_dir/cloud/<key>.json (formato nostro: lista di
    {"cidr","service","region"}). Ritorna (chiavi riuscite, errori per chiave)."""
    os.makedirs(cloud_dir(data_dir), exist_ok=True)
    ok, errors = [], {}
    for lst in CLOUD_LISTS:
        if cancel and cancel():
            raise InterruptedError
        if progress:
            progress(lst.name)
        try:
            entries = _fetch_cloud(lst, timeout)
            if len(entries) < 10:
                raise ValueError(f"lista troppo corta ({len(entries)} voci)")
            tmp = cloud_path(data_dir, lst.key) + ".part"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"provider": lst.name, "fetched": time.time(), "entries": entries}, f)
            os.replace(tmp, cloud_path(data_dir, lst.key))
            ok.append(lst.key)
        except InterruptedError:
            raise
        except Exception as e:  # noqa: BLE001
            errors[lst.name] = _short_error(e)
    return ok, errors


def _fetch_cloud(lst: CloudList, timeout: float) -> list[dict]:
    if lst.key == "aws":
        d = _json(lst.url, timeout=timeout)
        return ([{"cidr": p["ip_prefix"], "service": p.get("service", ""), "region": p.get("region", "")}
                 for p in d.get("prefixes", [])]
                + [{"cidr": p["ipv6_prefix"], "service": p.get("service", ""), "region": p.get("region", "")}
                   for p in d.get("ipv6_prefixes", [])])
    if lst.key == "gcp":
        d = _json(lst.url, timeout=timeout)
        return [{"cidr": p.get("ipv4Prefix") or p.get("ipv6Prefix"), "service": p.get("service", ""),
                 "region": p.get("scope", "")} for p in d.get("prefixes", []) if p.get("ipv4Prefix") or p.get("ipv6Prefix")]
    if lst.key == "cloudflare":
        v4 = _get(lst.url, timeout=timeout).decode().split()
        v6 = _get(CLOUDFLARE_V6, timeout=timeout).decode().split()
        return [{"cidr": c, "service": "", "region": ""} for c in v4 + v6 if "/" in c]
    if lst.key == "oracle":
        d = _json(lst.url, timeout=timeout)
        out = []
        for reg in d.get("regions", []):
            for c in reg.get("cidrs", []):
                out.append({"cidr": c["cidr"], "service": ",".join(c.get("tags", [])[:3]), "region": reg.get("region", "")})
        return out
    if lst.key == "azure":
        page = _get(lst.url, timeout=timeout).decode("utf-8", errors="replace")
        m = re.search(r"https://download\.microsoft\.com/download/[^\"' ]+ServiceTags_Public_\d+\.json", page)
        if not m:
            raise ValueError("link al file ServiceTags_Public non trovato nella pagina Microsoft")
        d = _json(m.group(0), timeout=timeout)
        out = []
        for v in d.get("values", []):
            props = v.get("properties", {})
            if props.get("region"):          # le voci regionali bastano (quelle globali le duplicano)
                for c in props.get("addressPrefixes", []):
                    out.append({"cidr": c, "service": props.get("systemService", "") or v.get("name", ""),
                                "region": props.get("region", "")})
        if not out:
            for v in d.get("values", []):
                for c in v.get("properties", {}).get("addressPrefixes", []):
                    out.append({"cidr": c, "service": v.get("name", ""), "region": ""})
        return out
    raise ValueError(lst.key)


class CloudRanges:
    """Le liste cloud in memoria: ip -> (provider, servizio, regione, cidr)."""

    def __init__(self, data_dir: str | None = None):
        self.nets: list[tuple] = []          # (network, provider, service, region)
        self.loaded: dict[str, tuple[int, float]] = {}
        self._cache: dict[str, tuple | None] = {}
        if data_dir:
            self.load(data_dir)

    @property
    def available(self) -> bool:
        return bool(self.nets)

    def load(self, data_dir: str) -> None:
        nets, loaded = [], {}
        for lst in CLOUD_LISTS:
            p = cloud_path(data_dir, lst.key)
            if not os.path.isfile(p):
                continue
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                n = 0
                for e in d.get("entries", []):
                    try:
                        nets.append((ipaddress.ip_network(e["cidr"], strict=False), lst.name, e.get("service", ""), e.get("region", "")))
                        n += 1
                    except ValueError:
                        continue
                loaded[lst.key] = (n, d.get("fetched") or os.path.getmtime(p))
            except (OSError, ValueError):
                continue
        self.nets, self.loaded, self._cache = nets, loaded, {}

    def lookup(self, ip: str) -> tuple | None:
        if ip in self._cache:
            return self._cache[ip]
        res = None
        try:
            a = ipaddress.ip_address(ip)
            best = None
            for net, prov, svc, reg in self.nets:
                if a.version == net.version and a in net and (best is None or net.prefixlen > best[0].prefixlen):
                    best = (net, prov, svc, reg)
            if best:
                res = (best[1], best[2], best[3], str(best[0]))
        except ValueError:
            pass
        if len(self._cache) > 20000:
            self._cache.clear()
        self._cache[ip] = res
        return res

    def describe(self) -> str:
        parts = []
        for lst in CLOUD_LISTS:
            if lst.key in self.loaded:
                n, t = self.loaded[lst.key]
                parts.append(f"{lst.name} {n:,} · {time.strftime('%Y-%m-%d', time.localtime(t))}")
        return "  ·  ".join(parts).replace(",", ".")


# ====================================================================== attivo: certificato TLS
def tls_cert(ip: str, sni: str | None = None, port: int = 443, timeout: float = 6) -> dict:
    """Si collega a ip:port in TLS (senza verificare la catena) e legge il certificato presentato."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    t0 = time.monotonic()
    with socket.create_connection((ip, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=sni or None) as tls:
            der = tls.getpeercert(binary_form=True)
            info = {"sni": sni or "", "port": port, "protocol": tls.version(), "cipher": (tls.cipher() or ("",))[0],
                    "ms": int((time.monotonic() - t0) * 1000)}
    if not der:
        info["error"] = "nessun certificato"
        return info
    info.update(_decode_cert(der))
    return info


def _decode_cert(der: bytes) -> dict:
    """Decodifica il DER con il decoder interno di ssl (via file PEM temporaneo)."""
    pem = ssl.DER_cert_to_PEM_cert(der)
    out = {"sha256": __import__("hashlib").sha256(der).hexdigest()}
    fd, path = tempfile.mkstemp(suffix=".pem")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(pem)
        d = ssl._ssl._test_decode_cert(path)  # type: ignore[attr-defined]  # noqa: SLF001
    except Exception as e:  # noqa: BLE001
        out["error"] = f"certificato non decodificabile: {e}"
        return out
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    def name(parts) -> str:
        items = [f"{k}={v}" for rdn in parts for k, v in rdn]
        return ", ".join(items)

    out["subject"] = name(d.get("subject", ()))
    out["issuer"] = name(d.get("issuer", ()))
    out["cn"] = next((v for rdn in d.get("subject", ()) for k, v in rdn if k == "commonName"), "")
    out["issuer_org"] = next((v for rdn in d.get("issuer", ()) for k, v in rdn if k == "organizationName"), "")
    out["not_before"] = d.get("notBefore", "")
    out["not_after"] = d.get("notAfter", "")
    out["san"] = [v for k, v in d.get("subjectAltName", ()) if k == "DNS"]
    out["serial"] = d.get("serialNumber", "")
    try:
        out["expired"] = ssl.cert_time_to_seconds(d["notAfter"]) < time.time()
    except (KeyError, ValueError):
        pass
    return out


# ====================================================================== servizi con chiave
def virustotal(ip: str, key: str, timeout: float = 15) -> dict:
    d = _json(f"https://www.virustotal.com/api/v3/ip_addresses/{ip}", {"x-apikey": key}, timeout)
    a = d.get("data", {}).get("attributes", {})
    st = a.get("last_analysis_stats", {})
    return {"malicious": st.get("malicious", 0), "suspicious": st.get("suspicious", 0), "harmless": st.get("harmless", 0),
            "undetected": st.get("undetected", 0), "reputation": a.get("reputation"), "as_owner": a.get("as_owner"),
            "country": a.get("country"), "network": a.get("network"),
            "tags": a.get("tags", [])[:8], "url": f"https://www.virustotal.com/gui/ip-address/{ip}"}


def abuseipdb(ip: str, key: str, timeout: float = 15) -> dict:
    d = _json(f"https://api.abuseipdb.com/api/v2/check?ipAddress={urllib.parse.quote(ip)}&maxAgeInDays=90",
              {"Key": key, "Accept": "application/json"}, timeout).get("data", {})
    return {"score": d.get("abuseConfidenceScore"), "reports": d.get("totalReports"), "last": d.get("lastReportedAt"),
            "isp": d.get("isp"), "usage": d.get("usageType"), "domain": d.get("domain"), "tor": d.get("isTor"),
            "whitelisted": d.get("isWhitelisted"), "country": d.get("countryCode"),
            "url": f"https://www.abuseipdb.com/check/{ip}"}


def shodan(ip: str, key: str, timeout: float = 15) -> dict:
    d = _json(f"https://api.shodan.io/shodan/host/{ip}?key={urllib.parse.quote(key)}", timeout=timeout)
    return {"ports": sorted(d.get("ports", [])), "hostnames": d.get("hostnames", [])[:8], "org": d.get("org"),
            "os": d.get("os"), "isp": d.get("isp"), "vulns": len(d.get("vulns", []) or []), "tags": d.get("tags", [])[:8],
            "last": d.get("last_update"), "url": f"https://www.shodan.io/host/{ip}"}


def ipinfo_io(ip: str, key: str, timeout: float = 15) -> dict:
    d = _json(f"https://ipinfo.io/{ip}?token={urllib.parse.quote(key)}", timeout=timeout)
    priv = d.get("privacy") or {}
    return {"hostname": d.get("hostname"), "org": d.get("org"), "city": d.get("city"), "region": d.get("region"),
            "country": d.get("country"), "anycast": d.get("anycast"), "vpn": priv.get("vpn"), "proxy": priv.get("proxy"),
            "tor": priv.get("tor"), "hosting": priv.get("hosting"), "url": f"https://ipinfo.io/{ip}"}


SERVICES = {"vt_key": ("virustotal", virustotal), "abuseipdb_key": ("abuseipdb", abuseipdb),
            "shodan_key": ("shodan", shodan), "ipinfo_key": ("ipinfo", ipinfo_io)}


# ====================================================================== tutto insieme
def is_private(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private or a.is_loopback or a.is_link_local or a.is_multicast
    except ValueError:
        return True


def collect(ip: str, sni: str | None, port: int, dns_names: list[str], cloud: CloudRanges | None, keys: dict,
            emit: Callable[[str, object], None], active: bool = True, cancel: Callable[[], bool] | None = None) -> dict:
    """Esegue tutti i passi e chiama emit(sezione, risultato) man mano (risultato = dict/str o
    {"error": ...}). Ritorna il dizionario completo."""
    out: dict = {"ip": ip, "queried": time.time(), "private": is_private(ip), "dns_names": dns_names}
    emit("dns_names", dns_names)

    def step(name, fn, *a):
        if cancel and cancel():
            return
        try:
            res = fn(*a)
        except Exception as e:  # noqa: BLE001
            res = {"error": _short_error(e)}
        out[name] = res
        emit(name, res)

    step("ptr", ptr, ip)
    if cloud is not None:
        step("cloud", lambda: cloud.lookup(ip) if cloud.available else {"error": "liste cloud non scaricate (Config)"})
    if not out["private"]:
        step("rdap", rdap, ip)
        if active:
            step("tls", tls_cert, ip, sni, port if port in (443, 8443, 853, 465, 993, 995) else 443)
        for k, (name, fn) in SERVICES.items():
            if keys.get(k):
                step(name, fn, ip, keys[k])
    return out


def _short_error(e: Exception) -> str:
    import urllib.error
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code} {e.reason}"
    if isinstance(e, urllib.error.URLError):
        return f"rete: {e.reason}"
    if isinstance(e, socket.timeout):
        return "timeout"
    return str(e) or type(e).__name__
