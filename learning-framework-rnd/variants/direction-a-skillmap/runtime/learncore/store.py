"""Versioned JSON documents with compare-and-swap writes.

Used for small, frequently read state (plan, competency map, learner profile).
Large or append-only facts belong in the journal.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable

from .fsutil import StaleWrite, file_lock, load_json_state, write_json


class Document:
    def __init__(self, path: str | Path, default_factory: Callable[[], dict] = dict):
        self.path = Path(path)
        self.lock_path = self.path.parent / "state.lock"
        self._default_factory = default_factory
        self._repaired_from_backup = False
        self._repair_note = ""

    # -- reads -----------------------------------------------------------
    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict:
        value, repaired, note = load_json_state(self.path, None)
        self._repaired_from_backup = repaired
        self._repair_note = note
        if value is None:
            value = self._default_factory()
            value.setdefault("version", 0)
        if not isinstance(value, dict):
            raise ValueError(f"{self.path} must contain a JSON object")
        value.setdefault("version", 0)
        return value

    def version(self) -> int:
        return int(self.load().get("version", 0))

    # -- writes ----------------------------------------------------------
    def save(self, data: dict, *, expected_version: int | None = None, backup: bool = True) -> dict:
        """Persist ``data``; reject the write if ``expected_version`` is outdated."""
        with file_lock(self.lock_path):
            current = self.load()
            current_version = int(current.get("version", 0))
            if expected_version is not None and current_version != int(expected_version):
                raise StaleWrite(
                    f"{self.path.name} changed since it was read "
                    f"(expected version {expected_version}, found {current_version}). "
                    "Re-run to rebuild the change on fresh state."
                )
            payload = copy.deepcopy(data)
            payload["version"] = current_version + 1
            write_json(self.path, payload, backup=backup)
            self._repaired_from_backup = False
            self._repair_note = ""
            return payload

    def update(self, mutate: Callable[[dict], dict | None]) -> dict:
        """Atomic read-modify-write. ``mutate`` may edit and/or return a dict."""
        with file_lock(self.lock_path):
            current = self.load()
            working = copy.deepcopy(current)
            result = mutate(working)
            payload = result if isinstance(result, dict) else working
            payload["version"] = int(current.get("version", 0)) + 1
            write_json(self.path, payload, backup=True)
            self._repaired_from_backup = False
            self._repair_note = ""
            return payload

    # -- diagnostics -----------------------------------------------------
    def repair_note(self) -> str:
        return self._repair_note if self._repaired_from_backup else ""


def merge_counts(base: dict, delta: dict) -> dict:
    out = dict(base)
    for key, value in delta.items():
        if isinstance(value, (int, float)) and isinstance(out.get(key), (int, float)):
            out[key] = out.get(key, 0) + value
        else:
            out[key] = value
    return out
