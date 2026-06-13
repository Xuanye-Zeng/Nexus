"""Decorator-based registry for Master Agent tools.

Each tool is an async callable: `(args: dict) -> Any`. The dispatcher in
agents/master.py looks tools up by name.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

ToolFn = Callable[[dict[str, Any]], Awaitable[Any]]


TOOLS: dict[str, ToolFn] = {}


def register_tool(name: str) -> Callable[[ToolFn], ToolFn]:
    def decorator(fn: ToolFn) -> ToolFn:
        if name in TOOLS:
            raise ValueError(f"tool {name!r} already registered")
        TOOLS[name] = fn
        return fn

    return decorator


def get_tool(name: str) -> ToolFn:
    if name not in TOOLS:
        raise KeyError(f"unknown tool {name!r}. Registered: {sorted(TOOLS)}")
    return TOOLS[name]


def list_tools() -> list[str]:
    return sorted(TOOLS)
