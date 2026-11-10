# DroidSnex — controllo delle nuove versioni.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Controllo di una nuova versione, solo quando l'utente preme il pulsante in Config (mai da solo) e
senza scaricare niente: legge un piccolo JSON dall'indirizzo impostato e confronta la versione.

Formati accettati all'indirizzo `update_url`:
  - progetto GitHub: https://github.com/<utente>/<progetto>  (predefinito: DEFAULT_URL), convertito in
                     https://api.github.com/repos/<utente>/<progetto>/releases/latest (campi tag_name, html_url, body)
  - file proprio:    {"version": "1.2.0", "url": "https://…/download", "notes": "cosa cambia"}
"""
from __future__ import annotations

import json
import re
import urllib.request

from . import __version__
from .i18n import tr

USER_AGENT = f"DroidSnex/{__version__}"
DEFAULT_URL = "https://github.com/tingon11/DroidSnex"      # usato quando in Config il campo è vuoto


def api_url(url: str) -> str:
    """L'indirizzo di un progetto GitHub (https://github.com/<utente>/<progetto>) diventa quello delle sue release."""
    m = re.match(r"^https://(?:www\.)?github\.com/([^/\s]+)/([^/\s#?]+?)(?:\.git)?(?:/releases(?:/latest)?)?/?$", url.strip(), re.I)
    return f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/releases/latest" if m else url.strip()


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3-beta' -> (1, 2, 3). Vuoto se non c'è nessun numero."""
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    return tuple(int(x) for x in m.group(0).split(".")) if m else ()


def is_newer(remote: str, local: str = __version__) -> bool:
    a, b = parse_version(remote), parse_version(local)
    n = max(len(a), len(b))
    return bool(a) and a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def read(data: dict) -> dict:
    """Normalizza la risposta: {"version", "url", "notes"}."""
    if not isinstance(data, dict):
        raise ValueError(tr("risposta non valida"))
    version = str(data.get("version") or data.get("tag_name") or data.get("name") or "").strip()
    if not parse_version(version):
        raise ValueError(tr("versione non trovata nella risposta"))
    url = str(data.get("url") if "version" in data else data.get("html_url") or "").strip()
    if not url.lower().startswith("https://"):
        url = ""
    notes = str(data.get("notes") or data.get("body") or "").strip()
    return {"version": version.lstrip("vV"), "url": url, "notes": notes[:2000]}


def check(url: str, timeout: float = 10) -> dict:
    """Legge la versione pubblicata. Ritorna {"version", "url", "notes", "newer"}; solleva OSError / ValueError."""
    page = (url or "").strip() or DEFAULT_URL
    url = api_url(page)
    if not url.lower().startswith("https://"):
        raise ValueError(tr("l'indirizzo deve iniziare con https://"))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - solo https, controllato sopra
        raw = r.read(256 * 1024)
    info = read(json.loads(raw.decode("utf-8", "replace")))
    info["newer"] = is_newer(info["version"])
    if not info["url"] and page != url:
        info["url"] = page.rstrip("/") + "/releases"
    return info
