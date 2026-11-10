"""Tabella live: TUI con curses (se disponibile) oppure fallback testuale con refresh periodico."""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time

from .model import GROUP_MODES, SORT_MODES, Group, Monitor

HELP = "[q]esci [e]esporta [s]ordina [g]raggruppa [d]DNS [/]filtro [↑↓ PgUp PgDn]scorri"


def _t(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts)) if ts else "-"


def _fit(s: str, n: int) -> str:
    s = str(s)
    return (s[: n - 1] + "…") if len(s) > n else s.ljust(n)


def _ports(g: Group) -> str:
    ps = sorted(g.ports)
    s = ",".join(str(p) for p in ps[:4])
    return s + ("+" if len(ps) > 4 else "")


def _bytes(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}T"


def format_rows(groups: list[Group], width: int) -> tuple[str, list[str]]:
    """Colonne: destinazione | app | n. connessioni | prima vista | ultima vista (+ porte, traffico, org)."""
    fixed = 2 + 12 + 6 + 9 + 9 + 7 + 6   # marker, porte, conn, prima, ultima, traffico, separatori
    rest = max(30, width - fixed)
    wd = max(18, int(rest * 0.38))
    wa = max(14, int(rest * 0.30))
    wo = max(0, rest - wd - wa)
    head = (" " + _fit("DESTINAZIONE", wd) + " " + _fit("PORTE", 11) + " " + _fit("APP", wa) + " " +
            "CONN".rjust(5) + "  " + _fit("PRIMA", 8) + " " + _fit("ULTIMA", 8) + " " + "TRAFF".rjust(6) +
            " " + _fit("ORG", wo))
    rows = []
    for g in groups:
        mark = "●" if g.active else " "
        rows.append(mark + _fit(g.dest, wd) + " " + _fit(_ports(g), 11) + " " + _fit(g.app, wa) + " " +
                    str(g.count).rjust(5) + "  " + _fit(_t(g.first), 8) + " " + _fit(_t(g.last), 8) + " " +
                    _bytes(g.bytes).rjust(6) + " " + _fit(g.org, wo))
    return head[:width], [r[:width] for r in rows]


class Controller:
    """Stato della vista + azioni condivise da TUI e modalità testuale."""

    def __init__(self, mon: Monitor, title: str, export_fn):
        self.mon, self.title, self.export_fn = mon, title, export_fn
        self.group_i, self.sort_i = 0, 0
        self.filter = ""
        self.message = ""
        self.quit = False

    @property
    def group(self):
        return GROUP_MODES[self.group_i]

    @property
    def sort(self):
        return SORT_MODES[self.sort_i]

    def header(self) -> str:
        vpn = {True: "VPN attiva", False: "VPN FERMA", None: "VPN ?"}[self.mon.vpn_on]
        return (f"DroidSnex — {self.title} — {vpn} — {len(self.mon.conns)} connessioni — "
                f"stato: {self.mon.status}")

    def modes(self) -> str:
        return (f"raggruppa: {self.group} | ordina: {self.sort} | DNS: {'nascosti' if self.mon.hide_dns else 'visibili'}"
                + (f" | filtro: '{self.filter}'" if self.filter else ""))

    def command(self, cmd: str):
        cmd = cmd.strip()
        if not cmd:
            return
        c = cmd[0].lower()
        if c == "q":
            self.quit = True
        elif c == "e":
            try:
                paths = self.export_fn()
                self.message = "Esportato: " + ", ".join(paths)
            except Exception as e:  # noqa: BLE001
                self.message = f"Errore export: {e}"
        elif c == "s":
            self.sort_i = (self.sort_i + 1) % len(SORT_MODES)
        elif c == "g":
            self.group_i = (self.group_i + 1) % len(GROUP_MODES)
        elif c == "d":
            self.mon.hide_dns = not self.mon.hide_dns
        elif c == "/":
            self.filter = cmd[1:].strip()


