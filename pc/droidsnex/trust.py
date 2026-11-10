"""Elenco delle destinazioni fidate ("trust"), salvato in un file JSON accanto al programma."""
from __future__ import annotations

import json
import os
import threading


class TrustStore:
    """Insieme di destinazioni fidate: domini o indirizzi IP. Persistente su disco."""

    def __init__(self, path: str):
        self.path = path
        self._items: set[str] = set()
        self._lock = threading.Lock()
        try:
            with open(path, encoding="utf-8") as f:
                self._items = {str(x).lower() for x in json.load(f).get("trusted", [])}
        except (OSError, ValueError):
            pass

    def is_trusted(self, label: str, ips=()) -> bool:
        with self._lock:
            return label.lower() in self._items or any(ip in self._items for ip in ips)

    def trust(self, label: str, ips=()) -> None:
        with self._lock:
            self._items.add(label.lower())
            # se la destinazione è solo un IP, lo segniamo anche come IP
            self._items.update(ip for ip in ips if ip == label)
        self._save()

    def untrust(self, label: str, ips=()) -> None:
        with self._lock:
            self._items.discard(label.lower())
            for ip in ips:
                self._items.discard(ip)
        self._save()

    def clear(self) -> int:
        """Toglie tutte le destinazioni fidate. Ritorna quante erano."""
        with self._lock:
            n = len(self._items)
            self._items.clear()
        self._save()
        return n

    def __len__(self) -> int:
        return len(self._items)

    def _save(self) -> None:
        with self._lock:
            data = {"trusted": sorted(self._items)}
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            pass
