"""System prompt construction and strict JSON response extraction.

Model output is untrusted: parse_answer NEVER raises and falls back to
extracting a command from prose when the model ignores the JSON contract
(small local models frequently do in multi-turn chat).
"""

from __future__ import annotations

import json
import re
from typing import Any

SYSTEM_PROMPT = """You are a terminal command assistant. The user asks in plain English for shell commands and how-to questions.

Rules:
- Reply with a SINGLE JSON object only. No markdown, no code fences, no prose, no apologies.
- Format: {"command": "<the shell command>", "info": "<1-2 line note on what it does>", "details": "<3-6 line explanation: prerequisites, steps, flags, gotchas>"}
- The command must be a real, safe, standard command. Never fabricate flags.
- For how-to/setup questions, give the most useful single command plus the setup steps in details.
- If no sensible or safe command exists, reply {"command": null, "info": "<brief reason>", "details": "<explanation>"}.
- Never suggest destructive or malicious commands (data destruction, remote code execution, malware).
- Prefer non-sudo variants; only include sudo when genuinely required.
- For questions unrelated to terminals or commands, reply {"command": null, "info": "<brief answer>", "details": ""}.
"""


def build_messages(query: str, history: list[dict] | None = None) -> list[dict]:
    """Build the message list sent to the API: fixed system prompt + history + query."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history or []:
        messages.append(turn)
    messages.append({"role": "user", "content": query})
    return messages


_FENCE_RE = re.compile(r"```(?:json|sh|bash|shell)?\s*(.*?)```", re.DOTALL)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

_KNOWN_BINARIES = [
    "kubectl", "aws", "gcloud", "az", "docker", "docker-compose", "podman",
    "helm", "terraform", "ansible", "git", "systemctl", "service", "curl",
    "wget", "ssh", "scp", "rsync", "tar", "grep", "sed", "awk", "python",
    "python3", "pip", "pip3", "npm", "yarn", "pnpm", "npx", "go", "cargo",
    "make", "gcc", "java", "mvn", "node", "ruby", "gem", "apt", "apt-get",
    "dnf", "yum", "pacman", "brew", "snap", "chmod", "chown", "ln", "cp",
    "mv", "rm", "mkdir", "touch", "cat", "echo", "export", "source", "kill",
    "ps", "top", "htop", "df", "du", "free", "mount", "umount", "fdisk",
    "parted", "ip", "ifconfig", "iptables", "ufw", "journalctl", "ls", "pwd",
    "whoami", "id", "hostname", "uname", "date", "nohup", "screen", "tmux",
    "vim", "nano", "less", "more", "head", "tail", "wc", "sort", "uniq",
    "cut", "tr", "xargs", "find", "locate", "which", "file", "stat", "lsof",
    "ss", "netstat", "traceroute", "ping", "dig", "nslookup", "nginx",
    "firewall-cmd", "firewalld", "sysctl", "openssl", "kubeadm", "minikube",
    "kind", "eksctl", "sam", "sls", "serverless",
]
_BINARY_RE = re.compile(r"^(?:" + "|".join(sorted(_KNOWN_BINARIES, key=len, reverse=True)) + r")\b")
_BINARY_INLINE_RE = re.compile(r"\b(?:" + "|".join(sorted(_KNOWN_BINARIES, key=len, reverse=True)) + r")\s")


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


def _command_from_line(line: str) -> str | None:
    line = line.strip().strip("`").strip()
    if not line or line.startswith(("#", "$", ">")):
        return None
    line = re.sub(r"^[-*•]\s+", "", line)
    line = re.sub(r"^(run|use|try|example|e\.g\.|command)\s*:\s*", "", line, flags=re.IGNORECASE)
    if _BINARY_RE.match(line):
        return line
    match = _BINARY_INLINE_RE.search(line)
    if match:
        cmd = line[match.start():]
        cmd = re.split(r"[.,]\s|\s+and\s+|\s+then\s+", cmd, maxsplit=1)[0]
        return cmd.strip()
    return None


def _first_command(text: str) -> str | None:
    """First command-like line from JSON-ish text, code fences, then the whole text."""
    match = re.search(r'"command"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1).replace('\\"', '"').strip()
    for fence_match in _FENCE_RE.finditer(text):
        for line in fence_match.group(1).splitlines():
            cmd = _command_from_line(line)
            if cmd:
                return cmd
    for line in text.splitlines():
        cmd = _command_from_line(line)
        if cmd:
            return cmd
    return None


def _prose_details(text: str, command: str | None) -> tuple[str, str]:
    """Split prose into a short info line and the remaining details."""
    cleaned = re.sub(r"```(?:json|sh|bash|shell)?|```", "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = re.sub(r"^[Ss]ure[!.,]?\s*", "", cleaned)
    cleaned = re.sub(r"^(Here's|Here is|The (best|simplest|easiest) way|You can|To do (this|that))\s*[:,]?\s*", "", cleaned)
    if command:
        cleaned = re.sub(re.escape(command), "", cleaned, flags=re.IGNORECASE)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned) if s.strip()]
    if len(sentences) <= 1 and ":" in cleaned:
        before, _, after = cleaned.partition(":")
        before, after = before.strip(), after.strip()
        if before and after:
            sentences = [before, after]
    info = sentences[0] if sentences else ""
    details = " ".join(sentences[1:]) if len(sentences) > 1 else ""
    if not info and command:
        info = "Runs the command to accomplish the task."
    return info[:200], details[:1200]


def fallback_parse(text: str) -> dict[str, Any] | None:
    """Parse prose/markdown replies (small models ignore the JSON contract).

    Extracts the first command-like line and uses the surrounding prose as
    info/details. Returns None only if no command-like line exists at all.
    """
    if not text or not text.strip():
        return None
    command = _first_command(text)
    if not command:
        return None
    info, details = _prose_details(text, command)
    return {"command": command, "info": info, "details": details}


def parse_answer(text: str) -> dict[str, Any]:
    """Turn model output into {command, info, details}. Never raises."""
    parsed = extract_json(text)
    if parsed is None:
        parsed = fallback_parse(text)
        if parsed is not None:
            return parsed
        return {
            "command": None,
            "info": "The model returned an unparseable response. Try again.",
            "details": "",
        }
    command = parsed.get("command")
    info = parsed.get("info")
    details = parsed.get("details")
    if not isinstance(command, str) or not command.strip():
        command = None
    if not isinstance(info, str) or not info.strip():
        info = ""
    if not isinstance(details, str) or not details.strip():
        details = ""
    return {"command": command, "info": info, "details": details}