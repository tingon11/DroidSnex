# DroidSnex — finestra iniziale: lingua e termini d'uso.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Finestra bloccante alla prima apertura: scelta della lingua (se non è già in config.json) e
accettazione dei termini d'uso / esclusione di responsabilità (droidsnex/terms.py), mostrati nella
lingua scelta. Sempre in primo piano, senza barra del titolo come il resto del programma, senza
possibilità di chiuderla: "Accetto" salva in config.json la versione dei termini e la data e il
programma parte; "Rifiuto" chiude il programma. Quando la versione dei termini cambia, vengono
richiesti di nuovo.

    welcome.run(app, settings, need_language, on_accept, on_reject)   # all'avvio
    welcome.show_terms(root, fonts)                                   # sola lettura, da "Informazioni e licenze"
"""
from __future__ import annotations

import time
import tkinter as tk

import customtkinter as ctk

from .. import __version__, terms
from ..i18n import LANGUAGES, set_language
from . import frameless, theme
from .widgets import button

WIDTH, HEIGHT = 760, 560


class WelcomeWindow(ctk.CTkToplevel):
    def __init__(self, root, settings, need_language: bool, on_accept, on_reject, read_only: bool = False):
        super().__init__(root, fg_color=theme.BG)
        self.root = root
        self.settings = settings
        self.on_accept, self.on_reject = on_accept, on_reject
        self.read_only = read_only
        self.lang = (settings.language if settings else "") or "it"
        self.fonts = theme.Fonts()
        self._frameless_done = False
        self._accept_ready = False
        self.title("DroidSnex")
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)
        try:
            theme.set_icon(self)
        except Exception:  # noqa: BLE001
            pass
        self.protocol("WM_DELETE_WINDOW", self._reject if not read_only else self._close)
        self.bind("<Escape>", lambda _e: self._close() if read_only else None)
        self.bind("<Map>", self._on_map, add="+")

        self.outer = ctk.CTkFrame(self, fg_color=theme.PANEL, border_width=1, border_color=theme.BORDER, corner_radius=0)
        self.outer.pack(fill="both", expand=True)
        self.bar = ctk.CTkFrame(self.outer, fg_color=theme.BG, corner_radius=0, height=36)
        self.bar.pack(fill="x", padx=1, pady=(1, 0))
        self.bar.pack_propagate(False)
        self.bar_title = ctk.CTkLabel(self.bar, text="", font=self.fonts.bold, text_color=theme.TEXT_SOFT, anchor="w")
        self.bar_title.pack(side="left", padx=14)
        ctk.CTkLabel(self.bar, text=f"v{__version__}", font=self.fonts.small, text_color=theme.TEXT_DIM).pack(side="right", padx=14)
        self.body = ctk.CTkFrame(self.outer, fg_color=theme.PANEL, corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        if need_language and not read_only:
            self._build_language()
        else:
            self._build_terms()
        self._place()
        self.after(60, self._raise)

    # ---------------------------------------------------------------- finestra
    def _place(self) -> None:
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{WIDTH}x{HEIGHT}+{max(0, (sw - WIDTH) // 2)}+{max(0, (sh - HEIGHT) // 2)}")

    def _on_map(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        if self._frameless_done or not getattr(self.root, "frameless", False):
            return
        if frameless.make_frameless(self, border_color=theme.BORDER):
            self._frameless_done = True

    def _raise(self, n: int = 0) -> None:
        """CTkToplevel su Windows nasconde e rimostra la finestra: la si porta davanti, sopra tutto, modale."""
        if not self.winfo_exists():
            return
        try:
            self.deiconify()
            self.update_idletasks()
            self._on_map()
            self.attributes("-topmost", True)
            self.lift()
            self.focus_force()
            self.grab_set()
        except tk.TclError:
            pass
        if n < 10 and (not self._frameless_done and getattr(self.root, "frameless", False)):
            self.after(150, lambda: self._raise(n + 1))

    def _clear(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()

    # ---------------------------------------------------------------- passo 1: lingua
    def _build_language(self) -> None:
        self._clear()
        self.bar_title.configure(text="DroidSnex")
        box = ctk.CTkFrame(self.body, fg_color="transparent")
        box.place(relx=0.5, rely=0.5, anchor="center")
        # titolo in tutte le lingue: chi apre il programma non ha ancora scelto
        ctk.CTkLabel(box, text="  ·  ".join(terms.labels(c)[3] for c in ("it", "en", "de", "fr")),
                     font=self.fonts.bold, text_color=theme.TEXT).pack(pady=(0, 2))
        ctk.CTkLabel(box, text="  ·  ".join(terms.labels(c)[3] for c in ("es", "nl", "pl", "el", "sq")),
                     font=self.fonts.small, text_color=theme.TEXT_DIM).pack(pady=(0, 18))
        grid = ctk.CTkFrame(box, fg_color="transparent")
        grid.pack()
        for i, (code, name) in enumerate(LANGUAGES.items()):
            ctk.CTkButton(grid, text=name, width=170, height=40, corner_radius=4, font=self.fonts.body,
                          fg_color=theme.PANEL_3, hover_color=theme.ACCENT_DIM, text_color=theme.TEXT,
                          border_width=1, border_color=theme.BORDER_STRONG,
                          command=lambda c=code: self._pick_language(c)).grid(row=i // 3, column=i % 3, padx=6, pady=6)

    def _pick_language(self, code: str) -> None:
        self.lang = code
        set_language(code)
        if self.settings is not None:
            self.settings.language = code          # salvato in config.json da App all'accettazione
        self._build_terms()

    # ---------------------------------------------------------------- passo 2: termini
    def _build_terms(self) -> None:
        self._clear()
        title, ok, no, _lang, note = terms.labels(self.lang)
        self.bar_title.configure(text=f"DroidSnex  ·  {title}")
        ctk.CTkLabel(self.body, text=title.upper(), font=self.fonts.title, text_color=theme.ACCENT, anchor="w").pack(
            fill="x", padx=20, pady=(14, 4))
        self.text = ctk.CTkTextbox(self.body, fg_color=theme.BG, text_color=theme.TEXT, font=self.fonts.body,
                                   wrap="word", border_width=1, border_color=theme.BORDER, corner_radius=4,
                                   scrollbar_button_color=theme.BORDER_STRONG, scrollbar_button_hover_color=theme.ACCENT_DIM)
        self.text.pack(fill="both", expand=True, padx=20, pady=(0, 8))
        self.text.insert("1.0", terms.text(self.lang))
        self.text.configure(state="disabled")
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 16))
        if self.read_only:
            button(row, "OK", self._close, primary=True, width=120).pack(side="right")
            ctk.CTkLabel(row, text=f"v{terms.TERMS_VERSION} · {terms.TERMS_DATE}", font=self.fonts.small,
                         text_color=theme.TEXT_DIM).pack(side="left")
            return
        self.note = ctk.CTkLabel(row, text=note, font=self.fonts.small, text_color=theme.TEXT_DIM, anchor="w",
                                 justify="left", wraplength=420)
        self.note.pack(side="left", fill="x", expand=True)
        self.btn_ok = button(row, ok, self._accept, primary=True, width=130)
        self.btn_ok.pack(side="right")
        self.btn_ok.configure(state="disabled")
        button(row, no, self._reject, danger=True, width=130).pack(side="right", padx=(0, 10))
        self.after(300, self._watch_scroll)

    def _watch_scroll(self) -> None:
        """"Accetto" si attiva solo quando il testo è stato fatto scorrere fino in fondo."""
        if not self.winfo_exists() or self._accept_ready:
            return
        try:
            _top, bottom = self.text.yview()
        except tk.TclError:
            return
        if bottom >= 0.999:
            self._accept_ready = True
            self.btn_ok.configure(state="normal")
            self.note.configure(text_color=theme.OK)
            return
        self.after(250, self._watch_scroll)

    def _accept(self) -> None:
        if not self._accept_ready:
            return
        if self.settings is not None:
            self.settings.terms_accepted = terms.TERMS_VERSION
            self.settings.terms_accepted_at = time.strftime("%Y-%m-%d %H:%M:%S")
            self.settings.language = self.lang
        self._close()
        if self.on_accept:
            self.on_accept()

    def _reject(self) -> None:
        self._close()
        if self.on_reject:
            self.on_reject()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


def run(app, settings, need_language: bool, on_accept, on_reject) -> WelcomeWindow:
    """All'avvio: scelta lingua (se `need_language`) e termini. `on_accept` prosegue, `on_reject` chiude."""
    return WelcomeWindow(app, settings, need_language, on_accept, on_reject)


def show_terms(root, _fonts=None) -> WelcomeWindow:
    """Solo lettura (da "Informazioni e licenze"), nella lingua corrente."""
    from ..i18n import language
    current = language()

    class _S:
        language = current
    return WelcomeWindow(root, _S, False, None, None, read_only=True)
