"""Parse the variant's human-authored templates into runtime structures.

The templates are the single source of truth for the default plan; the runtime
never hard-codes a curriculum.  Only the standard library is used.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import SCHEMA_VERSION

VARIANT_ROOT = Path(__file__).resolve().parent.parent.parent
TEMPLATE_DIR = VARIANT_ROOT / "templates"
MENTOR_DIR = VARIANT_ROOT / "mentors"
CURRICULUM_DIR = VARIANT_ROOT / "curriculum"
PROTOCOL_DIR = VARIANT_ROOT / "protocols"
FIXTURE = VARIANT_ROOT / "tests" / "fixtures" / "mentor_script.jsonl"

_HEADER_MAP = {
    "#": "n",
    "week": "week",
    "step_id": "step_id",
    "内容": "text",
    "owner": "mentor",
    "activity_id": "activity_id",
    "evidence": "evidence",
    "module_id": "module_id",
    "标题": "title",
    "能力目标": "goal",
    "activity_ids": "activity_ids",
    "exam_id": "exam_id",
    "probe_id": "probe_id",
    "问题": "question",
    "任务": "question",
    "期望要点": "expect",
    "判读": "reading",
}

_FIELD_RE = re.compile(r"^([a-z][a-z0-9_]*):\s*(.*)$")
_SEP_RE = re.compile(r"^:?-{3,}:?$")


class TemplateError(Exception):
    pass


def _clean_cell(cell: str) -> str:
    cell = cell.strip().strip("`").strip()
    if cell in ("—", "-", "–", "n/a", "N/A"):
        return ""
    return cell


def parse_markdown_table(lines: list[str]) -> list[dict]:
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell for cell in stripped.strip("|").split("|")]
        if all(_SEP_RE.match(cell.strip()) or not cell.strip() for cell in cells):
            continue
        rows.append([_clean_cell(cell) for cell in cells])
    if len(rows) < 2:
        return []
    header = rows[0]
    out = []
    for row in rows[1:]:
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))
        record = {}
        for index, name in enumerate(header):
            key = _HEADER_MAP.get(name.lower().strip(), name.strip())
            record[key] = row[index]
        out.append(record)
    return out


def parse_template(name: str) -> dict:
    """Return ``fields / tables / bullets`` for ``templates/<name>.md``."""
    path = TEMPLATE_DIR / f"{name}.md"
    if not path.exists():
        available = sorted(p.stem for p in TEMPLATE_DIR.glob("*.md"))
        raise TemplateError(f"unknown template {name!r}; available: {', '.join(available)}")
    fields: dict[str, str] = {}
    sections: list[tuple[str, list[str]]] = []
    current: list[str] | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.startswith("## "):
            current = []
            sections.append((raw[3:].strip(), current))
            continue
        if raw.startswith("# "):
            continue
        if current is None:
            match = _FIELD_RE.match(raw.strip())
            if match:
                fields[match.group(1)] = match.group(2).strip()
        else:
            current.append(raw)

    tables: dict[str, list[dict]] = {}
    bullets: dict[str, list[str]] = {}
    for title, lines in sections:
        rows = parse_markdown_table(lines)
        if rows:
            tables[title] = rows
        items = [line.strip()[2:].strip() for line in lines if line.strip().startswith("- ")]
        if items:
            bullets[title] = items

    steps = _first_table(tables, "step_id")
    modules = _first_table(tables, "module_id")
    probes = _first_table(tables, "probe_id")
    do_not_redo = _first_bullets(bullets, "do_not_redo", "不要重做", "反模式")
    constraints = _first_bullets(bullets, "约束", "constraint")

    normalized_steps = []
    for index, row in enumerate(steps, start=1):
        step_id = row.get("step_id") or f"step-{index}"
        normalized_steps.append(
            {
                "n": _to_int(row.get("n"), index),
                "week": _to_int(row.get("week"), 1),
                "step_id": step_id,
                "text": row.get("text", ""),
                "mentor": row.get("mentor", ""),
                "activity_id": row.get("activity_id", ""),
                "evidence": row.get("evidence", ""),
                "status": "todo",
                "evidence_log": [],
            }
        )

    normalized_modules = []
    for row in modules:
        activity_ids = [a.strip().strip("`") for a in row.get("activity_ids", "").split(",") if a.strip()]
        normalized_modules.append(
            {
                "module_id": row.get("module_id", ""),
                "week": _to_int(row.get("week"), 1),
                "title": row.get("title", ""),
                "goal": row.get("goal", ""),
                "activity_ids": activity_ids,
                "exam_id": row.get("exam_id", ""),
            }
        )

    normalized_probes = [
        {
            "probe_id": row.get("probe_id", ""),
            "question": row.get("question", ""),
            "expect": row.get("expect", ""),
            "reading": row.get("reading", ""),
        }
        for row in probes
    ]

    if not normalized_steps:
        raise TemplateError(f"template {name!r} has no step table (expected a 'step_id' table)")
    if not fields.get("template"):
        fields["template"] = name
    fields.setdefault("schema_version", str(SCHEMA_VERSION))
    return {
        "name": fields["template"],
        "fields": fields,
        "steps": normalized_steps,
        "modules": normalized_modules,
        "probes": normalized_probes,
        "do_not_redo": do_not_redo,
        "constraints": constraints,
        "title": fields.get("title", name),
        "mentor_order": [m.strip() for m in fields.get("mentor_order", "planner,concept,coach,examiner,reviewer").split(",") if m.strip()],
        "default_mentor": fields.get("default_mentor", "planner"),
        "plan_id": fields.get("plan_id", "plan-v1"),
        "minutes_per_week_default": _to_int(fields.get("minutes_per_week_default"), 12),
        "first_session_minutes": _to_int(fields.get("first_session_minutes"), 20),
        "goal_default": fields.get("goal_default", ""),
    }


def _first_table(tables: dict[str, list[dict]], key: str) -> list[dict]:
    for rows in tables.values():
        if rows and key in rows[0]:
            return rows
    return []


def _first_bullets(bullets: dict[str, list[str]], *needles: str) -> list[str]:
    for title, items in bullets.items():
        low = title.lower()
        if any(needle.lower() in low for needle in needles):
            return items
    return []


def _to_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def mentor_prompt(mentor: str) -> str:
    path = MENTOR_DIR / f"{mentor}.md"
    if not path.exists():
        raise TemplateError(f"missing mentor prompt: {path}")
    return path.read_text(encoding="utf-8").strip()


def curriculum_text(template: str) -> str:
    path = CURRICULUM_DIR / f"{template}.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def protocol_text() -> str:
    path = PROTOCOL_DIR / "handoff.md"
    return path.read_text(encoding="utf-8") if path.exists() else ""
