"""Pytest config — adds backend/ to sys.path so tests can import service
modules as `from services.X import Y` without an editable install. Mirrors
what celery_app.py / tasks.py do for the same reason.
"""
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
