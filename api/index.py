import sys
import os

# Make project root and web/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "web"))

from web.app import app  # noqa: F401 — Vercel uses this as the WSGI handler

# Vercel expects the WSGI callable to be named `app`
