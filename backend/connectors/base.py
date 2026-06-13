"""Abstract base class + registry for job-board connectors.

Every connector ingests from a different upstream (Adzuna API / Greenhouse
public JSON / Lever public JSON / Workday scraper) but emits the same
NormalizedListing shape so the rest of the M2 pipeline (sponsorship
classifier, LCA join, match scoring, UPSERT) is source-agnostic.

Adding a new source:
  1. Write `connectors/<source>.py` with `class FooConnector(JobConnector)`.
  2. Decorate the class with `@register_connector`.
  3. Import the module in `connectors/__init__.py` so the decorator fires.
  4. Done — `scripts/ingest_jobs.py --source foo` will dispatch to it.

This pattern keeps the orchestrator zero-knowledge about source specifics.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar


@dataclass
class NormalizedListing:
    """The canonical row shape every connector emits.

    Mirrors a subset of JobListing model columns — connector-side data only;
    embedding / match_score / sponsorship_* are filled later by the
    enrichment pipeline, not by the connector.
    """
    source: str            # 'adzuna' | 'greenhouse' | 'lever' | 'workday' ...
    source_id: str         # upstream id, unique within source
    source_url: str | None # link to the original posting
    company: str
    title: str
    location: str | None
    description_raw: str | None
    scraped_at: datetime

    def __repr__(self) -> str:
        return (
            f"{self.source}:{self.source_id} company={self.company!r} "
            f"title={self.title!r}"
        )


class JobConnector(ABC):
    """Base class for any job-source connector.

    Concrete connectors set the class variable `source_name` (used for
    registry lookup AND stored on every NormalizedListing.source) and
    implement `fetch()`.
    """

    source_name: ClassVar[str]

    @abstractmethod
    async def fetch(
        self,
        keyword: str | None = None,
        location: str | None = None,
        max_results: int = 50,
    ) -> list[NormalizedListing]:
        """Pull listings matching the (loose) filters.

        Connectors that don't natively support search (Greenhouse / Lever
        fetch all of one company's postings, then we filter post-hoc) should
        still honor `keyword` by case-insensitive title-substring match.
        `location` semantics are connector-defined — Adzuna sends as `where`,
        Greenhouse/Lever filter post-hoc against the JSON's location field.
        """


# ---- registry ----

CONNECTORS: dict[str, type[JobConnector]] = {}


def register_connector(cls: type[JobConnector]) -> type[JobConnector]:
    """Decorator. Adds the connector to the registry keyed by source_name."""
    if not getattr(cls, "source_name", None):
        raise TypeError(f"{cls.__name__} must define class var `source_name`")
    if cls.source_name in CONNECTORS:
        raise ValueError(f"connector {cls.source_name!r} already registered")
    CONNECTORS[cls.source_name] = cls
    return cls


def get_connector(name: str) -> JobConnector:
    """Return a connector instance by source name."""
    if name not in CONNECTORS:
        raise KeyError(
            f"unknown connector {name!r}. Registered: {sorted(CONNECTORS)}"
        )
    return CONNECTORS[name]()


def list_connectors() -> list[str]:
    return sorted(CONNECTORS)
