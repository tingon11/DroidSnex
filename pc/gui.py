#!/usr/bin/env python3
"""Avvio dell'interfaccia grafica:  python gui.py   (oppure: python gui.py --demo 127.0.0.1:8899)"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if len(sys.argv) > 1 and sys.argv[1] == "--guard":
    # guardiano (droidsnex/guard.py) lanciato dall'eseguibile impacchettato: pulisce il telefono se la GUI crasha
    from droidsnex.guard import main as guard_main  # noqa: E402
    raise SystemExit(guard_main(sys.argv[2:]))
try:
    from droidsnex.gui import main  # noqa: E402
except ImportError as e:
    sys.exit(f"Manca una dipendenza della GUI ({e.name}). Installa con:  pip install -r requirements-gui.txt")

raise SystemExit(main())
