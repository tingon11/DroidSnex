"""Schermo del telefono sul PC con scrcpy (Genymobile), come in AndrOsint.

scrcpy si usa SOLO dalla cartella pc/tools/scrcpy e si scarica SOLO dal pulsante in Config
(release ufficiale per Windows da GitHub): mai in automatico, mai quello del sistema.
Il processo scrcpy usa l'adb di pc/tools/platform-tools (variabile ADB), così non parte un
secondo server adb di versione diversa.

scrcpy apre la sua finestra (con la barra del titolo), esattamente come in AndrOsint: mouse e
tastiera dentro la finestra vanno al telefono.
"""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request
import zipfile
from typing import Callable

from .geo import USER_AGENT
from .platform_tools import TOOLS_DIR
from .proc import hidden

API_URL = "https://api.github.com/repos/Genymobile/scrcpy/releases/latest"
LATEST_URL = "https://github.com/Genymobile/scrcpy/releases/latest"
DOWNLOAD_URL = "https://github.com/Genymobile/scrcpy/releases/download/{tag}/scrcpy-win64-{tag}.zip"
WINDOW_TITLE = "DroidSnex · schermo"


def exe_name() -> str:
    return "scrcpy.exe" if os.name == "nt" else "scrcpy"


def local_dir(tools_dir: str = TOOLS_DIR) -> str:
    return os.path.join(tools_dir, "scrcpy")


def local_scrcpy(tools_dir: str = TOOLS_DIR) -> str | None:
    """scrcpy dentro tools/scrcpy (anche in una sottocartella, come nello zip ufficiale)."""
    root = local_dir(tools_dir)
    p = os.path.join(root, exe_name())
    if os.path.isfile(p):
        return p
    if os.path.isdir(root):
        for sub in sorted(os.listdir(root)):
            p = os.path.join(root, sub, exe_name())
            if os.path.isfile(p):
                return p
    return None


def version(path: str) -> str:
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10,
                             encoding="utf-8", errors="replace", **hidden()).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"scrcpy\s+v?([0-9][0-9.]*)", out)
    return m.group(1) if m else ""




def latest_tag(timeout: float = 20) -> str:
    """Tag dell'ultima release (es. v3.3.1): dall'API di GitHub, altrimenti dal redirect di /latest."""
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.load(r)
        tag = data.get("tag_name")
        if tag:
            return tag
    except Exception:  # noqa: BLE001 - si prova con il redirect
        pass
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        final = r.geturl()
    m = re.search(r"/tag/(v[0-9][0-9.]*)", final)
    if not m:
        raise ValueError(f"release di scrcpy non trovata ({final})")
    return m.group(1)


