import os
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from connectors import list_connectors
from routers import agent, customize_resume, emails, jobs, overview
from services.llm import LLM_PROFILES

app = FastAPI(title="Nexus API", version="1.4.0")

# Permissive CORS for local dev — the frontend runs on Vite's 5173 by default.
# Lock this down (specific origins) before any production deploy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customize_resume.router)
app.include_router(agent.router)
app.include_router(jobs.router)
app.include_router(emails.router)
app.include_router(overview.router)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Lightweight introspection — handy for debugging and for the portfolio
    walkthrough ("here's the full LLM routing table that's actually live")."""
    return {
        "status": "ok",
        "version": app.version,
        "embedding_model": settings.EMBEDDING_MODEL,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "llm_profiles": {
            purpose: {
                "provider": profile.provider,
                "model": profile.model,
                "temperature": profile.temperature,
            }
            for purpose, profile in LLM_PROFILES.items()
        },
        "connectors": list_connectors(),
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING") == "true",
    }
