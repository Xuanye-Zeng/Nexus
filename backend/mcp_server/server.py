"""MCP server exposing the Nexus tool registry to any MCP client.

The LangGraph Master Agent reaches these tools through `tools.get_tool`. This
module puts the same registry behind the Model Context Protocol so an editor or
desktop client (Claude Desktop, Cursor, …) can call them directly, without
going through the agent's intent classifier.

Design notes
------------
**Thin adapters, one source of truth.** Every function below delegates to
`get_tool(name)(args)`. Business logic stays in `tools/`; nothing is
reimplemented here. What this layer adds is a typed signature per tool — the
MCP SDK derives the JSON input schema from it — plus a description and the
annotations a client needs to decide how much to trust a call.

**Read-only by default.** Three registry tools change state: `ingest_jobs`
UPSERTs listings, `rescore_listings` rewrites match scores, and `delete_emails`
soft-deletes rows. An MCP client is driven by a model, and a model that can
call `delete_emails` on a whim is a bad trade for the convenience of not
typing a flag. They register only when NEXUS_MCP_ALLOW_MUTATIONS is truthy,
and they carry the annotations (`destructive_hint`, `idempotent_hint`) that let
a client prompt before running them.
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from tools import get_tool

# Importing the package runs the @register_tool decorators.
import tools  # noqa: F401  isort:skip


MUTATIONS_ENV = "NEXUS_MCP_ALLOW_MUTATIONS"


def mutations_allowed() -> bool:
    return os.getenv(MUTATIONS_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


async def _call(name: str, **kwargs: Any) -> str:
    """Dispatch into the registry, dropping unset optional args.

    Tools read their inputs with `args.get(...)` and apply their own defaults,
    so forwarding an explicit None would override a default the tool meant to
    control. Result is JSON-encoded because MCP tool results are text.
    """
    args = {k: v for k, v in kwargs.items() if v is not None}
    result = await get_tool(name)(args)
    return json.dumps(result, indent=2, default=str)


# ── read-only tools ──────────────────────────────────────────────────────────


async def search_jobs(
    keyword: str | None = None,
    location: str | None = None,
    company: str | None = None,
    source: str | None = None,
    sponsors_only: bool = False,
    min_score: float | None = None,
    min_confidence: float | None = None,
    limit: int = 10,
) -> str:
    """Search stored job listings with filters and ranking.

    Listings explicitly marked no_sponsorship or us_citizen_only are hidden by
    default; pass sponsors_only=true to keep only confirmed sponsors.
    """
    return await _call(
        "search_jobs",
        keyword=keyword,
        location=location,
        company=company,
        source=source,
        sponsors_only=sponsors_only,
        min_score=min_score,
        min_confidence=min_confidence,
        limit=limit,
    )


async def triage_emails(
    category: str | None = None,
    min_importance: int | None = None,
    sender: str | None = None,
    unread_only: bool = False,
    include_deleted: bool = False,
    limit: int = 20,
) -> str:
    """List triaged emails filtered by category, importance, or sender."""
    return await _call(
        "triage_emails",
        category=category,
        min_importance=min_importance,
        sender=sender,
        unread_only=unread_only,
        include_deleted=include_deleted,
        limit=limit,
    )


async def classify_sponsorship_for_jd(jd_text: str, company: str | None = None) -> str:
    """Classify a job description's visa-sponsorship stance.

    Returns status, a verbatim evidence quote from the JD, a CPT/OPT signal and
    a confidence score. Evidence is quoted from the input rather than
    paraphrased, so an empty evidence string means the JD said nothing.
    """
    return await _call("classify_sponsorship_for_jd", jd_text=jd_text, company=company)


async def get_top_resume_sections_for_jd(jd_text: str, k: int = 8) -> str:
    """Retrieve the k resume sections most relevant to a job description,
    ranked by pgvector cosine distance over section embeddings."""
    return await _call("get_top_resume_sections_for_jd", jd_text=jd_text, k=k)


async def customize_resume(jd_text: str, top_k: int | None = None) -> str:
    """Draft a resume tailored to a job description from stored profile sections."""
    return await _call("customize_resume", jd_text=jd_text, top_k=top_k)


# ── state-changing tools (registered only when explicitly allowed) ───────────


async def ingest_jobs(
    source: str,
    keyword: str | None = None,
    location: str | None = None,
    max: int = 15,
) -> str:
    """Pull fresh listings from a connector and upsert them.

    `source` is one of adzuna, greenhouse, lever, workday. Calls the upstream
    job board, so results depend on an external service.
    """
    return await _call(
        "ingest_jobs", source=source, keyword=keyword, location=location, max=max
    )


async def rescore_listings() -> str:
    """Recompute match_score for every stored listing against the active
    profile. Idempotent — safe to re-run after a resume edit."""
    return await _call("rescore_listings")


async def delete_emails(
    category: str | None = None,
    sender: str | None = None,
    email_id: str | None = None,
    max_importance: int | None = None,
) -> str:
    """Delete emails matching a filter. Destructive and not reversible from
    here — prefer triage_emails first to confirm what the filter selects."""
    return await _call(
        "delete_emails",
        category=category,
        sender=sender,
        email_id=email_id,
        max_importance=max_importance,
    )


READ_ONLY_TOOLS = [
    (search_jobs, ToolAnnotations(read_only_hint=True, idempotent_hint=True)),
    (triage_emails, ToolAnnotations(read_only_hint=True, idempotent_hint=True)),
    (
        classify_sponsorship_for_jd,
        ToolAnnotations(read_only_hint=True, open_world_hint=True),
    ),
    (get_top_resume_sections_for_jd, ToolAnnotations(read_only_hint=True, idempotent_hint=True)),
    (customize_resume, ToolAnnotations(read_only_hint=True, open_world_hint=True)),
]

MUTATING_TOOLS = [
    (
        ingest_jobs,
        ToolAnnotations(read_only_hint=False, idempotent_hint=True, open_world_hint=True),
    ),
    (rescore_listings, ToolAnnotations(read_only_hint=False, idempotent_hint=True)),
    (
        delete_emails,
        ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False),
    ),
]


def build_server() -> MCPServer:
    """Assemble the server. Kept separate from run() so tests can introspect
    the registered tool set without starting a transport."""
    server = MCPServer(
        name="nexus",
        instructions=(
            "Tools over a personal job-search database: search stored listings, "
            "check a job description's sponsorship stance, retrieve resume "
            "sections relevant to a JD, and triage email. Sponsorship verdicts "
            "quote the JD verbatim — treat an empty evidence field as 'the "
            "posting did not say', not as a denial."
        ),
    )

    for fn, hints in READ_ONLY_TOOLS:
        server.add_tool(fn, annotations=hints)

    if mutations_allowed():
        for fn, hints in MUTATING_TOOLS:
            server.add_tool(fn, annotations=hints)

    return server


def main() -> None:
    build_server().run(transport="stdio")


if __name__ == "__main__":
    main()
