# DroidSnex — finestra del manuale.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Il manuale (docs/manual/<lingua>/MANUAL.md) formattato in una finestra del programma, senza barra
del titolo come le altre: titoli, paragrafi, grassetto/corsivo/codice, elenchi puntati e numerati
annidati, tabelle, immagini (ridimensionate alla larghezza, clic = apre l'immagine intera), link
(interni = salta al capitolo, esterni = browser) e un indice dei capitoli a sinistra.

Un piccolo interprete Markdown fatto qui, senza librerie esterne: copre quello che usano i manuali.

    ManualWindow(app, path)        # app.manual_win, una sola alla volta
"""
from __future__ import annotations

import os
import re
import tkinter as tk
import tkinter.font as tkfont
import webbrowser

import customtkinter as ctk
from PIL import Image, ImageTk

from ..i18n import LANGUAGES, tr
from . import frameless, theme
from .widgets import window_buttons

CODE_BG = "#121821"
HIT_BG = "#5a4a12"                 # ricerca: occorrenze
HIT_CUR_BG = "#fbbf24"             # ricerca: occorrenza corrente
QUOTE_BAR = "#2a3644"

RE_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RE_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
RE_IMAGE = re.compile(r"^\s*!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)\s*$")
RE_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
RE_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$")
RE_INLINE = re.compile(
    r"(\*\*\*(?P<bi>.+?)\*\*\*"
    r"|\*\*(?P<b>.+?)\*\*"
    r"|(?<![\w*])\*(?P<i>[^*\s](?:[^*]*?[^*\s])?)\*(?![\w*])"
    r"|`(?P<c>[^`]+)`"
    r"|!\[(?P<ia>[^\]]*)\]\((?P<iu>[^)\s]+)\)"
    r"|\[(?P<lt>[^\]]+)\]\((?P<lu>[^)\s]+)\)"
    r"|<(?P<au>https?://[^>\s]+)>)")


def slug(text: str) -> str:
    """Ancora di un titolo come la calcola GitHub: minuscole, via la punteggiatura, spazi -> trattini."""
    t = re.sub(r"[*`_]|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", text).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


def plain(text: str) -> str:
    """Testo senza la formattazione inline (per celle di tabella e indice)."""
    def rep(m):
        for k in ("bi", "b", "i", "c", "lt"):
            if m.group(k) is not None:
                return m.group(k)
        if m.group("au"):
            return m.group("au")
        return ""
    return RE_INLINE.sub(rep, text)


# ---------------------------------------------------------------------------- parser
def parse(md: str) -> list[tuple]:
    """Blocchi: ("h", livello, testo) ("p", testo) ("li", livello, marcatore, testo) ("img", alt, src, livello)
    ("table", righe) ("hr",) ("code", testo) ("quote", testo)."""
    lines = md.replace("\r\n", "\n").replace("\t", "    ").split("\n")
    out: list[tuple] = []
    para: list[str] = []
    list_indents: list[int] = []      # rientri degli elenchi aperti (per il livello di annidamento)

    def flush():
        if para:
            out.append(("p", " ".join(s.strip() for s in para)))
            para.clear()

    def level_of(indent: int) -> int:
        while list_indents and indent < list_indents[-1]:
            list_indents.pop()
        if not list_indents or indent > list_indents[-1]:
            list_indents.append(indent)
        return len(list_indents) - 1

    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append(("code", "\n".join(code)))
            i += 1
            continue
        if not s:
            flush()
            i += 1
            continue
        m = RE_HEADING.match(line)
        if m:
            flush()
            list_indents.clear()
            out.append(("h", len(m.group(1)), m.group(2)))
            i += 1
            continue
        if RE_HR.match(line):
            flush()
            list_indents.clear()
            out.append(("hr",))
            i += 1
            continue
        if s.startswith("|") and i + 1 < len(lines) and RE_TABLE_SEP.match(lines[i + 1]):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not RE_TABLE_SEP.match(lines[i]):
                    cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                    rows.append(cells)
                i += 1
            out.append(("table", rows))
            continue
        m = RE_IMAGE.match(line)
        if m:
            flush()
            indent = len(line) - len(line.lstrip())
            lvl = 0
            if list_indents and indent > list_indents[0]:
                lvl = len([x for x in list_indents if x < indent])
            out.append(("img", m.group(1), m.group(2), lvl))
            i += 1
            continue
        m = RE_LIST.match(line)
        if m:
            flush()
            lvl = level_of(len(m.group(1)))
            text = [m.group(3)]
            i += 1
            # righe di continuazione dello stesso punto (rientrate, non vuote, non un altro elemento)
            while i < len(lines) and lines[i].strip() and lines[i].startswith(" ") \
                    and not RE_LIST.match(lines[i]) and not RE_IMAGE.match(lines[i]):
                text.append(lines[i].strip())
                i += 1
            out.append(("li", lvl, m.group(2), " ".join(text)))
            continue
        if s.startswith(">"):
            flush()
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].strip())
                i += 1
            out.append(("quote", " ".join(q)))
            continue
        if not line.startswith(" "):
            list_indents.clear()
        para.append(line)
        i += 1
    flush()
    return out


# ---------------------------------------------------------------------------- finestra
class ManualWindow(ctk.CTkToplevel):
    def __init__(self, app, path: str):
        super().__init__(app, fg_color=theme.BG)
        self.app = app
        self.path = path
        self.base = os.path.dirname(path)
        self.blocks: list[tuple] = []
        self._images: list = []
        self._img_cache: dict[tuple, ImageTk.PhotoImage] = {}
        self._tag_n = 0
        self._width = 0
        self._resize_job = None
        self._frameless_done = False
        self._cells: list[tuple] = []        # celle delle tabelle: (etichetta, testo, sfondo, posizione nel testo)
        self._hits: list[tuple] = []         # risultati della ricerca: (posizione, fine | None, etichetta | None)
        self._hit_i = -1
        self._search_job = None
        self.title("DroidSnex · " + tr("Manuale"))
        self.protocol("WM_DELETE_WINDOW", self.close)
        try:
            if getattr(app, "_droidsnex_icon", None) is not None:
                self.iconphoto(False, app._droidsnex_icon)
        except tk.TclError:
            pass
        self._fonts()
        self._build()
        w, h = 1180, 860
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h = min(w, sw - 40), min(h, sh - 80)
        x = app.winfo_rootx() + max(0, (app.winfo_width() - w) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - h) // 3)
        self.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")
        self.bind("<Map>", self._on_map, add="+")
        self.bind("<Escape>", lambda _e: self._escape())
        self.bind("<Control-f>", lambda _e: self._focus_search())
        self.bind("<F3>", lambda _e: self.find_next(1))
        self.bind("<Shift-F3>", lambda _e: self.find_next(-1))
        # la barra del titolo di Windows va tolta PRIMA di caricare il testo: il caricamento dura più del
        # ritardo con cui CTkToplevel mostra la finestra, che altrimenti comparirebbe un attimo con la barra
        try:
            self.update_idletasks()
            self._on_map()
        except tk.TclError:
            pass
        self.load(path)
        self.after(60, self._raise)

    # ------------------------------------------------------------------ aspetto
    def _fonts(self) -> None:
        ui, mono = theme.ui_font(), theme.mono_font()
        self.f_body = tkfont.Font(family=ui, size=11)
        self.f_bold = tkfont.Font(family=ui, size=11, weight="bold")
        self.f_italic = tkfont.Font(family=ui, size=11, slant="italic")
        self.f_bi = tkfont.Font(family=ui, size=11, weight="bold", slant="italic")
        self.f_code = tkfont.Font(family=mono, size=10)
        self.f_h1 = tkfont.Font(family=ui, size=22, weight="bold")
        self.f_h2 = tkfont.Font(family=ui, size=16, weight="bold")
        self.f_h3 = tkfont.Font(family=ui, size=13, weight="bold")
        self.f_small = tkfont.Font(family=ui, size=9, slant="italic")
        self.f_toc = tkfont.Font(family=ui, size=10)

    def _build(self) -> None:
        f = self.app.fonts
        bar = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0, height=34)
        bar.pack(side="top", fill="x", padx=1, pady=(1, 0))
        bar.pack_propagate(False)
        logo = theme.logo(12)
        brand = (ctk.CTkLabel(bar, text="", image=logo) if logo is not None else
                 ctk.CTkLabel(bar, text="DROIDSNEX", font=(theme.mono_font(), 12, "bold")))
        brand.pack(side="left", padx=(12, 0))
        self.bar_label = ctk.CTkLabel(bar, text="", font=f.bold, text_color=theme.TEXT_SOFT)
        self.bar_label.pack(side="left")
        window_buttons(self, bar, self.close).pack(side="right")
        for x in (bar, brand, self.bar_label):
            frameless.enable_drag(self, x)

        body = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=0, border_width=1, border_color=theme.BORDER)
        body.pack(side="top", fill="both", expand=True, padx=1, pady=(0, 1))
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        # indice dei capitoli
        side = ctk.CTkFrame(body, fg_color=theme.BG, corner_radius=0, width=250)
        side.grid(row=0, column=0, sticky="ns")
        side.grid_propagate(False)
        side.pack_propagate(False)
        # ricerca nel testo (Ctrl+F): Invio = successivo, Maiusc+Invio = precedente
        self.search = ctk.CTkEntry(side, height=30, font=f.body, placeholder_text=tr("Cerca nel manuale  (Ctrl+F)"),
                                   fg_color=theme.INPUT, border_color=theme.BORDER_STRONG, border_width=1, corner_radius=4)
        self.search.pack(fill="x", padx=12, pady=(12, 4))
        self.search.bind("<KeyRelease>", self._search_typed)
        self.search.bind("<Return>", lambda _e: self.find_next(1))
        self.search.bind("<Shift-Return>", lambda _e: self.find_next(-1))
        srow = ctk.CTkFrame(side, fg_color="transparent")
        srow.pack(fill="x", padx=12)
        self.search_count = ctk.CTkLabel(srow, text="", font=f.small, text_color=theme.TEXT_DIM, anchor="w")
        self.search_count.pack(side="left")
        for sym, step in (("▼", 1), ("▲", -1)):
            ctk.CTkButton(srow, text=sym, width=26, height=22, corner_radius=4, fg_color="transparent",
                          hover_color=theme.HOVER, text_color=theme.TEXT_SOFT, font=(theme.mono_font(), 10),
                          command=lambda d=step: self.find_next(d)).pack(side="right", padx=(2, 0))
        ctk.CTkLabel(side, text=tr("Indice").upper(), font=f.caption, text_color=theme.TEXT_FAINT, anchor="w").pack(
            fill="x", padx=16, pady=(10, 6))
        self.toc = tk.Text(side, bg=theme.BG, fg=theme.TEXT_SOFT, font=self.f_toc, wrap="word", bd=0,
                           highlightthickness=0, padx=14, pady=4, cursor="arrow", spacing1=3, spacing3=3)
        self.toc.pack(fill="both", expand=True)
        self.toc.tag_config("toc", lmargin1=0, lmargin2=18)
        self.toc.tag_config("toc3", lmargin1=16, lmargin2=30, foreground=theme.TEXT_DIM)
        self.toc.tag_config("hover", foreground=theme.ACCENT)

        # testo
        self.text = tk.Text(body, bg=theme.PANEL, fg=theme.TEXT, font=self.f_body, wrap="word", bd=0,
                            highlightthickness=0, padx=36, pady=22, cursor="arrow", spacing1=2, spacing3=2,
                            insertwidth=0, selectbackground=theme.ACCENT_DIM, exportselection=True)
        self.text.grid(row=0, column=1, sticky="nsew")
        sb = ctk.CTkScrollbar(body, command=self.text.yview, button_color=theme.BORDER_STRONG,
                              button_hover_color=theme.ACCENT_DIM)
        sb.grid(row=0, column=2, sticky="ns", padx=(0, 2), pady=2)
        self.text.configure(yscrollcommand=sb.set)
        self.text.bind("<Configure>", self._on_resize)
        self.text.bind("<Control-c>", lambda _e: self._copy())
        self._tags()

    def _tags(self) -> None:
        t = self.text
        t.tag_config("h1", font=self.f_h1, foreground=theme.TEXT, spacing1=4, spacing3=12)
        t.tag_config("h2", font=self.f_h2, foreground=theme.ACCENT, spacing1=26, spacing3=8)
        t.tag_config("h3", font=self.f_h3, foreground=theme.TEXT, spacing1=16, spacing3=6)
        t.tag_config("p", spacing1=4, spacing3=8, lmargin1=0, lmargin2=0)
        t.tag_config("bold", font=self.f_bold, foreground="#eef2f7")
        t.tag_config("italic", font=self.f_italic)
        t.tag_config("bi", font=self.f_bi)
        t.tag_config("code", font=self.f_code, background=CODE_BG, foreground="#e3c27b")
        t.tag_config("codeblock", font=self.f_code, background=CODE_BG, foreground=theme.TEXT, lmargin1=12,
                     lmargin2=12, rmargin=12, spacing1=0, spacing3=0)
        t.tag_config("link", foreground=theme.ACCENT, underline=True)
        t.tag_config("quote", foreground=theme.TEXT_SOFT, lmargin1=18, lmargin2=18, spacing1=4, spacing3=8,
                     font=self.f_italic)
        t.tag_config("caption", font=self.f_small, foreground=theme.TEXT_DIM, spacing1=2, spacing3=12)
        t.tag_config("hr", font=tkfont.Font(size=4), spacing1=10, spacing3=10)
        t.tag_config("hit", background=HIT_BG, foreground="#ffffff")
        t.tag_config("hitcur", background=HIT_CUR_BG, foreground="#0a0d12")
        t.tag_raise("hit")
        t.tag_raise("hitcur")
        t.tag_bind("link", "<Enter>", lambda _e: t.configure(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda _e: t.configure(cursor="arrow"))

    # ------------------------------------------------------------------ finestra
    def _on_map(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        if self._frameless_done or not getattr(self.app, "frameless", False):
            return
        if frameless.make_frameless(self, border_color=theme.BORDER):
            self._frameless_done = True

    def _raise(self, n: int = 0) -> None:
        if not self.winfo_exists():
            return
        try:
            self.deiconify()
            self.update_idletasks()
            self._on_map()
            self.lift()
            self.focus_force()
        except tk.TclError:
            return
        if n < 10 and not self._frameless_done and getattr(self.app, "frameless", False):
            self.after(150, lambda: self._raise(n + 1))

    def close(self) -> None:
        if getattr(self.app, "manual_win", None) is self:
            self.app.manual_win = None
        try:
            self.destroy()
        except tk.TclError:
            pass

    def _copy(self) -> str:
        try:
            sel = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return "break"
        self.clipboard_clear()
        self.clipboard_append(sel)
        return "break"

    # ------------------------------------------------------------------ contenuto
    def load(self, path: str) -> None:
        self.path, self.base = path, os.path.dirname(path)
        code = os.path.basename(self.base)
        self.bar_label.configure(text=f"   ·   {tr('Manuale')}   ·   {LANGUAGES.get(code, code)}")
        try:
            with open(path, encoding="utf-8") as fh:
                md = fh.read()
        except OSError as e:
            md = f"# {tr('Manuale')}\n\n{tr('impossibile aprire il manuale: {e}', e=e)}"
        self.blocks = parse(md)
        self._width = 0
        self.after(30, self.render)

    def _content_width(self) -> int:
        w = self.text.winfo_width()
        if w < 50:
            w = 1180 - 250 - 20
        return max(300, w - 2 * 36 - 8)

    def _on_resize(self, _e=None) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(250, self._maybe_rerender)

    def _maybe_rerender(self) -> None:
        self._resize_job = None
        if abs(self._content_width() - self._width) > 30:
            top = self.text.yview()[0]
            self.render()
            self.text.yview_moveto(top)
            if self.search.get().strip():
                self.find(self.search.get(), keep=True)
                self.text.yview_moveto(top)

    def _newtag(self, prefix: str) -> str:
        self._tag_n += 1
        return f"{prefix}{self._tag_n}"

    def render(self) -> None:
        t = self.text
        self._width = self._content_width()
        t.configure(state="normal")
        t.delete("1.0", "end")
        for tag in t.tag_names():
            if tag.startswith(("lnk", "li", "img")):
                t.tag_delete(tag)
        for name in t.mark_names():
            if name.startswith("h:"):
                t.mark_unset(name)
        self._images = []
        self._cells = []
        self.toc.configure(state="normal")
        self.toc.delete("1.0", "end")
        for tag in self.toc.tag_names():
            if tag.startswith("go"):
                self.toc.tag_delete(tag)
        prev = None
        for b in self.blocks:
            kind = b[0]
            if kind == "h":
                self._heading(b[1], b[2])
            elif kind == "p":
                self._inline(b[1], ("p",))
                t.insert("end", "\n", ("p",))
            elif kind == "li":
                self._item(b[1], b[2], b[3], tight=prev == "li")
            elif kind == "img":
                self._image(b[1], b[2], b[3])
            elif kind == "table":
                self._table(b[1])
            elif kind == "hr":
                self._hr()
            elif kind == "code":
                t.insert("end", b[1] + "\n", ("codeblock",))
                t.insert("end", "\n", ("p",))
            elif kind == "quote":
                self._inline(b[1], ("quote",))
                t.insert("end", "\n", ("quote",))
            prev = kind
        t.configure(state="disabled")
        self.toc.configure(state="disabled")

    def _heading(self, level: int, text: str) -> None:
        t = self.text
        tag = "h1" if level == 1 else "h2" if level == 2 else "h3"
        mark = "h:" + slug(text)
        t.mark_set(mark, "end-1c")
        t.mark_gravity(mark, "left")
        self._inline(text, (tag,))
        t.insert("end", "\n", (tag,))
        if level == 2:
            # filo sottile sotto i capitoli, su una riga sua
            self._rule(1, theme.BORDER)
            t.insert("end", "\n", ("hr",))
        if level in (2, 3) and plain(text).strip().lower() not in ("indice", "index", "contents", "inhalt",
                                                                   "sommaire", "índice", "inhoud", "spis treści",
                                                                   "περιεχόμενα", "përmbajtja"):
            go = self._newtag("go")
            self.toc.insert("end", plain(text) + "\n", ("toc" if level == 2 else "toc3", go))
            self.toc.tag_bind(go, "<Button-1>", lambda _e, m=mark: self.goto(m))
            self.toc.tag_bind(go, "<Enter>", lambda _e, g=go: (self.toc.tag_add("hover", f"{g}.first", f"{g}.last"),
                                                                 self.toc.configure(cursor="hand2")))
            self.toc.tag_bind(go, "<Leave>", lambda _e, g=go: (self.toc.tag_remove("hover", "1.0", "end"),
                                                                 self.toc.configure(cursor="arrow")))

    def _rule(self, height: int, color: str) -> None:
        line = tk.Frame(self.text, height=height, width=self._width, bg=color, bd=0, highlightthickness=0)
        self.text.window_create("end-1c", window=line)
        self.text.tag_add("hr", "end-2c", "end-1c")

    def _hr(self) -> None:
        self._rule(1, theme.BORDER_STRONG)
        self.text.insert("end", "\n", ("hr",))

    def _item(self, level: int, marker: str, text: str, tight: bool) -> None:
        t = self.text
        if marker in "-*+":
            sym = ("•", "◦", "▪")[min(level, 2)]
        else:
            sym = marker.rstrip(")").rstrip(".") + "."
        lm1 = 6 + level * 26
        lm2 = lm1 + max(18, self.f_body.measure(sym + "  "))
        tag = f"li{lm1}_{lm2}"
        if tag not in t.tag_names():
            t.tag_config(tag, lmargin1=lm1, lmargin2=lm2, spacing1=3, spacing3=3)
        t.insert("end", sym + " " * (2 if len(sym) == 1 else 1), (tag, "bold" if sym[0].isdigit() else ()))
        self._inline(text, (tag,))
        t.insert("end", "\n", (tag,))

    def _inline(self, text: str, base: tuple, extra: tuple = ()) -> None:
        t = self.text
        pos = 0
        for m in RE_INLINE.finditer(text):
            if m.start() > pos:
                t.insert("end", text[pos:m.start()], base + extra)
            if m.group("bi") is not None:
                self._inline(m.group("bi"), base, extra + ("bi",))
            elif m.group("b") is not None:
                self._inline(m.group("b"), base, extra + ("bold",))
            elif m.group("i") is not None:
                self._inline(m.group("i"), base, extra + ("italic",))
            elif m.group("c") is not None:
                t.insert("end", " " + m.group("c") + " ", base + extra + ("code",))
            elif m.group("iu") is not None:
                self._image(m.group("ia"), m.group("iu"), 0, inline=True)
            else:
                label = m.group("lt") or m.group("au")
                url = m.group("lu") or m.group("au")
                tag = self._newtag("lnk")
                t.tag_bind(tag, "<Button-1>", lambda _e, u=url: self.follow(u))
                t.insert("end", plain(label), base + extra + ("link", tag))
            pos = m.end()
        if pos < len(text):
            t.insert("end", text[pos:], base + extra)

    def _image(self, alt: str, src: str, level: int, inline: bool = False) -> None:
        t = self.text
        path = src if os.path.isabs(src) else os.path.normpath(os.path.join(self.base, src))
        indent = 6 + level * 26 + (26 if level else 0)
        maxw = max(200, self._width - indent)
        photo = self._photo(path, maxw)
        tag = self._newtag("img")
        t.tag_config(tag, lmargin1=indent, lmargin2=indent, spacing1=8, spacing3=2)
        if photo is None:
            t.insert("end", f"[{alt or os.path.basename(src)}]", (tag, "caption"))
        else:
            t.image_create("end", image=photo, padx=0, pady=0)
            t.tag_add(tag, "end-2c", "end-1c")
            self._images.append(photo)
            t.tag_bind(tag, "<Button-1>", lambda _e, p=path: self._open_file(p))
            t.tag_bind(tag, "<Enter>", lambda _e: t.configure(cursor="hand2"))
            t.tag_bind(tag, "<Leave>", lambda _e: t.configure(cursor="arrow"))
        if inline:
            return
        t.insert("end", "\n", (tag,))
        if alt:
            cap = self._newtag("img")
            t.tag_config(cap, lmargin1=indent, lmargin2=indent)
            t.insert("end", alt + "\n", ("caption", cap))

    def _photo(self, path: str, maxw: int) -> ImageTk.PhotoImage | None:
        key = (path, maxw)
        if key in self._img_cache:
            return self._img_cache[key]
        try:
            im = Image.open(path)
            im.load()
        except (OSError, ValueError):
            return None
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        if im.width > maxw:
            im = im.resize((maxw, max(1, int(im.height * maxw / im.width))), Image.LANCZOS)
        photo = ImageTk.PhotoImage(im)
        if len(self._img_cache) > 120:
            self._img_cache.clear()
        self._img_cache[key] = photo
        return photo

    def _table(self, rows: list[list[str]]) -> None:
        if not rows:
            return
        t = self.text
        ncol = max(len(r) for r in rows)
        lens = [max((len(plain(r[c])) if c < len(r) else 0) for r in rows) for c in range(ncol)]
        lens = [min(max(x, 6), 70) for x in lens]
        total = sum(lens) or 1
        width = self._width
        frame = tk.Frame(t, bg=theme.BORDER, bd=0, highlightthickness=0)
        where = t.index("end-1c")
        for c in range(ncol):
            frame.grid_columnconfigure(c, minsize=int(width * lens[c] / total), weight=0)
        for r, row in enumerate(rows):
            for c in range(ncol):
                cell = plain(row[c]) if c < len(row) else ""
                head = r == 0
                lab = tk.Label(frame, text=cell, font=self.f_bold if head else self.f_body, justify="left", anchor="nw",
                               bg=theme.PANEL_3 if head else (theme.PANEL if r % 2 else theme.BG),
                               fg=theme.TEXT if head else theme.TEXT_SOFT, padx=10, pady=6,
                               wraplength=max(60, int(width * lens[c] / total) - 22))
                lab.grid(row=r, column=c, sticky="nsew", padx=(0 if c == 0 else 1, 0), pady=(0 if r == 0 else 1, 0))
                self._cells.append((lab, cell, lab.cget("bg"), where))
                lab.bind("<MouseWheel>", self._wheel)
                lab.bind("<Button-4>", lambda _e: self.text.yview_scroll(-3, "units"))
                lab.bind("<Button-5>", lambda _e: self.text.yview_scroll(3, "units"))
        t.window_create("end-1c", window=frame)
        t.insert("end", "\n", ("p",))

    def _wheel(self, e) -> str:
        self.text.yview_scroll(int(-e.delta / 40) if abs(e.delta) >= 40 else (-1 if e.delta > 0 else 1), "units")
        return "break"

    # ------------------------------------------------------------------ ricerca
    def _focus_search(self) -> str:
        self.search.focus_set()
        self.search.select_range(0, "end")
        return "break"

    def _escape(self) -> None:
        """Esc: prima svuota la ricerca, poi chiude la finestra."""
        if self.search.get():
            self.search.delete(0, "end")
            self.find("")
            self.text.focus_set()
        else:
            self.close()

    def _search_typed(self, e=None) -> None:
        if e is not None and e.keysym in ("Return", "Shift_L", "Shift_R", "Escape", "F3"):
            return
        if self._search_job is not None:
            self.after_cancel(self._search_job)
        self._search_job = self.after(180, lambda: self.find(self.search.get()))

    def find(self, query: str, keep: bool = False) -> int:
        """Evidenzia tutte le occorrenze (testo e celle delle tabelle) e va alla prima. Ritorna quante sono."""
        self._search_job = None
        t = self.text
        t.tag_remove("hit", "1.0", "end")
        t.tag_remove("hitcur", "1.0", "end")
        for lab, _text, bg, _where in self._cells:
            try:
                lab.configure(bg=bg)
            except tk.TclError:
                pass
        old = self._hit_i if keep else -1
        self._hits, self._hit_i = [], -1
        q = query.strip()
        if len(q) < 2:
            self.search_count.configure(text="")
            return 0
        low = q.lower()
        # niente Text.search (con immagini e tabelle incorporate non e' affidabile): si legge il testo a pezzi
        # con dump() e si cerca riga per riga, tenendo la colonna reale di ogni pezzo
        lines: dict[int, list[tuple[int, str]]] = {}
        for _kind, value, index in t.dump("1.0", "end-1c", text=True):
            ln, col = (int(x) for x in index.split("."))
            for part in value.split("\n"):
                if part:
                    lines.setdefault(ln, []).append((col, part))
                ln, col = ln + 1, 0
        for ln in sorted(lines):
            segs = lines[ln]
            joined = "".join(x for _c, x in segs).lower()
            at = joined.find(low)
            while at >= 0 and len(self._hits) < 2000:
                cols = []
                for off, last in ((at, False), (at + len(low), True)):
                    acc = 0
                    for col, part in segs:
                        if off < acc + len(part) or (last and off == acc + len(part)):
                            cols.append(col + off - acc)
                            break
                        acc += len(part)
                if len(cols) == 2:
                    pos, end = f"{ln}.{cols[0]}", f"{ln}.{cols[1]}"
                    t.tag_add("hit", pos, end)
                    self._hits.append((pos, end, None))
                at = joined.find(low, at + len(low))
        for lab, text, _bg, where in self._cells:
            if low in text.lower():
                lab.configure(bg=HIT_BG)
                self._hits.append((where, None, lab))
        self._hits.sort(key=lambda h: tuple(int(x) for x in h[0].split(".")))
        if self._hits:
            self._hit_i = min(old, len(self._hits) - 1) if old >= 0 else -1
            self.find_next(0 if old >= 0 else 1)
        else:
            self.search_count.configure(text=tr("nessun risultato"))
        return len(self._hits)

    def find_next(self, step: int = 1) -> str:
        if self._search_job is not None:                 # Invio subito dopo aver scritto
            self.after_cancel(self._search_job)
            self.find(self.search.get())
            return "break"
        if not self._hits:
            return "break"
        t = self.text
        t.tag_remove("hitcur", "1.0", "end")
        if 0 <= self._hit_i < len(self._hits) and self._hits[self._hit_i][2] is not None:
            self._hits[self._hit_i][2].configure(bg=HIT_BG)
        self._hit_i = (self._hit_i + step) % len(self._hits)
        pos, end, lab = self._hits[self._hit_i]
        if lab is not None:
            lab.configure(bg=HIT_CUR_BG)
        else:
            t.tag_add("hitcur", pos, end)
        t.see(pos)
        t.yview_scroll(0, "units")
        if t.dlineinfo(pos) is None or lab is not None:
            t.yview(f"{pos} linestart")
        self.search_count.configure(text=f"{self._hit_i + 1} / {len(self._hits)}")
        return "break"

    # ------------------------------------------------------------------ navigazione
    def goto(self, mark: str) -> None:
        try:
            self.text.yview(mark)
        except tk.TclError:
            pass

    def follow(self, url: str) -> None:
        if url.startswith("#"):
            self.goto("h:" + url[1:].lower())
        elif re.match(r"^[a-z]+://|^mailto:", url, re.I):
            webbrowser.open(url)
        else:
            path = url.split("#", 1)[0]
            self._open_file(path if os.path.isabs(path) else os.path.normpath(os.path.join(self.base, path)))

    def _open_file(self, path: str) -> None:
        if not os.path.exists(path):
            return
        try:
            if os.name == "nt":
                os.startfile(path)  # type: ignore[attr-defined]
            else:
                webbrowser.open("file://" + path)
        except OSError:
            pass


def open_manual(app, path: str) -> ManualWindow:
    """Una sola finestra del manuale: se c'è già, la riporta davanti (ricaricando se la lingua è cambiata)."""
    win = getattr(app, "manual_win", None)
    if win is not None:
        try:
            if win.winfo_exists():
                if win.path != path:
                    win.load(path)
                win._raise()
                return win
        except tk.TclError:
            pass
    app.manual_win = ManualWindow(app, path)
    return app.manual_win


__all__ = ["ManualWindow", "open_manual", "parse", "slug"]
