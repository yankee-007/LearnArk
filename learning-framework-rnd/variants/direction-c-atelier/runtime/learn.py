"""LearnArk Atelier CLI entry point.

Usage:
    python runtime/learn.py <command> [options]
    learn.cmd <command> [options]

The vendored ``learncore`` package sits next to this file; the direction's own
logic lives in ``atelier/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from atelier.commands import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
