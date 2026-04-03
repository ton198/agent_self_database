from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

from pk_agent.claude_api import anthropic_png_block, make_client, message_text
from pk_agent.config import Settings
from pk_agent.logutil import one_line

log = logging.getLogger(__name__)


def _usage_log_fragment(resp: object) -> str:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return ""
    inp = getattr(usage, "input_tokens", None)
    out = getattr(usage, "output_tokens", None)
    if inp is None and out is None:
        return ""
    return f" tokens_in={inp} tokens_out={out}"


GEN_SYSTEM = """You are a personal knowledge-base assistant. From the retrieved history snippets and the current
screen screenshot, produce one proactive hint. You see the foreground window; the red ring marks the approximate
pointer. Be brief, actionable, and natural; keep the body under about 200 words. If retrieval is empty or too thin,
say you are unsure and give a generic, low-risk suggestion.

Ground hints in what the user is doing—writing, reading, searching, collaborating, etc.—and infer where they might be
stuck (e.g. blocked on how to start, how to interpret text, or how to find an answer). Not limited to those examples.
Combine retrieved snippets to guess what content or step might help.

Output a single JSON object only—no Markdown.
JSON shape:
{"title": "short popup title", "body": "hint body", "cite_ids": ["optional chunk_id from retrieval"]}
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*", "", s).strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        raise ValueError("no json object in model output")
    return json.loads(m.group())


def generate_tip(
    settings: Settings,
    *,
    meta_text: str,
    image_png: bytes | None,
    retrieved_context: str,
    gate_reason: str,
) -> tuple[str, str, list[str]]:
    """Returns (title, body, cite_ids). Empty strings on failure."""
    if not settings.anthropic_api_key.strip():
        log.warning("hint: skip ANTHROPIC_API_KEY empty")
        return "", "", []

    png = image_png or b""
    if len(png) < 32:
        log.warning("hint: skip no image")
        return "", "", []

    client = make_client(settings)
    head = (
        f"Gate model rationale:\n{gate_reason}\n\n"
        f"Window and pointer notes:\n{(meta_text or '').strip()[:4000]}\n\n"
        f"Retrieved snippets:\n{retrieved_context[:8000]}"
    )
    user_content: Any = [
        anthropic_png_block(png),
        {"type": "text", "text": head},
    ]
    log.info(
        "hint: calling model=%s gate_reason=%s image_bytes=%d",
        settings.claude_model,
        one_line(gate_reason, 120),
        len(png),
    )
    try:
        resp = client.messages.create(
            model=settings.claude_model,
            max_tokens=1024,
            system=GEN_SYSTEM,
            messages=cast(Any, [{"role": "user", "content": user_content}]),
            temperature=0.4,
        )
        raw = message_text(resp)
        data = _extract_json_object(raw)
        title = str(data.get("title") or "Hint").strip()[:120]
        body = str(data.get("body") or "").strip()[:2000]
        cites = data.get("cite_ids") or []
        cite_ids = [str(x) for x in cites if x][:20]
        log.info(
            "hint: done title=%s body=%s cite_ids=%s%s",
            one_line(title, 80),
            one_line(body, 200),
            cite_ids,
            _usage_log_fragment(resp),
        )
        return title, body, cite_ids
    except Exception as e:
        log.warning("hint: failed %s", e)
        return "", "", []
