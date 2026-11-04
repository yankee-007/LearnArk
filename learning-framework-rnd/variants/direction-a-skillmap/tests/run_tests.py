"""SkillMap (direction A) test suite.

Deterministic, offline, no network: every case runs the real CLI as a subprocess
with ``LEARNARK_LLM=mock`` and a JSONL mentor script, so it exercises argument
parsing, state, journal, git and the evidence rules exactly as a learner would.

Run:  python tests/run_tests.py [-v]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "runtime" / "learn.py"
DEFAULT_SCRIPT = ROOT / "tests" / "fixtures" / "mentor_script.jsonl"

TESTS: list = []
VERBOSE = "-v" in sys.argv


# ---------------------------------------------------------------------------
# harness
# ---------------------------------------------------------------------------
def test(fn):
    TESTS.append(fn)
    return fn


def base_env(now: str | None = None, script: Path | None = None) -> dict:
    env = dict(os.environ)
    env.update({"LEARNARK_LLM": "mock", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    for key in ("LEARNARK_NOW", "LEARNARK_PROJECT", "LEARNARK_MOCK_SCRIPT"):
        env.pop(key, None)
    if now:
        env["LEARNARK_NOW"] = now
    env["LEARNARK_MOCK_SCRIPT"] = str(script or DEFAULT_SCRIPT)
    return env


def run(args, cwd=None, now=None, script=None, expect=0, timeout=180) -> subprocess.CompletedProcess:
    command = [sys.executable, str(ENTRY), *[str(item) for item in args]]
    proc = subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=base_env(now, script),
        timeout=timeout,
    )
    if expect is not None and proc.returncode != expect:
        raise AssertionError(
            "command %s -> exit %s (expected %s)\nstdout:\n%s\nstderr:\n%s"
            % (" ".join(str(a) for a in args[:3]), proc.returncode, expect, proc.stdout[-3000:], proc.stderr[-2000:])
        )
    return proc


def run_json(args, **kwargs):
    proc = run([*args, "--json"], **kwargs)
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError as exc:
        raise AssertionError(f"not pure JSON from {args}: {exc}\n{proc.stdout[:2000]}\n{proc.stderr[:1000]}")


def new_project(tmp: Path, name="proj", template="agent-dev", goal="能独立设计与实现最小可用 Agent", minutes=None) -> Path:
    project = tmp / name
    args = ["init", "--goal", goal, "--dir", str(project), "--template", template]
    if minutes:
        args += ["--minutes-per-week", str(minutes)]
    run(args, cwd=tmp)
    return project


def journal(project: Path) -> list[dict]:
    path = project / ".learnark" / "journal" / "events.jsonl"
    events = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events


def kinds(project: Path) -> list[str]:
    return [event.get("kind") for event in journal(project)]


def of_kind(project: Path, kind: str) -> list[dict]:
    return [event for event in journal(project) if event.get("kind") == kind]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def map_path(project: Path) -> Path:
    return project / ".learnark" / "state" / "map.json"


def plan_path(project: Path) -> Path:
    return project / ".learnark" / "state" / "plan.json"


def node_of(project: Path, node_id: str) -> dict:
    return next(node for node in read_json(map_path(project))["nodes"] if node["id"] == node_id)


def edit_node(project: Path, node_id: str, **changes) -> None:
    data = read_json(map_path(project))
    for node in data["nodes"]:
        if node["id"] == node_id:
            node.update(changes)
    write_json(map_path(project), data)


def make_script(path: Path, entries: list[tuple[str, str, dict | None]]) -> Path:
    """Write a mentor script: ``(match, visible_text, update_dict_or_None)``."""
    lines = []
    for match, text, update in entries:
        reply = text
        if update is not None:
            reply += "\n```learn-update\n" + json.dumps(update, ensure_ascii=False) + "\n```"
        lines.append(json.dumps({"match": match, "reply": reply}, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def upd(
    *,
    help_level: int = 0,
    activity: str = "A1-explain",
    correct=None,
    misconception=None,
    next_text="继续",
    mastery: int = 0,
    artifact=None,
    probe=None,
    diagnosis=None,
) -> dict:
    block = {
        "help_level": help_level,
        "attempt": {"activity_id": activity, "correct": correct},
        "probe": probe,
        "misconception": misconception,
        "next": next_text,
        "mastery_delta": mastery,
        "artifact": artifact,
        "diagnosis": diagnosis,
    }
    return block


def skip_diagnosis(project: Path) -> None:
    run(["diagnose", "--skip", "--project", project], expect=0)


# ---------------------------------------------------------------------------
# 1. init
# ---------------------------------------------------------------------------
@test
def test_init_is_idempotent(tmp: Path) -> None:
    project = new_project(tmp)
    for rel in (".learnark/project.json", "AGENTS.md", "README.md", ".gitignore", ".learnark/state/map.json"):
        assert (project / rel).exists(), f"missing {rel}"
    assert (project / ".git").is_dir(), "git repository not initialised"
    data = read_json(project / ".learnark" / "project.json")
    assert data["template"] == "agent-dev" and data["schema_version"] == 1
    first_goal = data["goal"]

    second = run(["init", "--goal", "别的目标", "--dir", project], expect=0)
    assert "已存在" in second.stdout
    data2 = read_json(project / ".learnark" / "project.json")
    assert data2["goal"] == first_goal, "init must not overwrite an existing goal"
    nodes = read_json(map_path(project))["nodes"]
    assert [node["id"] for node in nodes] == ["A1", "A2", "B1", "B2", "B3", "C1", "C2", "C3", "C4", "D1", "D2", "E1"]
    prereqs = {node["id"]: node["prereqs"] for node in nodes}
    assert prereqs["C2"] == ["C1", "B2"]
    assert prereqs["C3"] == ["C2", "B3"]
    assert prereqs["D2"] == ["D1", "C2"]
    assert prereqs["E1"] == ["C3", "C4"]
    assert prereqs["A1"] == []


# ---------------------------------------------------------------------------
# 2. offline end-to-end
# ---------------------------------------------------------------------------
@test
def test_offline_end_to_end(tmp: Path) -> None:
    project = new_project(tmp)
    start = run(["start", "--project", project, "--minutes", "20"], expect=0)
    assert "离线脚本导师" in start.stdout
    # 20-minute sessions cap the diagnosis at 2 probes so an activity still fits.
    assert "诊断探针 1/2" in start.stdout
    assert "只做 2 题" in start.stdout

    say = run(["say", "我学过 API 调用，但没写过工具调用", "--project", project], expect=0)
    assert "离线脚本导师" in say.stdout

    status = run_json(["status", "--project", project], expect=0)
    assert status["goal"]
    assert status["plan"]["mode"] in ("diagnose", "stage")
    assert status["offline"] is True

    pause = run(["pause", "--project", project], expect=0)
    assert "交接" in pause.stdout
    assert (project / ".learnark" / "handoff" / "latest.md").exists()

    sync = run(["sync", "--project", project], expect=0)
    lowered = sync.stdout.lower()
    for word in ("written", "committed", "pushed"):
        assert word in lowered, f"sync output missing {word}: {sync.stdout}"

    doctor = run(["doctor", "--project", project], expect=0)
    assert "全部检查通过" in doctor.stdout

    out = tmp / "export.md"
    run(["export", "--out", out, "--project", project], expect=0)
    assert out.exists() and out.stat().st_size > 200

    sessions = list((project / "sessions").glob("*.md"))
    assert sessions, "no session markdown written"
    assert "mentor_turn" in kinds(project)
    assert (project / "sessions").exists()


# ---------------------------------------------------------------------------
# 3. idempotency
# ---------------------------------------------------------------------------
@test
def test_same_answer_is_not_counted_twice(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    script = make_script(
        tmp / "s.jsonl",
        [("HELP2", "这是分步引导。", upd(help_level=2, correct=True, activity="A1-explain"))],
    )
    run(["say", "HELP2 请给我分步提示", "--project", project], script=script, expect=0)
    attempts = [e for e in of_kind(project, "attempt") if e["payload"].get("activity_id") == "A1-explain"]
    assert len(attempts) == 1, f"expected 1 attempt, got {len(attempts)}"
    levels = of_kind(project, "level_up")
    assert not levels, "help_level=2 must not raise a level"

    second = run(["say", "HELP2 请给我分步提示", "--project", project], script=script, expect=0)
    assert "已记录" in second.stdout or "记录过" in second.stdout, second.stdout
    attempts2 = [e for e in of_kind(project, "attempt") if e["payload"].get("activity_id") == "A1-explain"]
    assert len(attempts2) == 1, "replayed answer must not create a second attempt"
    assert len(of_kind(project, "assisted_completion")) == 1


# ---------------------------------------------------------------------------
# 4. evidence rules: help level + single level per turn
# ---------------------------------------------------------------------------
@test
def test_help_level_gate_and_single_level(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    script = make_script(
        tmp / "help.jsonl",
        [
            ("H2", "分步引导完成。", upd(help_level=2, correct=True, mastery=3)),
            ("H1", "只给一句方向。", upd(help_level=1, correct=True, mastery=3)),
        ],
    )
    run(["say", "H2", "--project", project], script=script, expect=0)
    node = node_of(project, "A1")
    assert node["level"] == 0, f"help_level=2 promoted A1 to L{node['level']}"
    assert of_kind(project, "assisted_completion"), "assisted_completion event missing"
    assert not of_kind(project, "level_up"), "assisted completion must not emit level_up"

    run(["say", "H1", "--project", project], script=script, expect=0)
    assert node_of(project, "A1")["level"] == 1
    ups = of_kind(project, "level_up")
    assert len(ups) == 1 and ups[0]["payload"]["to"] == 1, f"expected exactly one +1 level_up, got {ups}"
    plan = read_json(plan_path(project))
    assert plan["stage"] == "drill", f"explain pass should advance to drill, plan stage={plan['stage']}"


# ---------------------------------------------------------------------------
# 5. diagnosis cap
# ---------------------------------------------------------------------------
@test
def test_diagnosis_never_sets_above_l1(tmp: Path) -> None:
    project = new_project(tmp)
    entries = []
    probes = ["第一题", "第二题", "第三题", "第四题", "第五题"]
    for index, probe in enumerate(probes):
        entries.append((probe, f"探针 {index + 1} 的答案。", upd(help_level=0, correct=True, activity="diagnose", mastery=3)))
    script = make_script(tmp / "diag.jsonl", entries)
    run(["start", "--project", project], script=script, expect=0)
    for probe in probes:
        run(["say", probe, "--project", project], script=script, expect=0)
    nodes = {node["id"]: node["level"] for node in read_json(map_path(project))["nodes"]}
    anchors = ["B1", "C2", "D2", "A2", "E1"]
    for anchor in anchors:
        assert nodes[anchor] == 1, f"{anchor} should be L1 from diagnosis, got L{nodes[anchor]}"
    assert all(level <= 1 for level in nodes.values()), f"diagnosis raised a level above L1: {nodes}"
    diagnosis = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]
    assert diagnosis["status"] == "done"
    statuses = [probe["status"] for probe in diagnosis["probes"]]
    assert statuses == ["done"] * 5


# ---------------------------------------------------------------------------
# 5b. diagnosis probe claims + placement (A-S2)
# ---------------------------------------------------------------------------
_PROBE_ANCHORS = ["B1", "C2", "D2", "A2", "E1"]


def _diagnosis_script(path: Path, correct_nodes: set[str], prefix: str) -> Path:
    """A mentor script whose machine block carries a ``probe`` claim per anchor."""
    entries = []
    for index, anchor in enumerate(_PROBE_ANCHORS, start=1):
        ok = anchor in correct_nodes
        claim = {"node": anchor, "level": 1 if ok else 0, "reason": f"{anchor} probe rating"}
        entries.append(
            (
                f"{prefix}{index}",
                f"{anchor} {'答对' if ok else '没答对'}",
                upd(help_level=0, correct=None, activity="diagnose", probe=claim),
            )
        )
    return make_script(path, entries)


def _run_diagnosis(project: Path, script: Path, prefix: str) -> list[str]:
    outputs = [run(["start", "--project", project], script=script, expect=0).stdout]
    for index in range(1, len(_PROBE_ANCHORS) + 1):
        outputs.append(run(["say", f"{prefix}{index}", "--project", project], script=script, expect=0).stdout)
    return outputs


@test
def test_placement_all_correct_profile(tmp: Path) -> None:
    """A-S2: a fully correct diagnosis places B1 at apply via the probe block."""
    script = _diagnosis_script(tmp / "all-correct.jsonl", set(_PROBE_ANCHORS), "全")
    project = new_project(tmp, name="all-correct-proj")
    _run_diagnosis(project, script, "全")

    levels = {node["id"]: node["level"] for node in read_json(map_path(project))["nodes"]}
    for anchor in _PROBE_ANCHORS:
        assert levels[anchor] == 1, f"{anchor} should be L1 from its probe claim, got L{levels[anchor]}"
    assert all(level <= 1 for level in levels.values()), "diagnosis must never exceed L1"

    probes = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"]
    assert all(probe["probe_claim"]["level"] in (0, 1) for probe in probes), probes

    decision = run_json(["next", "--project", project], expect=0)
    assert decision["selected"]["node"] == "B1", decision["selected"]
    assert decision["selected"]["stage"] == "apply"
    assert decision["selected"]["activity_id"] == "B1-apply"
    assert any(reason.startswith("诊断定位") for reason in decision["reasons"]), decision["reasons"]
    events = of_kind(project, "placement_applied")
    assert events, "placement_applied event missing"
    payload = events[-1]["payload"]
    assert payload["node"] == "B1" and payload["probe"] == "Q1" and payload["level"] == 1
    plan = read_json(plan_path(project))
    assert plan["current_node"] == "B1" and plan["stage"] == "apply"
    assert plan["placement"]["node"] == "B1"
    # A2 is L1 too, but its own prereq A1 is still L0 -> excluded and not placed.
    excluded = {item["node"]: item["reason"] for item in decision["excluded"]}
    assert "A2" in excluded and "A1" in excluded["A2"], excluded.get("A2")


@test
def test_placement_mostly_wrong_profile(tmp: Path) -> None:
    """A-S2: mostly-wrong answers keep the learner at A1-explain."""
    script = _diagnosis_script(tmp / "mostly-wrong.jsonl", {"A2"}, "偏")
    project = new_project(tmp, name="mostly-wrong-proj")
    _run_diagnosis(project, script, "偏")

    levels = {node["id"]: node["level"] for node in read_json(map_path(project))["nodes"]}
    assert levels["A2"] == 1 and levels["B1"] == 0, levels
    decision = run_json(["next", "--project", project], expect=0)
    assert decision["selected"]["activity_id"] == "A1-explain", decision["selected"]
    assert not of_kind(project, "placement_applied"), "A2 alone cannot place (A1 is L0)"
    assert decision.get("placement") is None
    plan = read_json(plan_path(project))
    assert plan["current_node"] == "A1" and plan["stage"] == "explain"


@test
def test_probe_claim_validation(tmp: Path) -> None:
    """Bad probe claims are rejected without changing the map."""
    project = new_project(tmp)
    # level 2 is out of range -> the whole block is invalid; the probe is consumed
    # conservatively as L0 (never as null) and nothing is applied.
    bad_level = make_script(
        tmp / "bad-level.jsonl",
        [("坏级", "评级给到 L2。", upd(help_level=0, correct=None, activity="diagnose", probe={"node": "B1", "level": 2, "reason": "x"}))],
    )
    run(["start", "--project", project], script=bad_level, expect=0)
    run(["say", "坏级", "--project", project], script=bad_level, expect=0)
    assert of_kind(project, "mentor_update_invalid"), "level=2 probe must be invalid"
    assert node_of(project, "B1")["level"] == 0
    first = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"][0]
    assert first["status"] == "done" and first["correct"] is False, first

    # The right shape but the wrong anchor: recorded, ignored, cursor unchanged.
    wrong_anchor = make_script(
        tmp / "wrong-anchor.jsonl",
        [("错锚", "给 D2 评级。", upd(help_level=0, correct=None, activity="diagnose", probe={"node": "D2", "level": 1, "reason": "x"}))],
    )
    run(["say", "错锚", "--project", project], script=wrong_anchor, expect=0)
    assert of_kind(project, "probe_claim_rejected"), "mismatched probe anchor must be rejected"
    assert node_of(project, "D2")["level"] == 0 and node_of(project, "B1")["level"] == 0
    probes = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"]
    assert probes[1]["status"] == "pending", "a rejected claim must not advance the probe cursor"

    # A matching claim for the probe that is actually being asked does advance it.
    matching = make_script(
        tmp / "matching.jsonl",
        [("答对", "C2 答对了。", upd(help_level=0, correct=None, activity="diagnose", probe={"node": "C2", "level": 1, "reason": "ok"}))],
    )
    run(["say", "答对", "--project", project], script=matching, expect=0)
    probes = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"]
    assert probes[1]["status"] == "done" and probes[1]["level_set"] == 1, probes[1]
    assert node_of(project, "C2")["level"] == 1


@test
def test_probe_followup_does_not_advance(tmp: Path) -> None:
    """An extra mentor question is part of the same probe, not the next one."""
    project = new_project(tmp)
    script = make_script(
        tmp / "followup.jsonl",
        [
            ("追问一", "先别急，猜一下：这段是谁执行的？", upd(help_level=0, correct=None, activity="diagnose", probe=None)),
            ("正式答", "B1 判 L0。", upd(help_level=0, correct=None, activity="diagnose", probe={"node": "B1", "level": 0, "reason": "误解仍在"})),
        ],
    )
    run(["start", "--project", project], script=script, expect=0)
    run(["say", "追问一", "--project", project], script=script, expect=0)
    probes = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"]
    assert probes[0]["status"] == "pending", "a follow-up turn must not advance the probe"
    assert of_kind(project, "probe_deferred"), "follow-up must be logged as deferred"
    assert not of_kind(project, "diagnosis_probe"), "no probe answer may be recorded yet"

    run(["say", "正式答", "--project", project], script=script, expect=0)
    probes = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"]
    assert probes[0]["status"] == "done" and probes[0]["level_set"] == 0, probes[0]
    assert probes[0]["correct"] is False, "a done probe never records correct=null"


@test
def test_three_answers_map_to_their_own_probes(tmp: Path) -> None:
    """Three sequential answers must land on Q1/Q2/Q3 anchors B1/C2/D2."""
    project = new_project(tmp)
    script = make_script(
        tmp / "three.jsonl",
        [
            ("序一", "B1 判 L1。", upd(help_level=0, correct=None, activity="diagnose", probe={"node": "B1", "level": 1, "reason": "ok"})),
            ("序二", "C2 判 L0。", upd(help_level=0, correct=None, activity="diagnose", probe={"node": "C2", "level": 0, "reason": "漏了终止条件"})),
            ("序三", "D2 判 L1。", upd(help_level=0, correct=None, activity="diagnose", probe={"node": "D2", "level": 1, "reason": "区分清楚"})),
        ],
    )
    run(["start", "--project", project], script=script, expect=0)
    for text in ("序一", "序二", "序三"):
        run(["say", text, "--project", project], script=script, expect=0)
    probes = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"]
    assert [(probe["node"], probe["status"], probe["level_set"]) for probe in probes[:3]] == [
        ("B1", "done", 1),
        ("C2", "done", 0),
        ("D2", "done", 1),
    ], probes[:3]
    assert [probe["status"] for probe in probes[3:]] == ["pending", "pending"], probes[3:]
    assert all(probe["correct"] is not None for probe in probes[:3]), "done probes must carry a judgement"


@test
def test_runtime_next_matches_start(tmp: Path) -> None:
    """`runtime_next` (context) and `start`'s task card must agree, placed or not."""
    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_engine  # noqa: PLC0415

        strong_script = _diagnosis_script(tmp / "rn-strong.jsonl", set(_PROBE_ANCHORS), "强")
        strong = new_project(tmp, name="rn-strong")
        _run_diagnosis(strong, strong_script, "强")
        strong_ctx = sm_engine.Context(strong, None, None)
        context = strong_ctx.model_context()
        assert "runtime_next" in context
        assert '"activity_id": "B1-apply"' in context, context[-800:]
        start_out = run(["start", "--project", strong], script=strong_script, expect=0).stdout
        assert "B1-apply" in start_out
        assert "A1-explain" not in start_out
        status = run_json(["status", "--project", strong], expect=0)
        assert status["runtime_next"]["activity_id"] == "B1-apply"
        assert status["current"]["activity_id"] == "B1-apply"

        weak_script = _diagnosis_script(tmp / "rn-weak.jsonl", {"A2"}, "弱")
        weak = new_project(tmp, name="rn-weak")
        _run_diagnosis(weak, weak_script, "弱")
        weak_ctx = sm_engine.Context(weak, None, None)
        assert '"activity_id": "A1-explain"' in weak_ctx.model_context()
        weak_start = run(["start", "--project", weak], script=weak_script, expect=0).stdout
        assert "A1-explain" in weak_start
        assert "B1-apply" not in weak_start
    finally:
        sys.path.remove(str(ROOT / "runtime"))


