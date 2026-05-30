from fastapi import FastAPI

from config import settings

app = FastAPI(title="Nexus API", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "ollama_model": settings.OLLAMA_MODEL,
    }
