"""Client dello stream JSON-lines, con riconnessione automatica (cavo staccato, app riavviata...)."""
from __future__ import annotations

import json
import socket
import threading
import time
from typing import Callable

from .adb import Adb, AdbError
from .i18n import tr

HEARTBEAT_TIMEOUT = 15.0   # l'agent invia un "ping" ogni 5 s se non ci sono eventi


class StreamClient(threading.Thread):
    """
    Si collega a host:port (lato PC dell'`adb forward`) e consegna ogni evento
    a `on_event`. Se la connessione cade:
      1. aspetta che il device torni visibile ad adb (cavo ricollegato);
      2. rifà `adb forward` (adb lo perde quando il device si disconnette);
      3. se l'agent non risponde, rilancia la cattura sul telefono;
      4. si ricollega chiedendo gli eventi persi: {"cmd":"since","seq":<ultimo visto>}.
    """

    def __init__(self, host: str, port: int, on_event: Callable[[dict], None],
                 on_status: Callable[..., None], adb: Adb | None = None, remote_port: int = 8888,
                 watchdog: int = 0, restart_capture: bool = True):
        super().__init__(daemon=True, name="StreamClient")
        self.host, self.port, self.remote_port = host, port, remote_port
        self.on_event, self.on_status, self.adb = on_event, on_status, adb
        # watchdog > 0: l'agent si ferma da solo se resta senza questo PC per N secondi
        self.watchdog = watchdog
        self.restart_capture = restart_capture
        self.last_seq = 0
        self.connected = False
        self.vpn_on: bool | None = None
        self.instance: str | None = None
        self._stop = threading.Event()
        self._sock: socket.socket | None = None

    def stop(self):
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass

    # ------------------------------------------------------------------
    def run(self):
        failures = 0
        while not self._stop.is_set():
            got_data = False
            try:
                got_data = self._session()
            except (OSError, ValueError) as e:
                self.on_status(tr("connessione persa: {e}", e=e), "err")
            self.connected = False
            if self._stop.is_set():
                break
            failures = 0 if got_data else failures + 1
            self._recover(failures)
            # backoff: 0.5 s, 1 s, 2 s ... fino a 5 s
            self._stop.wait(min(5.0, 0.5 * (2 ** min(failures, 4))) if failures else 0.5)

    def _session(self) -> bool:
        """Una sessione di lettura. Ritorna True se ha ricevuto almeno l'hello."""
        s = socket.create_connection((self.host, self.port), timeout=5)
        self._sock = s
        got_hello = False
        try:
            s.settimeout(HEARTBEAT_TIMEOUT)
            # Comando iniziale: ripresa dello stream dal punto in cui eravamo rimasti
            cmd = {"cmd": "since", "seq": self.last_seq}
            if self.watchdog:
                cmd["watchdog"] = self.watchdog
            s.sendall((json.dumps(cmd) + "\n").encode())
            buf = b""
            while not self._stop.is_set():
                try:
                    chunk = s.recv(65536)
                except socket.timeout:
                    self.on_status(tr("nessun dato dal telefono da 15 s, riconnessione..."), "err")
                    return got_hello
                if not chunk:
                    # Con `adb forward` attivo ma nessun server sul telefono, adb
                    # accetta la connessione e la chiude subito: arriviamo qui.
                    if not got_hello:
                        self.on_status(tr("l'agent sul telefono non risponde (cattura ferma?)"), "err")
                    return got_hello
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    kind = ev.get("ev")
                    if kind == "hello":
                        got_hello = True
                        self.connected = True
                        self.vpn_on = ev.get("vpn")
                        # Se l'agent sul telefono è stato riavviato i numeri di sequenza
                        # ripartono da 1: ci ricolleghiamo chiedendo tutto dall'inizio.
                        inst = ev.get("instance")
                        if self.instance is not None and inst != self.instance and self.last_seq > 0:
                            self.instance, self.last_seq = inst, 0
                            self.on_status(tr("agent riavviato sul telefono, risincronizzazione..."))
                            return True
                        self.instance = inst
                        self.on_status(tr("collegato (eventi recuperati: {n})", n=ev.get("replay", 0)), "ok")
                        continue
                    if kind in ("ping", "status"):
                        self.vpn_on = ev.get("vpn", self.vpn_on)
                    seq = ev.get("seq")
                    if isinstance(seq, int):
                        if seq <= self.last_seq:
                            continue        # duplicato (già ricevuto prima della disconnessione)
                        self.last_seq = seq
                    self.on_event(ev)
        finally:
            try:
                s.close()
            except OSError:
                pass
        return got_hello

    def _recover(self, failures: int):
        if not self.adb:
            self.on_status(tr("riconnessione a {addr}...", addr=f"{self.host}:{self.port}"))
            return
        try:
            if not self.adb.is_online():
                self.on_status(tr("telefono scollegato: ricollega il cavo USB..."), "err")
                self.adb.wait_for_device(on_wait=lambda: None)
                if self._stop.is_set():
                    return
                self.on_status(tr("telefono ricollegato"), "ok")
            # adb perde i forward quando il device si disconnette: lo rifacciamo sempre
            self.adb.forward(self.port, self.remote_port)
            # Dopo qualche tentativo a vuoto, l'agent probabilmente non è in esecuzione
            if self.restart_capture and (failures in (2, 6) or (failures > 6 and failures % 10 == 0)):
                self.on_status(tr("riavvio della cattura sul telefono..."))
                self.adb.start_capture()
        except AdbError as e:
            self.on_status(f"adb: {e}", "err")
            time.sleep(1)
