"""Vendor the pinned shared core into a variant, or verify that a variant's copy matches.

Usage:
    python shared/vendor_core.py --variant variants/direction-a-skillmap
    python shared/vendor_core.py --check variants/direction-a-skillmap
    python shared/vendor_core.py --check-all
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "core-v1" / "learncore"
PIN = ROOT / "core-v1" / "CORE_VERSION"


def read_version() -> str:
    text = (CORE / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("CORE_VERSION"):
            return line.split('"')[1]
    return "unknown"


def vendor(variant: Path) -> Path:
    target = variant / "runtime" / "learncore"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(CORE, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return target


def files_of(base: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(base)): p.read_bytes()
        for p in base.rglob("*.py")
        if "__pycache__" not in p.parts
    }


def check(variant: Path) -> list[str]:
    target = variant / "runtime" / "learncore"
    if not target.exists():
        return [f"{variant}: missing runtime/learncore"]
    expected, actual = files_of(CORE), files_of(target)
    problems = []
    for name, data in expected.items():
        if name not in actual:
            problems.append(f"{variant}: missing {name}")
        elif actual[name] != data:
            problems.append(f"{variant}: differs from core-v1: {name}")
    extra = set(actual) - set(expected)
    for name in sorted(extra):
        # variants may add modules, but must not silently modify core files
        problems.append(f"{variant}: extra file in vendored core: {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant")
    parser.add_argument("--check")
    parser.add_argument("--check-all", action="store_true")
    parser.add_argument("--root", default=str(ROOT.parent / "variants"))
    args = parser.parse_args(argv)
    version = read_version()
    if args.variant:
        variant = Path(args.variant)
        target = vendor(variant)
        (variant / "runtime" / "CORE_VERSION").write_text(version + "\n", encoding="utf-8")
        print(f"vendored learncore {version} -> {target}")
        return 0
    problems: list[str] = []
    if args.check:
        problems += check(Path(args.check))
    if args.check_all:
        for variant in sorted(Path(args.root).glob("direction-*")):
            problems += check(variant)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"core {version}: all vendored copies match")
    return 0


if __name__ == "__main__":
    sys.exit(main())
