"""Output rendering: command + short info + details + optional danger warnings."""

from __future__ import annotations

import sys
from typing import TextIO

from opsai.security import danger_flags, sanitize_output

_NONE_HEADER = "  [NO COMMAND]"
_DANGER_HEADER = "  [WARNING]"
_DETAILS_HEADER = "  Details"


def render(command: str | None, info: str, details: str = "", out: TextIO | None = None) -> None:
    """Print the command prominently, then the info line and a details block.
    Output is scrubbed of terminal escape sequences before display."""
    out = out or sys.stdout
    command = sanitize_output(command)
    info = sanitize_output(info) or ""
    details = sanitize_output(details) or ""
    if command:
        flags = danger_flags(command)
        print(f"\n  > {command}", file=out)
        if flags:
            print(
                f"  {_DANGER_HEADER} This command involves: {', '.join(flags)}.",
                file=out,
            )
        if info:
            print(f"  {info}", file=out)
        if details:
            print(f"  {_DETAILS_HEADER}", file=out)
            for line in details.splitlines():
                print(f"    {line}", file=out)
        print(file=out)
    else:
        print(f"\n  {_NONE_HEADER} {info}\n", file=out)
        if details:
            for line in details.splitlines():
                print(f"  {line}", file=out)
            print(file=out)