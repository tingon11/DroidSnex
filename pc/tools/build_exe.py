#!/usr/bin/env python3
"""Crea DroidSnex.exe con PyInstaller, in una cartella (pc/dist/DroidSnex/), e facoltativamente ricompila l'APK.

Da eseguire su Windows, nella cartella pc/ (o da qualunque cartella: i percorsi sono assoluti):

    python tools\\build_exe.py              # cartella dist\\DroidSnex\\ con DroidSnex.exe, DroidSnex.apk e le risorse (+ zip)
    python tools\\build_exe.py --apk        # prima gradlew assembleDebug, poi l'exe con l'APK appena compilato
    python tools\\build_exe.py --apk --release
    python tools\\build_exe.py --console    # exe con la finestra della console (per vedere gli errori)

Serve PyInstaller nello stesso ambiente Python della GUI:  pip install pyinstaller

La compilazione e' sempre quella normale "in cartella" (onedir): l'exe carica le risorse da
dist/DroidSnex/_internal/ senza estrarre niente. Il file unico (--onefile) non e' piu' previsto: si
auto-estrae in una cartella temporanea a ogni avvio e gli antivirus lo segnalano spesso per sbaglio.
In piu' lo script NON usa UPX, incorpora le informazioni di versione Windows (nome prodotto, azienda,
versione, copyright) e l'icona, ed esclude i moduli inutili. Se Windows Security blocca comunque l'exe:
aggiungi un'esclusione per la cartella (Sicurezza di Windows > Protezione da virus e minacce > Gestisci
impostazioni > Esclusioni) e segnala il falso positivo a Microsoft (https://www.microsoft.com/wdsi/filesubmission).

L'APK dell'agent finisce nella release come DroidSnex.apk, accanto a DroidSnex.exe (e quindi nello zip): e'
il compilato piu' recente fra android/app/build/outputs/apk/{release,debug}, <progetto>/DroidSnex.apk e
pc/agent.apk. Il programma lo trova da solo li' accanto.

Cosa finisce nella cartella: il codice, gli assets (logo, icona, mappa 1:50m, contorni), DroidSnex.apk, LICENSE,
NOTICE, THIRD_PARTY_NOTICES.md, la cartella LICENSES e docs/ (manuali). Cosa resta FUORI e viene scaricato dal tab Config
nella cartella accanto all'exe (o in %LOCALAPPDATA%\\DroidSnex se quella non e' scrivibile): adb
(platform-tools), scrcpy, database DB-IP, mappa 1:10m, liste di reputazione e range cloud. Anche
config.json, trusted.json, sessions/ e captures/ stanno accanto all'exe e NON entrano nella release:
config.json contiene dati personali (chiavi API). Niente di tutto questo va ridistribuito con
l'eseguibile (termini di Google per platform-tools, licenze dei database).

Risultato:  pc/dist/DroidSnex/DroidSnex.exe + DroidSnex.apk  (+ zip pc/dist/DroidSnex-<versione>.zip con tutta la cartella)
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

PC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(PC)
ANDROID = os.path.join(REPO, "android")
APK_OUT = {"debug": os.path.join(ANDROID, "app", "build", "outputs", "apk", "debug", "app-debug.apk"),
           "release": os.path.join(ANDROID, "app", "build", "outputs", "apk", "release", "app-release.apk")}


def say(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def run(cmd: list[str], cwd: str) -> None:
    say(" ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def build_apk(release: bool) -> str:
    wrapper = os.path.join(ANDROID, "gradlew.bat" if os.name == "nt" else "gradlew")
    if not os.path.isfile(wrapper):
        sys.exit(f"gradlew non trovato in {ANDROID}: apri il progetto android/ in Android Studio una volta, "
                 "oppure compila l'APK da li' e copialo in pc/agent.apk")
    task = "assembleRelease" if release else "assembleDebug"
    run([wrapper, task], cwd=ANDROID)
    src = APK_OUT["release" if release else "debug"]
    if not os.path.isfile(src):
        sys.exit(f"APK non trovato dopo la build: {src}")
    dst = os.path.join(PC, "agent.apk")
    shutil.copy2(src, dst)
    say(f"APK copiato in {dst}")
    return dst


def newest_apk() -> str | None:
    """Il compilato piu' recente dell'agent fra quelli che si trovano nel progetto."""
    found = [p for p in (APK_OUT["release"], APK_OUT["debug"], os.path.join(REPO, "DroidSnex.apk"),
                         os.path.join(PC, "agent.apk")) if os.path.isfile(p)]
    return max(found, key=os.path.getmtime) if found else None


PRIVATE = ("config.json", "trusted.json", "sessions", "captures", "data", "tools")


def version() -> str:
    sys.path.insert(0, PC)
    try:
        from droidsnex import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "dev"


EXCLUDES = ["unittest", "pydoc", "doctest", "test", "tests", "lib2to3", "xmlrpc", "pdb", "cProfile", "profile",
            "tkinter.test", "distutils", "setuptools", "pip", "numpy", "matplotlib", "scipy", "pandas"]


def version_tuple(v: str) -> tuple[int, int, int, int]:
    nums = []
    for part in v.split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    nums = (nums + [0, 0, 0, 0])[:4]
    return tuple(nums)  # type: ignore[return-value]


def write_version_info(path: str, ver: str) -> None:
    """File di versione Windows per PyInstaller: nome prodotto, azienda, versione, copyright.
    Un exe senza queste informazioni e' uno dei segnali che gli antivirus pesano di piu'."""
    t = version_tuple(ver)
    txt = f"""# -*- coding: utf-8 -*-
VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'DroidSnex'),
      StringStruct('FileDescription', 'DroidSnex - monitor del traffico di rete Android'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'DroidSnex'),
      StringStruct('LegalCopyright', 'Copyright (c) 2026 DroidSnex - licenza MIT'),
      StringStruct('OriginalFilename', 'DroidSnex.exe'),
      StringStruct('ProductName', 'DroidSnex'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(txt)


def build_exe(console: bool) -> str:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("PyInstaller non installato:  pip install pyinstaller")
    sep = ";" if os.name == "nt" else ":"
    ver = version()
    build_dir = os.path.join(PC, "build")
    os.makedirs(build_dir, exist_ok=True)
    vinfo = os.path.join(build_dir, "version_info.txt")
    write_version_info(vinfo, ver)
    apk = newest_apk()
    if apk is None:
        say("ATTENZIONE: nessun APK compilato trovato: la release sara' senza agent (usa --apk o compila da Android Studio)")
    datas = [(os.path.join(PC, "droidsnex", "gui", "assets"), os.path.join("droidsnex", "gui", "assets"))]
    for name in ("LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.md"):
        p = os.path.join(REPO, name)
        if os.path.isfile(p):
            datas.append((p, "."))
    lic_dir = os.path.join(REPO, "LICENSES")
    if os.path.isdir(lic_dir):
        datas.append((lic_dir, "LICENSES"))
    docs = os.path.join(PC, "docs")                  # manuali: docs/manual/<lingua>/MANUAL.md + immagini
    if os.path.isdir(docs):
        datas.append((docs, "docs"))
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onedir", "--name", "DroidSnex",
           "--noupx",                                   # UPX e' il primo motivo di falsi positivi
           "--icon", os.path.join(PC, "droidsnex", "gui", "assets", "droidsnex.ico"),
           "--distpath", os.path.join(PC, "dist"), "--workpath", build_dir, "--specpath", build_dir,
           "--collect-all", "customtkinter",            # customtkinter ha file .json/.otf che altrimenti mancano
           "--hidden-import", "PIL.ImageTk", "--hidden-import", "PIL._tkinter_finder", "--hidden-import", "tkinter.ttk", "--hidden-import", "tkinter.filedialog"]
    if os.name == "nt":
        cmd += ["--version-file", vinfo]
    for m in EXCLUDES:
        cmd += ["--exclude-module", m]
    if not console:
        cmd.append("--windowed")
    for src, dst in datas:
        cmd += ["--add-data", f"{src}{sep}{dst}"]
    cmd.append(os.path.join(PC, "gui.py"))
    run(cmd, cwd=PC)
    ext = ".exe" if os.name == "nt" else ""
    folder = os.path.join(PC, "dist", "DroidSnex")
    exe = os.path.join(folder, "DroidSnex" + ext)
    if not os.path.isfile(exe):
        sys.exit("PyInstaller non ha prodotto l'eseguibile (vedi i messaggi sopra)")
    if apk is not None:                              # l'agent accanto all'exe, con il nome della release
        shutil.copy2(apk, os.path.join(folder, "DroidSnex.apk"))
        say(f"APK nella release: DroidSnex.apk  (da {os.path.relpath(apk, REPO)})")
    for name in PRIVATE:                             # mai dati personali o file scaricati nella release
        if os.path.exists(os.path.join(folder, name)):
            sys.exit(f"dist/DroidSnex/{name} non deve stare nella release (dati personali o file scaricati): "
                     "toglilo e rilancia")
    archive = shutil.make_archive(os.path.join(PC, "dist", f"DroidSnex-{ver}"), "zip",
                                  root_dir=os.path.join(PC, "dist"), base_dir="DroidSnex")
    say(f"fatto: {folder}  ·  zip: {os.path.basename(archive)}")
    return exe


def main() -> int:
    ap = argparse.ArgumentParser(description="DroidSnex: eseguibile Windows in cartella (e, con --apk, l'APK dell'agent)")
    ap.add_argument("--apk", action="store_true", help="ricompila l'APK con gradlew prima dell'exe")
    ap.add_argument("--release", action="store_true", help="con --apk: assembleRelease invece di assembleDebug")
    ap.add_argument("--console", action="store_true", help="exe con console (utile per vedere gli errori)")
    ap.add_argument("--no-exe", action="store_true", help="solo l'APK, niente eseguibile")
    a = ap.parse_args()
    if a.apk:
        build_apk(a.release)
    if not a.no_exe:
        build_exe(a.console)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
