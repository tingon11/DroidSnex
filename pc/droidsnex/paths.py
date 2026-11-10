"""Dove stanno le cose: risorse incluse (sola lettura) e file di lavoro (scrivibili).

Da sorgente tutto sta in pc/: codice, data/, tools/, sessions/, captures/, config.json. Nell'eseguibile
Windows (PyInstaller in cartella, vedi tools/build_exe.py) il codice e le risorse incluse (assets,
licenze) stanno in dist/DroidSnex/_internal/: lì non si salva niente. L'agent sta accanto
all'exe come DroidSnex.apk. I file di lavoro vanno accanto all'eseguibile
(DroidSnex.exe) e, se quella cartella non e' scrivibile (es. Programmi), in %LOCALAPPDATA%\\DroidSnex.

    BUNDLE_DIR   risorse incluse: LICENSE, NOTICE, LICENSES/, docs/ (sola lettura)
    MANUAL_DIR   manuali: docs/manual/<lingua>/MANUAL.md (pulsante "Manuale" nel menu di sinistra)
    HOME_DIR     file di lavoro: data/, tools/, sessions/, captures/, config.json, trusted.json
"""
from __future__ import annotations

import os
import sys

FROZEN = bool(getattr(sys, "frozen", False))
_PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # cartella pc/ (da sorgente)

BUNDLE_DIR = getattr(sys, "_MEIPASS", None) or _PC


def _writable(d: str) -> bool:
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".droidsnex-write-test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _home() -> str:
    if not FROZEN:
        return _PC
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if _writable(exe_dir):
        return exe_dir
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "DroidSnex")


HOME_DIR = _home()

MANUAL_DIR = os.path.join(BUNDLE_DIR, "docs", "manual")


def manual_path(lang: str) -> str | None:
    """MANUAL.md nella lingua, altrimenti in inglese, altrimenti in italiano; None se non c'e' niente."""
    for code in (lang, "en", "it"):
        p = os.path.join(MANUAL_DIR, code or "", "MANUAL.md")
        if code and os.path.isfile(p):
            return p
    return None
