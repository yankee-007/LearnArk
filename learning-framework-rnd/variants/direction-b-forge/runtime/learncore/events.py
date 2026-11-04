"""Append-only learning journal with idempotent writes.

Design notes
------------
* The journal is the authoritative record of what happened during learning.
  Snapshots (see :mod:`learncore.store`) are a cache that can always be rebuilt.
* Every mutating command passes a ``dedupe_key``. Re-running a command after a
  timeout or an interrupted shell therefore cannot double count progress.
* The dedupe index is written under the same lock as the journal append, so two
  processes racing with the same key produce exactly one event.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from . import clock
from .fsutil import StateCorrupt, append_jsonl, file_lock, read_jsonl, write_json


def new_id(prefix: str = "ev") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class Journal:
    def __init__(self, journal_path: str | Path, index_path: str | Path | None = None):
        self.path = Path(journal_path)
        self.index_path = Path(index_path) if index_path else self.path.parent / "dedupe.json"
        self.lock_path = self.path.parent / "journal.lock"

    # -- index -----------------------------------------------------------
    def _load_index(self) -> dict:
        try:
            import json

            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (ValueError, OSError):
            # A damaged index must never lose events: rebuild from the journal.
            return self._rebuild_index_from_journal()
        return data if isinstance(data, dict) else {}

    def _rebuild_index_from_journal(self) -> dict:
        index: dict[str, str] = {}
        for event in read_jsonl(self.path):
            key = event.get("dedupe_key")
            if key and key not in index:
                index[key] = event.get("id", "")
        return index

    # -- writes ----------------------------------------------------------
    def append(
        self,
        kind: str,
        payload: dict | None = None,
        *,
        dedupe_key: str | None = None,
        actor: str = "system",
        at: str | None = None,
        simulated: bool | None = None,
    ) -> dict | None:
        """Append an event. Returns ``None`` when ``dedupe_key`` was already used."""
        with file_lock(self.lock_path):
            index = self._load_index()
            if dedupe_key and dedupe_key in index:
                return None
            events = read_jsonl(self.path)
            seq = (events[-1].get("seq", 0) + 1) if events else 1
            event = {
                "id": new_id(),
                "seq": seq,
                "at": at or clock.now_iso(),
                "kind": kind,
                "actor": actor,
                "simulated": clock.is_simulated() if simulated is None else bool(simulated),
                "dedupe_key": dedupe_key,
                "payload": payload or {},
            }
            append_jsonl(self.path, event)
            if dedupe_key:
                index[dedupe_key] = event["id"]
                write_json(self.index_path, index)
            return event

    # -- reads -----------------------------------------------------------
    def all(self) -> list[dict]:
        events = read_jsonl(self.path)
        for ev in events:
            if "kind" not in ev:
                raise StateCorrupt(f"journal event missing 'kind': {ev}")
        return events

    def of_kind(self, *kinds: str) -> list[dict]:
        wanted = set(kinds)
        return [e for e in self.all() if e.get("kind") in wanted]

    def has(self, dedupe_key: str) -> bool:
        if not dedupe_key:
            return False
        if self.index_path.exists():
            return dedupe_key in self._load_index()
        return any(e.get("dedupe_key") == dedupe_key for e in self.all())

    def count(self) -> int:
        return len(self.all())

    def last(self, n: int = 1) -> list[dict]:
        return self.all()[-n:]

    def integrity(self) -> dict:
        """Cheap consistency report used by ``doctor``."""
        events = self.all()
        seqs = [e.get("seq") for e in events]
        ids = [e.get("id") for e in events]
        keys = [e.get("dedupe_key") for e in events if e.get("dedupe_key")]
        problems = []
        if seqs != sorted(seqs):
            problems.append("event sequence is not monotonic")
        if len(seqs) != len(set(seqs)):
            problems.append("duplicate event sequence numbers")
        if len(ids) != len(set(ids)):
            problems.append("duplicate event ids")
        if len(keys) != len(set(keys)):
            problems.append("duplicate dedupe keys in journal")
        return {
            "events": len(events),
            "last_at": events[-1]["at"] if events else None,
            "problems": problems,
        }