def download(tools_dir: str = TOOLS_DIR, progress: Callable[[int, int], None] | None = None,
             cancel: Callable[[], bool] | None = None, timeout: float = 60) -> str:
    """Scarica l'ultima release Windows di scrcpy in tools/scrcpy. Ritorna il percorso di scrcpy.exe."""
    if os.name != "nt":
        raise OSError("il download automatico di scrcpy è previsto solo per Windows: su Linux/macOS "
                      "copia scrcpy nella cartella tools/scrcpy")
    os.makedirs(tools_dir, exist_ok=True)
    tag = latest_tag()
    url = DOWNLOAD_URL.format(tag=tag)
    fd, tmp_zip = tempfile.mkstemp(suffix=".zip", dir=tools_dir)
    os.close(fd)
    tmp_dir = tempfile.mkdtemp(prefix="scrcpy-", dir=tools_dir)
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
                if not target.startswith(root + os.sep):
                    raise ValueError(f"percorso non valido nello zip: {m.filename}")
            z.extractall(tmp_dir)
        # lo zip ufficiale ha una cartella radice (scrcpy-win64-vX.Y.Z)
        src = tmp_dir
        entries = os.listdir(tmp_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
            src = os.path.join(tmp_dir, entries[0])
        if not os.path.isfile(os.path.join(src, exe_name())):
            raise ValueError(f"{exe_name()} non presente nello zip {os.path.basename(url)}")
        dest = local_dir(tools_dir)
        old = dest + ".old"
        shutil.rmtree(old, ignore_errors=True)
        if os.path.isdir(dest):
            try:
                os.replace(dest, old)          # scrcpy.exe in uso non si sovrascrive (Windows)
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


class ScrcpyError(RuntimeError):
    pass


class Scrcpy:
    """Un processo scrcpy alla volta."""

    def __init__(self, adb_path: str | None = None):
        self.adb_path = adb_path
        self.proc: subprocess.Popen | None = None
        self.output: collections.deque = collections.deque(maxlen=40)
        self.title = WINDOW_TITLE

    @property
    def path(self) -> str | None:
        return local_scrcpy()

    @property
    def available(self) -> bool:
        return self.path is not None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, serial: str | None, max_size: int = 1024, bitrate: str = "4M", max_fps: int = 30,
              borderless: bool = False, on_top: bool = False, stay_awake: bool = True, extra: tuple = (),
              title: str | None = None, lock_portrait: bool = True, window_scale: float = 0.5) -> None:
        """Apre la finestra di scrcpy (la sua, con la barra del titolo), con le stesse opzioni di AndrOsint:
        risoluzione max 1024, 4 Mbps, 30 fps, senza audio, telefono sveglio. La finestra parte a
        `window_scale` della dimensione del video (0.5 = metà); la si può poi ridimensionare."""
        if self.running():
            return
        exe = self.path
        if not exe:
            raise ScrcpyError("scrcpy non presente nella cartella tools: scaricalo dal tab Config")
        ver = version(exe)
        major = int(ver.split(".")[0]) if ver and ver[0].isdigit() else 0
        self.title = title or f"{WINDOW_TITLE} · {int(time.time()) % 100000}"
        argv = [exe]
        if serial:
            argv += ["-s", serial]
        if max_size:
            argv += ["--max-size", str(max_size)]
        if bitrate:
            argv += ["--video-bit-rate" if major >= 2 else "--bit-rate", bitrate]
        if max_fps:
            argv += ["--max-fps", str(max_fps)]
        if major >= 2:
            argv.append("--no-audio")
        if stay_awake:
            argv.append("--stay-awake")
        if borderless:
            argv.append("--window-borderless")
        if on_top:
            argv.append("--always-on-top")
        if lock_portrait:
            # orientamento verticale fisso, anche se il telefono viene ruotato
            argv.append("--capture-orientation=@0" if major >= 3 else "--lock-video-orientation=0")
        if window_scale and max_size and 0 < window_scale < 1:
            # altezza iniziale della finestra (la larghezza segue le proporzioni del telefono)
            argv += ["--window-height", str(int(max_size * window_scale))]
        argv += ["--window-title", self.title, *extra]
        env = os.environ.copy()
        if self.adb_path:
            env["ADB"] = self.adb_path
        try:
            self.proc = subprocess.Popen(argv, cwd=os.path.dirname(exe), env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         **hidden())
        except OSError as e:
            raise ScrcpyError(f"impossibile avviare scrcpy: {e}") from e
        self.output.clear()
        threading.Thread(target=self._drain, args=(self.proc,), daemon=True).start()

    def _drain(self, proc) -> None:
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self.output.append(line)
        except (OSError, ValueError):
            pass

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
        except OSError:
            pass

    def last_error(self) -> str:
        proc = self.proc
        if proc is None or proc.poll() is None or proc.returncode == 0:
            return ""
        errs = [x for x in self.output if "ERROR" in x or "error" in x.lower()]
        return "\n".join(errs or list(self.output)[-5:])

    # ------------------------------------------------------------ finestra (solo Windows)
    def find_window(self) -> int:
        """HWND della finestra di scrcpy (0 se non c'è ancora): prima per titolo, poi fra le finestre
        visibili del processo scrcpy (il titolo potrebbe non corrispondere alla lettera)."""
        if os.name != "nt":
            return 0
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        hwnd = int(u.FindWindowW(None, self.title) or 0)
        if hwnd:
            return hwnd
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return 0
        found = []
        pid = proc.pid

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def cb(h, _l):
            wpid = wt.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(wpid))
            if wpid.value == pid and u.IsWindowVisible(h) and not u.GetParent(h):
                n = u.GetWindowTextLengthW(h)
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(h, buf, n + 1)
                found.append((h, buf.value))
            return True
        u.EnumWindows(cb, 0)
        # la finestra video di scrcpy è quella con il nostro titolo o, se non c'è, la prima con un titolo
        for h, t in found:
            if t.startswith(WINDOW_TITLE):
                return int(h)
        return int(found[0][0]) if found else 0

    @staticmethod
    def set_owner(hwnd: int, owner_hwnd: int) -> bool:
        """Rende la finestra di scrcpy "posseduta" dalla nostra: resta sempre sopra DroidSnex (mai sotto),
        ma non sopra le altre applicazioni (niente always-on-top)."""
        if os.name != "nt" or not hwnd or not owner_hwnd:
            return False
        import ctypes
        import ctypes.wintypes as wt
        u = ctypes.windll.user32
        GWLP_HWNDPARENT = -8
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            fn = u.SetWindowLongPtrW
            fn.restype = ctypes.c_longlong
            fn.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_longlong]
        else:
            fn = u.SetWindowLongW
            fn.restype = ctypes.c_long
            fn.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
        fn(hwnd, GWLP_HWNDPARENT, owner_hwnd)
        SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x10, 0x20
        u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_FRAMECHANGED)
        return True

    @staticmethod
    def adopt(hwnd: int, parent_hwnd: int, w: int, h: int) -> bool:
        """Mette la finestra di scrcpy dentro la nostra (stile WS_CHILD, senza bordi)."""
        if os.name != "nt" or not hwnd:
            return False
        import ctypes
        u = ctypes.windll.user32
        GWL_STYLE, GWL_EXSTYLE = -16, -20
        WS_CHILD, WS_VISIBLE, WS_POPUP, WS_CAPTION, WS_THICKFRAME = 0x40000000, 0x10000000, 0x80000000, 0x00C00000, 0x00040000
        WS_EX_TOPMOST, WS_EX_APPWINDOW = 0x8, 0x40000
        style = u.GetWindowLongW(hwnd, GWL_STYLE)
        style = (style & ~(WS_POPUP | WS_CAPTION | WS_THICKFRAME)) | WS_CHILD | WS_VISIBLE
        u.SetWindowLongW(hwnd, GWL_STYLE, style)
        ex = u.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u.SetWindowLongW(hwnd, GWL_EXSTYLE, ex & ~(WS_EX_TOPMOST | WS_EX_APPWINDOW))
        if not u.SetParent(hwnd, parent_hwnd):
            return False
        u.MoveWindow(hwnd, 0, 0, max(1, w), max(1, h), True)
        return True

    @staticmethod
    def move(hwnd: int, w: int, h: int) -> None:
        if os.name == "nt" and hwnd:
            import ctypes
            ctypes.windll.user32.MoveWindow(hwnd, 0, 0, max(1, w), max(1, h), True)

    @staticmethod
    def focus(hwnd: int) -> None:
        if os.name == "nt" and hwnd:
            import ctypes
            ctypes.windll.user32.SetFocus(hwnd)


def describe() -> str:
    p = local_scrcpy()
    if not p:
        return ""
    v = version(p)
    return f"scrcpy {v}" if v else p

