"""CLI helpers: UTF-8 stdio, a single error envelope, and small formatting tools."""

from __future__ import annotations

import json
import os
import sys
import traceback

from .fsutil import LearnError, LockTimeout, StaleWrite

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_STATE = 3
EXIT_ENV = 4


def setup_stdio() -> None:
    """Force UTF-8 so Chinese mentor text survives Windows consoles and pipes."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def out(text: str = "") -> None:
    print(text)


def warn(text: str) -> None:
    print(text, file=sys.stderr)


def main(handler, argv: list[str] | None = None, *, prog: str = "learn") -> int:
    """Run ``handler(argv) -> int`` with consistent error handling."""
    setup_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        return int(handler(args) or 0)
    except SystemExit as exc:  # argparse
        return int(exc.code or 0)
    except (LockTimeout, StaleWrite) as exc:
        warn(f"{prog}: state changed concurrently: {exc}")
        return EXIT_STATE
    except LearnError as exc:
        warn(f"{prog}: {exc}")
        return EXIT_STATE
    except KeyboardInterrupt:
        warn(f"{prog}: interrupted; nothing was half-written (writes are atomic).")
        return 130
    except Exception as exc:  # pragma: no cover - defensive
        if os.environ.get("LEARNARK_DEBUG"):
            traceback.print_exc()
        warn(f"{prog}: unexpected error: {type(exc).__name__}: {exc}")
        return EXIT_ENV


def emit_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def table(rows: list[list[str]], headers: list[str] | None = None) -> str:
    data = ([headers] if headers else []) + [[str(c) for c in row] for row in rows]
    if not data:
        return ""
    widths = [max(len(str(row[i])) for row in data) for i in range(len(data[0]))]
    lines = []
    for index, row in enumerate(data):
        line = "  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
        lines.append(line)
        if index == 0 and headers:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)


def bullet_list(items: list[str], bullet: str = "-") -> str:
    return "\n".join(f"{bullet} {item}" for item in items)


def kv_block(pairs: list[tuple[str, object]]) -> str:
    width = max((len(str(k)) for k, _ in pairs), default=0)
    return "\n".join(f"{str(k).ljust(width)}  {v}" for k, v in pairs)


def confirm_yes(prompt: str, default: bool = False) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{prompt} {suffix} ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes", "是", "好")
