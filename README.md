# pk-agent

Screen capture → SQLite + Chroma; **cloud-only** Anthropic Messages API with inexpensive **Haiku 4.5** for gating and the same or a stronger model for hints; Tk popups.

## Prerequisites

1. Python 3.10+
2. Create an API key in the [Anthropic Console](https://console.anthropic.com/)
3. Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY`. Gating defaults to `CLAUDE_GATE_MODEL=claude-haiku-4-5` (low cost). **Do not use `claude-haiku-3`**—it is not a valid API model id (404).

## Install and run

```bash
pip install -e .
pk-agent doctor
pk-agent run
```

`pk-agent run` writes captures to `data/store.db` and `data/chroma/`, calls Claude on a schedule, and may show a popup.

Logging defaults to **INFO** (gating / RAG / hint / ingest / popup). Use `pk-agent run --verbose` (or `-v`) for per-capture and vector-hit detail.

## Notes

- Leave `ANTHROPIC_BASE_URL` empty for the official API; if you use a corporate proxy or custom gateway, set the Anthropic-compatible base URL it provides.
- Legacy env names still work: `CLOUD_LLM_API_KEY`, `CLOUD_LLM_MODEL`, and `CLOUD_GATE_MODEL` map to the same settings.
- By default only the **foreground window** is captured (`GetWindowRect` + region grab). Set `CAPTURE_ACTIVE_WINDOW_ONLY=false` in `.env` for the full primary monitor. Non-Windows falls back to full screen.
