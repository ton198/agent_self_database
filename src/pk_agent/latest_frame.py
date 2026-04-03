"""Thread-safe latest screen frame (+ prior frame, static timer) for gate / proactive."""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class LatestFrameSnapshot:
    """Empty image_png means no capture yet this session."""

    app_name: str = ""
    window_title: str = ""
    image_png: bytes = b""
    cursor_rel: tuple[int, int] | None = None
    # Previous committed frame (same window only); empty if none yet.
    prior_image_png: bytes = b""
    prior_app_name: str = ""
    prior_window_title: str = ""
    prior_cursor_rel: tuple[int, int] | None = None
    # Seconds accumulated while same window & capture skipped (low visual diff).
    static_same_window_seconds: float = 0.0


class LatestFrame:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap = LatestFrameSnapshot()

    def add_static_time(self, delta_seconds: float) -> None:
        if delta_seconds <= 0:
            return
        with self._lock:
            self._snap = LatestFrameSnapshot(
                app_name=self._snap.app_name,
                window_title=self._snap.window_title,
                image_png=self._snap.image_png,
                cursor_rel=self._snap.cursor_rel,
                prior_image_png=self._snap.prior_image_png,
                prior_app_name=self._snap.prior_app_name,
                prior_window_title=self._snap.prior_window_title,
                prior_cursor_rel=self._snap.prior_cursor_rel,
                static_same_window_seconds=self._snap.static_same_window_seconds
                + delta_seconds,
            )

    def reset_static_time(self) -> None:
        with self._lock:
            if self._snap.static_same_window_seconds == 0.0:
                return
            self._snap = LatestFrameSnapshot(
                app_name=self._snap.app_name,
                window_title=self._snap.window_title,
                image_png=self._snap.image_png,
                cursor_rel=self._snap.cursor_rel,
                prior_image_png=self._snap.prior_image_png,
                prior_app_name=self._snap.prior_app_name,
                prior_window_title=self._snap.prior_window_title,
                prior_cursor_rel=self._snap.prior_cursor_rel,
                static_same_window_seconds=0.0,
            )

    def update_focus_meta(self, *, app_name: str, window_title: str) -> None:
        """Foreground title/app changed but pixels unchanged; refresh labels only."""
        with self._lock:
            if not self._snap.image_png:
                return
            self._snap = LatestFrameSnapshot(
                app_name=app_name or "",
                window_title=window_title or "",
                image_png=self._snap.image_png,
                cursor_rel=self._snap.cursor_rel,
                prior_image_png=self._snap.prior_image_png,
                prior_app_name=self._snap.prior_app_name,
                prior_window_title=self._snap.prior_window_title,
                prior_cursor_rel=self._snap.prior_cursor_rel,
                static_same_window_seconds=0.0,
            )

    def update(
        self,
        *,
        image_png: bytes,
        app_name: str,
        window_title: str,
        cursor_rel: tuple[int, int] | None,
    ) -> None:
        with self._lock:
            new_app = app_name or ""
            new_title = window_title or ""
            old = self._snap
            new_key = (new_app, new_title)
            old_key = (old.app_name, old.window_title)

            prior_png = b""
            prior_app = ""
            prior_title = ""
            prior_crel: tuple[int, int] | None = None

            # Same window: keep previous frame for gate comparison; switch clears it.
            if old.image_png and new_key == old_key:
                prior_png = bytes(old.image_png)
                prior_app = old.app_name
                prior_title = old.window_title
                prior_crel = old.cursor_rel

            self._snap = LatestFrameSnapshot(
                app_name=new_app,
                window_title=new_title,
                image_png=image_png or b"",
                cursor_rel=cursor_rel,
                prior_image_png=prior_png,
                prior_app_name=prior_app,
                prior_window_title=prior_title,
                prior_cursor_rel=prior_crel,
                static_same_window_seconds=0.0,
            )

    def snapshot(self) -> LatestFrameSnapshot:
        with self._lock:
            s = self._snap
            return LatestFrameSnapshot(
                app_name=s.app_name,
                window_title=s.window_title,
                image_png=bytes(s.image_png),
                cursor_rel=s.cursor_rel,
                prior_image_png=bytes(s.prior_image_png),
                prior_app_name=s.prior_app_name,
                prior_window_title=s.prior_window_title,
                prior_cursor_rel=s.prior_cursor_rel,
                static_same_window_seconds=s.static_same_window_seconds,
            )


def format_rag_fallback(snap: LatestFrameSnapshot) -> str:
    """Short text for vector query fallback (no OCR body)."""
    head = f"[{snap.app_name}] {snap.window_title}".strip()
    if snap.cursor_rel is not None:
        cx, cy = snap.cursor_rel
        return f"{head}\nFocus relative to screenshot ~ ({cx}, {cy})".strip()
    return head


def format_gate_history_meta(snap: LatestFrameSnapshot) -> str:
    """Extra lines for gate: static duration + prior-frame hint."""
    base = format_rag_fallback(snap)
    lines = [base]
    if snap.static_same_window_seconds >= 1.0:
        lines.append(
            f"About {snap.static_same_window_seconds:.0f} s have passed with the same foreground window and almost no "
            "visual change since the last noticeable frame (fingerprint)."
        )
    if snap.prior_image_png:
        phead = f"[Earlier frame] [{snap.prior_app_name}] {snap.prior_window_title}".strip()
        lines.append(
            f"{phead}\nThe first image below is the earlier screenshot, the second is the current one; judge whether "
            "they are almost the same and whether the user may be stuck on one problem and need help."
        )
    return "\n".join(lines).strip()
