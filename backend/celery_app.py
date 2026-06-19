"""Celery instance + 6-hour beat schedule for auto-ingest.

Run from backend/:
    venv/bin/celery -A celery_app worker --loglevel=info    # the worker
    venv/bin/celery -A celery_app beat   --loglevel=info    # the scheduler
    venv/bin/celery -A celery_app worker --beat -l info     # both in one process (dev)

Tasks live in `tasks.py`; they wrap the same async pipeline `scripts/ingest_jobs`
uses, so a manual CLI run and a Celery-triggered run hit the exact same code
path (and the same DB UPSERT idempotency).
"""
import sys
from pathlib import Path

# Ensure `backend/` is on sys.path so forked worker processes can import
# `scripts.*`, `services.*`, `models.*`, etc. Without this, celery's
# ForkPoolWorker children don't inherit CWD on the path and tasks ImportError.
_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from celery import Celery
from celery.schedules import crontab

from config import settings

celery_app = Celery(
    "nexus",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    # Workday descriptions are 5-10KB each and the pipeline does an LLM call
    # per listing, so each ingest task can take 2-4 minutes. Give it room.
    task_time_limit=900,            # hard 15 min
    task_soft_time_limit=720,       # soft 12 min
    task_acks_late=True,
    worker_prefetch_multiplier=1,   # one task at a time per worker
)

# Each connector gets its own slot in the hour so the LLM (Groq + local
# Ollama) isn't fighting itself, and DB UPSERT contention stays low.
# Schedule is in UTC.
celery_app.conf.beat_schedule = {
    "ingest-adzuna-6h": {
        "task": "tasks.ingest_source",
        "schedule": crontab(minute=0, hour="*/6"),
        "args": ("adzuna", "software engineer", None, 15),
    },
    "ingest-greenhouse-6h": {
        "task": "tasks.ingest_source",
        "schedule": crontab(minute=15, hour="*/6"),
        "args": ("greenhouse", "engineer", None, 25),
    },
    "ingest-lever-6h": {
        "task": "tasks.ingest_source",
        "schedule": crontab(minute=30, hour="*/6"),
        "args": ("lever", "engineer", None, 20),
    },
    "ingest-workday-6h": {
        "task": "tasks.ingest_source",
        "schedule": crontab(minute=45, hour="*/6"),
        "args": ("workday", "software engineer", None, 25),
    },
}
