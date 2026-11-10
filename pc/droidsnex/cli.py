"""Interfaccia a riga di comando: installazione dell'agent, avvio della cattura e monitor live."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time

from . import DEFAULT_PORT, __version__
from . import platform_tools
from .adb import Adb, AdbError
from .export import export_all
from .model import Monitor
from .resolve import AsnDb, ReverseDns
from .stream import StreamClient
from .ui import Controller, run_ui

from .paths import BUNDLE_DIR, HOME_DIR

HERE = HOME_DIR                                  # cartella di lavoro: pc/ da sorgente, accanto all'exe se impacchettato
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def info(msg: str):
    print(f"[droidsnex] {msg}", flush=True)


def find_apk(explicit: str | None) -> str | None:
    if explicit:
        return explicit if os.path.isfile(explicit) else None
    candidates = [
        os.path.join(HERE, "DroidSnex.apk"),         # accanto all'exe nella release (tools/build_exe.py)
        os.path.join(HERE, "agent.apk"),
        os.path.join(BUNDLE_DIR, "DroidSnex.apk"),
        os.path.join(BUNDLE_DIR, "agent.apk"),      # incluso nell'eseguibile dalle versioni precedenti
        os.path.join(REPO, "DroidSnex.apk"),
        os.path.join(REPO, "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk"),
        os.path.join(REPO, "android", "app", "build", "outputs", "apk", "release", "app-release.apk"),
    ]
    return next((c for c in candidates if os.path.isfile(c)), None)


# ---------------------------------------------------------------------- passi

def step_device(adb: Adb):
    """a) adb presente e device collegato/autorizzato."""
    info(f"adb: {adb.path} ({adb.version()})")
    dev = adb.select_device()
    info(f"device: {dev.serial} {dev.model} (Android API {adb.sdk_int()})")
    return dev


def step_install(adb: Adb, apk_arg: str | None, force: bool = False):
    """b) adb install -r agent.apk  + permessi."""
    apk = find_apk(apk_arg)
    if apk:
        info(f"installazione di {apk} ...")
        out = adb.install(apk)
        info(out.splitlines()[-1] if out else "ok")
    elif adb.is_installed() and not force:
        info("APK non trovato, ma l'agent è già installato sul telefono: proseguo.")
    else:
        raise AdbError("APK dell'agent non trovato. Compilalo (vedi README) oppure indica il percorso con --apk.")
    for w in adb.grant_permissions():
        info(f"attenzione: {w}")
    info("permessi concessi (VPN pre-autorizzata via appops, notifiche, esclusione batteria)")


def probe_agent(port: int, timeout: float = 3.0) -> dict | None:
    """Prova a leggere l'evento 'hello' dall'agent attraverso il forward."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b'{"cmd":"since","seq":999999999}\n')     # niente replay: ci basta l'hello
            data = b""
            while b"\n" not in data:
                chunk = s.recv(4096)
                if not chunk:
                    return None
                data += chunk
            return json.loads(data.split(b"\n", 1)[0])
    except (OSError, ValueError):
        return None


def step_start(adb: Adb, port: int, remote_port: int, wait: float = 90):
    """c) avvio dell'app + attesa della VPN;  d) adb forward."""
    info("avvio della cattura sul telefono...")
    adb.start_capture()
    adb.forward(port, remote_port)
    info(f"adb forward tcp:{port} tcp:{remote_port}  (PC localhost:{port} -> telefono 127.0.0.1:{remote_port})")
    deadline = time.time() + wait
    hinted = False
    while time.time() < deadline:
        hello = probe_agent(port)
        if hello and hello.get("vpn"):
            info("VPN attiva, agent raggiungibile.")
            return True
        if not hinted and time.time() > deadline - wait + 4:
            hinted = True
            info("In attesa della VPN... Se sul telefono compare 'Richiesta di connessione', "
                 "sblocca lo schermo e tocca OK. Se è attiva un'altra VPN verrà sostituita.")
        time.sleep(1.5)
    info("la VPN non risulta attiva: controlla il telefono (vedi README > Troubleshooting).")
    return False


# ---------------------------------------------------------------------- monitor

def do_monitor(args, adb: Adb | None, title: str):
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    asn_path = args.asn_db or AsnDb.autodetect([HERE, os.path.join(HERE, "data"), os.getcwd()])
    asn = AsnDb(asn_path)
    if asn_path:
        info(f"db ASN: {asn_path} ({'ok' if asn.available else 'non disponibile: ' + str(asn.error)})")
    rdns = ReverseDns(enabled=not args.no_rdns)
    log_path = None if args.no_log else os.path.join(out_dir, time.strftime("stream-%Y%m%d-%H%M%S.jsonl"))
    mon = Monitor(rdns, asn, hide_dns=args.hide_dns, log_path=log_path)
    if log_path:
        info(f"stream grezzo salvato in {log_path}")

    def on_event(ev):
        ev["_inst"] = client.instance or ""
        mon.handle(ev)

    # watchdog: se questo programma sparisce per 20 s, l'agent sul telefono si ferma da solo
    client = StreamClient("127.0.0.1" if adb else args.host, args.port, on_event, mon.set_status,
                          adb=adb, remote_port=args.remote_port,
                          watchdog=0 if (adb is None or getattr(args, "keep_agent", False)) else 20)

    def export():
        return export_all(mon.snapshot(), out_dir, label_for=mon.dest_label)

    ctrl = Controller(mon, title, export)
    client.start()
    try:
        if args.duration:
            # modalità non interattiva: raccoglie per N secondi ed esporta
            t_end = time.time() + args.duration
            while time.time() < t_end:
                time.sleep(1)
            ctrl.command("e")
            info(ctrl.message)
        else:
            run_ui(ctrl, plain=args.plain)
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
        if args.export_on_exit and not args.duration and mon.conns:
            info("Esportato: " + ", ".join(export()))
        rdns.shutdown()
        mon.close()
    info(f"{len(mon.conns)} connessioni osservate.")


