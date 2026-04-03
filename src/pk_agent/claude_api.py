"""Shared Anthropic client construction and response text extraction."""

from __future__ import annotations

import base64

from anthropic import Anthropic

from pk_agent.config import Settings


def anthropic_png_block(png_bytes: bytes) -> dict:
    """Anthropic Messages API image block (base64 PNG)."""
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": b64,
        },
    }


def make_client(settings: Settings) -> Anthropic:
    base = settings.anthropic_base_url.strip()
    if base:
        return Anthropic(
            api_key=settings.anthropic_api_key,
            base_url=base.rstrip("/"),
        )
    return Anthropic(api_key=settings.anthropic_api_key)


def message_text(message: object) -> str:
    parts: list[str] = []
    content = getattr(message, "content", None) or []
    for block in content:
        if getattr(block, "type", None) == "text":
            t = getattr(block, "text", None)
            if t:
                parts.append(str(t))
    return "".join(parts).strip()
