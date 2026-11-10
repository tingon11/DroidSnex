"""Replay di una sessione registrata: rivede gli eventi del telefono nell'ordine e con i tempi reali.

La sessione (sessions.py, formato 2) contiene gli eventi ricevuti dall'agent con l'istante di
arrivo ("_t"). Il replay li rimanda a un Monitor tutto suo (lo stesso modello usato dal vivo), così
liste, mappa, grafo, timeline, DNS e alert mostrano esattamente ciò che esisteva all'istante scelto.
Andare indietro nel tempo = azzerare il Monitor e rimandare gli eventi dall'inizio fino al nuovo
istante (sono migliaia di eventi: pochi millisecondi).

La timeline non si ricava dal Monitor ma dagli eventi "bytes" e "close": per ogni secondo della
sessione si calcola quanto ha trasferito ogni app (`samples`), come fa il monitor dal vivo.
"""
from __future__ import annotations

import time

from .alerts import AlertEngine
from .model import Monitor

SPEEDS = (1, 10, 60)


def _t(ev: dict) -> float:
    return float(ev.get("_t") or 0.0)


class Replay:
    def __init__(self, session, rdns, asn, trust, geo, rep, tr, hide_dns: bool = False):
        self.session = session
        self.events = sorted((e for e in session.events if e.get("_t")), key=_t)
        self.marks = sorted(session.marks or [], key=lambda m: m.get("ts", 0))
        first = _t(self.events[0]) if self.events else session.started
        last = _t(self.events[-1]) if self.events else session.ended
        self.t0 = min(session.started or first, first)
        self.t1 = max(session.ended or last, last, self.t0 + 1)
        self.mon = Monitor(rdns, asn, hide_dns)
        self.alerts = AlertEngine(trust, geo, rep, tr)
        self.alerts.now = lambda: self.t
        self.mon.on_conn = self._on_conn
        self.t = self.t0
        self.pos = 0                       # prossimo evento da mandare
        self.playing = False
        self.speed = 1
        self.samples: list[tuple[float, dict]] = []     # (istante, {app: (entrata, uscita)}) per la timeline
        self._totals: dict[str, tuple[int, int]] = {}    # id flusso -> (uscita, entrata) gia' contati
        self._bucket: dict[str, list[int]] = {}
        self._bucket_t = 0.0
        self._last_real = 0.0
        self.new_samples: list[tuple[float, dict]] = []  # campioni prodotti dall'ultimo prelievo (play)

    # ------------------------------------------------------------------ stato
    @property
    def duration(self) -> float:
        return self.t1 - self.t0

    @property
    def done(self) -> bool:
        return self.t >= self.t1

    def _on_conn(self, c, first: bool) -> None:
        self.alerts.check(c, self.mon.dest_label(c), first)

    # ------------------------------------------------------------------ avanzamento
    def _flush_bucket(self) -> None:
        if self._bucket:
            sample = (self._bucket_t, {a: (v[0], v[1]) for a, v in self._bucket.items()})
            self.samples.append(sample)
            self.new_samples.append(sample)
            self._bucket = {}

    def _account(self, app: str, fid, out: int, inb: int, when: float) -> None:
        prev = self._totals.get(fid, (0, 0))
        dout, din = max(0, out - prev[0]), max(0, inb - prev[1])
        self._totals[fid] = (max(out, prev[0]), max(inb, prev[1]))
        if not dout and not din:
            return
        sec = float(int(when))
        if sec != self._bucket_t:
            self._flush_bucket()
            self._bucket_t = sec
        acc = self._bucket.setdefault(app, [0, 0])
        acc[0] += din
        acc[1] += dout

    def _feed(self, ev: dict) -> None:
        kind = ev.get("ev")
        when = _t(ev)
        inst = ev.get("_i", "")
        if kind == "bytes":
            for item in ev.get("flows", ()):
                try:
                    fid, out, inb = item[0], int(item[1]), int(item[2])
                except (TypeError, ValueError, IndexError):
                    continue
                c = self.mon.conns.get(f"{inst}:{fid}")
                if c:
                    self._account(c.app, c.key, out, inb, when)
        elif kind == "close":
            c = self.mon.conns.get(f"{inst}:{ev.get('id')}")
            if c:
                self._account(c.app, c.key, int(ev.get("bytes_out") or 0), int(ev.get("bytes_in") or 0), when)
        ev = dict(ev)
        ev["_inst"] = inst
        self.mon.handle(ev)

    def _run_to(self, t: float) -> None:
        """Manda al Monitor tutti gli eventi con istante <= t."""
        evs = self.events
        n = len(evs)
        while self.pos < n and _t(evs[self.pos]) <= t:
            self._feed(evs[self.pos])
            self.pos += 1
        if self._bucket and t - self._bucket_t >= 1:
            self._flush_bucket()
        self.t = min(max(t, self.t0), self.t1)

    def restart(self) -> None:
        self.mon.reset()
        self.alerts.reset()
        self.pos = 0
        self.t = self.t0
        self.samples = []
        self.new_samples = []
        self._totals = {}
        self._bucket = {}
        self._bucket_t = 0.0

    def seek(self, t: float) -> None:
        """Si sposta all'istante t (indietro = ripartenza dall'inizio)."""
        t = min(max(t, self.t0), self.t1)
        if t < self.t:
            self.restart()
        self._run_to(t)
        self.new_samples = []

    def advance(self, real_dt: float) -> None:
        """Un passo di play: avanza di real_dt secondi reali moltiplicati per la velocita'."""
        if not self.playing:
            return
        self._run_to(self.t + real_dt * self.speed)
        if self.done:
            self.playing = False

    def take_samples(self) -> list[tuple[float, dict]]:
        out, self.new_samples = self.new_samples, []
        return out

    # ------------------------------------------------------------------ segnalibri
    def mark_at(self, t: float, tolerance: float = 0.0) -> dict | None:
        best = None
        for m in self.marks:
            d = abs(m.get("ts", 0) - t)
            if d <= tolerance and (best is None or d < abs(best.get("ts", 0) - t)):
                best = m
        return best

    @staticmethod
    def clock(t: float) -> str:
        return time.strftime("%H:%M:%S", time.localtime(t))

    @staticmethod
    def hms(seconds: float) -> str:
        seconds = max(0, int(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
