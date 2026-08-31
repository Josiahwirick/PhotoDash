#!/usr/bin/env python3
"""Write KEY=VALUE env files compatible with bash `source` and systemd EnvironmentFile."""

from __future__ import annotations

import argparse
from pathlib import Path


def quote_env_value(value: str) -> str:
    """
    Double-quote a value so both bash `source` and systemd EnvironmentFile
    preserve it literally (no command substitution / variable expansion).
    """
    if "\n" in value or "\r" in value:
        raise ValueError("env values must not contain newlines")
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("$", "\\$")
        .replace("`", "\\`")
    )
    return f'"{escaped}"'


def write_env_file(path: Path, pairs: dict[str, str]) -> None:
    path.write_text(
        "".join(f"{key}={quote_env_value(value)}\n" for key, value in pairs.items()),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="Destination env file path")
    parser.add_argument(
        "assignments",
        nargs="+",
        help="KEY=VALUE assignments to write",
    )
    args = parser.parse_args()
    pairs: dict[str, str] = {}
    for item in args.assignments:
        if "=" not in item:
            raise SystemExit(f"Invalid assignment (expected KEY=VALUE): {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise SystemExit(f"Invalid assignment (empty key): {item!r}")
        pairs[key] = value
    write_env_file(args.path, pairs)


if __name__ == "__main__":
    main()
