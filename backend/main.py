from fastapi import FastAPI

from config import settings
from routers import customize_resume

app = FastAPI(title="Nexus API", version="0.5.0")
app.include_router(customize_resume.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "llm_model": settings.GROQ_MODEL,
        "embedding_model": settings.EMBEDDING_MODEL,
    }
