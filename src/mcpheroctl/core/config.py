"""Configuration management for mcpheroctl.

Handles reading/writing the API token and base URL to
~/.config/mcpheroctl/config.json.
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

CONFIG_DIR = Path.home() / ".config" / "mcpheroctl"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Default base URL for the MCPHero API
DEFAULT_BASE_URL = "https://api.mcphero.app"


class Config(BaseModel):
    """Persisted CLI configuration."""

    api_token: str | None = None
    base_url: str = DEFAULT_BASE_URL


def load_config() -> Config:
    """Load configuration from disk. Returns defaults if file does not exist."""
    if not CONFIG_FILE.exists():
        return Config()
    try:
        data = json.loads(CONFIG_FILE.read_text())
        return Config.model_validate(data)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Warning: corrupt config at {CONFIG_FILE}: {exc}", file=sys.stderr)
        return Config()


def save_config(config: Config) -> None:
    """Persist configuration to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _ = CONFIG_FILE.write_text(config.model_dump_json(indent=2) + "\n")


def require_token() -> str:
    """Return the stored API token or exit with an error message."""
    config = load_config()
    if not config.api_token:
        print(
            "Error: not authenticated. Run `mcpheroctl auth login --token <TOKEN>` first.",
            file=sys.stderr,
        )
        raise SystemExit(4)  # exit code 4 = permission denied / not authenticated
    return config.api_token


def get_base_url() -> str:
    """Return the configured API base URL."""
    return load_config().base_url
