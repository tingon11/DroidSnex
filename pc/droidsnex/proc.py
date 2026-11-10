"""Avvio di processi esterni (adb, scrcpy, guardiano) senza finestre di console su Windows.

Da un eseguibile senza console (PyInstaller --windowed) ogni subprocess.run/Popen di un programma a riga
di comando apre e chiude una finestra nera: con CREATE_NO_WINDOW + STARTUPINFO nascosto non succede.
Su Linux/macOS `hidden()` e' vuoto.
"""
from __future__ import annotations

import os
import subprocess


def hidden(extra_flags: int = 0) -> dict:
    """kwargs per subprocess.run/Popen: niente finestra di console (Windows), altrimenti nulla."""
    if os.name != "nt":
        return {}
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW | extra_flags, "startupinfo": si}