@test
def test_assisted_carryover_is_not_independent(tmp: Path) -> None:
    """A level right after help_level=3 is labelled assisted and capped at L1."""
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)
    script = make_script(
        tmp / "assisted.jsonl",
        [
            ("HELP3", "这是代做，记受助完成，不升等级。完整代码如下……", upd(help_level=3, correct=True, activity="A1-explain", mastery=3)),
            ("ISO", "同构题自己答对了。", upd(help_level=0, correct=True, activity="A1-explain", mastery=3)),
        ],
    )
    run(["say", "HELP3", "--project", project], script=script, expect=0)
    assert node_of(project, "A1")["level"] == 0
    run(["say", "ISO", "--project", project], script=script, expect=0)
    assert node_of(project, "A1")["level"] == 1, "assisted carry-over may only reach L1"

    ups = [event for event in of_kind(project, "level_up") if event["payload"].get("node") == "A1"]
    assert ups and ups[-1]["payload"]["reason"] == "after_assisted", ups[-1]["payload"]
    assert ups[-1]["payload"]["assisted"] is True
    attempts = [event for event in of_kind(project, "attempt") if event["payload"].get("node") == "A1"]
    assert any(event["payload"].get("assisted_context") for event in attempts)
    assert of_kind(project, "assisted_carryover"), "assisted_carryover event missing"

    status = run_json(["status", "--project", project], expect=0)
    change = status["help"]["last_level_change"]
    assert change["reason"] == "after_assisted" and change["assisted"] is True, change
    assert status["help"]["independent_attempts"] == 0, status["help"]
    assert status["help"]["assisted_completions"] >= 1
    human = run(["status", "--project", project], expect=0).stdout
    assert "受助后，不计为独立" in human
    assert "帮助：" in human


