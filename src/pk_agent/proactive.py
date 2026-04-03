from __future__ import annotations

import logging
import queue
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from pk_agent.config import Settings
from pk_agent.gating.cloud_gate import gate_should_notify
from pk_agent.generation.cloud_llm import generate_tip
from pk_agent.generation.rag import format_hits_for_prompt, retrieve_context
from pk_agent.latest_frame import LatestFrame, format_gate_history_meta, format_rag_fallback
from pk_agent.storage.db import (
    count_notifies_since,
    insert_notify_log,
    last_notify_time,
)
from pk_agent.storage.vector import VectorStore
from pk_agent.logutil import one_line

log = logging.getLogger(__name__)


def _start_of_local_day_utc() -> datetime:
    local = datetime.now().astimezone()
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc)


def proactive_tick(
    settings: Settings,
    session: Session,
    vector: VectorStore,
    notify_queue: queue.Queue[tuple[str, str]],
    latest_frame: LatestFrame,
) -> None:
    now = datetime.now(timezone.utc)
    log.debug("proactive: tick")
    last = last_notify_time(session)
    if last is not None:
        delta = (now - last).total_seconds()
        if delta < settings.min_notify_cooldown_seconds:
            left = int(settings.min_notify_cooldown_seconds - delta)
            log.info(
                "proactive: skip cooldown (%ds left, min=%ds)",
                left,
                settings.min_notify_cooldown_seconds,
            )
            return

    since_day = _start_of_local_day_utc()
    n_today = count_notifies_since(session, since_day)
    if n_today >= settings.max_notifies_per_day:
        log.info(
            "proactive: skip daily cap (%d/%d)",
            n_today,
            settings.max_notifies_per_day,
        )
        return

    snap = latest_frame.snapshot()
    rag_fallback = format_rag_fallback(snap)
    gate_meta = format_gate_history_meta(snap)
    log.info(
        "proactive: gate_context image_bytes=%d prior_bytes=%d static_s=%.1f gate_meta_chars=%d",
        len(snap.image_png),
        len(snap.prior_image_png),
        snap.static_same_window_seconds,
        len(gate_meta),
    )
    should, reason, search_q = gate_should_notify(
        settings,
        meta_text=gate_meta,
        image_png=snap.image_png if snap.image_png else None,
        prior_image_png=snap.prior_image_png if snap.prior_image_png else None,
    )
    if not should:
        return

    log.info(
        "proactive: gate said yes; RAG then hint (reason=%s)",
        one_line(reason, 160),
    )
    hits_text, hit_ids = retrieve_context(
        vector,
        search_q,
        settings.rag_top_k,
        fallback_text=rag_fallback,
    )
    retrieved = format_hits_for_prompt(hits_text)
    title, body, _cites = generate_tip(
        settings,
        meta_text=gate_meta,
        image_png=snap.image_png if snap.image_png else None,
        retrieved_context=retrieved,
        gate_reason=reason,
    )
    if not body.strip():
        log.info("proactive: hint empty body; skip notify")
        return

    insert_notify_log(session, title=title or "Hint", body=body)
    notify_queue.put((title or "Hint", body))
    log.info(
        "proactive: queued popup title=%r chunk_ids_used=%s",
        title or "Hint",
        hit_ids,
    )
