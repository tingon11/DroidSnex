"""Android Platform Tools (adb) scaricati da Google nella cartella del programma.

Come in AndrOsint: niente installazione nel sistema e niente modifiche al PATH.
Lo zip ufficiale di Google viene estratto in pc/tools/platform-tools/ e DroidSnex
usa SOLO quell'adb (mai quello del sistema o dell'Android SDK). Non viene mai
scaricato da solo: solo col pulsante 'Scarica / aggiorna da Google' nel tab Config.
"""
from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from typing import Callable

from .geo import USER_AGENT

from .paths import HOME_DIR
from .proc import hidden

TOOLS_DIR = os.path.join(HOME_DIR, "tools")   # pc/tools (da sorgente) o tools/ accanto all'eseguibile

BASE_URL = "https://dl.google.com/android/repository/platform-tools-latest-{os}.zip"
PAGE_URL = "https://developer.android.com/tools/releases/platform-tools"


def os_name() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def download_url() -> str:
    return BASE_URL.format(os=os_name())


def exe_name() -> str:
    return "adb.exe" if os.name == "nt" else "adb"


def local_dir(tools_dir: str = TOOLS_DIR) -> str:
    return os.path.join(tools_dir, "platform-tools")


def local_adb(tools_dir: str = TOOLS_DIR) -> str | None:
    p = os.path.join(local_dir(tools_dir), exe_name())
    return p if os.path.isfile(p) else None


def adb_version(path: str) -> str:
    """Prima riga utile di `adb version` (es. "1.0.41 · 35.0.2-12147458"), "" se non risponde."""
    try:
        out = subprocess.run([path, "version"], capture_output=True, text=True, timeout=10,
                             encoding="utf-8", errors="replace", **hidden()).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    bridge = ver = ""
    for line in out.splitlines():
        line = line.strip()
        if line.lower().startswith("android debug bridge version"):
            bridge = line.split()[-1]
        elif line.lower().startswith("version "):
            ver = line.split(None, 1)[1]
    return " · ".join(x for x in (bridge, ver) if x)


def download(tools_dir: str = TOOLS_DIR, progress: Callable[[int, int], None] | None = None,
             cancel: Callable[[], bool] | None = None, url: str | None = None, timeout: float = 60) -> str:
    """Scarica lo zip ufficiale e lo estrae in tools/platform-tools. Ritorna il percorso di adb."""
    os.makedirs(tools_dir, exist_ok=True)
    url = url or download_url()
    fd, tmp_zip = tempfile.mkstemp(suffix=".zip", dir=tools_dir)
    os.close(fd)
    tmp_dir = tempfile.mkdtemp(prefix="pt-", dir=tools_dir)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp_zip, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                if cancel and cancel():
                    raise InterruptedError
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress:
                    progress(got, total)
        with zipfile.ZipFile(tmp_zip) as z:
            root = os.path.realpath(tmp_dir)
            for m in z.infolist():
                target = os.path.realpath(os.path.join(tmp_dir, m.filename))
                if not target.startswith(root + os.sep):          # niente percorsi fuori dalla cartella
                    raise ValueError(f"percorso non valido nello zip: {m.filename}")
            z.extractall(tmp_dir)
        src = os.path.join(tmp_dir, "platform-tools")
        if not os.path.isfile(os.path.join(src, exe_name())):
            raise ValueError(f"{exe_name()} non presente nello zip")
        if os.name != "nt":
            for name in os.listdir(src):
                p = os.path.join(src, name)
                if os.path.isfile(p):
                    os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        dest = local_dir(tools_dir)
        old = dest + ".old"
        if os.path.isdir(old):
            shutil.rmtree(old, ignore_errors=True)
        if os.path.isdir(dest):
            # su Windows adb.exe in uso non si può sovrascrivere: si sposta la cartella vecchia
            try:
                os.replace(dest, old)
            except OSError:
                shutil.rmtree(dest, ignore_errors=True)
        os.replace(src, dest)
        shutil.rmtree(old, ignore_errors=True)
        return os.path.join(dest, exe_name())
    finally:
        try:
            os.remove(tmp_zip)
        except OSError:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)


def describe_platform() -> str:
    return f"{os_name()} · {platform.machine()}"
