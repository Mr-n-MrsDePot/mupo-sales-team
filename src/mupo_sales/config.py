"""
Configuration loader for MUPO Sales Team.

Loads:
  - Environment variables via pydantic-settings (.env)
  - Business rules from config/settings.yaml
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root: mupo-sales-team/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "settings.yaml"
DEFAULT_KNOWLEDGE = PROJECT_ROOT / "knowledge"
DEFAULT_DATA = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Runtime settings from environment."""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM — xAI / SpaceXAI
    xai_api_key: str = Field(default="", alias="XAI_API_KEY")
    xai_base_url: str = Field(default="https://api.x.ai/v1", alias="XAI_BASE_URL")
    xai_model: str = Field(default="grok-4.5", alias="XAI_MODEL")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    fallback_provider: str = Field(default="none", alias="FALLBACK_PROVIDER")
    fallback_model: str = Field(default="claude-3-5-sonnet-latest", alias="FALLBACK_MODEL")

    # Business
    company_name: str = Field(default="MUPO Entertainment", alias="COMPANY_NAME")
    brand_name: str = Field(default="MUPO TV", alias="BRAND_NAME")
    founder_name: str = Field(default="Michele Mupo", alias="FOUNDER_NAME")
    sales_from_name: str = Field(default="MUPO TV Partnerships", alias="SALES_FROM_NAME")
    sales_from_email: str = Field(default="partnerships@mupotv.example", alias="SALES_FROM_EMAIL")
    human_handoff_email: str = Field(default="michele@mupotv.example", alias="HUMAN_HANDOFF_EMAIL")
    human_handoff_slack_webhook: str = Field(default="", alias="HUMAN_HANDOFF_SLACK_WEBHOOK")

    deal_handoff_threshold_usd: float = Field(default=5000.0, alias="DEAL_HANDOFF_THRESHOLD_USD")
    strong_signal_notify: bool = Field(default=True, alias="STRONG_SIGNAL_NOTIFY")

    # Email
    email_mode: str = Field(default="dry_run", alias="EMAIL_MODE")
    gmail_credentials_path: str = Field(default="", alias="GMAIL_CREDENTIALS_PATH")
    instantly_api_key: str = Field(default="", alias="INSTANTLY_API_KEY")
    smartlead_api_key: str = Field(default="", alias="SMARTLEAD_API_KEY")
    linkedin_mode: str = Field(default="draft_only", alias="LINKEDIN_MODE")

    # Limits
    max_outreach_per_day: int = Field(default=40, alias="MAX_OUTREACH_PER_DAY")
    max_llm_calls_per_run: int = Field(default=50, alias="MAX_LLM_CALLS_PER_RUN")
    agent_timeout_seconds: int = Field(default=120, alias="AGENT_TIMEOUT_SECONDS")

    # Paths
    data_dir: Path = Field(default=DEFAULT_DATA, alias="DATA_DIR")
    knowledge_dir: Path = Field(default=DEFAULT_KNOWLEDGE, alias="KNOWLEDGE_DIR")
    config_path: Path = Field(default=DEFAULT_CONFIG, alias="CONFIG_PATH")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    dry_run: bool = Field(default=True, alias="DRY_RUN")
    enable_vector_memory: bool = Field(default=False, alias="ENABLE_VECTOR_MEMORY")

    def ensure_dirs(self) -> None:
        """Create data subdirectories if missing."""
        for sub in ("crm", "logs", "proposals", "memory"):
            (self.data_dir / sub).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Resolve relative paths against project root
    if not settings.data_dir.is_absolute():
        settings.data_dir = (PROJECT_ROOT / settings.data_dir).resolve()
    if not settings.knowledge_dir.is_absolute():
        settings.knowledge_dir = (PROJECT_ROOT / settings.knowledge_dir).resolve()
    if not settings.config_path.is_absolute():
        settings.config_path = (PROJECT_ROOT / settings.config_path).resolve()
    settings.ensure_dirs()
    return settings


@lru_cache
def load_yaml_config() -> dict[str, Any]:
    """Load settings.yaml business configuration."""
    path = get_settings().config_path
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_business_rules() -> dict[str, Any]:
    return load_yaml_config().get("business_rules", {})


def get_products() -> list[dict[str, Any]]:
    return load_yaml_config().get("products", [])


def get_handoff_threshold() -> float:
    env = get_settings().deal_handoff_threshold_usd
    yaml_val = get_business_rules().get("deal_handoff_threshold_usd")
    return float(yaml_val if yaml_val is not None else env)
