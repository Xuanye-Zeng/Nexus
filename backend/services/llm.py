"""LLM provider factory — get the right LLM for a given purpose.

Purpose-driven routing because different M1/M2 tasks have different
volume/quality tradeoffs:

  - sponsorship_classifier  -> HIGH volume (1 call per ingested listing),
                                SIMPLE task (4-class JSON output).
                                Local Ollama qwen2.5:14b: 6s/call steady-state,
                                5/5 fixture pass, NO rate limit. Right pick.

  - bullet_rewriter         -> LOW volume (a few calls per resume customize),
                                HIGH quality (long prompt, must obey strict
                                preservation rules). Groq llama-3.3-70b is
                                noticeably better here; volume fits free tier.

  - jd_keyword_extractor    -> LOW volume (1 call per resume customize), keep
                                Groq for consistency with bullet_rewriter run.

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
        provider="ollama",
        model="qwen2.5:14b",
        temperature=0.0,
    ),
    "bullet_rewriter": LLMProfile(
        provider="groq",
        model=settings.GROQ_MODEL,  # llama-3.3-70b-versatile by default
        temperature=None,
    ),
    "jd_keyword_extractor": LLMProfile(
        provider="groq",
        model=settings.GROQ_MODEL,
        temperature=0.0,
    ),
    "master_intent_classifier": LLMProfile(
        # Intent routing is structured JSON classification — qwen2.5:14b
        # local handles this as well as 70b for the v1 3-tool router,
        # and avoids burning Groq's daily token budget on every user turn.
        provider="ollama",
        model="qwen2.5:14b",
        temperature=0.0,
    ),
    "master_responder": LLMProfile(
        # Natural-language formatter over tool output. Same model as intent
        # for consistency; quality threshold is low here (it's summarizing
        # already-structured data, not generating novel content).
        provider="ollama",
        model="qwen2.5:14b",
        temperature=0.3,
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
