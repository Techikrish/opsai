"""CLI entry point for opsai."""

from __future__ import annotations

import argparse
import getpass
import sys

from opsai import __version__
from opsai import config as cfg
from opsai import keyring_store
from opsai.client import OpsaiError, chat_completion
from opsai.output import render
from opsai.prompt import build_messages, parse_answer
from opsai.security import inject_warning, looks_like_pasted_output


def _resolve_key(flag_key: str | None) -> str | None:
    if flag_key:
        return flag_key
    env_key = cfg.api_key_from_env()
    if env_key:
        return env_key
    return keyring_store.get_api_key()


def _run_query(query: str, settings: dict, api_key: str | None, history: list[dict] | None = None) -> dict:
    messages = build_messages(query, history)
    reply = chat_completion(
        base_url=settings["base_url"],
        model=settings["model"],
        api_key=api_key,
        messages=messages,
    )
    return parse_answer(reply)


def _warn_no_key() -> None:
    print(
        "  [NO API KEY] Set OPSAI_API_KEY (or OPENAI_API_KEY), run `opsai --config`\n"
        "  to store one in your OS keyring, or pass --api-key for this session only.\n",
        file=sys.stderr,
    )


def cmd_one_shot(query: str, settings: dict, api_key: str | None) -> int:
    if not api_key:
        _warn_no_key()
        return 1
    if looks_like_pasted_output(query):
        print(inject_warning())
    try:
        answer = _run_query(query, settings, api_key)
    except OpsaiError as exc:
        print(f"  [ERROR] {exc}", file=sys.stderr)
        return 1
    render(answer["command"], answer["info"])
    return 0


def cmd_chat(settings: dict, api_key: str | None) -> int:
    if not api_key:
        _warn_no_key()
        return 1
    history: list[dict] = []
    print(f"  opsai chat ({settings['model']} @ {settings['base_url']}) - 'exit' or Ctrl-D to quit\n")
    while True:
        try:
            query = input("opsai> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            continue
        if query.lower() in ("exit", "quit"):
            break
        if looks_like_pasted_output(query):
            print(inject_warning())
        try:
            answer = _run_query(query, settings, api_key, history)
        except OpsaiError as exc:
            print(f"  [ERROR] {exc}", file=sys.stderr)
            continue
        history.append({"role": "user", "content": query})
        render(answer["command"], answer["info"])
        if answer["command"]:
            history.append({"role": "assistant", "content": answer["command"]})
    return 0


def cmd_config() -> int:
    base_url = input(f"Base URL [{cfg.DEFAULT_BASE_URL}]: ").strip() or cfg.DEFAULT_BASE_URL
    model = input(f"Model [{cfg.DEFAULT_MODEL}]: ").strip() or cfg.DEFAULT_MODEL
    print("  API key (stored in OS keyring, never written to disk) - blank to skip:")
    key = getpass.getpass("> ").strip()
    if key:
        if keyring_store.store_api_key(key):
            print("  API key stored in OS keyring.")
        else:
            print(
                "  No keyring backend available - key NOT stored. Use the\n"
                "  OPSAI_API_KEY environment variable instead (see README).",
                file=sys.stderr,
            )
    cfg.save_config(base_url, model)
    print(f"  Saved settings to {cfg.CONFIG_FILE} (non-secret only).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="opsai",
        description="AI terminal command helper: ask in plain English, get the exact command.",
    )
    parser.add_argument("query", nargs="?", help="plain-English question, e.g. 'reboot into bios'")
    parser.add_argument("--chat", action="store_true", help="interactive multi-turn session")
    parser.add_argument("--config", action="store_true", help="set up base_url, model and API key")
    parser.add_argument("--base-url", help="OpenAI-compatible API base URL (overrides config/env)")
    parser.add_argument("--model", help="model name (overrides config/env)")
    parser.add_argument("--api-key", help="API key for this session only (never stored)")
    parser.add_argument("--version", action="version", version=f"opsai {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.config:
        return cmd_config()

    settings = cfg.resolve_config(
        {"base_url": args.base_url, "model": args.model}
    )
    api_key = _resolve_key(args.api_key)

    if args.chat:
        return cmd_chat(settings, api_key)
    if not args.query:
        build_parser().print_help()
        return 1
    return cmd_one_shot(args.query, settings, api_key)


if __name__ == "__main__":
    sys.exit(main())