def run_ui(ctrl: Controller, plain: bool = False):
    if not plain:
        try:
            import curses  # noqa: F401
        except ImportError:
            plain = True
    if plain or not sys.stdout.isatty():
        return _run_plain(ctrl)
    import curses
    return curses.wrapper(lambda scr: _run_curses(scr, ctrl))


# ---------------------------------------------------------------------- curses

def _run_curses(scr, ctrl: Controller):
    import curses
    curses.curs_set(0)
    scr.timeout(500)
    try:
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
    except curses.error:
        pass
    scroll = 0
    while not ctrl.quit:
        h, w = scr.getmaxyx()
        groups = ctrl.mon.groups(ctrl.group, ctrl.sort, ctrl.filter)
        head, rows = format_rows(groups, w - 1)
        body_h = max(1, h - 5)
        scroll = max(0, min(scroll, len(rows) - body_h))
        scr.erase()

        def put(y, x, s, attr=0):
            try:
                scr.addnstr(y, x, s, w - 1 - x, attr)
            except curses.error:
                pass

        put(0, 0, ctrl.header().ljust(w - 1), curses.color_pair(1) | curses.A_BOLD)
        put(1, 0, ctrl.modes(), curses.color_pair(3))
        put(2, 0, head, curses.A_BOLD | curses.A_UNDERLINE)
        for i, r in enumerate(rows[scroll: scroll + body_h]):
            put(3 + i, 0, r, curses.color_pair(2) if r.startswith("●") else 0)
        put(h - 2, 0, ctrl.message)
        put(h - 1, 0, f"{HELP}   righe {scroll + 1}-{min(len(rows), scroll + body_h)}/{len(rows)}", curses.A_DIM)
        scr.refresh()

        k = scr.getch()
        if k == -1:
            continue
        if k == curses.KEY_UP:
            scroll -= 1
        elif k == curses.KEY_DOWN:
            scroll += 1
        elif k == curses.KEY_PPAGE:
            scroll -= body_h
        elif k == curses.KEY_NPAGE:
            scroll += body_h
        elif k == ord("/"):
            curses.echo(); curses.curs_set(1)
            put(h - 2, 0, " " * (w - 1))
            put(h - 2, 0, "filtro (vuoto = nessuno): ")
            scr.timeout(-1)
            try:
                txt = scr.getstr(h - 2, 26, 60).decode("utf-8", "replace")
            except curses.error:
                txt = ""
            curses.noecho(); curses.curs_set(0); scr.timeout(500)
            ctrl.command("/" + txt)
            scroll = 0
        elif 0 < k < 256:
            ctrl.command(chr(k))


# ---------------------------------------------------------------------- testuale

def _run_plain(ctrl: Controller):
    """Fallback senza curses (es. Windows senza windows-curses): comandi + Invio."""
    def reader():
        while not ctrl.quit:
            try:
                line = input()
            except (EOFError, KeyboardInterrupt):
                ctrl.quit = True
                break
            ctrl.command(line)

    threading.Thread(target=reader, daemon=True).start()
    if os.name == "nt":
        os.system("")   # abilita le sequenze ANSI nella console di Windows
    interactive = sys.stdout.isatty()
    while not ctrl.quit:
        size = shutil.get_terminal_size((140, 40))
        groups = ctrl.mon.groups(ctrl.group, ctrl.sort, ctrl.filter)
        head, rows = format_rows(groups, size.columns - 1)
        out = [ctrl.header(), ctrl.modes(), head] + rows[: max(1, size.lines - 6)]
        out += [ctrl.message, "Comandi (+Invio): q esci | e esporta | s ordina | g raggruppa | d DNS | /testo filtro"]
        if interactive:
            sys.stdout.write("\x1b[H\x1b[2J" + "\n".join(out) + "\n")
        else:
            sys.stdout.write("\n".join(out) + "\n\n")
        sys.stdout.flush()
        for _ in range(20 if interactive else 50):
            if ctrl.quit:
                break
            time.sleep(0.1)
