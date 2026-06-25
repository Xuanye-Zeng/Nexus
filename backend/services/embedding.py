"""Embedding helper — nomic-embed-text via Ollama, 768d.

`embed_text` / `embed_documents` are the sync API kept for places that
genuinely run sync (scripts, batch tools).

`aembed_text` / `aembed_documents` wrap them in `asyncio.to_thread` so async
call sites (FastAPI routes, the M2 ingest pipeline, the M5 master agent
tools) don't block the event loop while Ollama is computing. Ollama's HTTP
call is the slow part (~30-50ms per embedding) — without to_thread, async
handlers serialize and the dashboard `top_jobs` fan-out gets bottlenecked.
"""
import asyncio

from langchain_ollama import OllamaEmbeddings

from config import settings

EMBEDDING_DIM = 768

_embeddings = OllamaEmbeddings(
    model=settings.EMBEDDING_MODEL,
    base_url=settings.OLLAMA_BASE_URL,
)


def embed_text(text: str) -> list[float]:
    return _embeddings.embed_query(text)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _embeddings.embed_documents(texts)


async def aembed_text(text: str) -> list[float]:
    """Non-blocking variant for async call sites."""
    return await asyncio.to_thread(_embeddings.embed_query, text)


async def aembed_documents(texts: list[str]) -> list[list[float]]:
    return await asyncio.to_thread(_embeddings.embed_documents, texts)
