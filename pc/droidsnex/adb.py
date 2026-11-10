"""Wrapper minimale attorno al comando `adb` (via subprocess, nessuna libreria esterna)."""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass

from . import ACTION_START, ACTION_STOP, ACTIVITY, PACKAGE
from . import platform_tools
from .i18n import tr
from .proc import hidden


def _parse_service_string(out: str) -> str:
    """Estrae la stringa UTF-16 dal dump di `service call` (le colonne fra apici: '1.2.3.4.5...')."""
    chunks = re.findall(r"'([^']*)'", out)
    text = "".join(chunks).replace(".", "").replace(" ", "")
    return text.strip()


class AdbError(RuntimeError):
    pass


@dataclass
class Device:
    serial: str
    state: str          # "device", "unauthorized", "offline", ...
    model: str = ""


def find_adb() -> str | None:
    """L'unico adb usato è quello scaricato da Google in pc/tools/platform-tools (mai quello del sistema)."""
    return platform_tools.local_adb()


class Adb:
    def __init__(self, serial: str | None = None):
        self.path = find_adb()
        if not self.path:
            raise AdbError(tr(
                "adb non trovato nella cartella tools: scaricalo dal tab Config "
                "(Android Platform Tools di Google, in pc/tools/platform-tools)."
            ))
        self.serial = serial

    # ------------------------------------------------------------------ base
    def run(self, *args: str, timeout: float = 30, check: bool = True, device: bool = True) -> str:
        cmd = [self.path]
        if device and self.serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace", **hidden())
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"timeout: {' '.join(cmd)}") from e
        except OSError as e:
            raise AdbError(tr("impossibile eseguire adb: {e}", e=e)) from e
        out = (p.stdout or "") + (p.stderr or "")
        if check and p.returncode != 0:
            raise AdbError(f"{' '.join(args)} -> {out.strip()}")
        return out.strip()

    def shell(self, command: str, timeout: float = 30, check: bool = False) -> str:
        return self.run("shell", command, timeout=timeout, check=check)

    def screencap(self, path: str, timeout: float = 20) -> None:
        """Screenshot del telefono (PNG) in `path`, via `adb exec-out screencap -p`."""
        cmd = [self.path] + (["-s", self.serial] if self.serial else []) + ["exec-out", "screencap", "-p"]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout, **hidden())
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"timeout: {' '.join(cmd)}") from e
        except OSError as e:
            raise AdbError(tr("impossibile eseguire adb: {e}", e=e)) from e
        if p.returncode != 0 or not p.stdout.startswith(b"\x89PNG"):
            raise AdbError("screencap -> " + (p.stderr or b"").decode("utf-8", "replace").strip()[:200])
        with open(path, "wb") as f:
            f.write(p.stdout)

    def version(self) -> str:
        return self.run("version", device=False).splitlines()[0]

    # ------------------------------------------------------------------ device
    def devices(self) -> list[Device]:
        out = self.run("devices", "-l", device=False)
        devs = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2 or line.startswith("*"):
                continue
            model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), "")
            devs.append(Device(parts[0], parts[1], model))
        return devs

    def select_device(self) -> Device:
        """Sceglie il device da usare. Errore chiaro se assente o non autorizzato."""
        devs = self.devices()
        if self.serial:
            devs = [d for d in devs if d.serial == self.serial]
        ready = [d for d in devs if d.state == "device"]
        if not ready:
            if any(d.state == "unauthorized" for d in devs):
                raise AdbError(tr("Device non autorizzato: sblocca il telefono e accetta "
                                  "'Consentire debug USB?' (spunta 'Consenti sempre da questo computer')."))
            if devs:
                raise AdbError(tr("Device in stato '{s}'. Ricollega il cavo o riavvia adb (adb kill-server).", s=devs[0].state))
            raise AdbError(tr("Nessun device collegato. Collega il telefono via USB con il Debug USB attivo."))
        if len(ready) > 1 and not self.serial:
            names = ", ".join(f"{d.serial} ({d.model})" for d in ready)
            raise AdbError(tr("Più device collegati: {names}. Scegline uno con --serial.", names=names))
        self.serial = ready[0].serial
        return ready[0]

    def is_online(self) -> bool:
        try:
            return any(d.serial == self.serial and d.state == "device" for d in self.devices())
        except AdbError:
            return False

    def wait_for_device(self, poll: float = 1.0, on_wait=None) -> None:
        """Attende che il device (ri)compaia: gestisce cavo staccato e riattaccato."""
        while not self.is_online():
            if on_wait:
                on_wait()
            time.sleep(poll)

    def identity(self) -> dict:
        """Dati per riconoscere il telefono fra una sessione e l'altra. Tutto best-effort:
        senza root, sui telefoni recenti IMEI e MAC reali spesso NON sono leggibili via adb
        (Android 10+ li nasconde anche alla shell); in quel caso restano vuoti e il telefono
        viene riconosciuto da seriale + Android ID (che cambia solo con un reset di fabbrica)."""
        info = {"serial": self.serial or "", "model": "", "brand": "", "manufacturer": "", "android": "", "sdk": 0,
                "android_id": "", "imei": "", "wifi_mac": "", "bt_mac": "", "read_at": time.time()}
        props = {"ro.product.model": "model", "ro.product.brand": "brand", "ro.product.manufacturer": "manufacturer",
                 "ro.build.version.release": "android"}
        for prop, key in props.items():
            try:
                info[key] = self.shell(f"getprop {prop}", timeout=8).strip()
            except AdbError:
                pass
        try:
            info["sdk"] = self.sdk_int()
        except AdbError:
            pass
        try:
            v = self.shell("settings get secure android_id", timeout=8).strip()
            info["android_id"] = v if re.fullmatch(r"[0-9a-fA-F]{8,32}", v) else ""
        except AdbError:
            pass
        # IMEI: su Android <= 9 "service call iphonesubinfo 1"; dal 10 in poi funziona (su alcuni
        # telefoni) solo passando il pacchetto chiamante; altrimenti SecurityException -> vuoto.
        for cmd in ("service call iphonesubinfo 1 s16 com.android.shell", "service call iphonesubinfo 1",
                    "service call iphonesubinfo 4 s16 com.android.shell"):
            try:
                imei = _parse_service_string(self.shell(cmd, timeout=8))
            except AdbError:
                imei = ""
            if re.fullmatch(r"[0-9]{14,16}", imei):
                info["imei"] = imei
                break
        for cmd in ("ip link show wlan0", "cat /sys/class/net/wlan0/address"):
            try:
                m = re.search(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})", self.shell(cmd, timeout=8).lower())
            except AdbError:
                m = None
            if m and m.group(1) not in ("00:00:00:00:00:00", "02:00:00:00:00:00"):
                info["wifi_mac"] = m.group(1)
                break
        try:
            v = self.shell("settings get secure bluetooth_address", timeout=8).strip().lower()
            if re.fullmatch(r"[0-9a-f]{2}(:[0-9a-f]{2}){5}", v):
                info["bt_mac"] = v
        except AdbError:
            pass
        return info

    def sdk_int(self) -> int:
        try:
            return int(self.shell("getprop ro.build.version.sdk").strip())
        except ValueError:
            return 0

    # ------------------------------------------------------------------ app
    def is_installed(self) -> bool:
        return f"package:{PACKAGE}" in self.shell(f"pm list packages {PACKAGE}")

    def installed_version(self) -> tuple[str, int] | None:
        """(versionName, versionCode) dell'agent installato sul telefono, None se non c'e'."""
        out = self.shell(f"dumpsys package {PACKAGE}", timeout=20)
        name = re.search(r"versionName=(\S+)", out)
        code = re.search(r"versionCode=(\d+)", out)
        if not name and not code:
            return None
        return (name.group(1) if name else "?", int(code.group(1)) if code else 0)

    def install(self, apk: str) -> str:
        # -r: reinstalla mantenendo i dati; -g: concede i permessi runtime dichiarati
        return self.run("install", "-r", "-g", apk, timeout=180)

    def uninstall(self) -> str:
        return self.run("uninstall", PACKAGE, check=False)

    def grant_permissions(self) -> list[str]:
        """
        Concede tutto ciò che si può concedere senza root, via adb:
         - ACTIVATE_VPN tramite appops: pre-autorizza la VPN, così il dialog di
           consenso non compare (se il produttore lo blocca, compare e va accettato a mano);
         - POST_NOTIFICATIONS (Android 13+) per la notifica del servizio;
         - esclusione dall'ottimizzazione batteria (evita che Doze fermi il servizio).
        Ritorna una lista di avvisi per ciò che non è riuscito.
        """
        warnings = []
        out = self.shell(f"appops set {PACKAGE} ACTIVATE_VPN allow")
        if out:
            warnings.append(f"appops ACTIVATE_VPN: {out}")
        if self.sdk_int() >= 33:
            out = self.shell(f"pm grant {PACKAGE} android.permission.POST_NOTIFICATIONS")
            if out and "Exception" in out:
                warnings.append(f"POST_NOTIFICATIONS: {out}")
        self.shell(f"dumpsys deviceidle whitelist +{PACKAGE}")
        return warnings

    def start_capture(self, lang: str | None = None) -> str:
        """Avvia la VPN. `lang`: lingua dell'app sul telefono (la stessa del programma PC)."""
        extra = f" --es lang {lang}" if lang else ""
        return self.shell(f"am start -n {ACTIVITY} -a {ACTION_START}{extra}")

    def stop_capture(self) -> str:
        return self.shell(f"am start -n {ACTIVITY} -a {ACTION_STOP}")

    def vpn_active(self) -> bool:
        """Controlla se la VPN di DroidSnex risulta attiva per il sistema."""
        out = self.shell("dumpsys connectivity", timeout=20)
        return PACKAGE in out and "VPN" in out and "CONNECTED" in out

    # ------------------------------------------------------------------ forward
    def forward(self, local_port: int, remote_port: int) -> None:
        """
        `adb forward tcp:L tcp:R`: il server adb sul PC ascolta su localhost:L e
        ogni connessione viene tunnelata via USB verso 127.0.0.1:R del telefono.
        Va rifatto dopo ogni riconnessione del cavo (adb dimentica i forward).
        """
        self.run("forward", f"tcp:{local_port}", f"tcp:{remote_port}")

    def remove_forward(self, local_port: int) -> None:
        self.run("forward", "--remove", f"tcp:{local_port}", check=False)

    def cleanup(self, local_port: int) -> list[str]:
        """Ferma la cattura, toglie il forward e disinstalla l'agent. Non solleva eccezioni."""
        done = []
        for label, fn in ((tr("cattura fermata"), self.stop_capture),
                          (tr("forward rimosso"), lambda: self.remove_forward(local_port)),
                          (tr("agent disinstallato"), self.uninstall)):
            try:
                fn()
                done.append(label)
            except AdbError as e:
                done.append(f"{label}: " + tr("errore: {e}", e=e))
        return done
