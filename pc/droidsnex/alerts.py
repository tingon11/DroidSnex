"""Alert sulle connessioni: cose che meritano uno sguardo mentre il monitor gira.

Regole (ognuna scatta una volta per destinazione/app):
  * new_untrusted  prima connessione verso una destinazione non fidata
  * new_country    primo IP in un paese mai visto in questa sessione
  * odd_port       porta diversa da quelle comuni (80, 443, 53, 853, 123, 5228...)
  * reputation     dominio presente in una lista di reputazione (tracker / malware)
  * doh            DNS-over-HTTPS/TLS: resolver pubblico contattato sulla 443/853,
                   che scavalca il DNS di sistema (e quindi il tab DNS)
"""
from __future__ import annotations

import time
from dataclasses import dataclass

COMMON_PORTS = {80, 443, 53, 853, 123, 5228, 5229, 5230, 5223, 5222, 993, 995, 465, 587, 143, 110, 4070, 3478,
                3479, 19302, 19305, 19306, 19307, 19308, 19309, 443, 8443, 8080, 1900, 5353, 67, 68, 547, 546}
DOH_HOSTS = {"dns.google", "dns.google.com", "cloudflare-dns.com", "mozilla.cloudflare-dns.com", "one.one.one.one",
             "dns.quad9.net", "dns9.quad9.net", "dns.adguard.com", "dns.adguard-dns.com", "doh.opendns.com",
             "dns.nextdns.io", "doh.cleanbrowsing.org", "dns.alidns.com", "doh.pub", "dns.sb", "doh.dns.sb",
             "dns.mullvad.net", "dns.controld.com", "freedns.controld.com", "security.cloudflare-dns.com",
             "family.cloudflare-dns.com", "dns10.quad9.net", "dns11.quad9.net"}
DOH_IPS = {"8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1", "9.9.9.9", "149.112.112.112", "94.140.14.14", "94.140.15.15",
           "208.67.222.222", "208.67.220.220", "45.90.28.0", "45.90.30.0", "2001:4860:4860::8888",
           "2001:4860:4860::8844", "2606:4700:4700::1111", "2606:4700:4700::1001", "2620:fe::fe", "2620:fe::9"}
LEVELS = {"new_untrusted": "info", "new_country": "warn", "odd_port": "warn", "reputation": "err", "doh": "warn",
          "anon": "warn"}
REP_LABEL = {"malware": "malware", "tracker": "tracker / pubblicità", "tor": "nodo di uscita Tor", "vpn": "VPN (indicativo, da ASN)"}


@dataclass
class Alert:
    ts: float
    kind: str
    level: str          # info | warn | err
    app: str
    dest: str
    ip: str
    port: int
    text: str           # testo già tradotto, pronto da mostrare

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class AlertEngine:
    """Tiene lo stato di cosa è già stato segnalato. Gli alert generati sono in `items` (max 2000)."""

    def __init__(self, trust, geo, reputation, tr):
        self.trust, self.geo, self.rep, self.tr = trust, geo, reputation, tr
        self.items: list[Alert] = []
        self.seen_dest: set[str] = set()
        self.seen_country: set[str] = set()
        self.seen_port: set[tuple[str, int]] = set()
        self.seen_rep: set[str] = set()
        self.seen_doh: set[tuple[str, str]] = set()
        self.counts = {"info": 0, "warn": 0, "err": 0}
        self.unread = 0
        self.started = time.time()
        self.now = time.time          # orologio: nel replay e' l'istante della sessione

    def reset(self) -> None:
        now = self.now
        self.__init__(self.trust, self.geo, self.rep, self.tr)
        self.now = now

    def _add(self, kind: str, c, dest: str, text: str) -> Alert:
        a = Alert(self.now(), kind, LEVELS[kind], c.app, dest, c.dst_ip, c.dst_port, text)
        self.items.append(a)
        if len(self.items) > 2000:
            del self.items[:200]
        self.counts[a.level] += 1
        self.unread += 1
        return a

    def check(self, c, dest: str, first_time: bool) -> list[Alert]:
        """Controlla una connessione (nuova, o con il nome scoperto dopo). Ritorna gli alert nuovi."""
        tr, out = self.tr, []
        host = dest[6:] if dest.startswith("[dns] ") else dest
        trusted = self.trust.is_trusted(host, (c.dst_ip,))
        if c.dst_port == 53 or c.host_src == "dns-query":
            return out                                  # le query DNS hanno il loro tab
        if dest not in self.seen_dest:
            self.seen_dest.add(dest)
            if not trusted:
                out.append(self._add("new_untrusted", c, dest, tr("nuova destinazione non fidata")))
        if first_time:
            place = self.geo.lookup(c.dst_ip) if self.geo else None
            if place and place.country and place.country not in self.seen_country:
                first = not self.seen_country
                self.seen_country.add(place.country)
                if not first or len(self.seen_dest) > 1:
                    out.append(self._add("new_country", c, dest, tr("nuovo paese: {c}", c=place.country)
                                         + (f" · {place.city}" if place.city else "")))
            if c.dst_port not in COMMON_PORTS and (dest, c.dst_port) not in self.seen_port:
                self.seen_port.add((dest, c.dst_port))
                out.append(self._add("odd_port", c, dest, tr("porta insolita {p}/{proto}", p=c.dst_port, proto=c.proto)))
        rep = self.rep.lookup(host, (c.dst_ip,), c.org) if self.rep else None
        if rep and dest not in self.seen_rep:
            self.seen_rep.add(dest)
            cat, src = rep
            kind = "anon" if cat in ("tor", "vpn") else "reputation"
            out.append(self._add(kind, c, dest, f"{tr(REP_LABEL[cat])} ({src})"))
        if (host in DOH_HOSTS or c.dst_ip in DOH_IPS) and c.dst_port in (443, 853) and (c.app, host) not in self.seen_doh:
            self.seen_doh.add((c.app, host))
            out.append(self._add("doh", c, dest, tr("DNS cifrato (DoH/DoT): le query di questa app non passano dal DNS di sistema")))
        return out