# ---------------------------------------------------------------------- main

def ensure_adb() -> None:
    """adb si usa solo da pc/tools/platform-tools e non viene mai scaricato da solo:
    si scarica col pulsante 'Scarica / aggiorna da Google' nel tab Config della GUI."""
    if not platform_tools.local_adb():
        raise AdbError(f"adb non presente in {platform_tools.local_dir()}: apri la GUI (python gui.py) e premi "
                       "'Scarica / aggiorna da Google' nel tab Config.")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="droidsnex",
                                description="Monitor delle connessioni di un telefono Android via USB (adb).")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd")

    def common(sp, monitor=True):
        sp.add_argument("-s", "--serial", help="seriale del device (se ne sono collegati più di uno)")
        sp.add_argument("--port", type=int, default=DEFAULT_PORT, help="porta locale sul PC (default 8888)")
        sp.add_argument("--remote-port", type=int, default=DEFAULT_PORT, help="porta dell'agent sul telefono")
        if monitor:
            sp.add_argument("--out", default=os.path.join(HERE, "captures"), help="cartella per export e log")
            sp.add_argument("--asn-db", help="db ASN locale (ip2asn-*.tsv[.gz] o GeoLite2-ASN.mmdb)")
            sp.add_argument("--no-rdns", action="store_true", help="disattiva il reverse DNS")
            sp.add_argument("--hide-dns", action="store_true", help="nasconde le query DNS (porta 53)")
            sp.add_argument("--plain", action="store_true", help="tabella testuale invece della TUI curses")
            sp.add_argument("--no-log", action="store_true", help="non salvare lo stream grezzo .jsonl")
            sp.add_argument("--export-on-exit", action="store_true", help="esporta CSV/JSON/pcapng all'uscita")
            sp.add_argument("--duration", type=int, help="raccogli per N secondi, esporta ed esci (no TUI)")

    r = sub.add_parser("run", help="tutto il flusso: verifica, installa, permessi, avvia, forward, monitor")
    common(r)
    r.add_argument("--apk", help="percorso dell'APK dell'agent")
    r.add_argument("--no-install", action="store_true", help="salta l'installazione dell'APK")
    r.add_argument("--keep-agent", action="store_true",
                   help="all'uscita NON fermare e NON disinstallare l'agent (default: ferma e disinstalla)")

    m = sub.add_parser("monitor", help="solo forward + monitor (agent già installato e avviato)")
    common(m)
    m.add_argument("--no-adb", action="store_true", help="collegati direttamente a --host:--port senza adb")
    m.add_argument("--host", default="127.0.0.1")

    i = sub.add_parser("install", help="installa l'APK e concede i permessi")
    common(i, monitor=False)
    i.add_argument("--apk")
    for name, hlp in (("start", "avvia la VPN sul telefono"), ("stop", "ferma la VPN sul telefono"),
                      ("uninstall", "disinstalla l'agent"), ("devices", "elenca i device adb")):
        common(sub.add_parser(name, help=hlp), monitor=False)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = ("run", "monitor", "install", "start", "stop", "uninstall", "devices")
    if not argv or (argv[0] not in commands and argv[0] not in ("-h", "--help", "--version")):
        argv = ["run"] + argv          # senza sottocomando = flusso completo
    args = parser.parse_args(argv)
    try:
        if args.cmd == "monitor" and args.no_adb:
            do_monitor(args, None, f"{args.host}:{args.port}")
            return 0

        ensure_adb()
        adb = Adb(serial=args.serial)
        if args.cmd == "devices":
            for d in adb.devices():
                print(f"{d.serial}\t{d.state}\t{d.model}")
            return 0
        dev = step_device(adb)
        if args.cmd == "install":
            step_install(adb, args.apk, force=True)
        elif args.cmd == "start":
            return 0 if step_start(adb, args.port, args.remote_port) else 1
        elif args.cmd == "stop":
            adb.stop_capture()
            info("cattura fermata")
        elif args.cmd == "uninstall":
            adb.remove_forward(args.port)
            info(adb.uninstall())
        elif args.cmd == "monitor":
            adb.forward(args.port, args.remote_port)
            do_monitor(args, adb, f"{dev.model or dev.serial}")
        elif args.cmd == "run":
            if not args.no_install:
                step_install(adb, args.apk)
            try:
                step_start(adb, args.port, args.remote_port)
                do_monitor(args, adb, f"{dev.model or dev.serial}")
            finally:
                # All'uscita (anche per errore o Ctrl+C) l'agent viene fermato e disinstallato.
                if args.keep_agent:
                    adb.remove_forward(args.port)
                elif adb.is_online():
                    for line in adb.cleanup(args.port):
                        info(line)
                else:
                    info("telefono scollegato: l'agent si fermerà da solo (watchdog)")
        return 0
    except AdbError as e:
        info(f"errore: {e}")
        return 2
    except KeyboardInterrupt:
        return 130
