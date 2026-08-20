"""System prompt construction and strict JSON response extraction."""

from __future__ import annotations

import json
import re
from typing import Any

SYSTEM_PROMPT = """You are a terminal command assistant. The user asks in plain English for a shell command.

Rules:
- Reply with a SINGLE JSON object only. No markdown, no code fences, no prose, no apologies.
- Format: {"command": "<the shell command>", "info": "<1-2 line note on what it does>"}
- The command must be a real, safe, standard command. Never fabricate flags.
- If no sensible or safe command exists, reply {"command": null, "info": "<brief reason>"}.
- Never suggest destructive or malicious commands (data destruction, remote code execution, malware).
- Prefer non-sudo variants; only include sudo when genuinely required.
- For questions unrelated to terminals or commands, reply {"command": null, "info": "<brief answer>"}.
"""


def build_messages(query: str, history: list[dict] | None = None) -> list[dict]:
    """Build the message list sent to the API: fixed system prompt + query only."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history or []:
        messages.append(turn)
    messages.append({"role": "user", "content": query})
    return messages


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from model output, tolerating fences/junk."""
    if not text:
        return None
    candidates = []
    for match in _FENCE_RE.finditer(text):
        candidates.append(match.group(1))
    if not candidates:
        candidates.append(text)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate.strip())
        except json.JSONDecodeError:
            match = _OBJECT_RE.search(candidate)
            if not match:
                continue
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                continue
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_answer(text: str) -> dict[str, Any]:
    """Turn model output into {command, info}. Never raises."""
    parsed = extract_json(text)
    if parsed is None:
        return {"command": None, "info": "The model returned an unparseable response. Try again."}
    command = parsed.get("command")
    info = parsed.get("info")
    if not isinstance(command, str) or not command.strip():
        command = None
    if not isinstance(info, str) or not info.strip():
        info = ""
    return {"command": command, "info": info}
