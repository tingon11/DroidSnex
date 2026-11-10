"""Guardiano: un processo a parte che sopravvive al crash del programma PC e pulisce il telefono.

Start lo avvia subito dopo aver installato l'agent, passandogli un tubo (stdin). Finché il programma
principale vive, il tubo resta aperto. Se il programma si chiude bene manda "bye" (ha già fermato e
disinstallato l'agent da solo) e il guardiano esce senza fare nulla. Se invece il programma crasha,
viene ucciso o chiuso brutalmente, il sistema chiude il tubo: il guardiano se ne accorge, ferma la
cattura, toglie il forward e disinstalla l'agent dal telefono (ritentando per un po' se il telefono
non risponde subito). Così l'app sul telefono non resta mai installata per sbaglio.

Uso (lanciato da gui/app.py, non a mano):
    python -m droidsnex.guard --adb <adb> --serial <seriale> --port <porta locale> --log <file>
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from . import ACTION_STOP, ACTIVITY, PACKAGE
from .proc import hidden

RETRY_SEC = 120          # per quanto insistere se il telefono non risponde (cavo staccato, ecc.)


def _run(adb: str, serial: str, *args: str, timeout: float = 60) -> tuple[int, str]:
    cmd = [adb] + (["-s", serial] if serial else []) + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                           errors="replace", **hidden())
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()


def cleanup(adb: str, serial: str, port: int, log) -> bool:
    """Ferma la cattura, toglie il forward, disinstalla. True se la disinstallazione e' riuscita."""
    rc, out = _run(adb, serial, "get-state", timeout=15)
    if rc != 0 or "device" not in out:
        log(f"telefono non raggiungibile: {out}")
        return False
    rc, out = _run(adb, serial, "shell", f"am start -n {ACTIVITY} -a {ACTION_STOP}")
    log(f"stop cattura: {out or rc}")
    time.sleep(1.5)
    _run(adb, serial, "shell", f"am force-stop {PACKAGE}")
    _run(adb, serial, "forward", "--remove", f"tcp:{port}", timeout=15)
    rc, out = _run(adb, serial, "uninstall", PACKAGE, timeout=90)
    log(f"uninstall: {out or rc}")
    rc2, out2 = _run(adb, serial, "shell", f"pm list packages {PACKAGE}", timeout=15)
    return f"package:{PACKAGE}" not in out2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adb", required=True)
    ap.add_argument("--serial", default="")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--log", default="")
    a = ap.parse_args(argv)

    def log(msg: str) -> None:
        line = time.strftime("%Y-%m-%d %H:%M:%S") + f"  guard[{os.getpid()}]  {msg}\n"
        if a.log:
            try:
                with open(a.log, "a", encoding="utf-8") as f:
                    f.write(line)
            except OSError:
                pass

    log(f"in ascolto: seriale {a.serial or '-'} porta {a.port}")
    # aspetta "bye" (chiusura regolare) o la fine del tubo (programma morto)
    line = b""
    try:
        line = sys.stdin.buffer.readline()
    except (OSError, ValueError):
        pass
    if line.strip() == b"bye":
        log("chiusura regolare del programma: niente da fare")
        return 0
    log("programma PC sparito: pulizia del telefono")
    t0 = time.time()
    while True:
        if cleanup(a.adb, a.serial, a.port, log):
            log("agent disinstallato")
            return 0
        if time.time() - t0 > RETRY_SEC:
            log("rinuncio: il telefono non ha risposto (l'agent si ferma da solo con il watchdog; "
                "al prossimo Start viene reinstallato e poi rimosso)")
            return 1
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
