"""Gate the MCP adapter layer.

The adapters in mcp_server/ are thin, which is exactly why they can rot
quietly: a tool renamed in tools/ leaves a wrapper that still advertises the
old name over MCP and only fails when a client calls it. These tests pin the
two things the layer is responsible for — the names it forwards to, and the
read-only-by-default policy.
"""
from __future__ import annotations

import json

import pytest

from mcp_server import server as mcp_srv
from tools import list_tools

READ_ONLY_NAMES = {
    "search_jobs",
    "triage_emails",
    "classify_sponsorship_for_jd",
    "get_top_resume_sections_for_jd",
    "customize_resume",
}
MUTATING_NAMES = {"ingest_jobs", "rescore_listings", "delete_emails"}


@pytest.fixture
def no_mutations(monkeypatch):
    monkeypatch.delenv(mcp_srv.MUTATIONS_ENV, raising=False)


@pytest.fixture
def with_mutations(monkeypatch):
    monkeypatch.setenv(mcp_srv.MUTATIONS_ENV, "1")


async def _tool_names(server) -> set[str]:
    return {t.name for t in await server.list_tools()}


@pytest.mark.anyio
async def test_read_only_by_default(no_mutations):
    names = await _tool_names(mcp_srv.build_server())
    assert names == READ_ONLY_NAMES
    assert not (names & MUTATING_NAMES), "mutating tools must not register by default"


@pytest.mark.anyio
async def test_mutations_opt_in(with_mutations):
    names = await _tool_names(mcp_srv.build_server())
    assert names == READ_ONLY_NAMES | MUTATING_NAMES


@pytest.mark.anyio
async def test_delete_is_annotated_destructive(with_mutations):
    """Clients decide whether to confirm based on these hints, so a wrong
    annotation is worse than a missing tool."""
    tools = {t.name: t for t in await mcp_srv.build_server().list_tools()}
    assert tools["delete_emails"].annotations.destructive_hint is True
    assert tools["search_jobs"].annotations.read_only_hint is True


@pytest.mark.anyio
async def test_every_exposed_tool_exists_in_the_registry(with_mutations):
    """Catches an adapter left pointing at a renamed or deleted tool."""
    registered = set(list_tools())
    for name in await _tool_names(mcp_srv.build_server()):
        assert name in registered, f"{name} is exposed over MCP but not registered"


@pytest.mark.anyio
async def test_call_omits_unset_args(monkeypatch):
    """Tools apply their own defaults via args.get(...), so forwarding an
    explicit None would override the default the tool meant to control."""
    seen: dict = {}

    async def fake_tool(args):
        seen.update(args)
        return {"ok": True}

    monkeypatch.setattr(mcp_srv, "get_tool", lambda name: fake_tool)

    out = await mcp_srv._call("search_jobs", keyword="ml", location=None, limit=5)

    assert seen == {"keyword": "ml", "limit": 5}
    assert "location" not in seen
    assert json.loads(out) == {"ok": True}
