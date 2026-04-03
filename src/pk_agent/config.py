from __future__ import annotations

import logging
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_cfg_log = logging.getLogger("pk_agent.config")

# Invalid or chat-style names that are not Anthropic Messages API model ids
_GATE_MODEL_REMAP: dict[str, str] = {
    "claude-haiku-3": "claude-haiku-4-5",
    "claude-3-haiku-20240307": "claude-haiku-4-5",
    "claude-3-haiku": "claude-haiku-4-5",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default=Path("data"))

    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "ANTHROPIC_API_KEY",
            "CLAUDE_API_KEY",
            "CLOUD_LLM_API_KEY",
        ),
    )
    anthropic_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("ANTHROPIC_BASE_URL", "CLAUDE_BASE_URL"),
    )
    # Hint / popup body (can use same family or a stronger model)
    claude_model: str = Field(
        default="claude-haiku-4-5-20251001",
        validation_alias=AliasChoices("CLAUDE_MODEL", "CLOUD_LLM_MODEL"),
    )
    # Gate: use Haiku 4.5 alias (cheapest current tier on API docs)
    claude_gate_model: str = Field(
        default="claude-haiku-4-5",
        validation_alias=AliasChoices("CLAUDE_GATE_MODEL", "CLOUD_GATE_MODEL"),
    )

    # True: capture only the active window (Windows GetWindowRect + mss region)
    capture_active_window_only: bool = Field(
        default=True,
        validation_alias="CAPTURE_ACTIVE_WINDOW_ONLY",
    )
    capture_interval_seconds: float = Field(
        default=2.0, validation_alias="CAPTURE_INTERVAL_SECONDS"
    )
    proactive_interval_seconds: float = Field(
        default=60.0, validation_alias="PROACTIVE_INTERVAL_SECONDS"
    )
    recent_context_minutes: int = Field(
        default=12, validation_alias="RECENT_CONTEXT_MINUTES"
    )
    frame_diff_threshold: float = Field(
        default=4.0, validation_alias="FRAME_DIFF_THRESHOLD"
    )
    min_notify_cooldown_seconds: int = Field(
        default=300, validation_alias="MIN_NOTIFY_COOLDOWN_SECONDS"
    )
    max_notifies_per_day: int = Field(
        default=30, validation_alias="MAX_NOTIFIES_PER_DAY"
    )

    rag_top_k: int = Field(default=6, validation_alias="RAG_TOP_K")
    ocr_merge_seconds: float = Field(
        default=45.0, validation_alias="OCR_MERGE_SECONDS"
    )
    # Max width/height of screenshot sent to Claude (uniform scale, PNG)
    vision_max_image_side: int = Field(
        default=1280, validation_alias="VISION_MAX_IMAGE_SIDE"
    )

    @model_validator(mode="after")
    def remap_invalid_gate_model(self) -> Self:
        g = (self.claude_gate_model or "").strip()
        if g in _GATE_MODEL_REMAP:
            new = _GATE_MODEL_REMAP[g]
            _cfg_log.warning(
                "CLAUDE_GATE_MODEL %r is not a valid API id; using %r",
                g,
                new,
            )
            self.claude_gate_model = new
        return self

    @property
    def db_path(self) -> Path:
        return self.data_dir / "store.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"


def load_settings() -> Settings:
    return Settings()
