"""Unit tests for opsai. All API calls are mocked - no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from opsai import cli, config as cfg, keyring_store
from opsai.client import OpsaiError, _validate_url, chat_completion
from opsai.output import render
from opsai.prompt import build_messages, extract_json, parse_answer
from opsai.security import danger_flags, looks_like_pasted_output, sanitize_output


class TestExtractJson:
    def test_plain_json(self):
        assert extract_json('{"command": "ls", "info": "x"}')["command"] == "ls"

    def test_json_fenced(self):
        text = '```json\n{"command": "pwd", "info": "y"}\n```'
        assert extract_json(text)["command"] == "pwd"

    def test_fence_with_junk_around(self):
        text = 'Sure!\n```\n{"command": "ls -la", "info": "z"}\n```\nHope that helps!'
        assert extract_json(text)["command"] == "ls -la"

    def test_json_with_leading_prose(self):
        text = 'Here you go: {"command": "df -h", "info": "disk usage"} thanks'
        assert extract_json(text)["command"] == "df -h"

    def test_garbage_returns_none(self):
        assert extract_json("lorem ipsum dolor") is None

    def test_empty_returns_none(self):
        assert extract_json("") is None


class TestParseAnswer:
    def test_valid(self):
        answer = parse_answer('{"command": "ls", "info": "list files"}')
        assert answer == {"command": "ls", "info": "list files"}

    def test_command_null_when_missing(self):
        answer = parse_answer('{"info": "nothing to do"}')
        assert answer["command"] is None

    def test_non_string_command_ignored(self):
        answer = parse_answer('{"command": 42, "info": "oops"}')
        assert answer["command"] is None

    def test_unparseable(self):
        answer = parse_answer("no json here at all")
        assert answer["command"] is None
        assert answer["info"]


class TestBuildMessages:
    def test_system_prompt_is_fixed(self):
        messages = build_messages("reboot into bios")
        assert messages[0]["role"] == "system"
        assert "JSON" in messages[0]["content"]
        assert messages[-1] == {"role": "user", "content": "reboot into bios"}
        assert len(messages) == 2

    def test_history_is_included(self):
        history = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "echo hi"}]
        messages = build_messages("second", history)
        assert len(messages) == 4


class TestConfig:
    def test_precedence_flags_over_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPSAI_MODEL", "env-model")
        monkeypatch.delenv("OPSAI_BASE_URL", raising=False)
        cfg.CONFIG_FILE = tmp_path / "config.json"
        monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "config.json")
        cfg.save_config("https://file.example/v1", "file-model")
        merged = cfg.resolve_config({"model": "flag-model"})
        assert merged["model"] == "flag-model"
        assert merged["base_url"] == "https://file.example/v1"

    def test_defaults(self, monkeypatch, tmp_path):
        for var in ("OPSAI_BASE_URL", "OPSAI_MODEL"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "nope.json")
        merged = cfg.resolve_config()
        assert merged["base_url"] == cfg.DEFAULT_BASE_URL
        assert merged["model"] == cfg.DEFAULT_MODEL

    def test_config_file_never_contains_api_key(self, tmp_path):
        cfg.CONFIG_FILE = tmp_path / "config.json"
        cfg.save_config(cfg.DEFAULT_BASE_URL, cfg.DEFAULT_MODEL)
        content = (tmp_path / "config.json").read_text()
        assert "key" not in content.lower()

    def test_env_api_key_priority(self, monkeypatch):
        monkeypatch.setenv("OPSAI_API_KEY", "env-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
        assert cfg.api_key_from_env() == "env-key"


class TestKeyringStore:
    def test_redact_hides_keys(self):
        text = "error: sk-abcdefghijklmnopqrstuvwxyz123456 failed"
        assert "[REDACTED]" in keyring_store.redact(text)
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in keyring_store.redact(text)

    def test_redact_leaves_normal_text(self):
        assert keyring_store.redact("just a normal error message") == "just a normal error message"


class TestDangerFlags:
    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "sudo apt update",
            "mkfs.ext4 /dev/sdb1",
            "dd if=/dev/zero of=/dev/sda",
            "curl http://x.sh | sh",
            "shutdown now",
            "fdisk /dev/sda",
        ],
    )
    def test_dangerous_commands_flagged(self, command):
        assert danger_flags(command)

    @pytest.mark.parametrize(
        "command",
        [
            "systemctl reboot --firmware-setup",
            "git log --oneline",
            "kubectl get pods",
            "docker ps",
        ],
    )
    def test_safe_commands_not_flagged(self, command):
        assert not danger_flags(command)


class TestPasteDetection:
    def test_multiline_command_like_paste(self):
        text = "user@host:~\n$ ls -la\ndrwxr-xr-x 2 root root"
        assert looks_like_pasted_output(text)

    def test_single_line_not_a_paste(self):
        assert not looks_like_pasted_output("how do I reboot into bios")

    def test_plain_multiline_question_not_a_paste(self):
        text = "how do I list pods\nin all namespaces please"
        assert not looks_like_pasted_output(text)


class TestClient:
    def test_validate_url_accepts_https(self):
        assert _validate_url("https://api.openai.com/v1") == "https://api.openai.com/v1"

    def test_validate_url_rejects_http_remote(self):
        with pytest.raises(OpsaiError):
            _validate_url("http://evil.example/v1")

    def test_validate_url_accepts_localhost_http(self):
        assert _validate_url("http://localhost:11434/v1") == "http://localhost:11434/v1"

    def test_validate_url_rejects_embedded_credentials(self):
        with pytest.raises(OpsaiError):
            _validate_url("https://user:pass@api.example.com/v1")

    def test_redirects_are_not_followed(self, monkeypatch):
        seen = {}

        def fake_post(url, headers=None, json=None, timeout=None, allow_redirects=True):
            seen["allow_redirects"] = allow_redirects
            return _FakeResponse(302, {"error": {}})

        monkeypatch.setattr("opsai.client.requests.post", fake_post)
        with pytest.raises(OpsaiError) as exc:
            chat_completion("https://api.openai.com/v1", "m", "sk-key", [])
        assert "redirect" in str(exc.value).lower()
        assert seen["allow_redirects"] is False

    def test_successful_chat(self, monkeypatch):
        def fake_post(url, headers=None, json=None, timeout=None, allow_redirects=True):
            assert headers["Authorization"] == "Bearer secret-key"
            assert "api-key" not in json["messages"][0]["content"]
            return _FakeResponse(200, {"choices": [{"message": {"content": '{"command": "ls"}'}}]})

        monkeypatch.setattr("opsai.client.requests.post", fake_post)
        reply = chat_completion("https://api.openai.com/v1", "gpt-4o-mini", "secret-key", [{"role": "user", "content": "hi"}])
        assert "ls" in reply

    def test_http_401_masked(self, monkeypatch):
        monkeypatch.setattr(
            "opsai.client.requests.post",
            lambda *a, **k: _FakeResponse(401, {"error": {"message": "invalid key sk-supersecret"}}),
        )
        with pytest.raises(OpsaiError) as exc:
            chat_completion("https://api.openai.com/v1", "m", "sk-badkey", [])
        assert "401" in str(exc.value)
        assert "sk-supersecret" not in str(exc.value)

    def test_connection_error_hint(self, monkeypatch):
        import requests

        def boom(*a, **k):
            raise requests.exceptions.ConnectionError()

        monkeypatch.setattr("opsai.client.requests.post", boom)
        with pytest.raises(OpsaiError) as exc:
            chat_completion("https://api.openai.com/v1", "m", None, [])
        assert "connect" in str(exc.value)


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class TestSanitizeOutput:
    def test_strips_ansi_csi_sequences(self):
        text = "\x1b[31mred\x1b[0m ls"
        assert sanitize_output(text) == "red ls"

    def test_strips_osc_sequences(self):
        text = "ls\x1b]0;fake-title\x07 -la"
        assert sanitize_output(text) == "ls -la"

    def test_strips_c0_control_chars(self):
        assert sanitize_output("a\x00b\x07c\x1bd") == "abcd"

    def test_keeps_normal_text_and_newlines(self):
        text = "git log --oneline\nShows history"
        assert sanitize_output(text) == text

    def test_none_passthrough(self):
        assert sanitize_output(None) is None


class TestOutput:
    def test_render_safe_command(self, capsys):
        render("git log --oneline", "Shows commit history in one line")
        captured = capsys.readouterr().out
        assert "> git log --oneline" in captured
        assert "Shows commit history" in captured
        assert "WARNING" not in captured

    def test_render_danger_warning(self, capsys):
        render("rm -rf /tmp/x", "Deletes directory")
        captured = capsys.readouterr().out
        assert "WARNING" in captured

    def test_render_no_command(self, capsys):
        render(None, "No safe command exists")
        captured = capsys.readouterr().out
        assert "NO COMMAND" in captured
        assert "No safe command exists" in captured

    def test_render_strips_terminal_escape_injection(self, capsys):
        render("ls\x1b[31m", "fake\x1b]0;spoof\x07")
        captured = capsys.readouterr().out
        assert "\x1b" not in captured
        assert "ls" in captured
        assert "spoof" not in captured


class TestConfigFileSecurity:
    def test_config_file_mode_is_0600(self, tmp_path):
        cfg.CONFIG_FILE = tmp_path / "config.json"
        cfg.save_config(cfg.DEFAULT_BASE_URL, cfg.DEFAULT_MODEL)
        assert (cfg.CONFIG_FILE).stat().st_mode & 0o777 == 0o600

    def test_no_leftover_tmp_files(self, tmp_path):
        cfg.CONFIG_FILE = tmp_path / "config.json"
        cfg.save_config(cfg.DEFAULT_BASE_URL, cfg.DEFAULT_MODEL)
        leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
        assert leftovers == []

    def test_symlink_at_config_path_not_followed(self, tmp_path):
        victim = tmp_path / "victim"
        victim.write_text("original")
        cfg.CONFIG_FILE = tmp_path / "config.json"
        (tmp_path / "config.json").symlink_to(victim)
        cfg.save_config("https://x.example/v1", "model-x")
        assert victim.read_text() == "original"
        assert not (tmp_path / "config.json").is_symlink()
        assert json.loads((tmp_path / "config.json").read_text())["model"] == "model-x"


class TestNoExecution:
    """Security invariant: the shipped package must contain no execution."""

    def test_no_subprocess_or_os_system_in_source(self):
        import os

        root = Path(os.path.dirname(cli.__file__)).parent.parent
        src = Path(root) / "src" / "opsai"
        for file in src.rglob("*.py"):
            code = file.read_text(encoding="utf-8")
            assert "subprocess" not in code, f"{file} uses subprocess"
            assert "os.system" not in code, f"{file} uses os.system"
            assert "eval(" not in code, f"{file} uses eval"
            assert "exec(" not in code, f"{file} uses exec"

    def test_cli_messages_never_send_extra_data(self, monkeypatch):
        import os

        for var in ("OPSAI_BASE_URL", "OPSAI_MODEL", "OPSAI_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setattr(cfg, "CONFIG_FILE", Path("/nonexistent/config.json"))
        monkeypatch.setattr(cli, "_resolve_key", lambda k: "test-key")
        sent = []

        def fake_chat(base_url, model, api_key, messages):
            sent.append(messages)
            return json.dumps({"command": "echo ok", "info": "fine"})

        monkeypatch.setattr(cli, "chat_completion", fake_chat)
        rc = cli.main(["list files"])
        assert rc == 0
        payload = sent[0]
        assert payload[0]["role"] == "system"
        assert payload[1]["content"] == "list files"
        assert len(payload) == 2


class TestCli:
    def test_no_args_shows_help(self, capsys, monkeypatch):
        monkeypatch.delenv("OPSAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr("opsai.keyring_store.get_api_key", lambda: None)
        rc = cli.main([])
        assert rc == 1
        assert "opsai" in capsys.readouterr().out

    def test_one_shot_no_key_warns(self, capsys, monkeypatch):
        monkeypatch.delenv("OPSAI_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr("opsai.keyring_store.get_api_key", lambda: None)
        rc = cli.main(["list files"])
        assert rc == 1
        assert "NO API KEY" in capsys.readouterr().err

    def test_one_shot_success(self, capsys, monkeypatch):
        monkeypatch.setattr("opsai.cli._resolve_key", lambda k: "test-key")

        def fake_chat(base_url, model, api_key, messages):
            return '{"command": "systemctl reboot --firmware-setup", "info": "Boots into UEFI"}'

        monkeypatch.setattr(cli, "chat_completion", fake_chat)
        rc = cli.main(["reboot into bios"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "systemctl reboot --firmware-setup" in out
        assert "UEFI" in out

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli.main(["--version"])
        assert exc.value.code == 0
        assert "opsai" in capsys.readouterr().out
