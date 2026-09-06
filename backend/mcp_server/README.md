# Nexus MCP server

Exposes the tool registry in `tools/` over the Model Context Protocol, so an
MCP client (Claude Desktop, Cursor, …) can query the job-search database
directly instead of going through the Master Agent's intent classifier.

## Run

```bash
venv/bin/python -m mcp_server            # read-only (default)
NEXUS_MCP_ALLOW_MUTATIONS=1 venv/bin/python -m mcp_server
```

Transport is stdio. The server needs the same environment the API does — it
opens its own `SessionLocal` through the tools.

## Client config

```json
{
  "mcpServers": {
    "nexus": {
      "command": "/absolute/path/to/backend/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/absolute/path/to/backend"
    }
  }
}
```

## Tools

Read-only, always registered:

| Tool | Purpose |
|---|---|
| `search_jobs` | filter and rank stored listings |
| `triage_emails` | list triaged email by category / importance / sender |
| `classify_sponsorship_for_jd` | sponsorship stance for a JD, with a verbatim evidence quote |
| `get_top_resume_sections_for_jd` | pgvector cosine top-k over resume sections |
| `customize_resume` | draft a JD-tailored resume from stored sections |

State-changing, registered only under `NEXUS_MCP_ALLOW_MUTATIONS`:

| Tool | Annotation | Why gated |
|---|---|---|
| `ingest_jobs` | idempotent, open-world | upserts listings, calls an external job board |
| `rescore_listings` | idempotent | rewrites `match_score` on every row |
| `delete_emails` | **destructive** | soft-deletes rows; not reversible from here |

## Why the default is read-only

An MCP client is driven by a model. Registering `delete_emails` unconditionally
means a misread instruction can delete rows, and the convenience saved is one
environment variable. The gate is coarse on purpose — a model cannot talk its
way past a tool that was never registered.

Annotations are the second layer: `destructive_hint` and `idempotent_hint` tell
a client whether to confirm before calling. They are asserted in
`tests/test_mcp_server.py`, because a wrong annotation is worse than a missing
tool — it tells the client to skip a confirmation it should have shown.

## Drift

`test_every_exposed_tool_exists_in_the_registry` fails if an adapter here points
at a tool that was renamed or removed in `tools/`. The adapters are thin enough
to rot silently otherwise: a stale wrapper keeps advertising the old name over
MCP and only breaks when a client actually calls it.
