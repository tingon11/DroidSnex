"""Traduzioni dell'interfaccia.

I testi nel codice sono in italiano e passano da tr():

    tr("Connessioni")                       -> "Connections" in inglese
    tr("fidata: {d}", d="example.com")      -> segnaposto con str.format

Le traduzioni stanno in i18n_strings.py (una riga per testo, una colonna per lingua).
Se un testo non è tradotto si usa l'italiano.
"""
from __future__ import annotations

from .i18n_strings import ORDER, STRINGS

LANGUAGES = {
    "it": "Italiano", "en": "English", "de": "Deutsch", "fr": "Français", "es": "Español",
    "nl": "Nederlands", "pl": "Polski", "el": "Ελληνικά", "sq": "Shqip",
}
_current = "it"


def set_language(code: str) -> None:
    global _current
    _current = code if code in LANGUAGES else "it"


def language() -> str:
    return _current


def tr(text: str, **kw) -> str:
    if _current != "it":
        row = STRINGS.get(text)
        if row:
            t = row[ORDER.index(_current)]
            if t:
                text = t
    return text.format(**kw) if kw else text