@test
def test_no_internal_terms_in_stdout(tmp: Path) -> None:
    """`start` and `say` must speak plain Chinese, never internal protocol terms."""
    banned = ("机器块", "claim", "help_level", "mentor_update")

    diagnose_project = new_project(tmp, name="terms-diagnose")
    diagnose_script = _diagnosis_script(tmp / "terms-diag.jsonl", {"B1"}, "术")
    outputs = _run_diagnosis(diagnose_project, diagnose_script, "术")
    for output in outputs:
        for token in banned:
            assert token not in output, f"{token!r} leaked into diagnosis stdout: {output[-600:]}"

    stage_project = new_project(tmp, name="terms-stage")
    skip_diagnosis(stage_project)
    stage_outputs = [run(["start", "--project", stage_project], expect=0).stdout]
    stage_script = make_script(
        tmp / "terms-stage.jsonl",
        [("答一下", "复述对了两个要点。", upd(help_level=1, correct=True, activity="A1-explain", mastery=1))],
    )
    stage_outputs.append(run(["say", "答一下", "--project", stage_project], script=stage_script, expect=0).stdout)
    for output in stage_outputs:
        for token in banned:
            assert token not in output, f"{token!r} leaked into stage stdout: {output[-600:]}"


@test
def test_weak_points_and_handoff_dedupe(tmp: Path) -> None:
    """The same misconception appears once in status and once in the handoff."""
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)
    label = "把 get 默认值套到 [] 上"
    script = make_script(
        tmp / "dup.jsonl",
        [
            ("DUP1", "又犯了同样的错。", upd(help_level=0, correct=False, activity="A1-explain", misconception=label)),
            ("DUP2", "还是同一个错。", upd(help_level=0, correct=False, activity="A1-explain", misconception=label)),
        ],
    )
    run(["say", "DUP1", "--project", project], script=script, expect=0)
    run(["say", "DUP2", "--project", project], script=script, expect=0)
    status = run_json(["status", "--project", project], expect=0)
    assert sum(1 for item in status["misconceptions"] if item["label"] == label) == 1, status["misconceptions"]
    assert sum(1 for item in status["weak_points"] if label in item) == 1, status["weak_points"]

    run(["pause", "--project", project], expect=0)
    handoff = (project / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    assert handoff.count(label) == 1, handoff


@test
def test_probes_render_once_with_consistent_anchors(tmp: Path) -> None:
    """Every probe renders exactly once, with the anchor declared for it."""
    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_model  # noqa: PLC0415

        probes = sm_model.probe_defs("agent-dev")
        assert [p["id"] for p in probes] == ["Q1", "Q2", "Q3", "Q4", "Q5"]
        assert [p["node"] for p in probes] == _PROBE_ANCHORS
        node_ids = {spec[0] for spec in sm_model.template_spec("agent-dev")["nodes"]}
        assert set(_PROBE_ANCHORS) <= node_ids
        assert len({p["question"] for p in probes}) == len(probes), "probe questions must be distinct"
    finally:
        sys.path.remove(str(ROOT / "runtime"))

    navigator = (ROOT / "mentors" / "navigator.md").read_text(encoding="utf-8")
    for phrase in ("tool call", "i += 0", "终止条件", "RAG", "会话记忆", "超时", "最小评测", "加法"):
        assert phrase in navigator, f"mentors/navigator.md no longer matches the runtime probes ({phrase!r})"

    project = new_project(tmp)
    script = _diagnosis_script(tmp / "render.jsonl", set(_PROBE_ANCHORS), "渲")
    outputs = _run_diagnosis(project, script, "渲")
    import re  # noqa: PLC0415

    rendered: list[tuple[str, str]] = []
    for output in outputs:
        rendered.extend(re.findall(r"诊断探针 (\d)/5 · 锚点 (\S+)", output))
    assert rendered == [("1", "B1"), ("2", "C2"), ("3", "D2"), ("4", "A2"), ("5", "E1")], rendered

    combined = "".join(outputs)
    for probe in probes:
        assert combined.count(probe["question"]) == 1, f"{probe['id']} rendered {combined.count(probe['question'])} times"


# ---------------------------------------------------------------------------
# 6. prereq gating (A-S1): availability gate is L1, mastery is L2
# ---------------------------------------------------------------------------
@test
def test_prereq_gate_excludes_locked_nodes(tmp: Path) -> None:
    project = new_project(tmp)
    decision = run_json(["next", "--project", project], expect=0)
    assert decision["selected"]["node"] == "A1"
    assert decision["gate"] == 1, "availability gate should be L1"
    excluded = {item["node"]: item["reason"] for item in decision["excluded"]}
    assert "C3" in excluded, "C3 must be excluded while C2 is L0"
    assert "C2" in excluded["C3"] and "L1" in excluded["C3"]
    assert len(decision["excluded"]) >= 2
    assert len(decision["reasons"]) >= 3

    # one prereq at L1 unlocks nothing yet: B3 is still L0
    edit_node(project, "C2", level=1, level_source="test")
    decision2 = run_json(["next", "--project", project], expect=0)
    excluded2 = {item["node"]: item["reason"] for item in decision2["excluded"]}
    assert "C3" in excluded2 and "B3" in excluded2["C3"] and "L0" in excluded2["C3"], excluded2.get("C3")
    assert decision2["selected"]["node"] == "A1"

    # both prereqs at the availability gate -> C3 is now selectable
    edit_node(project, "C2", level=1, level_source="test")
    edit_node(project, "B3", level=1, level_source="test")
    decision3 = run_json(["next", "--project", project], expect=0)
    candidates = [item["node"] for item in decision3["candidates"]]
    assert "C3" in candidates, f"C3 should unlock once C2 and B3 are L1: {candidates}"


@test
def test_gate_l1_still_blocks_l0_prereq(tmp: Path) -> None:
    """Availability is L1, not L0: one zero-prereq still locks the successor."""
    project = new_project(tmp)
    edit_node(project, "B1", level=1, level_source="test")
    decision = run_json(["next", "--project", project], expect=0)
    candidates = [item["node"] for item in decision["candidates"]]
    # B1 L1 unlocks its direct successors C1 and B2 ...
    assert "C1" in candidates and "B2" in candidates, candidates
    # ... but C2 also needs B2, and B2 is L0: C2 stays excluded.
    excluded = {item["node"]: item["reason"] for item in decision["excluded"]}
    assert "C2" in excluded, f"C2 must stay locked: {candidates}"
    assert "B2" in excluded["C2"] and "L0" in excluded["C2"]
    # A2 still needs A1 (L0), even though its own probe anchor is free.
    assert "A2" in excluded and "A1" in excluded["A2"]


# ---------------------------------------------------------------------------
# 7. gate_override caps at L1 (unit level, deterministic)
# ---------------------------------------------------------------------------
@test
def test_gate_override_caps_level(tmp: Path) -> None:
    project = new_project(tmp)
    run(["start", "--project", project, "--node", "C3"], expect=0)
    node = node_of(project, "C3")
    assert node["gate_override"] is True
    assert node["level"] == 0

    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_engine  # noqa: PLC0415
        import sm_model  # noqa: PLC0415

        class Stub:
            def __init__(self, map_doc):
                self.map = map_doc
                self.plan = {"session_id": "unit"}
                self.events = []

            def index(self):
                return sm_model.by_id(self.map)

            def event(self, kind, payload=None, dedupe_key=None, actor="runtime"):
                self.events.append({"kind": kind, "payload": payload or {}})
                return {"id": f"ev_unit_{len(self.events)}"}

            def mark(self, *names):
                return None

        map_doc = read_json(map_path(project))
        target = sm_model.by_id(map_doc)["C3"]
        assert target["gate_override"] is True
        ctx = Stub(map_doc)
        first = sm_engine.promote(
            ctx, target, 3, reason="unit", source="check", activity_id="C3-check", help_level=0, correct=True
        )
        second = sm_engine.promote(
            ctx, target, 3, reason="unit", source="check", activity_id="C3-check", help_level=0, correct=True
        )
        assert first["to"] == 1 and second["to"] == 1, (first, second)
        assert target["level"] == 1, f"gate_override must cap at L1, got L{target['level']}"
        assert any(event["kind"] == "level_cap" for event in ctx.events)

        # without the override the same calls reach L3
        ok = sm_model.by_id(map_doc)["A1"]
        ok["level"] = 0
        third = sm_engine.promote(ctx, ok, 3, reason="unit", source="check", activity_id="A1-check", help_level=0, correct=True)
        fourth = sm_engine.promote(ctx, ok, 3, reason="unit", source="check", activity_id="A1-check", help_level=0, correct=True)
        fifth = sm_engine.promote(ctx, ok, 3, reason="unit", source="check", activity_id="A1-check", help_level=0, correct=True)
        assert (third["to"], fourth["to"], fifth["to"]) == (1, 2, 3)
    finally:
        sys.path.remove(str(ROOT / "runtime"))


# ---------------------------------------------------------------------------
# 8. spaced repetition (A-S4)
# ---------------------------------------------------------------------------
@test
def test_review_queue_and_intervals(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    today = date.today()
    edit_node(
        project,
        "A1",
        level=2,
        level_source="test",
        review={"interval_index": 1, "due": (today + timedelta(days=3)).isoformat(), "lapses": 0, "last_review_at": None},
    )
    not_due = run(["review", "--project", project], expect=0)
    assert "0 个到期" in not_due.stdout
    assert (today + timedelta(days=3)).isoformat() in not_due.stdout

    edit_node(
        project,
        "A1",
        review={"interval_index": 1, "due": today.isoformat(), "lapses": 0, "last_review_at": None},
    )
    due = run(["review", "--project", project], expect=0)
    assert "复习队列" in due.stdout and "A1" in due.stdout
    plan = read_json(plan_path(project))
    assert plan["mode"] == "review" and plan["current_node"] == "A1"

    script = make_script(tmp / "review.jsonl", [("零提示作答", "独立答对。", upd(help_level=0, correct=True, activity="review"))])
    run(["say", "零提示作答", "--project", project], script=script, expect=0)
    node = node_of(project, "A1")
    assert node["review"]["interval_index"] == 2, node["review"]
    assert node["review"]["due"] == (today + timedelta(days=7)).isoformat(), node["review"]
    assert any(event["payload"].get("passed") is True for event in of_kind(project, "review_result"))


@test
def test_review_short_session_limit(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    today = date.today().isoformat()
    for node_id in ("A1", "A2"):
        edit_node(
            project,
            node_id,
            level=2,
            level_source="test",
            review={"interval_index": 1, "due": today, "lapses": 0, "last_review_at": None},
        )
    run(["start", "--project", project, "--minutes", "20"], expect=0)
    result = run(["review", "--project", project], expect=0)
    plan = read_json(plan_path(project))
    assert len(plan["review_queue"]) == 1, f"20-minute session should review 1 node, got {plan['review_queue']}"
    assert "1/2" in result.stdout


# ---------------------------------------------------------------------------
# 9. examiner must not help
# ---------------------------------------------------------------------------
@test
def test_examiner_help_is_voided(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    edit_node(project, "A1", level=2, level_source="test")
    data = read_json(plan_path(project))
    data.update(
        {
            "current_node": "A1",
            "stage": "check",
            "stage_progress": {"node": "A1", "stage": "check", "passed": False},
            "mode": "stage",
        }
    )
    write_json(plan_path(project), data)
    script = make_script(
        tmp / "exam.jsonl",
        [("作弊提示", "我先给你台阶。", upd(help_level=2, correct=True, activity="A1-check"))],
    )
    run(["start", "--project", project], script=script, expect=0)
    run(["say", "作弊提示", "--project", project], script=script, expect=0)
    assert of_kind(project, "examiner_help_violation"), "violation event missing"
    assert not [e for e in of_kind(project, "attempt") if e["payload"].get("activity_id") == "A1-check"]
    assert node_of(project, "A1")["level"] == 2, "voided turn must not change the level"


# ---------------------------------------------------------------------------
# 10. stage gate (A-S5)
# ---------------------------------------------------------------------------
@test
def test_stage_skip_is_rejected(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    script = make_script(
        tmp / "skip.jsonl",
        [("APPLY", "这是 apply 产物。", upd(help_level=0, correct=True, activity="A1-apply", artifact="artifacts/x.py"))],
    )
    proc = run(["say", "APPLY", "--project", project], script=script, expect=2)
    assert "跳过阶段" in proc.stderr + proc.stdout
    assert not [e for e in of_kind(project, "attempt") if e["payload"].get("activity_id") == "A1-apply"]
    plan = read_json(plan_path(project))
    assert plan["stage"] == "explain", "a rejected submission must not move the stage"


# ---------------------------------------------------------------------------
# 10b. artifact resolution (basename vs full path)
# ---------------------------------------------------------------------------
def _force_apply_stage(project: Path) -> None:
    edit_node(project, "A1", level=1, level_source="test")
    data = read_json(plan_path(project))
    data.update(
        {
            "mode": "stage",
            "current_node": "A1",
            "stage": "apply",
            "stage_progress": {"node": "A1", "stage": "apply", "passed": False},
            "mentor_override": None,
        }
    )
    write_json(plan_path(project), data)


@test
def test_artifact_paths_accept_basename(tmp: Path) -> None:
    """A real file in artifacts/ counts whether the mentor says basename or path."""
    for label, given in (("basename", "parse_record.py"), ("fullpath", "artifacts/parse_record.py")):
        project = new_project(tmp, name=f"artifact-{label}")
        skip_diagnosis(project)
        (project / "artifacts").mkdir(parents=True, exist_ok=True)
        (project / "artifacts" / "parse_record.py").write_text("print('ok')\n", encoding="utf-8")
        _force_apply_stage(project)
        script = make_script(
            tmp / f"{label}.jsonl",
            [("ART", "收到产物。", upd(help_level=0, activity="A1-apply", correct=True, artifact=given))],
        )
        run(["say", "ART", "--project", project], script=script, expect=0)
        assert node_of(project, "A1")["level"] == 2, (label, node_of(project, "A1")["level"])
        assert not of_kind(project, "artifact_missing"), f"{label} must not report artifact_missing"
        ups = [event for event in of_kind(project, "level_up") if event["payload"].get("node") == "A1"]
        assert ups and ups[-1]["payload"]["artifact"] == "artifacts/parse_record.py", ups[-2:]

    # A genuinely absent file is still a miss, and does not write an attempt.
    project = new_project(tmp, name="artifact-really-missing")
    skip_diagnosis(project)
    _force_apply_stage(project)
    script = make_script(
        tmp / "really-missing.jsonl",
        [("MISS", "文件不存在。", upd(help_level=0, activity="A1-apply", correct=True, artifact="nope.py"))],
    )
    run(["say", "MISS", "--project", project], script=script, expect=0)
    assert of_kind(project, "artifact_missing"), "missing artifact must be recorded"
    assert node_of(project, "A1")["level"] == 1
    assert not [e for e in of_kind(project, "attempt") if e["payload"].get("activity_id") == "A1-apply"]


# ---------------------------------------------------------------------------
# 11. handoff / switch
# ---------------------------------------------------------------------------
@test
def test_switch_writes_handoff(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)

    bad = run(["switch", "coach", "--project", project], expect=2)
    error = bad.stderr + bad.stdout
    assert "navigator" in error and "concept" in error, f"error must name the alternatives: {error}"

    unknown = run(["switch", "wizard", "--project", project], expect=2)
    assert "navigator" in (unknown.stderr + unknown.stdout)

    ok = run(["switch", "navigator", "--project", project], expect=0)
    assert "交接" in ok.stdout
    handoff = project / ".learnark" / "handoff" / "latest.md"
    assert handoff.exists()
    text = handoff.read_text(encoding="utf-8")
    for field in ("from", "to", "reason", "what_tried", "unresolved", "next"):
        assert field in text, f"handoff missing {field}"
    events = of_kind(project, "handoff")
    assert events, "handoff event missing"
    payload = events[-1]["payload"]
    assert payload["from"] == "concept" or payload["from"] == "navigator"
    assert payload["to"] == "navigator"
    assert payload["reason"]


@test
def test_pause_handoff_contract(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)
    run(["pause", "--note", "只学了 15 分钟", "--project", project], expect=0)
    text = (project / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    assert "## what_tried" in text and "## unresolved" in text and "## next" in text
    payload = of_kind(project, "handoff")[-1]["payload"]
    assert payload["trigger"] == "pause"
    assert "15" in payload["reason"]
    repeated = run(["pause", "--project", project], expect=0)
    assert "幂等" in repeated.stdout or "已存在" in repeated.stdout


# ---------------------------------------------------------------------------
# 12. recovery
# ---------------------------------------------------------------------------
@test
def test_recovery_from_copy(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)
    clone = tmp / "moved"
    shutil.copytree(project, clone)
    resumed = run(["start", "--project", clone], expect=0)
    assert "A1" in resumed.stdout
    status = run_json(["status", "--project", clone], expect=0)
    assert status["current"]["node"] == "A1"
    assert status["current"]["stage"] == "explain"


@test
def test_corrupt_snapshot_recovers_from_backup(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    (map_path(project)).write_text("{ this is not json", encoding="utf-8")
    status = run_json(["status", "--project", project], expect=0)
    assert status["repairs"], "expected a repair note after restoring from .bak"
    assert len(read_json(map_path(project))["nodes"]) == 12
    assert "recovered" in " ".join(status["repairs"])


@test
def test_torn_journal_tail_is_tolerated(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    events_path = project / ".learnark" / "journal" / "events.jsonl"
    with events_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"kind": "torn", "seq": 999')  # no newline, no closing brace
    status = run_json(["status", "--project", project], expect=0)
    assert status["journal"]["events"] >= 1
    run(["doctor", "--project", project], expect=0)


# ---------------------------------------------------------------------------
# 13. git: local bare remote + clone
# ---------------------------------------------------------------------------
@test
def test_git_push_and_clone(tmp: Path) -> None:
    bare = tmp / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, capture_output=True)
    project = new_project(tmp)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=str(project), check=True, capture_output=True)
    sync = run(["sync", "--project", project], expect=0)
    assert "pushed: yes" in sync.stdout, sync.stdout
    assert "pushed=yes" in sync.stdout

    # Regression for core 1.0.0's GitSync porcelain bug: a second sync used to
    # fail with "git add failed" because the first porcelain line lost its space.
    # A fresh --message guarantees a journal change (the bug's trigger).
    for attempt in range(2):
        again = run(["sync", "--message", f"regression sync {attempt}", "--project", project], expect=0)
        assert "commit-failed" not in again.stdout, again.stdout
        assert "written=yes" in again.stdout, again.stdout
        assert "committed=yes" in again.stdout, again.stdout
        assert "pushed=yes" in again.stdout, again.stdout

    clone = tmp / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    status = run_json(["status", "--project", clone], expect=0)
    assert status["goal"]
    assert status["sync"]["state"] in ("clean", "dirty", "no-repository")


# ---------------------------------------------------------------------------
# 14. determinism (A-S6)
# ---------------------------------------------------------------------------
@test
def test_next_json_is_byte_identical(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    first = run(["next", "--json", "--project", project], expect=0).stdout
    second = run(["next", "--json", "--project", project], expect=0).stdout
    assert first == second, "next --json is not deterministic"
    decision = json.loads(first)
    map_json = run_json(["map", "--project", project], expect=0)
    node = next(item for item in map_json["nodes"] if item["id"] == decision["selected"]["node"])
    assert node["level"] == decision["selected"]["level"]
    assert decision["selected"]["activity_id"] == f"{node['id']}-{decision['selected']['stage']}"
    for reason in decision["reasons"]:
        assert reason and "\n" not in reason
    assert len(decision["reasons"]) == 3


# ---------------------------------------------------------------------------
# 15. cross-topic template
# ---------------------------------------------------------------------------
@test
def test_email_template_uses_writing_nodes(tmp: Path) -> None:
    project = new_project(tmp, template="email", goal="能写出可直接发送的英文工作邮件")
    nodes = read_json(map_path(project))["nodes"]
    assert [node["id"] for node in nodes] == ["W1", "W6", "W2", "W3", "W4", "W5"]
    start = run(["start", "--project", project], expect=0)
    assert "诊断探针 1/3" in start.stdout
    assert "W2" in start.stdout
    decision = run_json(["next", "--project", project], expect=0)
    assert decision["selected"]["node"] == "W1"
    assert decision["selected"]["activity_id"] == "W1-explain"


# ---------------------------------------------------------------------------
# 16. status payload essentials
# ---------------------------------------------------------------------------
@test
def test_status_has_required_fields(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)
    payload = run_json(["status", "--project", project], expect=0)
    for key in ("goal", "current", "map", "plan", "weak_points", "misconceptions", "last_handoff", "next_action", "sync"):
        assert key in payload, f"status --json missing {key}"
    assert payload["map"]["levels"].get("L0") == 12
    assert payload["next_action"]


# ---------------------------------------------------------------------------
# 17. malformed mentor block is recorded, not applied
# ---------------------------------------------------------------------------
@test
def test_invalid_update_block_is_recorded(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    script = tmp / "bad.jsonl"
    script.write_text(
        json.dumps(
            {
                "match": "坏块",
                "reply": "坏块回复\n```learn-update\n{\"help_level\": 9, \"attempt\": \"not-an-object\"}\n```",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    run(["say", "坏块", "--project", project], script=script, expect=0)
    invalid = of_kind(project, "mentor_update_invalid")
    assert invalid, "mentor_update_invalid event missing"
    assert invalid[-1]["payload"]["raw_sha256"]
    assert invalid[-1]["payload"]["problems"]
    assert node_of(project, "A1")["level"] == 0


# ---------------------------------------------------------------------------
# 18. protocol repair is silent (log only) and still applies state
# ---------------------------------------------------------------------------
@test
def test_repair_is_silent_and_applies_state(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_engine  # noqa: PLC0415
        import sm_model  # noqa: PLC0415
        import sm_mentors  # noqa: PLC0415
        from learncore.llm import LLMResult  # noqa: PLC0415

        block = {
            "help_level": 1,
            "attempt": {"activity_id": "A1-explain", "correct": True},
            "probe": None,
            "misconception": None,
            "next": "进入 drill",
            "mastery_delta": 1,
            "artifact": None,
        }

        class FlakyLLM:
            """First reply omits the block; only the silent repair call provides it."""

            mode = "api"

            def __init__(self) -> None:
                self.calls = 0

            def chat(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return LLMResult(text="讲解先给你，机器块我漏了。", model="fake", mode="api")
                body = json.dumps(block, ensure_ascii=False)
                return LLMResult(text="补上。\n```learn-update\n" + body + "\n```", model="fake", mode="api")

        llm = FlakyLLM()
        ctx = sm_engine.Context(project, None, llm)
        ctx.plan.update(
            {
                "mode": "stage",
                "current_node": "A1",
                "stage": "explain",
                "stage_progress": sm_model.fresh_progress("A1", "explain"),
            }
        )
        ctx.mark("plan")
        ctx.ensure_session()
        turn = sm_mentors.turn(
            llm,
            system=ctx.system_prompt(),
            context=ctx.model_context(),
            user="learner answer",
            transcript=[],
        )
        assert llm.calls == 2, f"expected exactly one repair call, got {llm.calls}"
        assert getattr(turn, "repaired", False) is True
        outcome = sm_engine.process_turn(ctx, "learner answer", turn)
        assert outcome.notes == [], f"repair must not surface internal notices, got {outcome.notes}"
        assert ctx.journal.of_kind("mentor_update_retried"), "mentor_update_retried event missing"
        ctx.save()
        assert node_of(project, "A1")["level"] == 1, "the repaired block must still apply"
    finally:
        sys.path.remove(str(ROOT / "runtime"))


# ---------------------------------------------------------------------------
# 19. round-03: budget, on-demand switch, mentor authority, system openings
# ---------------------------------------------------------------------------
def _force_check_stage(project: Path, node: str = "A1", level: int = 2) -> None:
    edit_node(project, node, level=level, level_source="test")
    data = read_json(plan_path(project))
    data.update(
        {
            "mode": "stage",
            "current_node": node,
            "stage": "check",
            "stage_progress": {"node": node, "stage": "check", "passed": False},
            "mentor_override": None,
        }
    )
    write_json(plan_path(project), data)


@test
def test_short_budget_caps_probes_and_task(tmp: Path) -> None:
    """--minutes 10 must not claim 20 minutes and must run at most 2 probes."""
    project = new_project(tmp)
    script = _diagnosis_script(tmp / "short.jsonl", {"B1"}, "短")
    start = run(["start", "--project", project, "--minutes", "10"], script=script, expect=0)
    assert "10 分钟" in start.stdout
    assert "二十分钟" not in start.stdout
    assert "诊断探针 1/2" in start.stdout, start.stdout[-800:]
    assert "只做 2 题" in start.stdout
    constraints = read_json(project / ".learnark" / "project.json")["constraints"]
    assert constraints["short_session_minutes"] == 30

    run(["say", "短1", "--project", project], script=script, expect=0)
    second = run(["say", "短2", "--project", project], script=script, expect=0)
    assert "诊断探针 3/" not in second.stdout, "a 10-minute session must stop after 2 probes"

    probes = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]["probes"]
    assert [probe["status"] for probe in probes] == ["done", "done", "deferred", "deferred", "deferred"], probes
    deferred = of_kind(project, "diagnosis_deferred")
    assert deferred, "diagnosis_deferred event missing"
    assert deferred[-1]["payload"]["deferred"] == ["Q3", "Q4", "Q5"]

    decision = run_json(["next", "--project", project], expect=0)
    assert decision["estimated_minutes"] == 5, decision["estimated_minutes"]
    assert decision["budget_breakdown"]["diagnosis"] == 3
    status = run_json(["status", "--project", project], expect=0)
    assert status["plan"]["minutes_budget"] == 10
    assert status["plan"]["estimate_minutes"] == 5
    assert "5 分钟" in status["next_action"]

    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_engine  # noqa: PLC0415

        context = sm_engine.Context(project, None, None).model_context()
        assert "2 个诊断探针" in context, context[-600:]
    finally:
        sys.path.remove(str(ROOT / "runtime"))


@test
def test_switch_lists_mentors_and_allows_concept_on_demand(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    _force_apply_stage(project)
    run(["start", "--project", project], expect=0)

    status = run_json(["status", "--project", project], expect=0)
    assert "concept" in status["mentors"]["allowed"], status["mentors"]
    assert any(item["id"] == "concept" for item in status["mentors"]["catalog"])
    human = run(["status", "--project", project], expect=0).stdout
    assert "可切换" in human and "概念导师" in human

    switched = run(["switch", "concept", "--project", project], expect=0)
    assert "按需" in switched.stdout
    assert of_kind(project, "on_demand_switch"), "on_demand_switch event missing"
    after = run_json(["status", "--project", project], expect=0)
    assert after["mentors"]["current"] == "concept"
    assert after["plan"]["mentor"] == "concept"

    bad = run(["switch", "examiner", "--project", project], expect=2)
    error = bad.stderr + bad.stdout
    for name in ("navigator", "coach", "concept"):
        assert name in error, f"error must name {name}: {error}"


@test
def test_next_mentor_consistent_across_status_handoff_plan(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)
    run(["switch", "navigator", "--project", project], expect=0)
    run(["pause", "--project", project], expect=0)

    handoff = (project / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    assert "- from: navigator" in handoff and "- to: navigator" in handoff, handoff
    status = run_json(["status", "--project", project], expect=0)
    assert status["mentors"]["current"] == "navigator"
    assert status["plan"]["next_mentor"] == "navigator"
    plan = read_json(plan_path(project))
    assert plan["next_mentor"] == "navigator", plan.get("next_mentor")

    run(["start", "--project", project], expect=0)  # third start: must resolve the same mentor
    third = run_json(["status", "--project", project], expect=0)
    assert third["mentors"]["current"] == "navigator"
    assert third["mentors"]["next"] == "navigator"
    assert read_json(plan_path(project))["session_mentor"] == "navigator"
    assert read_json(plan_path(project))["next_mentor"] == "navigator"


@test
def test_openings_are_system_events_and_activity_labels(tmp: Path) -> None:
    """start/switch must not write learner turns; labels must match the answered activity."""
    project = new_project(tmp)
    script = _diagnosis_script(tmp / "labels.jsonl", set(_PROBE_ANCHORS), "标")
    _run_diagnosis(project, script, "标")

    turns = of_kind(project, "mentor_turn")
    assert len(turns) == 5, f"expected 5 learner turns, got {len(turns)}"
    assert all(event["payload"]["activity_id"] == "diagnose" for event in turns), [e["payload"]["activity_id"] for e in turns]
    assert not any(event["payload"].get("learner_text") in ("开始学习", "继续学习") for event in turns)
    assert of_kind(project, "session_opened"), "session_opened event missing"

    session_file = next((project / "sessions").glob("*.md"))
    text = session_file.read_text(encoding="utf-8")
    assert "开始学习" not in text and "继续学习" not in text
    assert text.count("## 学习者") == 5, text.count("## 学习者")
    assert "## 系统" in text
    # The 5th probe finished the diagnosis and placed B1, yet its label stays diagnose.
    assert read_json(plan_path(project))["current_node"] == "B1"

    # An apply pass must be labelled A1-apply, not A1-check.
    apply_project = new_project(tmp, name="label-apply")
    skip_diagnosis(apply_project)
    _force_apply_stage(apply_project)
    (apply_project / "artifacts").mkdir(parents=True, exist_ok=True)
    (apply_project / "artifacts" / "x.py").write_text("print(1)\n", encoding="utf-8")
    apply_script = make_script(
        tmp / "apply-label.jsonl",
        [("交产物", "产物收到。", upd(help_level=0, activity="A1-apply", correct=True, artifact="artifacts/x.py"))],
    )
    run(["say", "交产物", "--project", apply_project], script=apply_script, expect=0)
    last_turn = of_kind(apply_project, "mentor_turn")[-1]["payload"]
    assert last_turn["activity_id"] == "A1-apply", last_turn["activity_id"]
    assert read_json(plan_path(apply_project))["stage"] == "check"

    run(["pause", "--project", apply_project], expect=0)
    handoff = (apply_project / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    assert "本会话 1 轮对话" in handoff, handoff


# ---------------------------------------------------------------------------
# 20. round-04: verdict conflict, clone context, sync --recover
# ---------------------------------------------------------------------------
@test
def test_verbal_pass_without_evidence_is_conflict(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    _force_check_stage(project)
    script = make_script(
        tmp / "verbal.jsonl",
        [("说过了", "独立题这关过了，现在换场景。", upd(help_level=0, correct=None, activity="A1-check"))],
    )
    run(["start", "--project", project], script=script, expect=0)
    output = run(["say", "说过了", "--project", project], script=script, expect=0).stdout
    assert of_kind(project, "mentor_verdict_conflict"), "mentor_verdict_conflict event missing"
    assert node_of(project, "A1")["level"] == 2
    plan = read_json(plan_path(project))
    assert int(plan["stage_progress"].get("check_correct") or 0) == 0
    assert "阶段通过" not in output
    assert "以状态为准" in output
    assert not [event for event in of_kind(project, "level_up") if event["payload"].get("node") == "A1"]


@test
def test_clone_resume_examiner_context_has_check_activity(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    _force_check_stage(project)
    clone = tmp / "clone"
    shutil.copytree(project, clone)

    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_engine  # noqa: PLC0415

        ctx = sm_engine.Context(clone, None, None)
        context = ctx.model_context()
        assert '"activity_id": "A1-check"' in context, context[-800:]
        prompt = ctx.system_prompt()
        assert "A1-check" in prompt
        assert "本轮只能围绕" in prompt
    finally:
        sys.path.remove(str(ROOT / "runtime"))

    started = run(["start", "--project", clone], expect=0).stdout
    assert "A1-check" in started
    assert "B1-check" not in started


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _append_journal_event(project: Path, event_id: str, at: str) -> None:
    path = project / ".learnark" / "journal" / "events.jsonl"
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    event = {
        "id": event_id,
        "seq": (events[-1]["seq"] + 1) if events else 1,
        "at": at,
        "kind": "test_marker",
        "actor": "test",
        "simulated": False,
        "dedupe_key": f"test:{event_id}",
        "payload": {"marker": event_id},
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _commit_all(project: Path, message: str) -> None:
    _git(project, "add", "-A")
    _git(project, "-c", "user.name=Test", "-c", "user.email=test@local", "commit", "-q", "-m", message)


@test
def test_sync_recover_merges_two_clones(tmp: Path) -> None:
    bare = tmp / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, capture_output=True)
    project = new_project(tmp, name="origin")
    _git(project, "remote", "add", "origin", str(bare))
    run(["sync", "--project", project], expect=0)

    clone = tmp / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    _git(clone, "config", "user.name", "Test")
    _git(clone, "config", "user.email", "test@local")

    _append_journal_event(project, "ev_test_origin", "2026-11-04T04:00:01+08:00")
    _commit_all(project, "origin marker")
    _append_journal_event(clone, "ev_test_clone", "2026-11-04T04:00:02+08:00")
    _commit_all(clone, "clone marker")
    _git(clone, "push", "-q", "origin", "HEAD:master")
    _git(project, "fetch", "-q", "origin")

    recovered = run(["sync", "--recover", "--project", project], expect=0)
    assert "pushed: yes" in recovered.stdout, recovered.stdout
    origin_events = {event.get("id") for event in journal(project)}
    assert {"ev_test_origin", "ev_test_clone"} <= origin_events, origin_events
    third = tmp / "third"
    subprocess.run(["git", "clone", "-q", str(bare), str(third)], check=True, capture_output=True)
    third_events = {event.get("id") for event in journal(third)}
    assert {"ev_test_origin", "ev_test_clone"} <= third_events, "recovered events were not pushed"


@test
def test_sync_recover_snapshot_conflict_fails_with_file_list(tmp: Path) -> None:
    bare = tmp / "remote2.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, capture_output=True)
    project = new_project(tmp, name="origin2")
    _git(project, "remote", "add", "origin", str(bare))
    run(["sync", "--project", project], expect=0)

    clone = tmp / "clone2"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True, capture_output=True)
    _git(clone, "config", "user.name", "Test")
    _git(clone, "config", "user.email", "test@local")

    (project / "README.md").write_text("# origin changed this\n", encoding="utf-8")
    _commit_all(project, "origin readme")
    (clone / "README.md").write_text("# clone changed this too\n", encoding="utf-8")
    _commit_all(clone, "clone readme")
    _git(clone, "push", "-q", "origin", "HEAD:master")
    _git(project, "fetch", "-q", "origin")

    blocked = run(["sync", "--recover", "--project", project], expect=3)
    combined = blocked.stdout + blocked.stderr
    assert "README.md" in combined, combined
    assert "conflict" in combined.lower() or "冲突" in combined, combined
    status = run_json(["status", "--project", project], expect=0)
    assert status["sync"]["state"] in ("diverged", "unmerged"), status["sync"]
    doctor = run(["doctor", "--project", project], expect=None)
    assert doctor.returncode != 0, "doctor must fail while diverged"
    assert "sync --recover" in doctor.stdout


# ---------------------------------------------------------------------------
# 21. round-05: end-to-end budget, dialogue skip, truthful resume
# ---------------------------------------------------------------------------
def _force_node_stage(project: Path, node: str, stage: str, level: int = 1) -> None:
    edit_node(project, node, level=level, level_source="test")
    data = read_json(plan_path(project))
    data.update(
        {
            "mode": "stage",
            "current_node": node,
            "stage": stage,
            "stage_progress": {"node": node, "stage": stage, "passed": False},
            "mentor_override": None,
        }
    )
    write_json(plan_path(project), data)


@test
def test_budget_end_to_end_arithmetic(tmp: Path) -> None:
    """20 min = diagnosis 3 + activity 15 + wrap-up 2; 10 min = one small task."""
    project = new_project(tmp)
    script = _diagnosis_script(tmp / "e2e.jsonl", {"B1"}, "算")
    start = run(["start", "--project", project, "--minutes", "20"], script=script, expect=0)
    assert "诊断探针 1/2" in start.stdout, start.stdout[-900:]
    run(["say", "算1", "--project", project], script=script, expect=0)
    run(["say", "算2", "--project", project], script=script, expect=0)

    resumed = run(["start", "--project", project], script=script, expect=0).stdout
    assert "诊断 3" in resumed and "活动 15" in resumed and "收尾 2" in resumed, resumed[-1400:]
    assert "预计：15 分钟" in resumed
    decision = run_json(["next", "--project", project], expect=0)
    parts = decision["budget_breakdown"]
    assert (parts["diagnosis"], parts["activity"], parts["reserve"]) == (3, 15, 2), parts
    assert parts["activity"] + parts["diagnosis"] + parts["reserve"] <= 20
    status = run_json(["status", "--project", project], expect=0)
    assert status["plan"]["estimate_minutes"] == 15
    assert "15 分钟" in status["next_action"]

    ten = new_project(tmp, name="ten")
    ten_script = _diagnosis_script(tmp / "ten.jsonl", {"B1"}, "十")
    run(["start", "--project", ten, "--minutes", "10"], script=ten_script, expect=0)
    run(["say", "十1", "--project", ten], script=ten_script, expect=0)
    run(["say", "十2", "--project", ten], script=ten_script, expect=0)
    small = run(["start", "--project", ten], script=ten_script, expect=0).stdout
    assert "预计：5 分钟" in small, small[-1200:]
    assert "活动 5" in small and "诊断 3" in small and "收尾 2" in small
    ten_next = run_json(["next", "--project", ten], expect=0)
    assert ten_next["estimated_minutes"] == 5, ten_next["estimated_minutes"]


@test
def test_dialogue_skip_stops_diagnosis_and_keeps_levels(tmp: Path) -> None:
    project = new_project(tmp)
    script = make_script(
        tmp / "dialogue-skip.jsonl",
        [
            ("跳1", "B1 记 L1。", upd(activity="diagnose", correct=None, probe={"node": "B1", "level": 1, "reason": "答对"})),
            (
                "跳2",
                "诊断到此结束，剩下三题跳过。",
                upd(activity="diagnose", correct=None, probe={"node": "C2", "level": 1, "reason": "答对"}, diagnosis="skip"),
            ),
        ],
    )
    run(["start", "--project", project], script=script, expect=0)
    run(["say", "跳1", "--project", project], script=script, expect=0)
    run(["say", "跳2", "--project", project], script=script, expect=0)

    diagnosis = read_json(project / ".learnark" / "project.json")["learner"]["diagnosis"]
    assert diagnosis["status"] == "skipped", diagnosis
    assert diagnosis["end_reason"] == "dialogue_block", diagnosis
    assert [probe["status"] for probe in diagnosis["probes"]] == ["done", "done", "deferred", "deferred", "deferred"]
    assert node_of(project, "B1")["level"] == 1 and node_of(project, "C2")["level"] == 1
    assert of_kind(project, "diagnosis_skipped"), "diagnosis_skipped event missing"

    status = run_json(["status", "--project", project], expect=0)
    assert status["learner"]["diagnosis"]["status"] == "skipped"
    assert status["learner"]["diagnosis"]["deferred"] == ["Q3", "Q4", "Q5"]
    human = run(["status", "--project", project], expect=0).stdout
    assert "诊断：已跳过" in human
    assert "Q3" not in status["next_action"]


@test
def test_placement_survives_skip_and_levels_never_roll_back(tmp: Path) -> None:
    project = new_project(tmp)
    script = _diagnosis_script(tmp / "place-skip.jsonl", {"B1", "C2", "D2", "A2"}, "位")
    run(["start", "--project", project], script=script, expect=0)
    for index in range(1, 5):
        run(["say", f"位{index}", "--project", project], script=script, expect=0)
    run(["say", "跳过剩下的诊断", "--project", project], script=script, expect=0)

    plan = read_json(plan_path(project))
    assert plan["current_node"] == "B1", plan.get("current_node")
    assert plan["stage"] == "apply", plan.get("stage")
    assert (plan.get("placement") or {}).get("node") == "B1", plan.get("placement")
    for anchor in ("B1", "C2", "D2", "A2"):
        assert node_of(project, anchor)["level"] == 1, anchor


@test
def test_resume_note_never_claims_unearned_pass(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    _force_node_stage(project, "A1", "apply", level=1)
    (project / "artifacts").mkdir(parents=True, exist_ok=True)
    (project / "artifacts" / "x.py").write_text("print(1)\n", encoding="utf-8")
    script = make_script(
        tmp / "apply-then-check.jsonl",
        [("交产物", "产物收到。", upd(activity="A1-apply", correct=True, artifact="artifacts/x.py"))],
    )
    run(["say", "交产物", "--project", project], script=script, expect=0)
    assert read_json(plan_path(project))["stage"] == "check"

    started = run(["start", "--project", project], expect=0).stdout
    assert "本阶段还没有提交记录" in started, started[-1200:]
    assert "已通过" not in started
    assert "A1-check" in started

    status = run_json(["status", "--project", project], expect=0)
    assert status["plan"]["activity_id"] == "A1-check"
    assert "A1-check" in status["next_action"]


@test
def test_status_exposes_session_help_level(tmp: Path) -> None:
    project = new_project(tmp)
    skip_diagnosis(project)
    run(["start", "--project", project], expect=0)
    script = make_script(
        tmp / "help.jsonl",
        [("提示", "先想想边界条件。", upd(activity="A1-explain", correct=None, help_level=1))],
    )
    run(["say", "提示", "--project", project], script=script, expect=0)
    status = run_json(["status", "--project", project], expect=0)
    assert status["help"]["last_help_level"] == 1, status["help"]
    human = run(["status", "--project", project], expect=0).stdout
    assert "上次提示等级 1" in human


# ---------------------------------------------------------------------------
# 22. round-06: self-contained email probes, writing artifacts, template counts
# ---------------------------------------------------------------------------
@test
def test_email_probes_include_their_material(tmp: Path) -> None:
    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_model  # noqa: PLC0415

        probes = sm_model.probe_defs("email")
        q2 = next(probe for probe in probes if probe["id"] == "Q2")
        assert "材料：" in q2["question"], q2["question"]
        assert "November 12" in q2["question"]
        # Only probes that quote an existing text need a material block; Q1/Q3
        # are self-contained (the sentence to rewrite / a scenario brief).
        for probe in probes:
            if any(word in probe["question"] for word in ("下面", "以下", "材料")):
                assert "材料：" in probe["question"], probe
    finally:
        sys.path.remove(str(ROOT / "runtime"))


@test
def test_writing_artifact_is_autosaved_from_message(tmp: Path) -> None:
    project = new_project(tmp, name="mail-artifact", template="email", goal="能写出清楚的英文工作邮件")
    skip_diagnosis(project)
    edit_node(project, "W1", level=1, level_source="test")
    _force_node_stage(project, "W2", "apply", level=1)
    card = run(["start", "--project", project], expect=0).stdout
    assert "产物：" in card and ".md" in card, card[-900:]

    mail = (
        "Subject: New launch date\n\n"
        "Hi Mark,\n\n"
        "We need to move the launch to November 12 because the design files arrived late.\n"
        "Could you confirm by Friday that the new date works?\n\nThanks,\nTina"
    )
    script = make_script(
        tmp / "writing.jsonl",
        [("Subject: New launch date", "这版可以发。", upd(activity="W2-apply", correct=True))],
    )
    out = run(["say", mail, "--project", project], script=script, expect=0).stdout
    assert "产物：已把本轮文本存为" in out, out[-900:]
    saved = list((project / "artifacts").glob("w2-apply-*.md"))
    assert saved, "autosaved writing artifact missing"
    assert "November 12" in saved[0].read_text(encoding="utf-8")
    assert node_of(project, "W2")["level"] == 2
    assert of_kind(project, "artifact_autosaved"), "artifact_autosaved event missing"
    assert read_json(plan_path(project))["stage"] == "check"


@test
def test_email_template_counts_and_topic_are_derived(tmp: Path) -> None:
    project = new_project(tmp, name="mail-topic", template="email", goal="能写出清楚的英文工作邮件")
    script = make_script(tmp / "neutral.jsonl", [("开始学习", "好的，先看第一题。", upd(activity="diagnose", correct=None))])
    started = run(["start", "--project", project, "--minutes", "20"], script=script, expect=0).stdout
    assert "诊断探针 1/2" in started
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "6 个节点" in readme, readme[:400]
    assert "12 节点" not in readme and "12 个节点" not in readme
    for word in ("Agent", "API", "接口", "认证", "联调", "代码"):
        assert word not in started, f"{word!r} leaked into start output"
        assert word not in readme, f"{word!r} leaked into README"

    _force_node_stage(project, "W2", "check", level=2)
    sys.path.insert(0, str(ROOT / "runtime"))
    try:
        import sm_engine  # noqa: PLC0415

        ctx = sm_engine.Context(project, None, None)
        prompt = ctx.system_prompt()
        assert "英文工作邮件写作" in prompt
        assert "template=email" in ctx.model_context() or "email" in prompt
    finally:
        sys.path.remove(str(ROOT / "runtime"))


# ---------------------------------------------------------------------------
# 23. D-Reliability suite (tests/test_reliability.py)
# ---------------------------------------------------------------------------
@test
def test_reliability_suite_is_green(tmp: Path) -> None:
    """The dedicated reliability suite must pass as a whole, not just import."""
    suite = ROOT / "tests" / "test_reliability.py"
    assert suite.is_file(), f"missing {suite}"
    env = dict(os.environ)
    env.update({"LEARNARK_LLM": "mock", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    for key in ("LEARNARK_NOW", "LEARNARK_PROJECT", "LEARNARK_MOCK_SCRIPT", "LEARNARK_LOCK_TIMEOUT"):
        env.pop(key, None)
    proc = subprocess.run(
        [sys.executable, str(suite)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=900,
    )
    combined = (proc.stdout or "")[-2500:] + (proc.stderr or "")[-2500:]
    assert proc.returncode == 0, f"reliability suite failed (exit {proc.returncode}):\n{combined}"
    assert "reliability tests passed" in (proc.stdout or ""), combined


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------
def main() -> int:
    if not ENTRY.exists():
        print(f"missing entry point: {ENTRY}")
        return 1
    failures = []
    started = time.time()
    for fn in TESTS:
        tmp = Path(tempfile.mkdtemp(prefix="skillmap-test-"))
        began = time.time()
        try:
            fn(tmp)
            print(f"PASS  {fn.__name__}  ({time.time() - began:.1f}s)")
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception as exc:  # noqa: BLE001 - report every failure
            failures.append(fn.__name__)
            print(f"FAIL  {fn.__name__}  ({time.time() - began:.1f}s)")
            print(f"      {type(exc).__name__}: {exc}")
            if VERBOSE:
                traceback.print_exc()
            print(f"      kept for debugging: {tmp}")
    total = len(TESTS)
    passed = total - len(failures)
    print("")
    print(f"{passed}/{total} tests passed in {time.time() - started:.1f}s")
    if failures:
        print("failed: " + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
