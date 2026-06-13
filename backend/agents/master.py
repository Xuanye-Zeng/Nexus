"""Master Agent — LangGraph StateGraph orchestrating Nexus's tools.

Topology:

  START
    -> classify_intent  (LLM: master_intent_classifier)
    -> route            (conditional edge keyed on intent)
        -> search_jobs           (tool node, queries DB)
        -> customize_resume      (tool node, chains JD extractor + RAG + rewriter)
        -> classify_sponsorship  (tool node, JD-only sponsorship verdict)
        -> clarify               (no tool — propagates classifier's question)
    -> respond          (LLM: master_responder, turns tool output into NL)
  END

State carries the original user message, the classified intent, the raw
tool result, and the final response. Each pass is one user turn —
multi-turn conversation memory would live in the calling layer (the
CLI runner / FastAPI route), not in the graph itself.

Adding a new intent:
  1. Add the tool fn in tools/<name>.py with @register_tool("name").
  2. Add the routing rule + a TOOL_NODE entry below.
  3. Update the master_intent_classifier prompt so the LLM knows it exists.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select

from db import SessionLocal
from models import PromptTemplate
from services.llm import get_llm
from tools import get_tool


class AgentState(TypedDict, total=False):
    user_message: str
    intent: str               # 'search_jobs' | 'customize_resume' | 'classify_sponsorship_for_jd' | 'clarify'
    tool_args: dict[str, Any]
    tool_result: Any
    clarify_question: str
    response: str
    classifier_raw: str       # debug — raw LLM output
    classifier_reasoning: str
    error: str


VALID_TOOL_INTENTS = {
    "search_jobs",
    "customize_resume",
    "classify_sponsorship_for_jd",
}


# ---------- helpers ----------


async def _active_prompt(name: str) -> str:
    async with SessionLocal() as s:
        row = (
            await s.execute(
                select(PromptTemplate)
                .where(
                    PromptTemplate.name == name,
                    PromptTemplate.is_active.is_(True),
                )
                .order_by(PromptTemplate.version.desc())
                .limit(1)
            )
        ).scalar_one()
        return row.content


def _parse_intent_json(raw: str) -> dict:
    """Tolerant JSON extraction from the intent classifier output."""
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    if not s.startswith("{"):
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if m:
            s = m.group(0)
    return json.loads(s)


# ---------- nodes ----------


async def classify_intent_node(state: AgentState) -> AgentState:
    prompt = await _active_prompt("master_intent_classifier")
    llm = get_llm("master_intent_classifier")
    resp = llm.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=state["user_message"]),
        ]
    )
    raw = resp.content

    try:
        parsed = _parse_intent_json(raw)
    except json.JSONDecodeError as e:
        return {
            **state,
            "intent": "clarify",
            "clarify_question": (
                "I had trouble parsing your request. Could you rephrase — "
                "are you searching for jobs, customizing your resume to a JD, "
                "or checking sponsorship for a JD?"
            ),
            "classifier_raw": raw,
            "classifier_reasoning": f"json parse error: {e}",
        }

    intent = parsed.get("intent", "clarify")
    reasoning = parsed.get("reasoning", "")

    if intent == "clarify":
        return {
            **state,
            "intent": "clarify",
            "clarify_question": parsed.get("question", "Could you say more about what you want?"),
            "classifier_raw": raw,
            "classifier_reasoning": reasoning,
        }

    if intent not in VALID_TOOL_INTENTS:
        return {
            **state,
            "intent": "clarify",
            "clarify_question": (
                f"The model picked an unknown intent {intent!r}. "
                "Available: search_jobs / customize_resume / classify_sponsorship_for_jd."
            ),
            "classifier_raw": raw,
            "classifier_reasoning": reasoning,
        }

    return {
        **state,
        "intent": intent,
        "tool_args": parsed.get("args", {}) or {},
        "classifier_raw": raw,
        "classifier_reasoning": reasoning,
    }


async def _run_tool(state: AgentState, tool_name: str) -> AgentState:
    try:
        tool_fn = get_tool(tool_name)
        result = await tool_fn(state.get("tool_args") or {})
        return {**state, "tool_result": result}
    except Exception as e:  # surface tool errors instead of crashing the graph
        return {**state, "error": f"{tool_name} failed: {type(e).__name__}: {e}"}


async def search_jobs_node(state: AgentState) -> AgentState:
    return await _run_tool(state, "search_jobs")


async def customize_resume_node(state: AgentState) -> AgentState:
    return await _run_tool(state, "customize_resume")


async def classify_sponsorship_node(state: AgentState) -> AgentState:
    return await _run_tool(state, "classify_sponsorship_for_jd")


async def clarify_node(state: AgentState) -> AgentState:
    # No tool call — clarification text already on state.
    return state


async def respond_node(state: AgentState) -> AgentState:
    """Format the final user-facing response.

    Strategy:
      - clarify intent → echo the clarification question verbatim.
      - tool error → state the error plainly.
      - tool success → LLM formats the structured result into natural language.
    """
    if state.get("error"):
        return {**state, "response": f"❌ {state['error']}"}

    if state.get("intent") == "clarify":
        return {**state, "response": state.get("clarify_question", "Could you say more?")}

    tool_result = state.get("tool_result")
    if tool_result is None:
        return {**state, "response": "(no tool result)"}

    # For very compact results we don't need an LLM round-trip — render directly.
    if state["intent"] == "search_jobs" and isinstance(tool_result, dict):
        listings = tool_result.get("listings", [])
        if not listings:
            return {**state, "response": "No listings matched. Try widening filters or `ingest_jobs` first."}

    # Otherwise, let the LLM compose a tight summary.
    llm = get_llm("master_responder")
    system = (
        "You are summarizing a tool result for an international-student job-seeker. "
        "Be concise — at most 8 sentences. Lead with the most actionable fact "
        "(rank-1 job, sponsorship verdict, etc). When citing a job, include "
        "company + title + match_score and sponsorship status. Do not fabricate "
        "values beyond what is in the tool output. For customize_resume, give a "
        "1-line summary plus a hint that the full rewrite is in tool_result. "
        "Output plain markdown, no code fences around the whole reply."
    )
    user = (
        f"User asked: {state['user_message']!r}\n\n"
        f"Tool ({state['intent']}) result (JSON):\n"
        f"{json.dumps(tool_result, default=str, ensure_ascii=False)[:6000]}"
    )
    resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return {**state, "response": resp.content}


# ---------- routing ----------


def _route_after_intent(state: AgentState) -> str:
    intent = state.get("intent", "clarify")
    return {
        "search_jobs": "search_jobs_node",
        "customize_resume": "customize_resume_node",
        "classify_sponsorship_for_jd": "classify_sponsorship_node",
        "clarify": "clarify_node",
    }.get(intent, "clarify_node")


# ---------- graph construction (cached) ----------


_GRAPH = None


def _build_graph():
    global _GRAPH
    if _GRAPH is not None:
        return _GRAPH

    g = StateGraph(AgentState)
    g.add_node("classify_intent", classify_intent_node)
    g.add_node("search_jobs_node", search_jobs_node)
    g.add_node("customize_resume_node", customize_resume_node)
    g.add_node("classify_sponsorship_node", classify_sponsorship_node)
    g.add_node("clarify_node", clarify_node)
    g.add_node("respond", respond_node)

    g.add_edge(START, "classify_intent")
    g.add_conditional_edges(
        "classify_intent",
        _route_after_intent,
        {
            "search_jobs_node": "search_jobs_node",
            "customize_resume_node": "customize_resume_node",
            "classify_sponsorship_node": "classify_sponsorship_node",
            "clarify_node": "clarify_node",
        },
    )
    g.add_edge("search_jobs_node", "respond")
    g.add_edge("customize_resume_node", "respond")
    g.add_edge("classify_sponsorship_node", "respond")
    g.add_edge("clarify_node", "respond")
    g.add_edge("respond", END)

    _GRAPH = g.compile()
    return _GRAPH


# ---------- public API ----------


@dataclass
class MasterAgentResult:
    response: str
    intent: str
    tool_args: dict[str, Any] = field(default_factory=dict)
    tool_result: Any = None
    classifier_reasoning: str = ""
    error: str = ""


async def run_master_agent(user_message: str) -> MasterAgentResult:
    """Run one full turn through the StateGraph.

    Returns a flat dataclass so the CLI / FastAPI route don't need to know
    about LangGraph state shape.
    """
    graph = _build_graph()
    final: AgentState = await graph.ainvoke({"user_message": user_message})
    return MasterAgentResult(
        response=final.get("response", ""),
        intent=final.get("intent", ""),
        tool_args=final.get("tool_args") or {},
        tool_result=final.get("tool_result"),
        classifier_reasoning=final.get("classifier_reasoning", ""),
        error=final.get("error", ""),
    )
