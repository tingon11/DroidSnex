"""Scala di pericolosità di una destinazione non fidata: da 0 (bianco) a 5 (viola).

Si sommano dei punti per ogni segnale sospetto; il livello è il totale, tagliato a 5:
    +1  solo IP, nessun nome (né SNI, né DNS, né reverse DNS)
    +1  organizzazione sconosciuta (IP non presente nel db ASN)
    +1  paese diverso dal tuo (serve la posizione rilevata dall'IP pubblico in Config)
    +1  resolver DNS cifrato (DoH/DoT) contattato direttamente
    +2  porta insolita (non 80/443/53/…)
    +3  provider VPN (dal nome dell'organizzazione, indicativo)
    +4  tracker / pubblicità in lista
    +4  nodo di uscita Tor
    +5  malware in lista

    0 bianco · 1 giallo · 2 arancio · 3 rosso · 4 fucsia · 5 viola
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .alerts import COMMON_PORTS, DOH_HOSTS, DOH_IPS

COLORS = ("#e2e8f0", "#facc15", "#fb923c", "#f87171", "#e879f9", "#a78bfa")
NAMES = ("bianco", "giallo", "arancio", "rosso", "fucsia", "viola")
POINTS = {"ip_only": 1, "no_org": 1, "country": 1, "doh": 1, "odd_port": 2, "vpn": 3, "tracker": 4, "tor": 4,
          "malware": 5}
REASONS = {"ip_only": "solo IP, nessun nome", "no_org": "organizzazione sconosciuta", "country": "paese diverso dal tuo",
           "doh": "DNS cifrato (DoH/DoT)", "odd_port": "porta insolita", "vpn": "provider VPN (indicativo)",
           "tracker": "tracker / pubblicità", "tor": "nodo di uscita Tor", "malware": "malware in lista"}
MAX = len(COLORS) - 1


@dataclass
class Risk:
    level: int = 0                       # 0..5
    points: int = 0
    reasons: list = field(default_factory=list)

    @property
    def color(self) -> str:
        return COLORS[self.level]

    @property
    def name(self) -> str:
        return NAMES[self.level]


def color_of(level: int) -> str:
    return COLORS[max(0, min(MAX, level))]


def assess(dest: str, ips, org: str | None, ports, rep: tuple | None, countries=(), home_country: str = "",
           has_name: bool | None = None) -> Risk:
    """Punteggio di una destinazione non fidata. `rep` è il risultato di Reputation.lookup."""
    r = Risk()

    def add(key: str) -> None:
        r.points += POINTS[key]
        r.reasons.append(key)

    name = dest[6:] if dest.startswith("[dns] ") else dest
    if has_name is None:
        has_name = not _looks_ip(name)
    if not has_name:
        add("ip_only")
    if not org:
        add("no_org")
    if home_country and countries and all(c and c != home_country for c in countries):
        add("country")
    if name in DOH_HOSTS or any(ip in DOH_IPS for ip in ips):
        add("doh")
    if ports and any(p not in COMMON_PORTS for p in ports):
        add("odd_port")
    r.points = min(3, r.points)              # i segnali generici arrivano al massimo al rosso
    if rep and rep[0] in POINTS:
        add(rep[0])                          # fucsia e viola sono per le liste (tracker, Tor, malware)
    r.level = min(MAX, r.points)
    return r


def _looks_ip(s: str) -> bool:
    s = s.strip("[]")
    if ":" in s:
        return all(ch in "0123456789abcdefABCDEF:." for ch in s)
    parts = s.split(".")
    return len(parts) == 4 and all(p.isdigit() for p in parts)
