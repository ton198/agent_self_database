from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from pk_agent.config import Settings
from pk_agent.logutil import one_line
from pk_agent.storage.db import insert_chunk
from pk_agent.storage.vector import VectorStore

log = logging.getLogger(__name__)


def content_hash(app: str, window_title: str, text: str) -> str:
    raw = f"{app}\n{window_title}\n{text}".encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


@dataclass
class ScreenMergeBuffer:
    """Merge screen context lines into fewer DB rows per (app, window) burst."""

    settings: Settings
    vector: VectorStore
    app: str = ""
    window_title: str = ""
    pieces: list[str] = field(default_factory=list)
    window_start: float = field(default_factory=time.monotonic)
    _last_hash: str | None = None

    def push(
        self,
        session: Session,
        *,
        app_name: str,
        window_title: str,
        text: str,
    ) -> None:
        if not text.strip():
            return
        now = time.monotonic()
        key_changed = (app_name, window_title) != (self.app, self.window_title)
        if key_changed and self.pieces:
            self._flush(session)
        if key_changed:
            self.app = app_name
            self.window_title = window_title
            self.window_start = now
            self.pieces = []

        self.pieces.append(text.strip())
        elapsed = now - self.window_start
        if elapsed >= self.settings.ocr_merge_seconds:
            self._flush(session)
            self.window_start = time.monotonic()

    def flush(self, session: Session) -> None:
        if self.pieces:
            self._flush(session)
        self.pieces.clear()
        self.app = ""
        self.window_title = ""

    def _flush(self, session: Session) -> None:
        if not self.pieces:
            return
        merged = "\n".join(self.pieces).strip()
        self.pieces.clear()
        if not merged:
            return
        h = content_hash(self.app, self.window_title, merged)
        if h == self._last_hash:
            return
        self._last_hash = h
        chunk_id = insert_chunk(
            session,
            app_name=self.app,
            window_title=self.window_title,
            text=merged,
            content_hash=h,
        )
        self.vector.add(
            doc_id=chunk_id,
            text=merged,
            metadata={
                "app_name": self.app,
                "window_title": self.window_title,
                "source": "screen_visual",
            },
        )
        log.info(
            "ingest: chunk id=%s app=%r chars=%d title=%s",
            chunk_id,
            self.app,
            len(merged),
            one_line(self.window_title, 100),
        )
