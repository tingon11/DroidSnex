#!/usr/bin/env python3
"""Avvio rapido senza installazione: python run.py [comando] [opzioni]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from droidsnex.cli import main  # noqa: E402

raise SystemExit(main())
