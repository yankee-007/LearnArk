"""Forge 状态层：项目路径、状态文档、journal、会话、交接、模板。

约定（见 design.md §7）：
* ``.learnark/`` 是项目标记目录；``journal/events.jsonl`` 是权威事实流；
  ``state/*.json`` 是可重建的快照，但每次写入都带 ``schema_version`` 与 ``version``。
* 模板只在 ``templates/<id>.md`` 的 ```` ```json template ```` 围栏块里权威存在，
  其余中文小节是给人看的说明，本模块不解析。
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from learncore import clock
from learncore.events import Journal
from learncore.fsutil import (
    LearnError,
    StateCorrupt,
    StaleWrite,
    append_jsonl,
    atomic_write_text,
    file_lock,
    find_project_root,
    sha256_text,
    write_json,
)
from learncore.store import Document

SCHEMA_VERSION = 1
VARIANT_ID = "direction-b-forge"
VARIANT_VERSION = "0.2.4"
CORE_VERSION_FILE = "CORE_VERSION"

VARIANT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = VARIANT_DIR / "templates"
MENTORS_DIR = VARIANT_DIR / "mentors"
MOCK_FIXTURE = VARIANT_DIR / "tests" / "fixtures" / "mentor_script.jsonl"

MENTORS = ("coach", "critic", "guide")
DEFAULT_ALLOWED_EXT = (".py", ".md", ".json", ".txt", ".jsonl")
# 这些维度即使分数达标，note 里没有行号/段落级证据也照样开缺口卡（design §5）。
NARRATIVE_DIMS = ("explainability", "scenario_fit")
SELF_REPORT = "self_report"

_TEMPLATE_BLOCK = re.compile(
    r"```json[ \t]+template[ \t]*\r?\n(?P<body>.*?)```",
    re.DOTALL | re.IGNORECASE,
)


class UsageError(LearnError):
    """Bad command-line input (exit code 2)."""


class ForgeError(LearnError):
    """Project-level state problem (exit code 3)."""


def now_iso() -> str:
    return clock.now_iso()


def short_sha(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# 模板
# --------------------------------------------------------------------------- #
def list_templates() -> list[str]:
    if not TEMPLATES_DIR.is_dir():
        return []
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.md"))


def load_template(template_id: str) -> dict:
    """Read the fenced ```json template block; prose is ignored."""
    available = list_templates()
    if not template_id:
        template_id = "agent-dev"
    path = TEMPLATES_DIR / f"{template_id}.md"
    if not path.is_file():
        raise UsageError(f"未知模板 {template_id!r}；可选：{', '.join(available) or '(无)'}")
    text = path.read_text(encoding="utf-8")
    match = _TEMPLATE_BLOCK.search(text)
    if not match:
        raise ForgeError(f"模板 {path.name} 缺少 ```json template 围栏块")
    try:
        data = json.loads(match.group("body"))
    except json.JSONDecodeError as exc:
        raise ForgeError(f"模板 {path.name} 的 json 块无法解析：{exc}") from exc
    if not isinstance(data, dict):
        raise ForgeError(f"模板 {path.name} 的 json 块必须是对象")
    milestones = data.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        raise ForgeError(f"模板 {path.name} 缺少 milestones")
    seen = set()
    for item in milestones:
        if not isinstance(item, dict) or not item.get("id"):
            raise ForgeError(f"模板 {path.name} 的里程碑缺少 id")
        if item["id"] in seen:
            raise ForgeError(f"模板 {path.name} 里程碑 id 重复：{item['id']}")
        seen.add(item["id"])
        rubric = item.get("rubric")
        if not isinstance(rubric, list) or not rubric:
            raise ForgeError(f"模板 {path.name} 的 {item['id']} 缺少 rubric")
        for dim in rubric:
            for key in ("dim", "weight", "threshold"):
                if key not in dim:
                    raise ForgeError(f"模板 {path.name} 的 {item['id']} rubric 缺少 {key}")
    return data


def rubric_signature(milestones: list[dict]) -> str:
    """Deterministic hash of dims/weights/thresholds -- rubric is read-only."""
    rows = []
    for item in milestones:
        rows.append(
            [
                item.get("id"),
                [[d.get("dim"), int(d.get("weight", 0)), int(d.get("threshold", 0))] for d in item.get("rubric", [])],
            ]
        )
    return short_sha(json.dumps(rows, ensure_ascii=False, sort_keys=True))


TEMPLATE_ALLOWED_EXT = {
    "agent-dev": [".py", ".md", ".json", ".txt", ".jsonl"],
    "email": [".md", ".txt"],
}


def parse_deliverable(text: str, template_id: str = "agent-dev") -> dict:
    """Split a template deliverable string into verifiable paths + add rules."""
    parts = [p.strip() for p in re.split(r"[+＋]", text or "") if p.strip()]
    paths = []
    for part in parts:
        candidate = part.strip().rstrip("；;，,")
        if "/" in candidate or re.search(r"\.(py|md|json|txt|jsonl)$", candidate, re.IGNORECASE):
            paths.append(candidate)
    return {
        "text": text or "",
        "paths": paths,
        "allowed_ext": list(TEMPLATE_ALLOWED_EXT.get(template_id, DEFAULT_ALLOWED_EXT)),
        "min_bytes": 20,
    }


