"""Project state: paths, documents, and defaults.

Every fact the runtime trusts lives in ``.learnark/``.  Snapshots are caches that
can always be rebuilt from the journal; they are written atomically and keep a
``.bak`` so corruption is recoverable without losing a successful write.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from learncore import clock
from learncore.events import Journal
from learncore.fsutil import (
    LearnError,
    StateCorrupt,
    file_lock,
    find_project_root,
    read_jsonl,
)
from learncore.store import Document

from . import SCHEMA_VERSION
from .const import MENTORS, REVIEW_EVERY

# One cross-process write lock per project.  Every command that can modify the
# project takes it, so two terminals cannot interleave state saves and lose a
# learner message or a handoff.  The file is intentionally outside the journal
# lock: the journal lock only covers one append, not a whole read-modify-write.
PROJECT_LOCK_NAME = "project.lock"
LOCK_TIMEOUT_ENV = "LEARNARK_LOCK_TIMEOUT"
DEFAULT_LOCK_TIMEOUT = 60.0


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def learnark(self) -> Path:
        return self.root / ".learnark"

    @property
    def project_json(self) -> Path:
        return self.learnark / "project.json"

    @property
    def state_dir(self) -> Path:
        return self.learnark / "state"

    @property
    def studio_json(self) -> Path:
        return self.state_dir / "studio.json"

    @property
    def capability_json(self) -> Path:
        return self.state_dir / "capability.json"

    @property
    def reviews_json(self) -> Path:
        return self.state_dir / "reviews.json"

    @property
    def session_json(self) -> Path:
        return self.state_dir / "session.json"

    @property
    def mentors_dir(self) -> Path:
        return self.state_dir / "mentors"

    @property
    def journal_path(self) -> Path:
        return self.learnark / "journal" / "events.jsonl"

    @property
    def dedupe_path(self) -> Path:
        return self.learnark / "journal" / "dedupe.json"

    @property
    def handoff_dir(self) -> Path:
        return self.learnark / "handoff"

    @property
    def latest_handoff(self) -> Path:
        return self.handoff_dir / "latest.md"

    @property
    def sessions_dir(self) -> Path:
        return self.root / "sessions"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def usage_path(self) -> Path:
        return self.learnark / "usage.jsonl"

    def mentor_notes(self, mentor: str) -> Path:
        return self.mentors_dir / f"{mentor}.json"

    def ensure_dirs(self) -> None:
        for folder in (
            self.learnark,
            self.state_dir,
            self.mentors_dir,
            self.learnark / "journal",
            self.handoff_dir,
            self.sessions_dir,
            self.artifacts_dir,
        ):
            folder.mkdir(parents=True, exist_ok=True)


def resolve_root(project: str | None) -> Path:
    """Resolve the project root from ``--project``, env, or by walking upwards."""
    explicit = project or os.environ.get("LEARNARK_PROJECT")
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not (path / ".learnark").is_dir():
            raise LearnError(f"{path} is not a LearnArk project (missing .learnark/). Run 'init' first.")
        return path
    return find_project_root()


def open_paths(project: str | None = None) -> Paths:
    return Paths(resolve_root(project))


# -- cross-process write lock --------------------------------------------
def project_lock_path(paths: Paths) -> Path:
    return paths.learnark / PROJECT_LOCK_NAME


def lock_timeout(default: float = DEFAULT_LOCK_TIMEOUT) -> float:
    """Lock timeout in seconds; tests may shorten it via the environment."""
    raw = (os.environ.get(LOCK_TIMEOUT_ENV) or "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


@contextmanager
def project_lock(paths: Paths):
    """Serialise one mutating command against every other process."""
    with file_lock(project_lock_path(paths), timeout=lock_timeout()):
        yield


class ProjectJournal(Journal):
    """Journal hardened against the two crash windows core cannot see.

    1. A process killed mid-append can leave a torn final line without a
       newline.  ``read_jsonl`` tolerates that while it stays last, but the next
       append would concatenate onto it, hide the new event and make the file
       permanently unreadable.  We truncate the incomplete line before writing
       and record ``journal_tail_repaired``.
    2. The journal append is durable before the dedupe index is rewritten.  A
       crash in between leaves a valid but incomplete index, which would let a
       retried command double-count.  The index is reconciled against the
       journal (the authoritative stream) on every load.
    """

    def _repair_torn_tail(self) -> dict | None:
        path = self.path
        try:
            if not path.stat().st_size:
                return None
            with path.open("rb") as probe:
                probe.seek(-1, os.SEEK_END)
                if probe.read(1) == b"\n":
                    return None
            data = path.read_bytes()
        except OSError:
            return None
        cut = data.rfind(b"\n")
        keep = cut + 1 if cut >= 0 else 0
        removed = data[keep:]
        # A complete JSON object without a trailing newline is a *valid* last
        # event (e.g. restored from git); keep it and just terminate the line.
        try:
            parsed = json.loads(removed.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, dict):
            try:
                with path.open("ab") as handle:
                    handle.write(b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError:
                return None
            return None
        try:
            with path.open("r+b") as handle:
                handle.truncate(keep)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            return None
        return {
            "removed_bytes": len(removed),
            "removed_tail": removed[:80].decode("utf-8", "replace"),
            "path": path.name,
        }

    def _load_index(self) -> dict:
        index = super()._load_index()
        try:
            events = read_jsonl(self.path)
        except StateCorrupt:
            return index
        from_journal: dict[str, str] = {}
        for event in events:
            key = event.get("dedupe_key")
            if key and key not in from_journal:
                from_journal[key] = event.get("id", "")
        # Any mismatch means the index is stale; the journal always wins.
        if set(index) != set(from_journal):
            return from_journal
        return index

    def append(self, kind, payload=None, *, dedupe_key=None, actor="system", at=None, simulated=None):
        repaired = self._repair_torn_tail()
        event = super().append(
            kind,
            payload,
            dedupe_key=dedupe_key,
            actor=actor,
            at=at,
            simulated=simulated,
        )
        if repaired:
            super().append("journal_tail_repaired", repaired, actor="runtime")
        return event


def journal(paths: Paths) -> Journal:
    return ProjectJournal(paths.journal_path, paths.dedupe_path)


# -- document factories ---------------------------------------------------
def project_doc(paths: Paths) -> Document:
    return Document(paths.project_json, _default_project)


def studio_doc(paths: Paths) -> Document:
    return Document(paths.studio_json, _default_studio)

def capability_doc(paths: Paths) -> Document:
    return Document(paths.capability_json, default_capability)


def reviews_doc(paths: Paths) -> Document:
    return Document(paths.reviews_json, default_reviews)


def session_doc(paths: Paths) -> Document:
    return Document(paths.session_json, default_session)


def notes_doc(paths: Paths, mentor: str) -> Document:
    return Document(paths.mentor_notes(mentor), lambda: default_notes(mentor))


# -- defaults -------------------------------------------------------------
def _default_project() -> dict:
    return {"schema_version": SCHEMA_VERSION}


def _default_studio() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": clock.now_iso(),
        "current_mentor": "planner",
        "plan": {},
        "plan_changes": [],
        "mentors": {
            mentor: {
                "last_active": None,
                "notes_path": f".learnark/state/mentors/{mentor}.json",
                "open_loops": [],
                "turns": 0,
                "last_handoff_proposal": None,
            }
            for mentor in MENTORS
        },
        "last_handoff_id": None,
        "review_counter": {"since_review": 0, "every": REVIEW_EVERY},
        "dedupe": {"activity_ids": {}, "analogy_hashes": {}, "do_not_redo": []},
        "session": default_session(),
        "flags": {"plan_state": "empty", "force_new_representation": None, "exam_reask": False},
    }


def default_capability() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "nodes": [],
        "self_reports": [],
        "pending_exam": None,
    }


def default_reviews() -> dict:
    return {"schema_version": SCHEMA_VERSION, "reviews": []}


def default_session() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": None,
        "mentor": None,
        "started_at": None,
        "ended_at": None,
        "turn_index": 0,
        "offline": None,
        "path": None,
        "turns": [],
    }


def default_notes(mentor: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "mentor": mentor,
        "notes": [],
        "taught": [],
        "avoid": [],
        "conclusions": [],
        "style": "",
        "next_suggestion": "",
        "turns": 0,
    }


def load_with_repair(doc: Document) -> tuple[dict, str]:
    """Load a document and surface a repair note when ``.bak`` was used."""
    try:
        data = doc.load()
    except StateCorrupt:
        raise
    except ValueError as exc:
        # A syntactically valid JSON value of the wrong shape (``[]``, ``"x"``)
        # is corruption too; report it as a state error instead of a traceback.
        raise StateCorrupt(f"{doc.path.name} 内容损坏：{exc}") from exc
    return data, doc.repair_note()


def get_plan(studio: dict) -> dict:
    plan = studio.get("plan") or {}
    if not isinstance(plan, dict):
        plan = {}
    plan.setdefault("plan_id", "plan-v1")
    plan.setdefault("version", 1)
    plan.setdefault("authority", "planner")
    plan.setdefault("week_goals", [])
    plan.setdefault("steps", [])
    plan.setdefault("current_objective", {})
    plan.setdefault("minutes_per_week", 12)
    plan.setdefault("hash", "")
    return plan
