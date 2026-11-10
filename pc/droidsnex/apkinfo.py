"""Lettura dei dati essenziali di un file APK senza strumenti esterni (niente aapt).

L'APK e' uno zip; AndroidManifest.xml dentro e' in formato binario (AXML). Qui si legge solo il
necessario: il pool di stringhe e gli attributi dell'elemento <manifest> (package, versionCode,
versionName). Serve al tab Config per dire quale agent c'e' nel file scelto e se corrisponde
a quello installato sul telefono.
"""
from __future__ import annotations

import hashlib
import os
import struct
import zipfile
from dataclasses import dataclass

CHUNK_STRING_POOL = 0x0001
CHUNK_XML_START_ELEMENT = 0x0102
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10


@dataclass
class ApkInfo:
    path: str
    package: str = ""
    version_name: str = ""
    version_code: int = 0
    size: int = 0
    sha256: str = ""
    error: str = ""

    @property
    def version(self) -> str:
        if not self.version_name and not self.version_code:
            return "?"
        return f"{self.version_name or '?'} ({self.version_code})"


def _strings(data: bytes, off: int) -> list[str]:
    """Pool di stringhe AXML: offsets + testo UTF-16 (o UTF-8 se il flag e' acceso)."""
    _type, hdr, size, count, _styles, flags, strings_start, _styles_start = struct.unpack_from("<HHIIIIII", data, off)
    utf8 = bool(flags & 0x100)
    offsets = struct.unpack_from(f"<{count}I", data, off + hdr)
    base = off + strings_start
    out = []
    for o in offsets:
        p = base + o
        if utf8:
            # due lunghezze (caratteri, byte), ognuna su 1 o 2 byte
            n = data[p]
            p += 2 if n & 0x80 else 1
            n = data[p]
            if n & 0x80:
                n = ((n & 0x7F) << 8) | data[p + 1]
                p += 2
            else:
                p += 1
            out.append(data[p:p + n].decode("utf-8", "replace"))
        else:
            n = struct.unpack_from("<H", data, p)[0]
            p += 2
            if n & 0x8000:
                n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", data, p)[0]
                p += 2
            out.append(data[p:p + n * 2].decode("utf-16-le", "replace"))
    return out


def parse_manifest(data: bytes) -> dict:
    """{package, versionCode, versionName} dall'AndroidManifest.xml binario."""
    out: dict = {}
    pool: list[str] = []
    off = 8                                   # header del file (tipo 0x0003)
    while off + 8 <= len(data):
        ctype, hdr, size = struct.unpack_from("<HHI", data, off)
        if size < 8:
            break
        if ctype == CHUNK_STRING_POOL and not pool:
            pool = _strings(data, off)
        elif ctype == CHUNK_XML_START_ELEMENT:
            _line, _comment, _ns, name, attr_start, attr_size, attr_count = struct.unpack_from("<IIIIHHH", data, off + 8)
            if 0 <= name < len(pool) and pool[name] == "manifest":
                p = off + hdr + attr_start          # attributeStart e' relativo alla fine dell'header del chunk
                for _ in range(attr_count):
                    _ans, aname, raw, _tsize, _res0, dtype, value = struct.unpack_from("<IIIHBBI", data, p)
                    key = pool[aname] if 0 <= aname < len(pool) else ""
                    if key == "package":
                        out["package"] = pool[raw] if 0 <= raw < len(pool) else ""
                    elif key == "versionCode" and dtype == TYPE_INT_DEC:
                        out["versionCode"] = value
                    elif key == "versionName":
                        idx = raw if 0 <= raw < len(pool) else value if dtype == TYPE_STRING else -1
                        out["versionName"] = pool[idx] if 0 <= idx < len(pool) else ""
                    p += attr_size or 20
                break
        off += size
    return out


def read(path: str) -> ApkInfo:
    """Dati dell'APK in `path`; se qualcosa non va, `error` lo dice (l'oggetto torna comunque)."""
    info = ApkInfo(path=path)
    try:
        info.size = os.path.getsize(path)
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        info.sha256 = h.hexdigest()
        with zipfile.ZipFile(path) as z:
            m = parse_manifest(z.read("AndroidManifest.xml"))
        info.package = m.get("package", "")
        info.version_name = m.get("versionName", "")
        info.version_code = int(m.get("versionCode", 0) or 0)
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, struct.error) as e:
        info.error = f"{type(e).__name__}: {e}" if not str(e) else str(e)
    return info
