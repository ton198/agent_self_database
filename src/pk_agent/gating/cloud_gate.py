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


GATE_SYSTEM = """You are a gate model that decides whether to interrupt the user. Principle: when you could
offer a useful hint, lean toward interrupting. Judge whether the user likely needs real help—for example they are
writing or reading a difficult document, or searching for something and you believe a nudge would help. If you can
help, set should_notify accordingly. Do not fear interrupting when the help would be genuine. Common cases: writing
or studying, unclear search queries, typos or grammar issues, vague phrasing—though some wording may be intentional;
use context. When the user has clearly selected/highlighted text, they often need help. When on-screen content looks
hard to read or abstruse, they may need help. Work and learning contexts are prime times to be proactive. Act like an
active assistant, not a passive notifier (this matters).

If two images are provided—an earlier frame and the current one—compare whether they are almost the same (same UI,
largely static content). If the text says the user has stayed on the same window a long time with little visual change
and the two images are indeed very similar, they may be stuck on one problem; in that case prefer should_notify=true
when you can offer a concrete, useful next step.

Output only the following JSON object.
Output a single JSON object only—no Markdown, no other text.
JSON shape:
{"should_notify": true/false, "reason": "one short sentence", "search_query": "string for KB retrieval, may be empty"}
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


def gate_should_notify(
    settings: Settings,
    *,
    meta_text: str,
    image_png: bytes | None,
    prior_image_png: bytes | None = None,
) -> tuple[bool, str, str]:
    """
    Anthropic Messages API with vision + short meta. JSON gating.
    Optional prior_image_png: earlier frame for “stuck on same view” comparison.
    Returns (should_notify, reason, search_query); on failure (False, "", "").
    """
    png = image_png or b""
    if len(png) < 32:
        log.info("gating: skip no image")
        return False, "", ""

    if not settings.anthropic_api_key.strip():
        log.info("gating: skip ANTHROPIC_API_KEY empty")
        return False, "", ""

    meta = (meta_text or "").strip()
    prior = prior_image_png or b""
    has_prior = len(prior) >= 32
    client = make_client(settings)
    log.info(
        "gating: calling model=%s current_bytes=%d prior_bytes=%d meta_chars=%d",
        settings.claude_gate_model,
        len(png),
        len(prior) if has_prior else 0,
        len(meta),
    )
    intro = (
        "You will receive one or two PNGs. The red ring marks the approximate mouse position."
        + (
            " The first image is the earlier screenshot; the second is the newer (current) one."
            if has_prior
            else " Only one image is provided: the current screenshot."
        )
    )
    user_content: Any = [
        {"type": "text", "text": intro},
    ]
    if has_prior:
        user_content.append(anthropic_png_block(prior))
        user_content.append({"type": "text", "text": "↑ Earlier screenshot."})
    user_content.append(anthropic_png_block(png))
    user_content.append(
        {
            "type": "text",
            "text": f"↑ Current screenshot.\n\nWindow and context (not OCR):\n{meta[:4000]}",
        },
    )
    try:
        resp = client.messages.create(
            model=settings.claude_gate_model,
            max_tokens=512,
            system=GATE_SYSTEM,
            messages=cast(Any, [{"role": "user", "content": user_content}]),
            temperature=0.2,
        )
        raw = message_text(resp)
        data = _extract_json_object(raw)
        flag = bool(data.get("should_notify"))
        reason = str(data.get("reason") or "")[:500]
        q = str(data.get("search_query") or "")[:500]
        log.info(
            "gating: decision notify=%s reason=%s search_query=%s%s",
            flag,
            one_line(reason, 180),
            one_line(q, 120),
            _usage_log_fragment(resp),
        )
        return flag, reason, q
    except Exception as e:
        log.warning("gating: failed %s", e)
        return False, "", ""
