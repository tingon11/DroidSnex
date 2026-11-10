#!/usr/bin/env python3
"""
Genera droidsnex/gui/assets/vector-50m.json.gz: la mappa vettoriale inclusa nel programma.

Fonte: Natural Earth 1:50m (pubblico dominio), GeoJSON da
https://github.com/nvkelso/natural-earth-vector/tree/master/geojson
Scarica in una cartella i file elencati in droidsnex.vector.LAYER_FILES (con s=50m), poi:
    python tools/make_vector.py <cartella>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from droidsnex.vector import LAYER_FILES, convert  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "droidsnex", "gui", "assets", "vector-50m.json.gz")

if __name__ == "__main__":
    src = sys.argv[1]
    convert({k: os.path.join(src, v.format(s="50m") + ".geojson") for k, v in LAYER_FILES.items()}, OUT, q=100, cell=10)
    print(OUT, os.path.getsize(OUT) // 1024, "KB")
