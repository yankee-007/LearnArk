"""Project layout, state documents, scaffolding and the session markdown writer.

The journal (``.learnark/journal/events.jsonl``) is authoritative; the JSON
documents under ``.learnark/state/`` are a cache that can be rebuilt.  Every
write goes through :class:`learncore.fsutil.atomic_write_text` /
:class:`learncore.store.Document`, so an interrupted process never leaves a
half-written snapshot behind.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

from learncore import clock
from learncore.events import Journal
from learncore.fsutil import (
    LearnError,
    StateCorrupt,
    atomic_write_text,
    file_lock,
    find_project_root,
    short_hash,
)
from learncore.store import Document

import sm_model


SCHEMA_VERSION = sm_model.SCHEMA_VERSION
EXTRA_GITIGNORE = """.learnark/usage.jsonl
.learnark/project.lock
.learnark/state/*.lock
.learnark/journal/*.lock
.learnark/handoff/*.tmp
"""


def _read_backup(path: Path) -> dict | None:
    """Return ``<name>.bak`` as a JSON object, or ``None`` when unusable."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def repair_journal_tail(path: str | os.PathLike) -> str:
    """Drop a torn final journal line left by an interrupted append.

    ``learncore.events`` tolerates a torn tail when *reading*, but the next append
    would concatenate onto the fragment and corrupt that line for good (the whole
    journal then fails to load).  This repair runs before a command touches the
    journal: every complete event is kept, only the incomplete last line is
    dropped, and a last event that merely lost its trailing newline is preserved.
    The returned note is surfaced by ``status`` / ``doctor`` so the damage is
    reported instead of being silently hidden.

    A malformed line *before* the end is real corruption and raises
    :class:`StateCorrupt` rather than being discarded.
    """
    path = Path(path)
    lock_path = path.parent / "journal.lock"
    with file_lock(lock_path):
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            return ""
        if not raw:
            return ""
        text = raw.decode("utf-8", errors="replace")
        lines = text.split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        if not lines:
            return ""
        keep = len(lines)
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                if index != len(lines) - 1:
                    raise StateCorrupt(
                        f"{path} line {index + 1} is not valid JSON: {exc}"
                    ) from exc
                keep = index
        notes: list[str] = []
        if keep < len(lines):
            notes.append(
                f"journal 尾部有 {len(lines) - keep} 行不完整记录（写入被中断的残留），"
                "已丢弃残片；其余事件保留。"
            )
        needs_newline = not raw.endswith(b"\n")
        if keep < len(lines) or (needs_newline and keep > 0):
            body = "\n".join(lines[:keep])
            atomic_write_text(path, f"{body}\n" if body else "")
        return "".join(notes)


def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "learnark"


def _default_project() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "slug": "learnark",
        "goal": "",
        "template": sm_model.DEFAULT_TEMPLATE,
        "minutes_per_week": sm_model.default_minutes_per_week(sm_model.DEFAULT_TEMPLATE),
        "learner": {
            "name": "learner",
            "self_report": [],
            "diagnosis": {"status": "pending", "round": 0, "probes": [], "completed_at": None},
        },
        "constraints": {},
        "created_at": None,
        "updated_at": None,
    }


def _default_plan() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "current_node": None,
        "stage": None,
        "stage_started_at": None,
        "stage_progress": {},
        "session_id": None,
        "session_started_at": None,
        "session_file": None,
        "session_mentor": None,
        "session_active": False,
        "turn_index": 0,
        "minutes_budget": None,
        "session_goal": None,
        "mode": "idle",
        "review_queue": [],
        "mentor_override": None,
        "open_questions": [],
        "last_decision": {},
        "updated_at": None,
    }


def _default_memory() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "preferences": {"preferred_minutes": 20, "prefers_examples": False},
        "traits_observed": [],
        "help_profile": {"avg_help_level": None, "independent_rate": None, "turns": 0, "trend": "flat"},
        "updated_at": None,
    }


class Project:
    """Paths + lazily loaded documents for one learning project."""

    def __init__(self, root: str | os.PathLike, variant_dir: str | os.PathLike | None = None):
        self.root = Path(root).resolve()
        self.variant_dir = Path(variant_dir).resolve() if variant_dir else Path(__file__).resolve().parent.parent
        self.dot = self.root / ".learnark"
        self.state_dir = self.dot / "state"
        self.journal_dir = self.dot / "journal"
        self.handoff_dir = self.dot / "handoff"
        self.sessions_dir = self.root / "sessions"
        self.artifacts_dir = self.root / "artifacts"
        self.journal_path = self.journal_dir / "events.jsonl"
        self.dedupe_path = self.journal_dir / "dedupe.json"
        self.lock_path = self.dot / "project.lock"
        self.usage_path = self.dot / "usage.jsonl"
        self._docs: dict[str, Document] = {}
        self._repairs: list[str] = []

    # -- paths -----------------------------------------------------------
    def rel(self, path: str | os.PathLike) -> str:
        return Path(path).resolve().relative_to(self.root).as_posix()

    @property
    def project_path(self) -> Path:
        return self.dot / "project.json"

    @property
    def map_path(self) -> Path:
        return self.state_dir / "map.json"

    @property
    def plan_path(self) -> Path:
        return self.state_dir / "plan.json"

    @property
    def memory_path(self) -> Path:
        return self.state_dir / "memory.json"

    def exists(self) -> bool:
        return self.project_path.is_file()

    # -- documents -------------------------------------------------------
    def _doc(self, key: str, path: Path, factory) -> Document:
        if key not in self._docs:
            self._docs[key] = Document(path, factory)
        return self._docs[key]

    @property
    def project_doc(self) -> Document:
        return self._doc("project", self.project_path, _default_project)

    @property
    def map_doc(self) -> Document:
        return self._doc("map", self.map_path, lambda: sm_model.new_map(sm_model.DEFAULT_TEMPLATE))

    @property
    def plan_doc(self) -> Document:
        return self._doc("plan", self.plan_path, _default_plan)

    @property
    def memory_doc(self) -> Document:
        return self._doc("memory", self.memory_path, _default_memory)

    @property
    def journal(self) -> Journal:
        return Journal(self.journal_path, self.dedupe_path)

    def load(self) -> dict:
        """Load every document once; remember any backup repairs."""
        project = self.project_doc.load()
        template = project.get("template") or sm_model.DEFAULT_TEMPLATE
        extra_notes: list[str] = []
        map_data = self._load_map(template, extra_notes)
        plan = self.plan_doc.load()
        memory = self.memory_doc.load()
        self._repairs = [
            note
            for note in (
                self.project_doc.repair_note(),
                self.map_doc.repair_note(),
                self.plan_doc.repair_note(),
                self.memory_doc.repair_note(),
            )
            if note
        ] + extra_notes
        return {
            "project": project,
            "map": map_data,
            "plan": plan,
            "memory": memory,
            "repairs": list(self._repairs),
        }

    def _load_map(self, template: str, notes: list[str]) -> dict:
        """Load ``map.json``, restoring the level history from ``.bak`` if lost.

        ``map.json`` is the only document whose loss cannot be rebuilt from the
        journal (levels, evidence and review dates live here).  If the snapshot
        is missing or has no nodes, a usable ``map.json.bak`` is promoted and the
        repair is reported.  Without a backup the template map is rebuilt, but
        the downgrade is stated rather than silently accepted.
        """
        backup_path = self.map_path.with_name(self.map_path.name + ".bak")
        existed = self.map_path.is_file()
        map_data = self.map_doc.load()
        if existed and map_data.get("nodes"):
            sm_model.ensure_map_shape(map_data, template)
            return map_data
        backup = _read_backup(backup_path)
        backup_template = (backup or {}).get("template")
        if backup is not None and backup.get("nodes") and backup_template in (None, template):
            map_data = self.map_doc.save(backup, expected_version=None, backup=False)
            notes.append(
                "map.json 缺少节点（半写或丢失），已从备份 map.json.bak 恢复，等级未丢。"
            )
            sm_model.ensure_map_shape(map_data, template)
            return map_data
        if not existed:
            notes.append(
                "map.json 不存在且没有可用备份，已按模板重建；等级从 L0 开始。"
            )
        else:
            notes.append(
                "map.json 没有节点且没有可用备份，已按模板重建；等级从 L0 开始。"
            )
        return sm_model.new_map(template)

    def save_project(self, data: dict) -> dict:
        return self.project_doc.save(data, expected_version=data.get("version"))

    def save_map(self, data: dict) -> dict:
        return self.map_doc.save(data, expected_version=data.get("version"))

    def save_plan(self, data: dict) -> dict:
        return self.plan_doc.save(data, expected_version=data.get("version"))

    def save_memory(self, data: dict) -> dict:
        return self.memory_doc.save(data, expected_version=data.get("version"))

    @property
    def repairs(self) -> list[str]:
        return list(self._repairs)

    # -- locking ---------------------------------------------------------
    @contextmanager
    def lock(self, timeout: float = 20.0):
        """Serialise mutating commands for this project."""
        with file_lock(self.lock_path, timeout=timeout):
            yield

    # -- helpers ---------------------------------------------------------
    def ensure_dirs(self) -> None:
        for path in (self.dot, self.state_dir, self.journal_dir, self.handoff_dir, self.sessions_dir, self.artifacts_dir):
            path.mkdir(parents=True, exist_ok=True)

    def autosave_artifact(self, text: str, *, node_id: str, stage: str = "apply") -> str | None:
        """Save a writing submission as an artifact (email template).

        Writing nodes produce text, not code; requiring the learner to copy the
        email into a file cost an extra turn in round-06.  The runtime stores the
        submitted text itself and uses that path as evidence.
        """
        text = (text or "").strip()
        if not text:
            return None
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        stamp = clock.now().strftime("%Y%m%d-%H%M%S")
        path = self.artifacts_dir / f"{node_id.lower()}-{stage}-{stamp}.md"
        atomic_write_text(path, text + "\n")
        return self.rel(path)

    def artifact_info(self, artifact: str | None) -> dict | None:
        """Resolve a mentor-reported artifact path.

        Mentors often report just the basename (``parse_record.py``) while the
        file actually sits in ``artifacts/``.  We try the path as given relative
        to the project root, then relative to ``artifacts/``, then the basename
        under ``artifacts/``; only when none of them exists is this really an
        ``artifact_missing``.  The returned ``path`` is normalised to a
        project-relative POSIX path so evidence is stable.
        """
        if not artifact:
            return None
        raw = str(artifact).strip().replace("\\", "/").strip()
        if not raw or raw.startswith("/") or re.match(r"^[A-Za-z]:", raw) or ".." in Path(raw).parts:
            return {
                "path": raw,
                "given": raw,
                "exists": False,
                "sha256": None,
                "error": "artifact path must be relative and inside the project",
                "tried": [],
            }
        name = Path(raw).name
        candidates = [raw]
        if not raw.startswith("artifacts/"):
            candidates.append(f"artifacts/{raw}")
        if name and f"artifacts/{name}" not in candidates:
            candidates.append(f"artifacts/{name}")
        tried: list[str] = []
        for candidate in candidates:
            path = (self.root / candidate).resolve()
            try:
                path.relative_to(self.root)
            except ValueError:
                continue
            tried.append(candidate)
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                return {
                    "path": path.relative_to(self.root).as_posix(),
                    "given": raw,
                    "exists": True,
                    "sha256": digest,
                    "error": None,
                    "tried": tried,
                }
        return {"path": raw, "given": raw, "exists": False, "sha256": None, "error": "artifact missing", "tried": tried}

    def handoff_text(self, handoff: dict) -> str:
        def bullets(items, empty="- （无）"):
            if not items:
                return empty
            if isinstance(items, str):
                items = [items]
            return "\n".join(f"- {item}" for item in items)

        lines = [
            f"# Handoff · {handoff.get('from', '?')} → {handoff.get('to', '?')}",
            "",
            f"- from: {handoff.get('from')}",
            f"- to: {handoff.get('to')}",
            f"- at: {handoff.get('at')}",
            f"- project: {handoff.get('slug')} · template {handoff.get('template')}",
            f"- node: {handoff.get('node') or '（未定）'} · stage: {handoff.get('stage') or '（未定）'} · activity: {handoff.get('activity_id') or '（无）'}",
            f"- reason: {handoff.get('reason')}",
            "",
            "## what_tried",
            bullets(handoff.get("what_tried")),
            "",
            "## unresolved",
            bullets(handoff.get("unresolved")),
            "",
            "## next",
            bullets(handoff.get("next")),
            "",
        ]
        if handoff.get("context_digest"):
            lines += ["## context_digest", str(handoff["context_digest"]), ""]
        return "\n".join(lines)

    def write_handoff(self, handoff: dict) -> Path:
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        text = self.handoff_text(handoff)
        atomic_write_text(self.handoff_dir / "latest.md", text)
        stamp = (handoff.get("at") or clock.now_iso()).replace(":", "").replace("-", "")[:15]
        archive = self.handoff_dir / f"{stamp}-{handoff.get('from', 'x')}-to-{handoff.get('to', 'y')}.md"
        atomic_write_text(archive, text)
        return self.handoff_dir / "latest.md"

    def latest_handoff_text(self, max_lines: int = 40) -> str:
        path = self.handoff_dir / "latest.md"
        if not path.is_file():
            return ""
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return ""
        return "\n".join(lines[:max_lines])

    # -- sessions --------------------------------------------------------
    def new_session(self, mentor: str) -> dict:
        stamp = clock.now().strftime("%Y%m%d-%H%M%S")
        session_id = f"{stamp}-{short_hash(str(self.root) + stamp, 6)}"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{stamp}-{mentor}.md"
        path = self.sessions_dir / filename
        counter = 2
        while path.exists():
            path = self.sessions_dir / f"{stamp}-{mentor}-{counter}.md"
            counter += 1
        header = [
            f"# {clock.now().strftime('%Y-%m-%d %H:%M')} — SkillMap · {sm_model.MENTOR_LABELS.get(mentor, mentor)}",
            f"- session: {session_id}  mentor: {mentor}  activity: (diagnose)" if mentor == "navigator" else f"- session: {session_id}  mentor: {mentor}  activity: —",
            f"- started: {clock.now_iso()}  offline: false",
            "",
        ]
        atomic_write_text(path, "\n".join(header) + "\n")
        return {
            "session_id": session_id,
            "session_started_at": clock.now_iso(),
            "session_file": self.rel(path),
            "session_mentor": mentor,
            "session_active": True,
            "turn_index": 0,
        }

    def append_session_turn(self, plan: dict, *, mentor: str, activity_id: str, learner_text: str, mentor_text: str, record: list[str]) -> str:
        rel_path = plan.get("session_file")
        if not rel_path:
            info = self.new_session(mentor)
            plan.update(info)
            rel_path = info["session_file"]
        path = self.root / rel_path
        blocks = [
            "",
            f"## 学习者 · turn {int(plan.get('turn_index', 0)) + 1} · {activity_id or '-'}",
            learner_text.strip() or "（空）",
            "",
            f"## 导师 · {sm_model.MENTOR_LABELS.get(mentor, mentor)}",
            mentor_text.strip() or "（空）",
            "",
            "## 记录",
        ]
        blocks += [f"- {item}" for item in record] or ["- （无）"]
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        atomic_write_text(path, existing.rstrip() + "\n" + "\n".join(blocks) + "\n")
        return rel_path

    def append_session_system(
        self, plan: dict, *, mentor: str, activity_id: str, trigger: str, mentor_text: str, record: list[str]
    ) -> str:
        """Record a runtime event (start/continue/switch) without faking a learner turn.

        Openings used to be written as ``## 学习者 · 开始学习``, which polluted the
        authoritative session with utterances the learner never made and inflated
        turn counts.  They are now a ``系统`` block and never touch ``turn_index``.
        """
        rel_path = plan.get("session_file")
        if not rel_path:
            info = self.new_session(mentor)
            plan.update(info)
            rel_path = info["session_file"]
        path = self.root / rel_path
        blocks = [
            "",
            f"## 系统 · {trigger} · {activity_id or '-'}",
            f"- mentor: {mentor} · session: {plan.get('session_id')}",
            "",
            f"## 导师 · {sm_model.MENTOR_LABELS.get(mentor, mentor)}",
            mentor_text.strip() or "（空）",
            "",
            "## 记录",
        ]
        blocks += [f"- {item}" for item in record] or ["- （无）"]
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        atomic_write_text(path, existing.rstrip() + "\n" + "\n".join(blocks) + "\n")
        return rel_path


# ---------------------------------------------------------------------------
# scaffolding
# ---------------------------------------------------------------------------
def resolve_project_root(project_arg: str | None) -> Path:
    if project_arg:
        root = Path(project_arg).expanduser()
        if not (root / ".learnark").is_dir():
            raise LearnError(f"{root} is not a LearnArk project (missing .learnark/). Run `init --dir {root}` first.")
        return root.resolve()
    env = os.environ.get("LEARNARK_PROJECT")
    if env:
        root = Path(env).expanduser()
        if not (root / ".learnark").is_dir():
            raise LearnError(f"LEARNARK_PROJECT={root} has no .learnark/ directory.")
        return root.resolve()
    return find_project_root()


def init_project(
    root: Path,
    *,
    goal: str | None,
    template: str,
    minutes_per_week: int | None,
    learner_name: str | None,
) -> dict:
    """Create (or repair) a SkillMap project.  Safe to run twice."""
    root = root.resolve()
    project = Project(root)
    existed = project.exists()
    project.ensure_dirs()
    spec = sm_model.template_spec(template)
    now = clock.now_iso()
    created_files: list[str] = []

    if not existed:
        data = _default_project()
        data.update(
            {
                "slug": slugify(root.name),
                "goal": (goal or spec["default_goal"]).strip(),
                "template": template,
                "minutes_per_week": int(minutes_per_week or spec["default_minutes_per_week"]),
                "created_at": now,
                "updated_at": now,
                "core_version": _core_version(project.variant_dir),
                "constraints": {
                    "single_topic": True,
                    "no_free_chat": True,
                    "prereq_gate": sm_model.GATE,
                    "stages": list(sm_model.STAGES),
                    "review_intervals": list(sm_model.REVIEW_INTERVALS),
                    # Threshold, not a budget: below it a session runs <=2 probes
                    # and the task estimate is capped by the actual `--minutes`.
                    "short_session_minutes": sm_model.SHORT_DIAGNOSIS_MINUTES,
                    "short_diagnosis_probes": sm_model.SHORT_DIAGNOSIS_PROBES,
                    "review_single_minutes": sm_model.SHORT_SESSION_MINUTES,
                },
            }
        )
        data["learner"]["name"] = learner_name or "learner"
        project.project_doc.save(data)
        created_files.append(".learnark/project.json")
    else:
        data = project.project_doc.load()
        if goal and not data.get("goal"):
            data["goal"] = goal.strip()
        if minutes_per_week:
            data["minutes_per_week"] = int(minutes_per_week)
        if learner_name:
            data["learner"]["name"] = learner_name
        data["updated_at"] = now
        project.project_doc.save(data)

    template = data.get("template") or template
    if not project.map_path.exists():
        project.save_map(sm_model.new_map(template))
        created_files.append(".learnark/state/map.json")
    else:
        map_data = project.map_doc.load()
        before = len(map_data.get("nodes") or [])
        sm_model.ensure_map_shape(map_data, template)
        if len(map_data.get("nodes") or []) != before or not map_data.get("schema_version"):
            project.save_map(map_data)
            created_files.append(".learnark/state/map.json (repaired)")

    if not project.plan_path.exists():
        project.save_plan(_default_plan())
        created_files.append(".learnark/state/plan.json")
    if not project.memory_path.exists():
        project.save_memory(_default_memory())
        created_files.append(".learnark/state/memory.json")

    journal = project.journal
    journal_repair = repair_journal_tail(project.journal_path)
    journal.append(
        "project_created",
        {
            "slug": data.get("slug"),
            "goal": data.get("goal"),
            "template": template,
            "minutes_per_week": data.get("minutes_per_week"),
            "schema_version": SCHEMA_VERSION,
        },
        dedupe_key=f"project_created:{data.get('slug')}",
        actor="runtime",
    )
    if existed:
        journal.append(
            "init_repeated",
            {"slug": data.get("slug")},
            dedupe_key=f"init_repeated:{data.get('slug')}:{clock.today()}",
            actor="runtime",
        )

    for rel, writer in (
        ("AGENTS.md", agents_md),
        ("README.md", readme_md),
    ):
        path = root / rel
        if not path.exists():
            atomic_write_text(path, writer(data, template, entry=str(project.variant_dir / "runtime" / "learn.py")))
            created_files.append(rel)
        elif not existed:
            atomic_write_text(path, writer(data, template, entry=str(project.variant_dir / "runtime" / "learn.py")))
            created_files.append(rel)

    gitignore = root / ".gitignore"
    if not gitignore.exists():
        atomic_write_text(gitignore, EXTRA_GITIGNORE)
        created_files.append(".gitignore")
    else:
        text = gitignore.read_text(encoding="utf-8", errors="replace")
        missing = [line for line in EXTRA_GITIGNORE.splitlines() if line.strip() and line not in text.splitlines()]
        if missing:
            with gitignore.open("a", encoding="utf-8", newline="\n") as fh:
                if not text.endswith("\n"):
                    fh.write("\n")
                fh.write("\n".join(missing) + "\n")

    return {"project": project, "data": data, "created": created_files, "existed": existed, "journal_repair": journal_repair}


def _core_version(variant_dir: Path) -> str:
    path = variant_dir / "runtime" / "CORE_VERSION"
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"


def agents_md(data: dict, template: str, entry: str = r"<variant>\runtime\learn.py") -> str:
    goal = data.get("goal") or sm_model.default_goal(template)
    return f"""# AGENTS.md — how an agent must work in this SkillMap project

This folder is a LearnArk **SkillMap** learning project. The authoritative record
of what happened is `.learnark/journal/events.jsonl`; `.learnark/state/*.json` is
a cache. Never invent sessions, attempts, levels or handoffs.

## First action (always)

```powershell
python "{entry}" start --project .
```

`start` reads: `.learnark/project.json`, `.learnark/state/map.json`,
`.learnark/state/plan.json`, the journal and `.learnark/handoff/latest.md`.
It prints where learning stopped and the one task to do next. Do not ask the
learner to re-explain their progress — read it.

If this project was copied to another machine, replace the path above with this
machine's `variants/direction-a-skillmap/runtime/learn.py` (or use `learn.cmd`).

## Then follow the mentor protocol

- The runtime decides the active mentor from the stage:
  explain→concept, drill/apply→coach, check→examiner, diagnosis/review/handoff→navigator.
- Every mentor turn must end with exactly one `learn-update` block:

```learn-update
{{"help_level": 0, "attempt": {{"activity_id": "{_sample_node(template)}-explain", "correct": null}}, "misconception": null, "next": "next step", "mastery_delta": 0, "artifact": null}}
```

- `activity_id` must be `<node>-<stage>` or one of `diagnose`, `review`, `handoff`.
- `correct` is judged by the mentor; the **runtime** applies the rules: only
  `correct=true` with `help_level<=1` can raise a level, at most +1 per turn.
  `help_level>=2` is recorded as `assisted_completion` and caps at L1.
- `help_level` must be `0` in `check`; a higher value voids the turn.
- Never claim mastery. Levels change only through runtime events.

## Commands available to you

`start`, `say "<learner words>"`, `status --json`, `map --json`, `next --json`,
`review`, `pause`, `switch <mentor>`, `diagnose`, `sync`, `doctor`, `export --out FILE`.
Add `--project .` from outside the folder, `--offline` for the scripted mentor.

## Hard rules

1. Do not edit `.learnark/state/*.json` or the journal by hand; use the CLI.
2. Do not write levels or "mastered" into any file.
3. If a command fails, report the exit code and stderr instead of retrying blindly.
4. Learner self-report is a hypothesis, never evidence.
5. Goal for this project: {goal}
"""


def _sample_node(template: str) -> str:
    nodes = sm_model.template_spec(template)["nodes"]
    return nodes[0][0]


def readme_md(data: dict, template: str, entry: str = r"<variant>\runtime\learn.py") -> str:
    goal = data.get("goal") or sm_model.default_goal(template)
    first = sm_model.template_spec(template)["nodes"][0][0]
    probe_count = sm_model.total_probes(template)
    node_count = len(sm_model.template_spec(template)["nodes"])
    return f"""# SkillMap · {sm_model.template_spec(template)['title']}

目标：{goal}

## 现在输入什么

```powershell
python "{entry}" start
```

本模板共 {node_count} 个节点；第一次会做 {probe_count} 个诊断探针（可以回答“不知道”或“跳过”）。
之后每次只推进一个节点的一个阶段：讲解 → 操练 → 应用 → 检查。
新项目从 {first} 开始；先修没到 L1（可用门槛）的节点不会出现在 `next` 里。
诊断若把某个锚点判为 L1 且它的先修就绪，会直接从那节点的 apply 起步（跳过讲解与操练）。
如果项目被复制到别的机器，把上面路径换成那台机器的
`variants/direction-a-skillmap/runtime/learn.py`（或直接用 `learn.cmd`）。

## 常用命令

| 命令 | 作用 |
| --- | --- |
| `start [--minutes 20]` | 恢复或开始今天的学习 |
| `say "你的回答"` | 回答导师 / 交产物路径 |
| `status [--json]` | 我学到哪、哪里弱、下一步 |
| `map [--json]` | {node_count} 节点能力地图与等级 |
| `next [--json]` | 下一个节点与 3 条理由 |
| `review` | 到期复习队列（走 check） |
| `pause` | 收工，写交接并提交 git |
| `switch <mentor>` | 切换导师（受阶段限制） |
| `diagnose` | 重新跑诊断 |
| `sync` / `doctor` / `export --out FILE` | 同步 / 自检 / 导出档案 |

学习记录在 `.learnark/`（状态与事件）、`sessions/`（每次会话）、`artifacts/`（产物）。
没有远程时 `sync` 只做本地提交，并明确告诉你 `pushed=no`。
离线模式（`--offline` 或 `LEARNARK_LLM=mock`）用脚本导师，输出带 `[离线脚本导师]`，
不代表真实教学质量。
"""


def gitignore_text() -> str:
    return EXTRA_GITIGNORE
