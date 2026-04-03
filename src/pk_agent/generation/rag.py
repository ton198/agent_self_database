from __future__ import annotations

import logging

from pk_agent.logutil import one_line
from pk_agent.storage.vector import VectorStore

log = logging.getLogger(__name__)


def retrieve_context(
    store: VectorStore, query: str, k: int, fallback_text: str
) -> tuple[str, list[str]]:
    """Return (joined context for LLM, list of chunk ids)."""
    q = (query or "").strip() or fallback_text[:2000]
    used_fallback = not (query or "").strip()
    hits = store.query(q, k=max(1, k))
    log.info(
        "rag: query=%s top_k=%d hits=%d fallback_text=%s",
        one_line(q, 160),
        k,
        len(hits),
        used_fallback,
    )
    if hits:
        log.debug(
            "rag: hit_ids=%s distances=%s",
            [h.get("id") for h in hits],
            [h.get("distance") for h in hits],
        )
    if not hits:
        return "", []
    parts: list[str] = []
    ids: list[str] = []
    for h in hits:
        cid = str(h.get("id") or "")
        txt = (h.get("text") or "").strip()
        meta = h.get("metadata") or {}
        head = f"[chunk_id={cid} app={meta.get('app_name','')}]"
        if txt:
            parts.append(f"{head}\n{txt}")
            ids.append(cid)
    return "\n\n---\n\n".join(parts), ids


def format_hits_for_prompt(hits_context: str) -> str:
    if not hits_context.strip():
        return "(No relevant retrieval hits in the knowledge base; answer conservatively and do not invent entries.)"
    return hits_context
