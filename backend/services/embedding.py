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
