"""Configuration for file analysis agent."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Runtime configuration for the file analysis agent."""

    cache_dir: Path = Field(
        default=Path.home() / ".file_analysis_cache",
        description="Directory where cached markdown and metadata are stored",
    )
    max_return_chars: int = Field(
        default=5000, description="Maximum characters returned by tools"
    )
    regex_default_flags: str = Field(
        default="im", description="Default regex flags used when none are provided"
    )
    token_limit: int = Field(
        default=4000, description="Maximum tokens returned by read_full_file before truncation"
    )
    encoding_name: str = Field(
        default="cl100k_base", description="Tiktoken encoding name for token counting"
    )
    conversion_timeout: int = Field(
        default=45, description="Maximum seconds allowed for conversion/caching step"
    )


ROOT_CONFIG = Path(__file__).resolve().parents[2] / "organizer.config.json"


def _load_config_from_file() -> AgentConfig:
    """Load configuration from the main config file if present."""
    if ROOT_CONFIG.exists():
        data = json.loads(ROOT_CONFIG.read_text())
        cfg = AgentConfig(**data.get("file_analysis_agent", {}))
    else:
        cfg = AgentConfig()
    cfg.cache_dir = Path(cfg.cache_dir).expanduser()
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    return cfg


CONFIG = _load_config_from_file()


def update_config(**kwargs) -> AgentConfig:
    """Update global configuration values.

    Returns the updated configuration.
    """

    global CONFIG
    CONFIG = CONFIG.model_copy(update=kwargs)
    CONFIG.cache_dir = Path(CONFIG.cache_dir).expanduser()
    CONFIG.cache_dir.mkdir(parents=True, exist_ok=True)
    return CONFIG
