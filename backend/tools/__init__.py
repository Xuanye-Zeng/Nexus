"""Tool functions exposed to the Master Agent.

Each tool is a thin wrapper over existing services/* logic — the agent layer
does not implement business logic, it only routes intents to existing
capabilities. This keeps tools and services testable in isolation.

Adding a tool: define the function in a new module, decorate with
`@register_tool("name")`, and add it to TOOL_DESCRIPTIONS in
master_intent_classifier so the intent classifier learns about it. The
dispatcher in agents/master.py discovers tools by name automatically.
"""
from . import (  # noqa: F401
    customize_resume,
    delete_emails,
    get_top_resume_sections,
    ingest_jobs,
    rescore_listings,
    search_jobs,
    sponsorship,
    triage_emails,
)
from .registry import TOOLS, get_tool, list_tools, register_tool  # noqa: F401

__all__ = [
    "TOOLS",
    "get_tool",
    "list_tools",
    "register_tool",
]
