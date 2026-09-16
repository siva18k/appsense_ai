from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Sequence

import chromadb
import httpx

from .settings import get_settings

LOCAL_EMBED_PREFIXES = ("all-minilm", "all-mpnet", "paraphrase-", "multi-qa-")


def kb_collection() -> str:
    return _collection_name("knowledge")


def code_collection() -> str:
    return _collection_name("codebase")


def skills_collection() -> str:
    return _collection_name("skills")


def _collection_name(base: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "", get_settings().embedding_model.lower())[:32]
    return f"{base}_{slug or 'default'}"


def _use_api_embeddings() -> bool:
    model = (get_settings().embedding_model or "").lower()
    return not any(model.startswith(p) for p in LOCAL_EMBED_PREFIXES)


class STEmbeddingFunction:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self._model = SentenceTransformer(model_name)

    def name(self) -> str:
        return f"st:{self.model_name}"

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(list(input), show_progress_bar=False)
        return [v.tolist() for v in vectors]


class ApiEmbeddingFunction:
    """OpenAI-compatible embeddings (Mistral, OpenAI, etc.) using the LLM API key."""

    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def name(self) -> str:
        return f"api:{self.model}"

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        return self._embed(list(input))

    def embed_documents(self, input: Sequence[str]) -> list[list[float]]:
        return self._embed(list(input))

    def embed_query(self, input: Sequence[str]) -> list[list[float]]:
        return self._embed(list(input))

    def _embed(self, texts: list[str]) -> list[list[float]]:
        texts = [t if t.strip() else " " for t in texts]
        vectors: list[list[float]] = []
        batch = 16
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/embeddings"
        with httpx.Client(timeout=60.0) as client:
            for i in range(0, len(texts), batch):
                chunk = texts[i : i + batch]
                resp = client.post(
                    url,
                    headers=headers,
                    json={"model": self.model, "input": chunk},
                )
                resp.raise_for_status()
                data = resp.json().get("data") or []
                data = sorted(data, key=lambda row: row.get("index", 0))
                vectors.extend(row["embedding"] for row in data)
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding API returned an unexpected number of vectors")
        return vectors


@lru_cache(maxsize=4)
def _local_embedding_fn(model_name: str):
    try:
        return STEmbeddingFunction(model_name)
    except ImportError:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        return DefaultEmbeddingFunction()


def get_embedding_fn():
    settings = get_settings()
    if _use_api_embeddings():
        if not settings.llm_api_key:
            raise RuntimeError("LLM_API_KEY is required for API embeddings (e.g. mistral-embed)")
        return ApiEmbeddingFunction(
            settings.llm_base_url, settings.llm_api_key, settings.embedding_model
        )
    return _local_embedding_fn(settings.embedding_model)


def chroma_client() -> chromadb.PersistentClient:
    path = str(get_settings().chroma_path)
    return chromadb.PersistentClient(path=path)


def get_collection(name: str):
    return chroma_client().get_or_create_collection(
        name=name,
        embedding_function=get_embedding_fn(),
        metadata={"hnsw:space": "cosine"},
    )


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 140) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(n, start + chunk_size)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(" "))
            if cut > chunk_size * 0.4:
                end = start + cut
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        start = max(0, end - overlap)
    return chunks


def upsert_chunks(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict[str, Any]],
) -> None:
    if not ids:
        return
    col = get_collection(collection_name)
    batch = 32
    for i in range(0, len(ids), batch):
        col.upsert(
            ids=ids[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )


def delete_by_metadata(collection_name: str, where: dict[str, Any]) -> None:
    col = get_collection(collection_name)
    try:
        col.delete(where=where)
    except Exception:
        pass


def query_project(
    collection_name: str,
    project_id: str,
    query: str,
    n_results: int = 6,
    extra_where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    col = get_collection(collection_name)
    where: dict[str, Any] = {"project_id": project_id}
    if extra_where:
        where = {"$and": [where, extra_where]}
    try:
        result = col.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []
    docs = (result.get("documents") or [[]])[0]
    metas = (result.get("metadatas") or [[]])[0]
    dists = (result.get("distances") or [[]])[0]
    ids = (result.get("ids") or [[]])[0]
    out = []
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        out.append(
            {
                "id": ids[i] if i < len(ids) else "",
                "text": doc,
                "metadata": meta,
                "distance": dists[i] if i < len(dists) else None,
            }
        )
    return out
