"""OpenAI-compatible chat completions client.

Works with OpenAI, Groq, Ollama, LM Studio - anything speaking the
OpenAI /v1/chat/completions protocol.
"""

from __future__ import annotations

from typing import Any

import requests

from opsai.keyring_store import redact

TIMEOUT_SECONDS = 30


class OpsaiError(Exception):
    """User-facing error; message is safe to print (already redacted)."""


_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def is_local_url(url: str) -> bool:
    """True if the URL points at a local model server (Ollama/LM Studio)."""
    lowered = url.lower()
    try:
        host = lowered.split("//", 1)[1].split("/")[0].split(":")[0]
    except IndexError:
        return False
    return host in _LOCAL_HOSTS


def _validate_url(url: str) -> str:
    url = url.rstrip("/")
    lowered = url.lower()
    if "@" in url.split("/")[2].split("?")[0]:
        raise OpsaiError("base_url must not contain embedded credentials (user:pass@host).")
    if lowered.startswith("http://"):
        host = lowered[len("http://"):].split("/")[0].split(":")[0]
        if host not in _LOCAL_HOSTS:
            raise OpsaiError(
                f"Refusing plaintext HTTP to non-localhost host {host!r}. "
                "Use HTTPS or a local model server (Ollama/LM Studio)."
            )
    elif not lowered.startswith("https://"):
        raise OpsaiError("base_url must start with https:// (or http://localhost).")
    return url


def chat_completion(
    base_url: str,
    model: str,
    api_key: str | None,
    messages: list[dict[str, Any]],
    *,
    timeout: int = TIMEOUT_SECONDS,
) -> str:
    """Send messages, return the assistant's reply text."""
    url = f"{_validate_url(base_url)}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
    }
    try:
        resp = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout,
            allow_redirects=False,
        )
    except requests.exceptions.ConnectionError as exc:
        raise OpsaiError(
            f"Could not connect to {redact(base_url)}. "
            "Is the server running and the URL correct?"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise OpsaiError(f"Request timed out after {timeout}s.") from exc
    except requests.exceptions.RequestException as exc:
        raise OpsaiError(f"Request failed: {redact(str(exc))}") from exc

    if resp.status_code != 200:
        if 300 <= resp.status_code < 400:
            raise OpsaiError(
                f"API server returned a redirect ({resp.status_code}); redirects are "
                "not followed. Check that base_url points directly at the API endpoint."
            )
        raise OpsaiError(_error_from_response(resp))
    try:
        body = resp.json()
    except ValueError as exc:
        raise OpsaiError("Server returned non-JSON response.") from exc
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpsaiError("Server response was missing expected fields.") from exc


def _error_from_response(resp: requests.Response) -> str:
    try:
        data = resp.json()
        message = data.get("error", {}).get("message", "")
    except ValueError:
        message = resp.text[:300]
    message = message or f"HTTP {resp.status_code}"
    if resp.status_code == 401:
        return "Authentication failed (HTTP 401): check your API key."
    return f"API error {resp.status_code}: {redact(message)}"