def normalize_milestone(raw: dict, index: int, template_id: str = "agent-dev") -> dict:
    rubric = []
    for dim in raw.get("rubric", []):
        rubric.append(
            {
                "dim": str(dim["dim"]),
                "criteria": str(dim.get("criteria", "")),
                "weight": int(dim["weight"]),
                "threshold": int(dim["threshold"]),
            }
        )
    return {
        "id": str(raw["id"]),
        "title": str(raw.get("title", raw["id"])),
        "deliverable": parse_deliverable(str(raw.get("deliverable", "")), template_id),
        "activity_id": str(raw.get("activity_id", f"{raw['id']}-artifact-review")),
        "gate": dict(raw.get("gate") or {"requires_artifact": True, "requires_review": True, "requires_defense": True}),
        "rubric": rubric,
        "defense_questions": [
            {
                "qid": str(q.get("qid", f"{raw['id']}-q{i + 1}")),
                "dim": str(q.get("dim", rubric[0]["dim"])),
                "question": str(q.get("question", "")),
            }
            for i, q in enumerate(raw.get("defense_questions", []))
        ],
        "status": "active" if index == 0 else "locked",
        "artifact_ids": [],
        "review_ids": [],
        "pass_evidence": {},
        "passed_at": None,
    }


def build_brief(template: dict, *, goal: str, minutes_per_week: int, slug: str) -> dict:
    template_id = template.get("template_id", "agent-dev")
    milestones = [normalize_milestone(raw, i, template_id) for i, raw in enumerate(template["milestones"])]
    return {
        "schema_version": SCHEMA_VERSION,
        "slug": slug,
        "goal": goal,
        "template": template.get("template_id", "agent-dev"),
        "template_id": template.get("template_id", "agent-dev"),
        "display_name": template.get("display_name", ""),
        "minutes_per_week": int(minutes_per_week),
        "session_minutes_default": int(template.get("session_minutes_default", 25)),
        "constraints": list(template.get("constraints", [])),
        "artifact_dir": template.get("artifact_dir", "artifacts"),
        "score_range": list(template.get("score_range", [1, 4])),
        "pass_rule": template.get("pass_rule", "all_dims_at_or_above_threshold_and_defense_passed"),
        "defense_rules": dict(
            template.get("defense_rules")
            or {"questions_per_milestone": 3, "min_ok": 2, "heaviest_dim_must_pass": True, "decided_by": "runtime"}
        ),
        "gap_rules": dict(template.get("gap_rules") or {}),
        "rubric_sha256": rubric_signature(milestones),
        "start_profile": None,
        "milestones": milestones,
        "current_milestone": milestones[0]["id"] if milestones else None,
        "completed": False,
        "completed_at": None,
        "next": None,
        "updated_at": now_iso(),
    }


def defs_of(brief: dict, milestone: dict | None) -> tuple[dict, dict]:
    """Convenience: (rubric_by_dim, defense_rules)."""
    rubric = {d["dim"]: d for d in (milestone or {}).get("rubric", [])}
    return rubric, dict(brief.get("defense_rules") or {})


# --------------------------------------------------------------------------- #
# 项目
# --------------------------------------------------------------------------- #
def slugify(text: str, fallback: str = "forge") -> str:
    ascii_part = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    if ascii_part:
        return ascii_part[:40]
    return f"{fallback}-{short_sha(text or fallback)[:6]}"


