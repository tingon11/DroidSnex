"""Posizione del telefono letta via adb, senza permessi in più per l'agent.

Android tiene in memoria l'ultima posizione di ogni sorgente (gps, rete, fused, passive) e la mostra in
`adb shell dumpsys location`. Qui si legge quell'elenco e si sceglie la più affidabile: precisione di
metri quando il GPS ha un punto recente, contro le decine di chilometri della posizione ricavata dall'IP
pubblico. Niente internet. Se la localizzazione è spenta o nessuna app l'ha usata di recente, l'elenco
è vuoto e si resta con la posizione di prima.

    best(adb)  ->  Fix(lat, lon, accuracy_m, provider, age_s) | None
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Location[gps 45.649500,13.776800 hAcc=12 et=+1d2h3m4s5ms alt=...]   (Android 8+; con alcune lingue i
# decimali escono con la virgola: 45,649500,13,776800).  Android 7 e precedenti: acc=12
_LOC = re.compile(r"Location\[(\w+)\s+(-?\d+[.,]\d+),(-?\d+[.,]\d+)([^\]]*)\]")
_ACC = re.compile(r"\b(?:hAcc|acc)=(\d+(?:[.,]\d+)?)")
_ET = re.compile(r"\bet=\+?((?:\d+d)?(?:\d+h)?(?:\d+m(?!s))?(?:\d+s)?(?:\d+ms)?)")
_PART = re.compile(r"(\d+)(ms|d|h|m|s)")
_UNIT = {"d": 86400.0, "h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
_RANK = {"gps": 0, "fused": 1, "network": 2, "passive": 3}


@dataclass
class Fix:
    lat: float
    lon: float
    accuracy: float | None      # metri (None = non dichiarata)
    provider: str               # gps, fused, network, passive
    age: float | None           # secondi da quando è stata rilevata (None = non si sa)


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def _elapsed(text: str) -> float | None:
    """"+1d2h3m4s5ms" (tempo dall'accensione al momento del rilevamento) in secondi."""
    m = _ET.search(text)
    if not m or not m.group(1):
        return None
    return sum(int(n) * _UNIT[u] for n, u in _PART.findall(m.group(1)))


def parse(dump: str, uptime: float | None = None) -> list[Fix]:
    """Tutte le posizioni presenti nell'uscita di `dumpsys location`, senza doppioni."""
    out: dict[tuple, Fix] = {}
    for m in _LOC.finditer(dump):
        try:
            lat, lon = _num(m.group(2)), _num(m.group(3))
        except ValueError:
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (abs(lat) < 1e-6 and abs(lon) < 1e-6):
            continue
        rest = m.group(4)
        a = _ACC.search(rest)
        et = _elapsed(rest)
        age = max(0.0, uptime - et) if uptime is not None and et is not None else None
        fix = Fix(lat, lon, _num(a.group(1)) if a else None, m.group(1).lower(), age)
        key = (fix.provider, round(lat, 6), round(lon, 6))
        if key not in out or (age is not None and (out[key].age is None or age < out[key].age)):
            out[key] = fix
    return list(out.values())


def choose(fixes: list[Fix]) -> Fix | None:
    """La più affidabile: prima quelle recenti (meno di un'ora), poi la più precisa; a parità, il GPS."""
    if not fixes:
        return None

    def score(f: Fix):
        old = 0 if f.age is None or f.age < 3600 else 1 if f.age < 86400 else 2
        return (old, f.accuracy if f.accuracy is not None else 5000.0, _RANK.get(f.provider, 4), f.age or 0.0)
    return min(fixes, key=score)


def best(adb) -> Fix | None:
    """Legge la posizione dal telefono collegato (adb è un droidsnex.adb.Adb con il device scelto)."""
    dump = adb.shell("dumpsys location", timeout=20)
    uptime = None
    try:
        uptime = float(adb.shell("cat /proc/uptime", timeout=5).split()[0])
    except (ValueError, IndexError):
        pass
    return choose(parse(dump, uptime))
