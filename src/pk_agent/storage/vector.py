from __future__ import annotations

import threading
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings


class VectorStore:
    """Chroma persistent collection for screen context chunks (thread-safe wrapper)."""

    def __init__(self, persist_path: Path, collection_name: str = "screen_kb") -> None:
        persist_path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(self, *, doc_id: str, text: str, metadata: dict) -> None:
        with self._lock:
            self._col.add(
                ids=[doc_id],
                documents=[text],
                metadatas=[_sanitize_meta(metadata)],
            )

    def query(self, query_text: str, k: int) -> list[dict]:
        with self._lock:
            res = self._col.query(
                query_texts=[query_text],
                n_results=max(1, k),
                include=["documents", "metadatas", "distances"],
            )
        out: list[dict] = []
        ids = res.get("ids") or [[]]
        docs = res.get("documents") or [[]]
        metas = res.get("metadatas") or [[]]
        dists = res.get("distances") or [[]]
        if not ids or not ids[0]:
            return out
        for i, did in enumerate(ids[0]):
            out.append(
                {
                    "id": did,
                    "text": (docs[0][i] if docs and docs[0] else "") or "",
                    "metadata": (metas[0][i] if metas and metas[0] else {}) or {},
                    "distance": (dists[0][i] if dists and dists[0] else None),
                }
            )
        return out


def _sanitize_meta(meta: dict) -> dict:
    clean: dict = {}
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean[str(k)] = v
        else:
            clean[str(k)] = str(v)[:512]
    return clean
