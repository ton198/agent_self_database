"""Resize screenshot and mark cursor for vision models (no OCR)."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw


def cursor_relative_to_capture(
    cursor: tuple[int, int] | None,
    origin_left: int,
    origin_top: int,
    width: int,
    height: int,
) -> tuple[int, int] | None:
    """Map screen cursor to (x, y) inside capture; None if outside."""
    if cursor is None:
        return None
    x, y = cursor
    rx, ry = x - origin_left, y - origin_top
    if rx < 0 or ry < 0 or rx >= width or ry >= height:
        return None
    return rx, ry


def build_visual_context_png(
    img: Image.Image,
    cursor_rel: tuple[int, int] | None,
    *,
    max_side: int,
) -> bytes:
    """
    RGB PNG: optional uniform scale so max(w,h) <= max_side, red ring at cursor.
    """
    rgb = img.convert("RGB")
    w, h = rgb.size
    if w <= 0 or h <= 0:
        raise ValueError("empty image")

    scale = 1.0
    if max(w, h) > max_side:
        scale = max_side / max(w, h)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        rgb = rgb.resize((nw, nh), Image.Resampling.LANCZOS)
        w, h = nw, nh

    draw_on: tuple[int, int] | None = None
    if cursor_rel is not None:
        cx = int(cursor_rel[0] * scale)
        cy = int(cursor_rel[1] * scale)
        if 0 <= cx < w and 0 <= cy < h:
            draw_on = (cx, cy)

    if draw_on is not None:
        cx, cy = draw_on
        draw = ImageDraw.Draw(rgb)
        r = max(10, min(w, h) // 35)
        draw.ellipse(
            (cx - r, cy - r, cx + r, cy + r),
            outline=(220, 40, 40),
            width=max(2, r // 5),
        )

    buf = io.BytesIO()
    rgb.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