class Project:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.learnark = self.root / ".learnark"
        self.state_dir = self.learnark / "state"
        self.journal_dir = self.learnark / "journal"
        self.handoff_dir = self.learnark / "handoff"
        self.sessions_dir = self.root / "sessions"
        self.artifacts_dir = self.root / "artifacts"
        self.journal = Journal(self.journal_dir / "events.jsonl", self.journal_dir / "dedupe.json")
        self._docs: dict[str, Document] = {}
        self._repairs: list[str] = []

    # -- construction ----------------------------------------------------
    @classmethod
    def find(cls, start: str | os.PathLike | None = None) -> "Project":
        explicit = start or os.environ.get("LEARNARK_PROJECT")
        root = find_project_root(explicit or os.getcwd())
        return cls(root)

    @classmethod
    def create(cls, root: str | Path) -> "Project":
        project = cls(root)
        for path in (
            project.learnark,
            project.state_dir,
            project.journal_dir,
            project.handoff_dir,
            project.sessions_dir,
            project.artifacts_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        return project

    # -- documents -------------------------------------------------------
    def doc(self, name: str) -> Document:
        if name not in self._docs:
            if name == "project":
                path = self.learnark / "project.json"
            elif name == "session":
                path = self.state_dir / "session.json"
            else:
                path = self.state_dir / f"{name}.json"
            self._docs[name] = Document(path, _default_for(name))
        return self._docs[name]

    def load(self, name: str) -> dict:
        value = self.doc(name).load()
        note = self.doc(name).repair_note()
        if note and note not in self._repairs:
            self._repairs.append(note)
        return value

    def save(self, name: str, data: dict, *, expected_version: int | None = None) -> dict:
        return self.doc(name).save(data, expected_version=expected_version)

    def repair_notes(self) -> list[str]:
        return list(self._repairs)

    def note_repair(self, text: str) -> None:
        """Record a user-visible recovery action (printed by status/doctor)."""
        text = str(text or "").strip()
        if text and text not in self._repairs:
            self._repairs.append(text)

    @contextmanager
    def write_lock(self, timeout: float = 60.0):
        """Serialize every mutating command on one project.

        Per-document CAS (``Document.save``) still protects individual files, but a
        command touches several documents (journal + artifacts + brief). Without a
        project-wide lock two processes can each append a *different* event and then
        race on the snapshots: the loser aborts after its event is already durable,
        which used to leave an artifact that the dedupe index refused to recreate.
        """
        raw = os.environ.get("LEARNARK_LOCK_TIMEOUT")
        if raw:
            try:
                timeout = max(0.0, float(raw))
            except ValueError:
                pass
        with file_lock(self.learnark / "write.lock", timeout=timeout):
            yield

    # -- convenience -----------------------------------------------------
    def exists(self) -> bool:
        return (self.learnark / "project.json").is_file()

    def require(self) -> "Project":
        if not self.exists():
            raise ForgeError(
                f"{self.root} 不是 LearnArk 项目（缺少 .learnark/project.json）。先运行 init。"
            )
        return self

    def rel(self, path: str | Path) -> str:
        try:
            return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
        except ValueError:
            return str(path)

    def journal_append(self, kind: str, payload: dict | None = None, *, dedupe_key: str | None = None, actor: str = "runtime"):
        self._prepare_journal_for_append()
        event = self.journal.append(kind, payload or {}, dedupe_key=dedupe_key, actor=actor)
        return event

    # -- journal durability ---------------------------------------------
    def _prepare_journal_for_append(self) -> None:
        """Drop a torn final line and heal the dedupe index before appending.

        The core journal treats an invalid *last* line as crash residue, but it
        appends after it. A new event then either merges with the torn fragment
        (and is silently tolerated as "torn" forever) or turns the fragment into a
        mid-file corruption. The journal is append-only, so an unparseable final
        line can never be a committed event; dropping it is lossless.
        """
        path = self.journal.path
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return
        if not data:
            return
        lines = data.splitlines(keepends=True)
        kept = list(lines)
        while kept:
            body = kept[-1].rstrip(b"\r\n")
            if not body.strip():
                break
            try:
                event = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                kept.pop()
                continue
            if not isinstance(event, dict) or not event.get("kind"):
                kept.pop()
                continue
            break
        if len(kept) != len(lines):
            atomic_write_bytes(path, b"".join(kept))
            self.note_repair(
                f"journal 尾部 {len(lines) - len(kept)} 行是未写完的记录，已丢弃（其余事件保留）"
            )
        elif data and not data.endswith(b"\n"):
            # The JSON itself is complete but the line terminator is missing (a
            # partial write). Keep the event and terminate it, otherwise the next
            # append would glue its JSON onto this line.
            atomic_write_bytes(path, data + b"\n")
            self.note_repair("journal 最后一行缺少换行符，已补上（事件保留）")
        self._repair_dedupe_index()

    def _repair_dedupe_index(self) -> None:
        """Re-add journal keys missing from the idempotency index.

        ``Journal.append`` writes the event before the index. If the process dies
        in between, a retry of the same command would append a second event. The
        journal already contains the authoritative key, so merge it back.
        """
        index_path = self.journal.index_path
        if not index_path.is_file():
            return
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return  # a corrupt index is rebuilt by Journal._load_index itself
        if not isinstance(index, dict):
            return
        missing: dict[str, str] = {}
        for event in self.journal.all():
            key = event.get("dedupe_key")
            if key and key not in index:
                missing[key] = event.get("id", "")
        if missing:
            index.update(missing)
            write_json(index_path, index)
            self.note_repair(f"去重索引补齐 {len(missing)} 个键（从 journal 重建）")

    # -- handoff ---------------------------------------------------------
    def latest_handoff(self) -> dict:
        path = self.handoff_dir / "latest.json"
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
            except (json.JSONDecodeError, OSError):
                pass
        md = self.handoff_dir / "latest.md"
        if md.is_file():
            return {"raw": md.read_text(encoding="utf-8"), "from": "", "to": "", "reason": "", "open_items": [], "ref": ""}
        return {}

    def write_handoff(
        self,
        *,
        from_mentor: str,
        to_mentor: str,
        reason: str,
        open_items: list[str],
        ref: str,
        next_step: str = "",
        note: str = "",
        session_id: str = "",
    ) -> dict:
        at = now_iso()
        payload = {
            "from": from_mentor,
            "to": to_mentor,
            "reason": reason,
            "open_items": [str(item) for item in open_items],
            "ref": ref,
            "next": next_step,
            "note": note,
            "session": session_id,
            "at": at,
        }
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(self.handoff_dir / "latest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        lines = [
            "# LearnArk 交接记录",
            "",
            f"- from: `{from_mentor}`",
            f"- to: `{to_mentor}`",
            f"- reason: {reason}",
            f"- ref: `{ref}`",
            f"- session: `{session_id}`",
            f"- at: {at}",
            "",
            "## open_items",
            *(f"- {item}" for item in payload["open_items"]),
            "" if payload["open_items"] else "- (无)",
            "",
            "## next",
            next_step or "(由 next 命令按状态计算)",
            "",
        ]
        if note:
            lines += ["## note", note, ""]
        atomic_write_text(self.handoff_dir / "latest.md", "\n".join(lines) + "\n")
        return payload


def _default_for(name: str):
    return {
        "project": lambda: {"schema_version": SCHEMA_VERSION},
        "brief": lambda: {"schema_version": SCHEMA_VERSION, "milestones": [], "current_milestone": None},
        "artifacts": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
        "reviews": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
        "gaps": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
        "defense": lambda: {"schema_version": SCHEMA_VERSION, "items": []},
        "session": lambda: {
            "schema_version": SCHEMA_VERSION,
            "session_id": None,
            "mentor": "coach",
            "file": None,
            "started_at": None,
            "last_active_at": None,
            "ended_at": None,
            "turn_index": 0,
            "turns": [],
            "switches": [],
        },
    }[name]


@dataclass
class State:
    """One consistent read of every snapshot, plus CAS versions for saving."""

    project: dict
    brief: dict
    artifacts: dict
    reviews: dict
    gaps: dict
    defense: dict
    session: dict
    versions: dict = field(default_factory=dict)

    # -- milestone helpers ----------------------------------------------
    @property
    def milestones(self) -> list[dict]:
        return self.brief.get("milestones", [])

    def milestone(self, mid: str | None = None) -> dict | None:
        target = mid or self.brief.get("current_milestone")
        for item in self.milestones:
            if item.get("id") == target:
                return item
        return None

    @property
    def current(self) -> dict | None:
        return self.milestone()

    def items(self, name: str) -> list[dict]:
        bucket = getattr(self, name)
        return bucket.setdefault("items", [])

    def add_item(self, name: str, item: dict) -> dict:
        self.items(name).append(item)
        return item

    def save(self, project: Project, *names: str) -> None:
        for name in names:
            data = getattr(self, name)
            saved = project.save(name, data, expected_version=self.versions.get(name))
            self.versions[name] = saved.get("version")
            setattr(self, name, saved)


def _clone_dict(value) -> dict | None:
    return copy.deepcopy(value) if isinstance(value, dict) else None


def _journal_assisted_level(events: list[dict], index: int) -> int:
    """Max coach/critic help between the previous artifact event and ``index``."""
    last = -1
    for position in range(index):
        if events[position].get("kind") == "artifact_added":
            last = position
    best = 0
    for event in events[last + 1 : index]:
        if event.get("kind") != "mentor_turn":
            continue
        payload = event.get("payload") or {}
        if payload.get("mentor") not in ("coach", "critic"):
            continue
        level = payload.get("help_level")
        if isinstance(level, int) and not isinstance(level, bool):
            best = max(best, level)
    return best


def _artifact_file_for_event(project: Project, mid: str, payload: dict) -> Path | None:
    """Find (or re-copy from the original source) the file an artifact event describes."""
    sha = str(payload.get("sha256") or "")
    if not sha:
        return None
    dest = str(payload.get("dest") or "").replace("\\", "/")
    if dest:
        candidate = project.root / dest
        if candidate.is_file() and sha256_file(candidate) == sha:
            return candidate
    base = project.root / "artifacts" / mid
    if base.is_dir():
        for candidate in sorted(base.rglob("*")):
            if candidate.is_file() and sha256_file(candidate) == sha:
                return candidate
    source = str(payload.get("source_path") or "")
    if source:
        candidate = Path(source)
        if candidate.is_file() and sha256_file(candidate) == sha:
            target = project.root / dest if dest else base / str(payload.get("path") or candidate.name)
            atomic_write_bytes(target, candidate.read_bytes())
            return target
    return None


def _reconcile_artifacts(project: Project, state: State, events: list[dict]) -> bool:
    changed = False
    for index, event in enumerate(events):
        if event.get("kind") != "artifact_added":
            continue
        payload = event.get("payload") or {}
        mid = payload.get("milestone")
        sha = payload.get("sha256")
        milestone = state.milestone(mid)
        if not mid or not sha or milestone is None:
            continue
        items = state.artifacts.setdefault("items", [])
        if any(item.get("milestone") == mid and item.get("sha256") == sha for item in items):
            continue
        path = _artifact_file_for_event(project, str(mid), payload)
        if path is None:
            project.note_repair(
                f"journal 记录了 {mid} 作品 {str(sha)[:12]}，但快照与磁盘都找不到对应文件；"
                "先运行 artifact add 重新登记或从备份恢复该文件"
            )
            continue
        item_id = f"a-{mid}-{str(sha)[:8]}"
        if any(item.get("id") == item_id for item in items):
            continue
        suffix = Path(str(payload.get("path") or path.name)).suffix.lower()
        same_suffix = [
            item
            for item in items
            if item.get("milestone") == mid and Path(str(item.get("path") or "")).suffix.lower() == suffix
        ]
        assisted = payload.get("assisted_level")
        if not isinstance(assisted, int) or isinstance(assisted, bool):
            assisted = _journal_assisted_level(events, index)
        item = {
            "id": item_id,
            "milestone": mid,
            "path": project.rel(path),
            "sha256": str(sha),
            "size": int(payload.get("size") or path.stat().st_size),
            "assisted_level": assisted,
            "supersedes": same_suffix[-1]["id"] if same_suffix else None,
            "source": str(payload.get("source") or "recovered"),
            "kind": str(payload.get("kind") or "file"),
            "note": str(payload.get("note") or "")[:200],
            "added_at": event.get("at") or now_iso(),
            "event_id": event.get("id"),
            "recovered": True,
        }
        items.append(item)
        milestone.setdefault("artifact_ids", []).append(item_id)
        project.note_repair(f"从 journal 恢复作品 {item_id}（{item['path']}），快照已补齐")
        changed = True
    return changed


def _review_from_event(event: dict, state: State) -> dict | None:
    payload = event.get("payload") or {}
    review_id = payload.get("review_id")
    mid = payload.get("milestone")
    milestone = state.milestone(mid)
    if not review_id or milestone is None:
        return None
    stored = _clone_dict(payload.get("review"))
    if stored is None:
        scores = payload.get("scores") or {}
        rubric = []
        for dim in milestone.get("rubric", []):
            name = dim.get("dim")
            if name not in scores:
                continue
            try:
                score = int(scores[name])
            except (TypeError, ValueError):
                continue
            rubric.append({"dim": name, "score": score, "note": "（从 journal 恢复：原始 note 未落盘）"})
        if not rubric:
            return None
        stored = {
            "id": review_id,
            "milestone": mid,
            "artifact_id": payload.get("artifact_id"),
            "artifact_ids": payload.get("artifact_ids") or [],
            "artifact_sha256": payload.get("artifact_sha256"),
            "rubric": rubric,
            "gap_dims": payload.get("gap_dims") or [],
            "unverified_dims": payload.get("unverified_dims") or [],
            "low_dims": payload.get("gap_dims") or [],
            "extra_gap_dims": payload.get("unverified_dims") or [],
            "clamped": [],
            "unevidenced": payload.get("unevidenced") or [],
            "claims_without_evidence": payload.get("claims_without_evidence") or [],
            "registered_paths": payload.get("registered_paths") or [],
            "conflicts": payload.get("conflicts") or [],
            "weighted": payload.get("weighted", 0),
            "threshold_pass": bool(payload.get("threshold_pass")),
            "proposed_by": "llm",
            "validated_by": "runtime",
            "offline": bool(payload.get("offline")),
        }
    stored["id"] = review_id
    stored["milestone"] = mid
    stored.setdefault("artifact_id", payload.get("artifact_id"))
    stored["event_id"] = event.get("id")
    stored["recovered"] = True
    stored["at"] = stored.get("at") or event.get("at") or now_iso()
    return stored


def _reconcile_reviews(project: Project, state: State, events: list[dict]) -> bool:
    changed = False
    existing = {item.get("id") for item in state.reviews.get("items", [])}
    for event in events:
        if event.get("kind") != "review_recorded":
            continue
        payload = event.get("payload") or {}
        review_id = payload.get("review_id")
        if not review_id or review_id in existing:
            continue
        milestone = state.milestone(payload.get("milestone"))
        if milestone is None:
            project.note_repair(f"journal 有评审 {review_id}，但里程碑 {payload.get('milestone')!r} 不在当前项目；未自动恢复")
            continue
        artifact_id = payload.get("artifact_id")
        if artifact_id and not any(item.get("id") == artifact_id for item in state.artifacts.get("items", [])):
            project.note_repair(f"journal 有评审 {review_id}，但作品 {artifact_id} 不在快照；未自动恢复，先恢复作品")
            continue
        review = _review_from_event(event, state)
        if review is None:
            project.note_repair(f"journal 有评审 {review_id}，但事件内容不足以恢复；请重新 review")
            continue
        state.reviews.setdefault("items", []).append(review)
        existing.add(review_id)
        milestone.setdefault("review_ids", []).append(review_id)
        project.note_repair(f"从 journal 恢复评审 {review_id}（{payload.get('milestone')}），快照已补齐")
        changed = True
    return changed


def _reconcile_defense(project: Project, state: State, events: list[dict]) -> bool:
    existing = {item.get("id"): item for item in state.defense.get("items", [])}
    rules = state.brief.get("defense_rules") or {}
    latest: dict[str, tuple[dict, dict | None]] = {}
    for event in events:
        if event.get("kind") != "defense_recorded":
            continue
        payload = event.get("payload") or {}
        defense_id = payload.get("defense_id")
        if not defense_id:
            continue
        latest[defense_id] = (event, _clone_dict(payload.get("defense")))
    changed = False
    for defense_id, (event, stored) in latest.items():
        payload = event.get("payload") or {}
        attempts = int(payload.get("attempts") or (stored or {}).get("attempts") or 0)
        current = existing.get(defense_id)
        if current is None:
            artifact_id = payload.get("artifact_id")
            if artifact_id and not any(item.get("id") == artifact_id for item in state.artifacts.get("items", [])):
                project.note_repair(f"journal 有防御 {defense_id}，但作品 {artifact_id} 不在快照；未自动恢复，先恢复作品")
                continue
            if stored is None:
                stored = {
                    "id": defense_id,
                    "milestone": payload.get("milestone"),
                    "artifact_id": payload.get("artifact_id"),
                    "questions": [],
                    "unsupported_questions": [],
                    "ok_count": int(payload.get("ok_count") or 0),
                    "min_ok": int(rules.get("min_ok", 2) or 2),
                    "heaviest_dims": [],
                    "heaviest_ok": bool(payload.get("heaviest_ok")),
                    "status": payload.get("status") or "pending",
                    "passed": bool(payload.get("passed")),
                    "attempts": attempts,
                    "decided_by": "runtime",
                    "source": "journal_replay",
                }
            stored["id"] = defense_id
            stored.setdefault("milestone", payload.get("milestone"))
            stored.setdefault("artifact_id", payload.get("artifact_id"))
            stored["recovered"] = True
            stored["at"] = stored.get("at") or event.get("at") or now_iso()
            state.defense.setdefault("items", []).append(stored)
            existing[defense_id] = stored
            project.note_repair(f"从 journal 恢复防御记录 {defense_id}，快照已补齐")
            changed = True
            continue
        current_attempts = int(current.get("attempts") or 0)
        newer = attempts > current_attempts or (
            stored is not None and stored.get("passed") and not current.get("passed")
        )
        if not newer:
            continue
        if stored is not None:
            current.clear()
            current.update(stored)
        else:
            current.update(
                {
                    "ok_count": int(payload.get("ok_count") or 0),
                    "heaviest_ok": bool(payload.get("heaviest_ok")),
                    "status": payload.get("status") or current.get("status"),
                    "passed": bool(payload.get("passed")),
                    "attempts": attempts,
                }
            )
        current["recovered"] = True
        current["at"] = current.get("at") or event.get("at") or now_iso()
        project.note_repair(f"从 journal 恢复防御记录 {defense_id} 的最新判定")
        changed = True
    return changed


GAP_OPEN_KINDS = {
    "gap_created": "open",
    "gap_updated": "open",
    "gap_reopened": "open",
    "gap_learned": "learning",
    "gap_unverified": "unverified",
    "gap_dropped": "stale",
}


def _reconcile_gaps(project: Project, state: State, events: list[dict]) -> bool:
    """Replay the *latest* gap event; an existing card only wins when it agrees.

    A crash after ``gap_closed`` (or ``gap_learned``) but before gaps.json is
    written leaves an older open card on disk. Keeping "snapshot always wins"
    would silently resurrect a closed gap, so compare the snapshot status with
    the last journal state and apply that state when they differ.
    """
    existing = {item.get("gap_id"): item for item in state.gaps.get("items", [])}
    latest: dict[str, tuple[dict, dict | None]] = {}
    for event in events:
        kind = event.get("kind")
        if kind not in GAP_OPEN_KINDS and kind != "gap_closed":
            continue
        payload = event.get("payload") or {}
        gap_id = payload.get("gap_id")
        if not gap_id:
            continue
        card = _clone_dict(payload.get("card"))
        latest[gap_id] = (event, card)
    changed = False
    for gap_id, (event, card) in latest.items():
        kind = event.get("kind")
        payload = event.get("payload") or {}
        target = "closed" if kind == "gap_closed" else GAP_OPEN_KINDS[kind]
        current = existing.get(gap_id)
        if current is None:
            if card is None:
                milestone = state.milestone(payload.get("milestone"))
                rule = next(
                    (
                        dim
                        for dim in (milestone or {}).get("rubric", [])
                        if dim.get("dim") == payload.get("dim")
                    ),
                    None,
                )
                if not payload.get("dim") or rule is None:
                    continue
                card = {
                    "gap_id": gap_id,
                    "milestone": payload.get("milestone"),
                    "dim": payload.get("dim"),
                    "score": int(payload.get("score", 0) or 0),
                    "threshold": int(payload.get("threshold", rule.get("threshold", 0)) or 0),
                    "weight": int(payload.get("weight", rule.get("weight", 0)) or 0),
                    "note": "（从 journal 恢复：原始 note 未落盘）",
                    "evidence": {},
                    "source_review": payload.get("source_review") or payload.get("review_id"),
                    "attempts": int(payload.get("attempts") or 1),
                    "stale_drops": int(payload.get("stale_drops") or 0),
                    "extra_trigger": bool(payload.get("extra_trigger")),
                    "created_at": event.get("at") or now_iso(),
                    "closed_by": None,
                    "closed_by_review": None,
                    "closed_at": None,
                }
            if kind == "gap_closed":
                card.update(
                    {
                        "closed_by": payload.get("closed_by") or "review",
                        "closed_by_review": payload.get("review_id"),
                        "closed_at": event.get("at") or now_iso(),
                        "closed_artifact_sha": payload.get("artifact_sha256"),
                    }
                )
            elif kind == "gap_learned":
                card["learn_count"] = int(payload.get("learn_count") or card.get("learn_count", 0) or 0)
            elif kind == "gap_dropped":
                card["stale_drops"] = int(payload.get("stale_drops") or card.get("stale_drops", 0) or 0)
            card.update(
                {
                    "status": target,
                    "unverified": target == "unverified",
                    "recovered": True,
                    "updated_at": event.get("at") or now_iso(),
                }
            )
            state.gaps.setdefault("items", []).append(card)
            existing[gap_id] = card
            project.note_repair(f"从 journal 恢复缺口卡 {gap_id}，快照已补齐")
            changed = True
            continue
        if current.get("status") == target:
            if target != "closed":
                continue
            if current.get("closed_by_review") == payload.get("review_id"):
                continue
        if card is not None:
            current.update(card)
        current["status"] = target
        current["unverified"] = target == "unverified"
        if kind == "gap_closed":
            current.update(
                {
                    "closed_by": payload.get("closed_by") or "review",
                    "closed_by_review": payload.get("review_id"),
                    "closed_at": event.get("at") or now_iso(),
                    "closed_artifact_sha": payload.get("artifact_sha256"),
                }
            )
        elif kind == "gap_learned":
            current["learn_count"] = int(payload.get("learn_count") or current.get("learn_count", 0) or 0)
        elif kind == "gap_dropped":
            current["stale_drops"] = int(payload.get("stale_drops") or current.get("stale_drops", 0) or 0)
        current["recovered"] = True
        current["updated_at"] = event.get("at") or current.get("updated_at") or now_iso()
        project.note_repair(f"从 journal 恢复缺口卡 {gap_id} 的最新状态：{target}")
        changed = True
    return changed


def _reconcile_session(project: Project, state: State, events: list[dict]) -> bool:
    """Advance the session turn counter when the journal is ahead of session.json.

    Otherwise the next ``say`` reuses a turn number whose events already exist,
    the dedupe index drops the new event, and the turn is silently lost.
    """
    session_id = state.session.get("session_id")
    if not session_id:
        return False
    current = int(state.session.get("turn_index") or 0)
    highest = current
    for event in events:
        if event.get("kind") != "mentor_turn":
            continue
        payload = event.get("payload") or {}
        if payload.get("session") != session_id:
            continue
        turn = payload.get("turn")
        if isinstance(turn, int) and not isinstance(turn, bool) and turn > highest:
            highest = turn
    if highest <= current:
        return False
    state.session["turn_index"] = highest
    state.session["last_active_at"] = now_iso()
    project.note_repair(f"从 journal 恢复会话语轮次：{current} → {highest}（避免同一轮重复计数）")
    return True


def reconcile_state(project: Project, state: State) -> None:
    """Replay journal facts missing from snapshots (write-ahead recovery).

    The journal is authoritative; snapshots are a cache. A crash between an
    event append and the snapshot save used to lose the fact forever because the
    dedupe index then blocked the retry. This replay closes that window; it only
    ever adds missing entities or advances a snapshot to the latest journal state.
    """
    try:
        events = project.journal.all()
    except StateCorrupt as exc:
        project.note_repair(f"journal 无法完整读取，跳过自动恢复：{exc}")
        return
    changed = {
        "artifacts": _reconcile_artifacts(project, state, events),
        "reviews": _reconcile_reviews(project, state, events),
        "defense": _reconcile_defense(project, state, events),
        "gaps": _reconcile_gaps(project, state, events),
        "session": _reconcile_session(project, state, events),
    }
    if changed["artifacts"] or changed["reviews"]:
        # Milestone artifact_ids/review_ids live in brief.json.
        changed["brief"] = True
    names = [name for name in ("artifacts", "reviews", "defense", "gaps", "session", "brief") if changed.get(name)]
    if not names:
        return
    try:
        state.save(project, *names)
    except StaleWrite as exc:
        project.note_repair(f"journal 恢复与另一个写入冲突，未覆盖现有状态：{exc}")


def load_state(project: Project) -> State:
    state = State(
        project=project.load("project"),
        brief=project.load("brief"),
        artifacts=project.load("artifacts"),
        reviews=project.load("reviews"),
        gaps=project.load("gaps"),
        defense=project.load("defense"),
        session=project.load("session"),
    )
    for name in ("project", "brief", "artifacts", "reviews", "gaps", "defense", "session"):
        state.versions[name] = int(getattr(state, name).get("version", 0))
    reconcile_state(project, state)
    return state


# --------------------------------------------------------------------------- #
# 会话
# --------------------------------------------------------------------------- #
def _unique_stem(base: str, directory: Path, suffix: str = ".md") -> str:
    stem = base
    index = 2
    while (directory / f"{stem}{suffix}").exists():
        stem = f"{base}-{index}"
        index += 1
    return stem


def ensure_session(project: Project, state: State, mentor: str | None = None, *, force_new: bool = False) -> dict:
    """Reuse the open session, or start a new ``sessions/YYYYMMDD-HHMMSS-<mentor>.md``."""
    session = state.session
    active = bool(session.get("session_id")) and not session.get("ended_at")
    if active and not force_new:
        if mentor and session.get("mentor") != mentor:
            session["mentor"] = mentor
        return session
    chosen = mentor or session.get("mentor") or "coach"
    if chosen not in MENTORS:
        chosen = "coach"
    project.sessions_dir.mkdir(parents=True, exist_ok=True)
    stem = _unique_stem(f"{clock.stamp_for_filename()}-{chosen}", project.sessions_dir)
    path = project.sessions_dir / f"{stem}.md"
    header = [
        f"# {clock.now().strftime('%Y-%m-%d %H:%M')} — Forge · {chosen}",
        f"- session: {stem}  mentor: {chosen}  activity: (pending)",
        f"- learner: P1  goal: {state.brief.get('goal', '')}  offline: false",
        "",
    ]
    atomic_write_text(path, "\n".join(header) + "\n")
    session.update(
        {
            "session_id": stem,
            "mentor": chosen,
            "file": project.rel(path),
            "started_at": now_iso(),
            "last_active_at": now_iso(),
            "ended_at": None,
            "turn_index": 0,
            "turns": [],
            "switches": [],
        }
    )
    return session


def append_session_turn(
    project: Project,
    state: State,
    *,
    learner_text: str,
    mentor_text: str,
    mentor: str,
    record: dict | None = None,
    activity: str = "",
    kind: str = "turn",
) -> Path:
    session = state.session
    if not session.get("session_id"):
        ensure_session(project, state, mentor)
    path = project.root / (session.get("file") or "")
    if not session.get("file") or not path.parent.exists():
        path = project.sessions_dir / f"{session['session_id']}.md"
        session["file"] = project.rel(path)
    heading = {"start": "## 开场", "system": "## 运行时"}.get(kind)
    chunks = [""]
    if heading:
        chunks += [heading, ""]
    # 学习者 / 导师 / 记录（spec-core §5）
    if learner_text:
        chunks += ["## 学习者", learner_text.strip(), ""]
    if mentor_text:
        chunks += ["## 导师", mentor_text.strip(), ""]
    if record:
        chunks.append("## 记录")
        if record.get("help_level") is not None:
            chunks.append(f"- help_level: {record.get('help_level')}")
        attempt = record.get("attempt")
        if isinstance(attempt, dict) and attempt:
            chunks.append(
                f"- attempt: correct={attempt.get('correct')} (activity {attempt.get('activity_id', '-')})"
            )
        if record.get("misconception"):
            chunks.append(f"- misconception: {record.get('misconception')}")
        if record.get("next"):
            chunks.append(f"- next: {record.get('next')}")
        runtime_next = record.get("runtime_next")
        if isinstance(runtime_next, dict) and runtime_next.get("action"):
            chunks.append(
                f"- runtime_next: {runtime_next.get('action')}（{runtime_next.get('ref') or '-'}）："
                f"{runtime_next.get('reason', '')[:120]}"
            )
        conflict = record.get("conflict")
        if isinstance(conflict, dict) and conflict.get("mentioned"):
            chunks.append(
                f"- mentor_next_conflict: 导师提到 {conflict.get('mentioned')}，"
                f"与 runtime_next 不一致（{conflict.get('source')}）"
            )
        inference = record.get("help_level_inferred")
        if isinstance(inference, dict):
            chunks.append(
                f"- help_level_inferred: {inference.get('declared')} → L{inference.get('inferred')}"
                f"（{inference.get('why', '')}）"
            )
        if record.get("activity"):
            chunks.append(f"- activity: {record.get('activity')}")
        if record.get("offline"):
            chunks.append("- offline: true (脚本导师，不代表真实 LLM 教学)")
        chunks.append("")
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(chunks).rstrip() + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    session["last_active_at"] = now_iso()
    session.setdefault("turns", []).append(
        {"role": "learner", "text": learner_text[:600], "at": now_iso()}
    )
    session["turns"].append({"role": mentor, "text": mentor_text[:600], "at": now_iso()})
    session["turns"] = session["turns"][-8:]
    if activity:
        session["activity"] = activity
    return path


def close_session(project: Project, state: State, note: str = "") -> None:
    if state.session.get("session_id") and not state.session.get("ended_at"):
        state.session["ended_at"] = now_iso()
        state.session["end_note"] = note
        path = project.root / (state.session.get("file") or "")
        if path.is_file():
            with open(path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(f"\n## 结束\n- at: {now_iso()}\n- note: {note}\n")
                fh.flush()


# --------------------------------------------------------------------------- #
# 文件工具
# --------------------------------------------------------------------------- #
def atomic_write_bytes(path: str | Path, data: bytes) -> None:
    """Byte-exact atomic write (used when copying artifacts, so sha256 never drifts)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text_safe(path: str | Path, limit: int = 20000) -> str:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[:limit]


def line_count(text: str) -> int:
    return len(text.splitlines())


def core_version() -> str:
    path = Path(__file__).resolve().parent / CORE_VERSION_FILE
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
