from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from routers import agent, customize_resume, emails, jobs, overview

app = FastAPI(title="Nexus API", version="1.1.0")

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
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llm_model": settings.GROQ_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
    }
