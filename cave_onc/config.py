"""Central configuration — single typed entry point for all secrets and config.

Nothing else in the codebase should read ``os.environ`` directly.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Optional

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Project-wide settings loaded from environment variables or a ``.env`` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── CDISC Library ──────────────────────────────────────────────────
    cdisc_library_api_key: Optional[SecretStr] = None
    cdisc_library_api_key_secondary: Optional[SecretStr] = None

    # ── DeepSeek V4 (primary L3 LLM) ──────────────────────────────────
    deepseek_api_key: Optional[SecretStr] = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ── Zhipu GLM (secondary L3 LLM) ──────────────────────────────────
    glm_api_key: Optional[SecretStr] = None
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_model: str = "glm-4.6"

    # ── Local LLM endpoint (optional fallback) ────────────────────────
    local_llm_base_url: Optional[str] = None
    local_llm_model: str = "qwen2.5-7b-instruct"

    # ── OpenRouter (multi-model cross-validation) ─────────────────────
    openrouter: Optional[SecretStr] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # ── Audit store ───────────────────────────────────────────────────
    audit_db_path: Path = Path("audit/cave_audit.db")


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached singleton ``Settings`` instance."""
    return Settings()
