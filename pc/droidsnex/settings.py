"""Impostazioni del programma PC (pc/config.json): posizione, mappa, lingua, database.

I percorsi (database città, APK dell'agent) vengono salvati RELATIVI alla cartella del programma
(pc/ da sorgente, la cartella dell'exe se impacchettato) quando ci stanno dentro: così la cartella si
può spostare o copiare senza rompere la configurazione. Un percorso fuori dalla cartella resta
assoluto. `resolve()` li riporta ad assoluti quando servono.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields

from .paths import FROZEN, HOME_DIR

PATH_FIELDS = ("geo_db", "agent_apk")
# da sorgente anche la radice del progetto (la cartella sopra pc/) conta come "dentro": un APK in
# <progetto>/DroidSnex.apk o in android/app/build/... viene salvato come ../DroidSnex.apk, cosi' spostando
# tutto il progetto continua a funzionare
_ROOTS = [HOME_DIR] if FROZEN else [HOME_DIR, os.path.dirname(HOME_DIR)]


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))]) \
            == os.path.normcase(os.path.abspath(root))
    except ValueError:                      # Windows: unita' diverse
        return False


def to_stored(path: str) -> str:
    """Forma da salvare: relativa a HOME_DIR se il file sta dentro il programma (o il progetto), altrimenti com'e'."""
    p = (path or "").strip()
    if not p or not os.path.isabs(p):
        return p
    if not any(_inside(p, r) for r in _ROOTS):
        return p
    try:
        rel = os.path.relpath(p, HOME_DIR)
    except ValueError:
        return p
    return rel.replace(os.sep, "/")


def resolve(path: str) -> str:
    """Percorso assoluto: i relativi sono rispetto a HOME_DIR."""
    p = (path or "").strip()
    if not p or os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(HOME_DIR, p))



@dataclass
class Settings:
    home_lat: float | None = None        # la tua posizione (dove sta il telefono)
    home_lon: float | None = None
    home_name: str = ""
    home_country: str = ""               # paese della posizione rilevata dall'IP pubblico (scala di rischio)
    map_dark: bool = True                # mappa ricolorata in scuro, come il resto dell'interfaccia
    map_heat: bool = True                # mappa: stati colorati in base al traffico scambiato
    language: str = ""                   # lingua dell'interfaccia (vedi i18n.LANGUAGES); vuota = non ancora scelta
    terms_accepted: str = ""             # versione dei termini d'uso accettata (terms.TERMS_VERSION); vuota = mai
    terms_accepted_at: str = ""          # quando (data e ora locali)
    geo_db: str = ""                     # percorso del .mmdb; vuoto = data/dbip-city-lite.mmdb
    ip_active: bool = True               # Dettaglio IP: permesso il contatto attivo (certificato TLS)
    vt_key: str = ""                     # chiavi API facoltative per il Dettaglio IP (vuote = servizio disattivo)
    abuseipdb_key: str = ""
    shodan_key: str = ""
    ipinfo_key: str = ""
    update_url: str = ""                 # dove controllare le nuove versioni (solo dal pulsante in Config); vuoto = updates.DEFAULT_URL
    agent_apk: str = ""                  # APK dell'agent da installare sul telefono; vuoto = quello predefinito (cli.find_apk)

    @classmethod
    def load(cls, path: str) -> "Settings":
        s = cls()
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            names = {f.name for f in fields(cls)}
            for k, v in data.items():
                if k in names:
                    setattr(s, k, v)
        except (OSError, ValueError):
            return s
        # config.json vecchio con percorsi assoluti dentro il programma: lo si converte subito in relativo
        if any(to_stored(getattr(s, k) or "") != (getattr(s, k) or "") for k in PATH_FIELDS):
            s.save(path)
        return s

    def resolve(self, name: str) -> str:
        """Il percorso assoluto del campo `name` (geo_db, agent_apk)."""
        return resolve(getattr(self, name, "") or "")

    def save(self, path: str) -> None:
        data = asdict(self)
        for k in PATH_FIELDS:
            data[k] = to_stored(data.get(k) or "")
            setattr(self, k, data[k])
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError:
            pass
