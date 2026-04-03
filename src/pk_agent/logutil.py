"""Helpers for concise log lines (no newlines / long spills)."""


def one_line(s: str, max_len: int = 200) -> str:
    x = " ".join((s or "").split())
    if len(x) <= max_len:
        return x
    return x[: max_len - 1] + "…"
