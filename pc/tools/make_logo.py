#!/usr/bin/env python3
# DroidSnex — logo e icona, stesso stile di AndrOsint.  Copyright (C) 2026 Andrea Cumini <andrea@osintinfo.net>
"""Rigenera logo e icona dell'applicazione (stile AndrOsint / Seity).

Il logo e' la scritta bicolore "DroidSnex" nel carattere Panchang Semibold:
prima parte bianca, seconda nel colore d'accento dell'interfaccia. L'icona e'
il quadrato scuro arrotondato con le iniziali "DS" e la barretta d'accento.

Serve il carattere Panchang installato sul PC (Fontshare). I file prodotti
finiscono in droidsnex/gui/assets/ e viaggiano con il programma: per usarlo
il carattere non serve.

    python tools\\make_logo.py
    python tools\\make_logo.py --font C:\\percorso\\Panchang-Variable.ttf
"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "droidsnex" / "gui" / "assets"

WORD_WHITE = "Droid"
WORD_ACCENT = "Snex"
INITIALS = "DS"
ACCENT = "#7b95dd"          # stesso accento di AndrOsint
WEIGHT = b"Semibold"

FONT_FILE = "Panchang-Variable.ttf"
FONT_DIRS = (
    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    Path.home() / "Library" / "Fonts",
    Path.home() / ".local" / "share" / "fonts",
    Path("/usr/share/fonts"),
)

LOGO_HEIGHT = 160  # altezza del PNG: abbondante, l'interfaccia lo riduce
ICON_SIZES = [(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48),
              (64, 64), (128, 128), (256, 256)]

_FONT_PATH: str | None = None


def find_font() -> str | None:
    """Panchang-Variable.ttf (come AndrOsint); in mancanza un file statico Panchang Semibold/Bold."""
    for folder in FONT_DIRS:
        if (folder / FONT_FILE).is_file():
            return str(folder / FONT_FILE)
    for folder in FONT_DIRS:
        if folder.is_dir():
            hits = [h for h in glob.glob(str(folder / "**" / "Panchang*"), recursive=True)
                    if h.lower().endswith((".ttf", ".otf"))]
            for pref in ("variable", "semibold", "bold", "medium"):
                for h in hits:
                    if pref in os.path.basename(h).lower():
                        return h
            if hits:
                return hits[0]
    return None


def font(size: int) -> ImageFont.FreeTypeFont:
    if not _FONT_PATH:
        sys.exit(f"Carattere {FONT_FILE} non trovato: installalo da fontshare.com o indica il file con --font.")
    loaded = ImageFont.truetype(_FONT_PATH, size)
    try:
        loaded.set_variation_by_name(WEIGHT)     # solo per il font variabile
    except (OSError, ValueError, AttributeError):
        pass
    return loaded


def wordmark(white: str, accent: str, size: int = 400) -> Image.Image:
    """Scritta bicolore su fondo trasparente, ritagliata al vivo."""
    face = font(size)
    width = int(face.getlength(white + accent)) + size
    image = Image.new("RGBA", (width, size * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x, y = size // 2, size // 2
    draw.text((x, y), white, font=face, fill="white")
    draw.text((x + face.getlength(white), y), accent, font=face, fill=ACCENT)
    return image.crop(image.getbbox())


def logo() -> Image.Image:
    mark = wordmark(WORD_WHITE, WORD_ACCENT)
    width = round(mark.width * LOGO_HEIGHT / mark.height)
    return mark.resize((width, LOGO_HEIGHT), Image.LANCZOS)


def icon() -> Image.Image:
    """Icona stile Seity: quadrato scuro arrotondato, iniziali, barretta d'accento."""
    size = 1024
    k = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(52 * k), fill=(40, 52, 66, 255))
    border = int(5 * k)
    draw.rounded_rectangle((border, border, size - 1 - border, size - 1 - border),
                           radius=int(47 * k), fill=(13, 17, 23, 255))
    mark = wordmark(INITIALS, "")
    scale = min(184 * k / mark.width, 106 * k / mark.height)
    mark = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.LANCZOS)
    image.alpha_composite(mark, ((size - mark.width) // 2, int(115 * k) - mark.height // 2))
    rgb = tuple(int(ACCENT.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    draw.rounded_rectangle((int(85 * k), int(192 * k), int(170 * k), int(209 * k)),
                           radius=int(8.5 * k), fill=rgb + (255,))
    return image.resize((256, 256), Image.LANCZOS)


def main() -> None:
    global _FONT_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--font", help="file del carattere Panchang (variabile o statico)")
    a = ap.parse_args()
    _FONT_PATH = a.font or find_font()
    ASSETS.mkdir(parents=True, exist_ok=True)
    mark = logo()
    mark.save(ASSETS / "logo.png")
    ico = icon()
    ico.save(ASSETS / "droidsnex.ico", "ICO", sizes=ICON_SIZES)
    ico.save(ASSETS / "droidsnex.png")
    print(f"logo.png {mark.size}, droidsnex.ico e droidsnex.png in {ASSETS}  (carattere: {_FONT_PATH})")


if __name__ == "__main__":
    main()
