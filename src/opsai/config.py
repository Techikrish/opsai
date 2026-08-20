"""Configuration handling.

Non-secret settings only (base_url, model). API keys NEVER live here -
they are stored in the OS keyring or provided via environment variables.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

ENV_BASE_URL = "OPSAI_BASE_URL"
ENV_MODEL = "OPSAI_MODEL"
ENV_API_KEY = "OPSAI_API_KEY"
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "opsai"
    return Path.home() / ".config" / "opsai"


CONFIG_FILE = config_dir() / "config.json"


def _env_config() -> dict:
    cfg = {}
    for env, key in ((ENV_BASE_URL, "base_url"), (ENV_MODEL, "model")):
        val = os.environ.get(env)
        if val:
            cfg[key] = val
    return cfg


def _file_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if k in ("base_url", "model")}
    except (OSError, json.JSONDecodeError):
        return {}


def resolve_config(flags: dict | None = None) -> dict:
    """Merge config sources with precedence: flags > env vars > file > defaults."""
    flags = flags or {}
    cfg = {
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
    }
    cfg.update(_file_config())
    cfg.update(_env_config())
    for key in ("base_url", "model"):
        val = flags.get(key)
        if val:
            cfg[key] = val
    return cfg


def save_config(base_url: str, model: str) -> None:
    """Persist non-secret settings. Refuses to ever store api keys.

    Written atomically via a private, 0600 temp file so a pre-planted
    symlink on the predictable tmp path can never be followed, and the
    final file never exists with default (0644) permissions.
    """
    target_dir = CONFIG_FILE.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    cfg = _file_config()
    cfg["base_url"] = base_url
    cfg["model"] = model
    fd, tmp_path = tempfile.mkstemp(dir=target_dir, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, CONFIG_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def api_key_from_env() -> str | None:
    """API key from environment only - never from config files."""
    return os.environ.get(ENV_API_KEY) or os.environ.get(ENV_OPENAI_API_KEY)
