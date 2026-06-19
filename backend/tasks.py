"""Celery task definitions for Nexus background work.

Tasks are thin wrappers over the same async pipeline `scripts/ingest_jobs`
uses — they convert Celery's sync invocation to an asyncio event loop and
return a small JSON-safe summary.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

# Ensure `backend/` is on sys.path inside worker subprocesses. macOS Python
# uses spawn (not fork) for multiprocessing on 3.13+, so a sys.path mutation
# in celery_app.py doesn't propagate to the worker process. Each task module
# has to add it again at import time.
_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from celery_app import celery_app
from scripts.ingest_jobs import main as ingest_main  # eager import to surface path issues at worker boot

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.ingest_source", bind=True)
def ingest_source(
    self,                       # noqa: ANN001 — celery binds the task instance
    source: str,
    keyword: str | None = None,
    location: str | None = None,
    max_results: int = 20,
) -> dict[str, Any]:
    """Run one full ingest cycle for a single connector.

    Args mirror `scripts/ingest_jobs.main()`. Returns a small status dict
    (committed counts + status / match-layer breakdowns) so the Celery
    result backend keeps something human-readable.
    """
    logger.info(
        "ingest_source start id=%s source=%s keyword=%s loc=%s max=%d",
        self.request.id, source, keyword, location, max_results,
    )

    exit_code = asyncio.run(
        ingest_main(
            source=source,
            keyword=keyword,
            location=location,
            max_results=max_results,
            dry_run=False,
        )
    )

    return {
        "source": source,
        "keyword": keyword,
        "location": location,
        "max_results": max_results,
        "exit_code": int(exit_code or 0),
        "task_id": self.request.id,
    }
