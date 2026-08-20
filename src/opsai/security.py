"""Security helpers: danger heuristics and paste-injection warnings.

The tool NEVER executes commands; these flags exist so the user sees a
warning banner before copying anything risky.
"""

from __future__ import annotations

import re

_DANGER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("recursive deletion", re.compile(r"\brm\s+(-[^\s]*r[^\s]*\s+)?.*", re.IGNORECASE)),
    ("privilege escalation", re.compile(r"\bsudo\b", re.IGNORECASE)),
    ("filesystem formatting", re.compile(r"\bmkfs\b", re.IGNORECASE)),
    ("raw device writes", re.compile(r"\bdd\s+.*\bof=", re.IGNORECASE)),
    ("remote code execution via pipe", re.compile(r"\b(curl|wget)\b.*\|\s*(sh|bash|zsh)\b", re.IGNORECASE)),
    ("disk partitioning", re.compile(r"\b(parted|fdisk)\b", re.IGNORECASE)),
    ("kernel module removal", re.compile(r"\brmmod\b", re.IGNORECASE)),
    ("shutdown/power off", re.compile(r"\b(shutdown|poweroff)\b", re.IGNORECASE)),
    ("package purge", re.compile(r"\b(purge|autoremove)\b", re.IGNORECASE)),
    ("firewall flush", re.compile(r"\biptables\b.*\b-F\b", re.IGNORECASE)),
]


def danger_flags(command: str) -> list[str]:
    """Return the list of danger categories detected in a command."""
    if not command:
        return []
    flags = []
    for label, pattern in _DANGER_PATTERNS:
        if pattern.search(command):
            flags.append(label)
    return flags


_PROMPT_RE = re.compile(r"^\s*[$#>]\s")
_CMDLIKE_RE = re.compile(r"^[a-zA-Z0-9_./-]+(\s|\|)")
_STOPWORDS = {
    "a", "an", "and", "are", "can", "could", "did", "do", "does", "for",
    "give", "how", "i", "in", "is", "my", "of", "on", "please", "show",
    "tell", "the", "that", "this", "to", "was", "we", "were", "what",
    "when", "where", "which", "who", "why", "will", "with", "would", "you",
}


def looks_like_pasted_output(text: str) -> bool:
    """Heuristic: multi-line input with prompt/command lines is likely a paste."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    prompt_lines = sum(1 for ln in lines if _PROMPT_RE.match(ln))
    cmd_like = 0
    for ln in lines:
        if not _CMDLIKE_RE.match(ln):
            continue
        if ln.split()[0].lower() in _STOPWORDS:
            continue
        cmd_like += 1
    return prompt_lines >= 1 or cmd_like >= 2


def inject_warning() -> str:
    return (
        "  [WARNING] Input looks like pasted terminal output. Only text you typed\n"
        "  is sent to the model; nothing from this paste will be executed."
    )


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[@-Z\\-_]|\x1b[P_^].*?(?:\x1b\\)")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_output(text: str | None) -> str | None:
    """Strip terminal escape sequences and control chars from model output.

    Model output is untrusted data: a compromised or malicious server could
    embed ANSI escapes that manipulate the terminal (spoof the command, hide
    characters, trigger terminal exploits). Rendering is the only place model
    text hits the terminal, so we scrub it there.
    """
    if text is None:
        return None
    text = _ANSI_ESCAPE_RE.sub("", text)
    return _CONTROL_RE.sub("", text)
