"""LLM provider factory — get the right LLM for a given purpose.

Purpose-driven routing because different M1/M2 tasks have different
volume/quality tradeoffs.

CURRENT ROUTING (all-cloud after 2026-09-02):
  Every task points at Groq. Rationale: qwen2.5:14b in Ollama holds
  ~10 GB resident on the M4 Air 24 GB — memory pressure went amber
  with 10 GB of swap active. Groq is ~50× faster (500+ tokens/sec vs
  ~10 t/s on-device) so batch ingest finishes in seconds instead of
  minutes, and volume comfortably fits the free tier. This is exactly
  the swap `LLM_PROFILES` was designed for: the four ex-Ollama tasks
  are four one-line edits, zero call-site changes.

  If Groq daily budget ever bites: `provider="ollama"` + `model=
  "qwen2.5:3b"` (2-3 GB resident, 4/5 fixture pass — the intern_cpt
  case is the known miss) is the drop-in fallback per task.

Adding a new task: add an entry to LLM_PROFILES, then call get_llm("your_task").
Switching a task's backend: edit one line in LLM_PROFILES (or set the
corresponding env var). No code changes in the calling sites.
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from config import settings


@dataclass(frozen=True)
class LLMProfile:
    provider: str   # 'groq' | 'ollama'
    model: str
    # Temperature defaults: 0 for classification/extraction (deterministic),
    # leave None for rewriting (let model pick).
    temperature: float | None = 0.0


# Purpose -> LLMProfile. Edit here to swap backends.
LLM_PROFILES: dict[str, LLMProfile] = {
    "sponsorship_classifier": LLMProfile(
        # HIGH volume (one call per ingested listing), simple 4-class JSON.
        # Moved off Ollama 2026-09-02 to free ~10 GB local RAM — Groq's
        # 500+ t/s throughput takes batch ingest from minutes to seconds.
        provider="groq",
        model=settings.GROQ_MODEL,
        temperature=0.0,
    ),
    "bullet_rewriter": LLMProfile(
        # LOW volume (a few calls per resume customize), HIGH quality —
        # long preservation-rule prompt where a 70b model is noticeably
        # better than 14b at obeying the number-preservation invariant.
        provider="groq",
        model=settings.GROQ_MODEL,
        temperature=None,
    ),
    "jd_keyword_extractor": LLMProfile(
        # LOW volume — chained with bullet_rewriter on the same JD.
        provider="groq",
        model=settings.GROQ_MODEL,
        temperature=0.0,
    ),
    "master_intent_classifier": LLMProfile(
        # Structured JSON routing; runs on every user agent turn. Groq
        # is fast enough that latency perceptibly improves vs local.
        provider="groq",
        model=settings.GROQ_MODEL,
        temperature=0.0,
    ),
    "master_responder": LLMProfile(
        # Natural-language formatter over tool output. Slight T so the
        # phrasing isn't robotic; quality threshold is low (summarizing
        # already-structured data, not generating novel content).
        provider="groq",
        model=settings.GROQ_MODEL,
        temperature=0.3,
    ),
    "email_classifier": LLMProfile(
        # 8-class JSON classification with importance 1-5.
        provider="groq",
        model=settings.GROQ_MODEL,
        temperature=0.0,
    ),
}


def get_llm(purpose: str) -> BaseChatModel:
    """Return a chat-model client for the named purpose.

    Raises KeyError if `purpose` is not registered in LLM_PROFILES.
    """
    profile = LLM_PROFILES.get(purpose)
    if profile is None:
        raise KeyError(
            f"no LLM profile for purpose={purpose!r}. "
            f"Registered: {sorted(LLM_PROFILES)}"
        )

    if profile.provider == "groq":
        kwargs = {
            "model": profile.model,
            "api_key": settings.GROQ_API_KEY.get_secret_value(),
        }
        if profile.temperature is not None:
            kwargs["temperature"] = profile.temperature
        return ChatGroq(**kwargs)

    if profile.provider == "ollama":
        kwargs = {
            "model": profile.model,
            "base_url": settings.OLLAMA_BASE_URL,
        }
        if profile.temperature is not None:
            kwargs["temperature"] = profile.temperature
        return ChatOllama(**kwargs)

    raise ValueError(f"unknown provider {profile.provider!r}")


def describe_profile(purpose: str) -> str:
    """Single-line human-readable description, for logging."""
    p = LLM_PROFILES.get(purpose)
    if p is None:
        return f"purpose={purpose!r} UNREGISTERED"
    return f"{p.provider}/{p.model} (T={p.temperature})"
