"""Secure API key storage.

Keys go in the OS keyring (GNOME Keyring / KWallet / Keychain / Credential
Manager) via the `keyring` package. If no keyring backend is available, keys
are taken from the environment only - plaintext keys are NEVER written to
disk by this tool.
"""

from __future__ import annotations

import re

import keyring

SERVICE_NAME = "opsai"
USERNAME = "api-key"

_KEY_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{24,})")


def store_api_key(key: str) -> bool:
    """Store key in OS keyring. Returns False if no backend is available."""
    try:
        keyring.set_password(SERVICE_NAME, USERNAME, key)
        return keyring.get_password(SERVICE_NAME, USERNAME) == key
    except Exception:
        return False


def get_api_key() -> str | None:
    """Retrieve key from keyring, or None if unavailable/missing."""
    try:
        return keyring.get_password(SERVICE_NAME, USERNAME)
    except Exception:
        return None


def delete_api_key() -> bool:
    """Remove key from keyring. Returns False if nothing was removed."""
    try:
        keyring.delete_password(SERVICE_NAME, USERNAME)
        return True
    except keyring.errors.PasswordDeleteError:
        return False
    except Exception:
        return False


def redact(text: str) -> str:
    """Replace any key-like token with [REDACTED] before printing."""
    return _KEY_PATTERN.sub("[REDACTED]", text)
