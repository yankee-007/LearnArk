"""Tempo (direction D) test suite.

Runs standalone with the standard library only: ``python tests/run_tests.py``.
Default mentor is the offline script (``LEARNARK_LLM=mock``); no network is used.
All spaced-repetition assertions go through ``learncore.clock`` + ``LEARNARK_NOW``
and are reported as simulated time (the events carry ``simulated: true``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
ENTRY = RUNTIME / "learn.py"
FIXTURE = ROOT / "experiments" / "fixtures" / "tempo-budget.json"
REPAIR_SCRIPT = ROOT / "tests" / "fixtures" / "repair_script.jsonl"
sys.path.insert(0, str(RUNTIME))

import tempo  # noqa: E402
from learncore import clock  # noqa: E402
from learncore.fsutil import StaleWrite, write_json  # noqa: E402

NOW0 = "2026-11-04T19:00:00+08:00"
BASE = Path(tempfile.mkdtemp(prefix="tempo-tests-"))
RESULTS: list[tuple[str, bool, str]] = []


# --------------------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------------------


def fresh(name: str) -> Path:
    path = BASE / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def run(
    args: list[str],
    cwd: Path,
    *,
    now: str | None = NOW0,
    offline: bool = True,
    expect: int | None = 0,
    env_extra: dict | None = None,
) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith("LEARNARK_")}
    env.update({"LEARNARK_LLM": "mock", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    env.pop("LEARNARK_NOW", None)
    if now:
        env["LEARNARK_NOW"] = now
    if env_extra:
        env.update(env_extra)
    command = [sys.executable, str(ENTRY), *args]
    if offline:
        command.append("--offline")
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=240,
    )
    out = proc.stdout or ""
    err = proc.stderr or ""
    if expect is not None and proc.returncode != expect:
        raise AssertionError(
            f"command {' '.join(args)} exited {proc.returncode}, expected {expect}\n"
            f"--- stdout ---\n{out[-3000:]}\n--- stderr ---\n{err[-2000:]}"
        )
    return {"code": proc.returncode, "out": out, "err": err, "text": out + err}


def init_proj(
    name: str,
    *,
    template: str = "agent-dev",
    now: str = NOW0,
    minutes_per_week: int | None = None,
    goal: str = "能独立设计、实现并评测一个可用的 Agent 应用",
) -> Path:
    work = fresh(name)
    proj = work / "proj"
    args = ["init", "--goal", goal, "--dir", str(proj), "--template", template]
    if minutes_per_week is not None:
        args += ["--minutes-per-week", str(minutes_per_week)]
    run(args, work, now=now)
    return proj


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_state(proj: Path, name: str) -> dict:
    return read_json(proj / ".learnark" / "state" / f"{name}.json")


def journal(proj: Path) -> list[dict]:
    path = proj / ".learnark" / "journal" / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def kinds(proj: Path) -> Counter:
    return Counter(event.get("kind") for event in journal(proj))


def status_json(proj: Path, now: str = NOW0) -> dict:
    result = run(["status", "--json", "--project", str(proj)], proj, now=now)
    text = result["out"].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        return json.loads(text[start:])


def load_store(proj: Path, now: str | None = NOW0, *, offline: bool = True) -> tempo.Store:
    if now:
        clock.simulate(now)
    return tempo.Store(proj, offline=offline).load()


def make_cand(
    activity_id: str,
    activity_type: str,
    skill: str,
    minutes: int,
    *,
    tier: int,
    source: str,
    due_at: str | None = None,
    overdue: int = 0,
    level: int = 1,
    new: bool = False,
    errors: int = 0,
    plan_progress: float = 0.0,
    leech: bool = False,
    template: str | None = None,
) -> dict:
    return {
        "activity_id": activity_id,
        "activity_type": activity_type,
        "template": template or activity_type,
        "skill": skill,
        "skill_title": skill,
        "minutes": minutes,
        "mentor": tempo.ACTIVITY_MENTOR.get(activity_type, "coach"),
        "tier": tier,
        "source": source,
        "due": due_at is not None,
        "due_at": due_at,
        "overdue_days": overdue,
        "level": level,
        "new": new,
        "errors_7d": errors,
        "plan_progress": plan_progress,
        "leech": leech,
        "card_id": None,
        "card_ids": [],
        "recent_skill": False,
        "today_template": False,
        "label": activity_id,
        "task": "test",
    }


def activity_dict(
    activity_id: str,
    activity_type: str,
    skill: str,
    *,
    minutes: int = 5,
    level: int = 0,
    mentor: str | None = None,
    block_id: str | None = None,
    step_index: int | None = None,
) -> dict:
    return {
        "activity_id": activity_id,
        "activity_type": activity_type,
        "template": activity_type,
        "skill": skill,
        "skill_title": skill,
        "minutes": minutes,
        "level": level,
        "mentor": mentor or tempo.ACTIVITY_MENTOR.get(activity_type, "coach"),
        "tier": 3,
        "source": "test",
        "block_id": block_id,
        "step_index": step_index,
        "card_ids": [],
        "card_id": None,
        "template_id": "agent-dev",
        "task": "test task",
    }


def updates_for(activity: dict, *, help_level: int = 0, correct: bool = True, mastery: int = 1, **extra) -> dict:
    payload = {
        "help_level": help_level,
        "attempt": {"activity_id": activity["activity_id"], "correct": correct},
        "misconception": None,
        "next": "下一步建议（测试）",
        "mastery_delta": mastery,
    }
    payload.update(extra)
    return payload


def apply(
    store: tempo.Store,
    session: dict,
    activity: dict,
    text: str,
    payload: dict | None,
    *,
    mode: str = "api",
    error: str = "",
    visible: str = "",
    previous_mentor: str = "",
) -> dict:
    raw = json.dumps(payload, ensure_ascii=False) if payload is not None else "no block"
    turn_index = tempo.count_session_turns(store, session["id"])
    return tempo.apply_turn(
        store,
        session,
        activity,
        text,
        raw,
        payload,
        error,
        turn_index,
        mode,
        visible=visible,
        previous_mentor=previous_mentor,
    )


# --------------------------------------------------------------------------------------
# tests: contract / e2e
# --------------------------------------------------------------------------------------


def test_init_idempotent():
    work = fresh("init")
    proj = work / "proj"
    first = run(["init", "--goal", "测试目标", "--dir", str(proj)], work)
    assert "已创建" in first["out"]
    required = [
        ".learnark/project.json",
        ".learnark/state/schedule.json",
        ".learnark/state/skills.json",
        ".learnark/state/cards.json",
        ".learnark/state/blocks.json",
        ".learnark/journal/events.jsonl",
        ".learnark/journal/dedupe.json",
        "AGENTS.md",
        "README.md",
        ".gitignore",
        ".gitattributes",
        "sessions",
        "artifacts",
    ]
    for relative in required:
        assert (proj / relative).exists(), f"missing {relative}"
    assert (proj / ".gitattributes").read_text(encoding="utf-8").strip().endswith("* -text")
    meta = read_json(proj / ".learnark/project.json")
    assert meta["goal"] == "测试目标"
    assert meta["schema_version"] == 1
    assert meta["template_id"] == "agent-dev"
    assert len(read_state(proj, "skills")["skills"]) == 10
    cards = read_state(proj, "cards")["cards"]
    assert len(cards) == 12
    assert sum(1 for card in cards if card["due_at"] == NOW0) == 2, "only a small diagnostic set is due on day one"
    assert any(card["due_at"] > NOW0 for card in cards), "the rest must be spread into future days"
    assert any(event["kind"] == "initial_cards_spread" for event in journal(proj))
    assert (proj / ".git").exists()

    second = run(["init", "--goal", "另一个目标", "--dir", str(proj)], work)
    assert second["code"] == 0 and "已存在" in second["out"]
    assert read_json(proj / ".learnark/project.json")["goal"] == "测试目标"
    assert kinds(proj)["project_initialized"] == 1
    agents = (proj / "AGENTS.md").read_text(encoding="utf-8")
    assert "start" in agents and "不得" in agents and "journal" in agents
    readme = (proj / "README.md").read_text(encoding="utf-8")
    assert "现在输入什么" in readme and "start" in readme


def test_offline_e2e():
    proj = init_proj("e2e")
    start = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    assert "[离线脚本导师]" in start["out"]
    assert "候选" in start["out"] and "为什么是它" in start["out"]
    say = run(
        ["say", "循环的三种停止条件是：达成目标、轮次上限、连续两次没有新信息", "--project", str(proj)],
        proj,
    )
    assert "提示级别 0（独立完成）" in say["out"] and "证据：观察记录" in say["out"]
    state = status_json(proj)
    assert state["today"]["items_started"] == 1
    agent_loop = next(skill for skill in state["skills"] if skill["id"] == "agent-loop")
    assert agent_loop["level"] == 1
    assert agent_loop["last_help_level"] == 0 and agent_loop["last_evidence_kind"] == "independent"
    assert state["last_turn"]["help_level"] == 0 and state["last_turn"]["assisted"] is False
    pause = run(["pause", "--note", "测试结束", "--project", str(proj)], proj)
    assert "git state" in pause["out"]
    handoff = proj / ".learnark" / "handoff" / "latest.md"
    assert handoff.exists()
    text = handoff.read_text(encoding="utf-8")
    for field in ("上次停在哪", "试过什么", "哪里不稳", "下一步", "未决问题"):
        assert field in text, f"handoff missing {field}"
    sync = run(["sync", "--project", str(proj)], proj)
    assert "written=" in sync["out"] and "committed=" in sync["out"] and "pushed=" in sync["out"]
    doctor = run(["doctor", "--project", str(proj)], proj)
    assert "0 项问题" in doctor["out"]
    export = proj / "artifacts" / "export.md"
    run(["export", "--out", str(export), "--project", str(proj)], proj)
    assert export.stat().st_size > 100
    found = kinds(proj)
    for kind in ("schedule_decision", "session_opened", "turn", "attempt", "activity_completed", "handoff"):
        assert found[kind] >= 1, f"missing journal kind {kind}"
    sessions = list((proj / "sessions").glob("*.md"))
    assert sessions
    session_text = sessions[0].read_text(encoding="utf-8")
    assert "## 学习者" in session_text and "## 导师" in session_text
    assert "循环的三种停止条件" in session_text


# --------------------------------------------------------------------------------------
# tests: budgets
# --------------------------------------------------------------------------------------


def test_budget_parsing():
    cases = {
        "今天只有二十分钟": 20,
        "只有一刻钟": 15,
        "半小时": 30,
        "20分钟": 20,
        "20 min": 20,
        "二十五分钟": 25,
        "一会儿": 10,
        "五分钟": 5,
        "三分钟": 5,
        "九十分钟": 45,
        "45": 45,
    }
    for text, expected in cases.items():
        parsed = tempo.parse_budget_text(text)
        assert parsed.parsed and parsed.minutes == expected, (text, parsed.as_dict())
    hour = tempo.parse_budget_text("我有 一小时")
    assert hour.minutes == 45 and hour.clamped and "上限" in hour.note
    short = tempo.parse_budget_text("三分钟")
    assert short.minutes == 5 and "最少 5 分钟" in short.note
    assert tempo.parse_budget_text("今天状态一般").parsed is False

    parsed, source, note = tempo.budget_for_start(3, None, 20)
    assert parsed.minutes == 5 and source == "flag"
    parsed, source, note = tempo.budget_for_start(None, "今天只有二十分钟", 20)
    assert parsed.minutes == 20 and source == "text"
    parsed, source, note = tempo.budget_for_start(None, "随便学点", 20)
    assert parsed.minutes == 20 and "默认" in note

    proj = init_proj("budget-start")
    run(["start", "今天只有二十分钟", "--project", str(proj)], proj)
    assert status_json(proj)["today"]["minutes_budget"] == 20
    assert read_state(proj, "schedule")["today"]["minutes_budget"] == 20

    proj2 = init_proj("budget-say")
    said = run(["say", "只有一刻钟", "--project", str(proj2)], proj2)
    assert "不改今日预算" in said["out"], said["out"]
    assert status_json(proj2)["today"]["minutes_budget"] == 20
    assert read_state(proj2, "schedule")["today"]["minutes_budget"] == 20
    assert any(event["kind"] == "budget_ignored_in_answer" and event["payload"]["matched"] == "一刻钟" for event in journal(proj2))


# --------------------------------------------------------------------------------------
# tests: direction acceptance D-S1 / D-S2 / D-S3
# --------------------------------------------------------------------------------------


def fixture_candidates(now: str) -> tuple[dict, list[dict]]:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    candidates = []
    for item in data["candidates"]:
        entry = {key: value for key, value in item.items() if key not in ("key", "due_offset_days")}
        offset = item.get("due_offset_days")
        if offset is None:
            entry.update({"due": False, "due_at": None, "overdue_days": 0})
        else:
            entry.update(
                {
                    "due": True,
                    "due_at": clock.add_days(now, int(offset)),
                    "overdue_days": max(0, -int(offset)),
                }
            )
        entry.setdefault("recent_skill", False)
        entry.setdefault("today_template", False)
        candidates.append(entry)
    return data, candidates


def test_d_s1_budget_changes_choice():
    clock.simulate(NOW0)
    try:
        data, candidates = fixture_candidates(NOW0)
        for budget in (5, 20, 45):
            expected = data["expect"][str(budget)]
            runs = [tempo.select_activities(candidates, budget, max_items=2) for _ in range(3)]
            first = runs[0]
            assert first["chosen"]["activity_id"] == expected["chosen"], (budget, first["chosen"])
            assert first["plan_ids"] == expected["plan"], (budget, first["plan_ids"])
            blobs = [json.dumps(result, ensure_ascii=False, sort_keys=True) for result in runs]
            assert blobs[0] == blobs[1] == blobs[2], f"budget {budget} is not deterministic"
        five = tempo.select_activities(candidates, 5, max_items=2)
        row_b = next(row for row in five["rows"] if row["activity_id"] == "kata-B")
        assert "本次放不下" in row_b["reason"], row_b["reason"]
        assert "下次（约 15 分钟）" in row_b["reason"], row_b["reason"]
        assert "超出剩余" not in row_b["reason"], row_b["reason"]
        twenty = tempo.select_activities(candidates, 20, max_items=2)
        assert next(row for row in twenty["rows"] if row["activity_id"] == "kata-B")["factors"]["U"] == 1.0
        forty_five = tempo.select_activities(candidates, 45, max_items=2)
        row = next(row for row in forty_five["rows"] if row["activity_id"] == "kata-B")
        expected_score = 0.40 * 1.0 + 0.20 * (1 / 3) + 0.20 * (15 / 45)
        assert abs(row["score"] - expected_score) < 1e-5, (row["score"], expected_score)
        assert [candidate["activity_id"] for candidate in forty_five["plan"]] == ["kata-B", "quiz-C"]
    finally:
        clock.simulate(None)


def test_d_s2_due_priority():
    clock.simulate(NOW0)
    try:
        candidates = [
            make_cand("due-overdue3", "recall_card", "skill-x", 5, tier=1, source="due_card", due_at=clock.add_days(NOW0, -3), overdue=3, level=1),
            make_cand("block-step", "concept_block", "skill-y", 12, tier=2, source="block_step", plan_progress=1.0, level=0),
            make_cand("new-skill", "concept_block", "skill-z", 10, tier=3, source="weak_new", level=0, new=True),
        ]
        result = tempo.select_activities(candidates, 20, max_items=1)
        assert result["chosen"]["activity_id"] == "due-overdue3"
        due_row = next(row for row in result["rows"] if row["activity_id"] == "due-overdue3")
        assert due_row["factors"]["U"] == 1.0
        assert "到期组" in result["reason_line"]
        block_row = next(row for row in result["rows"] if row["activity_id"] == "block-step")
        new_row = next(row for row in result["rows"] if row["activity_id"] == "new-skill")
        assert "tier 2 未进入" in block_row["reason"], block_row["reason"]
        assert "tier 3 未进入" in new_row["reason"], new_row["reason"]
        with_plan = tempo.select_activities(candidates, 20, max_items=2)
        assert with_plan["chosen"]["activity_id"] == "due-overdue3"
    finally:
        clock.simulate(None)


def test_d_s3_same_day_no_repeat():
    proj = init_proj("d-s3")
    run(["start", "--minutes", "10", "--project", str(proj)], proj)
    items = read_state(proj, "schedule")["today"]["items"]
    assert len(items) == 1
    second = run(["start", "--minutes", "10", "--project", str(proj)], proj)
    assert "[未完成]" in second["out"], second["out"]
    assert any(event["kind"] == "activity_replaced" for event in journal(proj))
    items = read_state(proj, "schedule")["today"]["items"]
    assert len(items) == 2
    assert items[0]["activity_id"] != items[1]["activity_id"]
    assert items[0]["skill"] != items[1]["skill"]
    assert items[0]["activity_type"] != items[1]["activity_type"]
    third = run(["start", "--minutes", "10", "--project", str(proj)], proj)
    assert "今日已排 2/2 项" in third["out"]
    assert len(read_state(proj, "schedule")["today"]["items"]) == 2


# --------------------------------------------------------------------------------------
# tests: SRS
# --------------------------------------------------------------------------------------


def test_srs_ladder_and_lapse():
    clock.simulate(NOW0)
    try:
        card = {"id": "c1", "step": 0, "ease": 1.0, "lapses": 0, "consecutive_lapses": 0, "leech": False}
        first = tempo.grade_card(card, "good", NOW0)
        assert first["step"] == 1 and card["due_at"] == clock.add_days(NOW0, 2)
        day2 = clock.add_days(NOW0, 2)
        second = tempo.grade_card(card, "good", day2)
        expected_interval = tempo.interval_for(2, 1.30)
        assert second["step"] == 2 and card["due_at"] == clock.add_days(day2, expected_interval)
        assert abs(card["ease"] - 1.30) < 1e-9
        card.update({"step": 4, "ease": 1.0, "lapses": 0, "consecutive_lapses": 0, "leech": False})
        lapse = tempo.grade_card(card, "again", day2)
        assert lapse["step"] == 2 and lapse["due_at"] == clock.add_days(day2, 1)
        assert abs(card["ease"] - 0.85) < 1e-9 and card["lapses"] == 1, "ease clamps at 0.85"
        assert lapse["new_leech"] is False
        second_lapse = tempo.grade_card(card, "again", day2)
        assert second_lapse["step"] == 0 and second_lapse["new_leech"] is True and card["leech"] is True
        for _ in range(10):
            tempo.grade_card(card, "again", day2)
        assert card["ease"] >= 0.85 - 1e-9
        card.update({"step": 6, "ease": 1.6, "consecutive_lapses": 0, "leech": False})
        easy = tempo.grade_card(card, "easy", day2)
        assert 1 <= easy["interval_days"] <= 90
        hard = dict(card)
        hard.update({"step": 2, "ease": 1.0})
        hard_change = tempo.grade_card(hard, "hard", day2)
        assert hard_change["step"] == 2 and hard_change["interval_days"] >= 1
    finally:
        clock.simulate(None)


def test_srs_simulated_clock_cli():
    proj = init_proj("srs-cli")
    clock.simulate(NOW0)
    try:
        run(["start", "--minutes", "20", "--project", str(proj)], proj, now=NOW0)
        run(["say", "连续两次没有新信息", "--project", str(proj)], proj, now=NOW0)
        card = next(c for c in read_state(proj, "cards")["cards"] if c["id"] == "card-0002")
        assert card["step"] == 1, card
        assert card["due_at"] == clock.add_days(NOW0, 2), card["due_at"]
        day2 = clock.add_days(NOW0, 2)
        run(["say", "连续两次没有新信息", "--project", str(proj)], proj, now=day2)
        card = next(c for c in read_state(proj, "cards")["cards"] if c["id"] == "card-0002")
        expected_interval = tempo.interval_for(2, 1.30)
        assert card["step"] == 2 and card["due_at"] == clock.add_days(day2, expected_interval), card
        day3 = clock.add_days(NOW0, 3)
        due = json.loads(run(["due", "--json", "--project", str(proj)], proj, now=day3)["out"])
        ids = {item["id"] for item in due["cards"]}
        assert "card-0002" not in ids, "the reviewed card must leave the due queue until day 6"
        assert any(item["overdue_days"] >= 3 for item in due["cards"])
        assert due["simulated"] is True
        attempts = [event for event in journal(proj) if event["kind"] == "attempt"]
        assert attempts and all(event.get("simulated") is True for event in attempts)
    finally:
        clock.simulate(None)


def test_backlog_fold_and_session_cap():
    proj = init_proj("backlog")
    clock.simulate(NOW0)
    try:
        cards_path = proj / ".learnark" / "state" / "cards.json"
        data = read_json(cards_path)
        for card in data["cards"]:
            card["due_at"] = clock.add_days(NOW0, -1)
        extra = dict(data["cards"][0])
        extra.update({"id": "card-9999", "front": "额外积压卡", "source_event": "test:seed"})
        data["cards"].append(extra)
        write_json(cards_path, data)
        started = run(["start", "--minutes", "20", "--project", str(proj)], proj)
        assert "[调整]" in started["out"] and "顺延 3 天" in started["out"], started["out"]
        events = journal(proj)
        folded = [event for event in events if event["kind"] == "backlog_folded"]
        assert folded, "13 due cards must trigger backlog_folded"
        remaining = [card for card in read_state(proj, "cards")["cards"] if tempo.is_due(card["due_at"], NOW0)]
        assert len(remaining) <= 12, len(remaining)
        decision = [event for event in events if event["kind"] == "schedule_decision"][-1]
        tier1_cards = [
            candidate
            for candidate in decision["payload"]["candidates"]
            if candidate["tier"] == 1 and candidate["source"] == "due_card"
        ]
        assert len(tier1_cards) <= 3, tier1_cards
    finally:
        clock.simulate(None)


def test_weekly_card_cap():
    assert tempo.weekly_card_cap(600) == 13
    assert tempo.weekly_card_cap(180) == 5
    assert tempo.weekly_card_cap(45) == 5
    assert tempo.weekly_card_cap(3600) == 40
    proj = init_proj("card-cap", minutes_per_week=45)
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        for index in range(5):
            store.cards["cards"].append(
                {
                    "id": f"card-test-{index}",
                    "skill": "agent-loop",
                    "kind": "recall",
                    "front": f"f{index}",
                    "back": "b",
                    "tags": ["test"],
                    "source_event": "test:seed",
                    "step": 0,
                    "ease": 1.0,
                    "interval_days": 1,
                    "due_at": NOW0,
                    "last_review_at": None,
                    "lapses": 0,
                    "consecutive_lapses": 0,
                    "leech": False,
                    "needs_rewrite": False,
                    "created_at": NOW0,
                }
            )
        out = {"cards": [], "notes": []}
        tempo._apply_card_create(
            store,
            {"op": "create", "skill": "agent-loop", "kind": "recall", "front": "新卡正面", "back": "新卡背面", "tags": ["test"]},
            {},
            "attempt:test:queue",
            NOW0,
            out,
        )
        assert out["cards"] and out["cards"][0]["queued"] is True, out
        assert any(event["kind"] == "card_queued" for event in store.journal.all())
    finally:
        clock.simulate(None)


# --------------------------------------------------------------------------------------
# tests: evidence / mentor contract
# --------------------------------------------------------------------------------------


def test_idempotent_say():
    proj = init_proj("idem")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    text = "连续两次没有新信息"
    first = run(["say", text, "--project", str(proj)], proj)
    before = kinds(proj)
    level_before = {skill["id"]: skill["level"] for skill in read_state(proj, "skills")["skills"]}
    card_before = {card["id"]: card for card in read_state(proj, "cards")["cards"]}
    second = run(["say", text, "--project", str(proj)], proj)
    after = kinds(proj)
    assert "重复执行" in second["out"]
    for kind in ("turn", "attempt", "card_reviewed", "level_change", "activity_completed"):
        assert after[kind] == before[kind], f"{kind}: {before[kind]} -> {after[kind]}"
    assert {skill["id"]: skill["level"] for skill in read_state(proj, "skills")["skills"]} == level_before
    assert {card["id"]: card["step"] for card in read_state(proj, "cards")["cards"]} == {
        card["id"]: card["step"] for card in card_before.values()
    }
    session_files = list((proj / "sessions").glob("*.md"))
    assert sum(path.read_text(encoding="utf-8").count("## 学习者") for path in session_files) == 1


def test_evidence_rules():
    proj = init_proj("evidence")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        # 1) assisted (help_level 2) never raises a level
        act = activity_dict("concept-assisted", "concept_block", "tool-contract", minutes=10)
        session = tempo.open_session(store, act, 10, "opening")
        payload = updates_for(act, help_level=2, correct=True, mastery=1)
        out = apply(store, session, act, "引导后复述", payload)
        assert out["evidence"]["assisted"] is True
        assert store.skill("tool-contract")["level"] == 0
        assert out["evidence"]["level"] == "observed"
        # 2) independent correct with help_level 0 raises exactly one level
        act2 = activity_dict("recall-independent", "recall_card", "agent-loop", minutes=5)
        session2 = tempo.open_session(store, act2, 10, "opening")
        out2 = apply(store, session2, act2, "想-做-看-停，以及三种停止条件", updates_for(act2, help_level=0, correct=True, mastery=1))
        assert store.skill("agent-loop")["level"] == 1, out2
        # 3) same skill same day cannot go +2
        act3 = activity_dict("recall-again", "recall_card", "agent-loop", minutes=5)
        session3 = tempo.open_session(store, act3, 10, "opening")
        apply(store, session3, act3, "另一种说法", updates_for(act3, help_level=0, correct=True, mastery=1))
        assert store.skill("agent-loop")["level"] == 1
        # 4) help_level 3 is assistance, not evidence
        act4 = activity_dict("kata-assisted", "code_kata", "tool-calling", minutes=15)
        session4 = tempo.open_session(store, act4, 20, "opening")
        out4 = apply(store, session4, act4, "示例已给全", updates_for(act4, help_level=3, correct=True, mastery=1))
        assert store.skill("tool-calling")["level"] == 0 and out4["evidence"]["assisted"] is True
        # 5) pure card practice caps at L2
        store.skill("tool-contract")["level"] = 2
        store.touch("skills")
        act5 = activity_dict("recall-cap", "recall_card", "tool-contract", minutes=5, level=2)
        session5 = tempo.open_session(store, act5, 10, "opening")
        out5 = apply(store, session5, act5, "零提示答对", updates_for(act5, help_level=0, correct=True, mastery=1))
        assert store.skill("tool-contract")["level"] == 2, out5
        assert any("上限" in note or "L3" in note for note in out5["notes"]), out5["notes"]
        store.save()
    finally:
        clock.simulate(None)


def test_l3_requires_artifact_and_delayed_retest():
    proj = init_proj("l3")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        block = tempo.ensure_block(store, NOW0)
        # Force a known kata step so the artifact path is deterministic in this test.
        block["steps"][0] = {
            "skill": "tool-contract",
            "activity_type": "code_kata",
            "minutes": 15,
            "done": False,
            "evidence_ref": "",
            "artifact": "",
        }
        store.touch("blocks")
        index, step = 0, block["steps"][0]
        skill_id = step["skill"]
        act = activity_dict(
            f"block-{block['week']}-step{index + 1}-{skill_id}",
            "code_kata",
            skill_id,
            minutes=15,
            block_id=block["id"],
            step_index=index,
        )
        session = tempo.open_session(store, act, 20, "opening")
        (proj / "artifacts").mkdir(exist_ok=True)
        (proj / "artifacts" / "demo.py").write_text("print('demo')\n", encoding="utf-8")
        payload = updates_for(act, help_level=0, correct=True, mastery=1, artifact="artifacts/demo.py")
        apply(store, session, act, "代码在 artifacts/demo.py", payload)
        skill = store.skill(skill_id)
        assert skill["block_artifact_at"] and skill["block_artifact_path"] == "artifacts/demo.py"
        assert skill["level"] <= 2
        assert any(event["kind"] == "block_artifact" for event in store.journal.all())

        # day 3: verified retest too early -> not L3
        clock.simulate(clock.add_days(NOW0, 3))
        quiz = activity_dict("quiz-day3", "quiz", skill_id, minutes=6)
        session2 = tempo.open_session(store, quiz, 10, "opening")
        apply(store, session2, quiz, "第 3 天全对", updates_for(quiz, help_level=0, correct=True, mastery=1))
        assert store.skill(skill_id)["level"] <= 2
        assert not any(event["kind"] == "l3_granted" for event in store.journal.all())

        # day 8: verified retest >= 7 days after the artifact -> L3
        clock.simulate(clock.add_days(NOW0, 8))
        quiz2 = activity_dict("quiz-day8", "quiz", skill_id, minutes=6)
        session3 = tempo.open_session(store, quiz2, 10, "opening")
        out = apply(store, session3, quiz2, "第 8 天全对", updates_for(quiz2, help_level=0, correct=True, mastery=1))
        assert store.skill(skill_id)["level"] == 3, out
        granted = [event for event in store.journal.all() if event["kind"] == "l3_granted"]
        assert granted and granted[-1]["payload"]["days"] >= 7

        # pure card practice can never reach L3, even with an artifact string
        store.skill("grounding")["level"] = 2
        store.touch("skills")
        card_act = activity_dict("recall-l3-try", "recall_card", "grounding", minutes=5, level=2)
        session4 = tempo.open_session(store, card_act, 10, "opening")
        apply(store, session4, card_act, "卡背都答对", updates_for(card_act, help_level=0, correct=True, mastery=1, artifact="artifacts/fake.py"))
        assert store.skill("grounding")["level"] == 2
        store.save()
    finally:
        clock.simulate(None)


def test_mentor_cannot_change_schedule():
    proj = init_proj("no-reschedule")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("recall-scheduled", "recall_card", "agent-loop", minutes=5)
        session = tempo.open_session(store, act, 20, "opening")
        items_before = len(store.schedule["today"]["items"])
        payload = {
            "help_level": 0,
            "attempt": {"activity_id": "topic-multi-agent", "correct": True},
            "misconception": None,
            "next": "直接学多 Agent",
            "mastery_delta": 3,
        }
        out = apply(store, session, act, "我答对了", payload)
        assert out["conflict"] is True
        assert store.skill("agent-loop")["level"] == 1, "mastery_delta=3 must clamp to +1"
        found = Counter(event["kind"] for event in store.journal.all())
        assert found["mentor_schedule_conflict"] >= 1
        assert found["mentor_update_clamped"] >= 1
        assert found["mentor_suggestion"] >= 1
        assert len(store.schedule["today"]["items"]) == items_before, "mentor must not add a scheduled activity"
        for event in store.journal.all():
            if event["kind"] == "mentor_schedule_conflict":
                assert event["payload"]["decision"] == "keep-schedule"
        store.save()
    finally:
        clock.simulate(None)


def test_examiner_hint_leak():
    proj = init_proj("hint-leak")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("quiz-hint", "quiz", "guardrails", minutes=6, mentor="examiner")
        session = tempo.open_session(store, act, 10, "opening")
        payload = updates_for(act, help_level=1, correct=True, mastery=1)
        out = apply(store, session, act, "我猜是输出过滤", payload)
        assert out["hint_leak"] is True
        assert out["evidence"]["level"] == "observed"
        assert store.skill("guardrails")["level"] == 0
        found = Counter(event["kind"] for event in store.journal.all())
        assert found["examiner_hint_leak"] == 1
        store.save()
    finally:
        clock.simulate(None)


def test_update_validation():
    proj = init_proj("validation")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("recall-validation", "recall_card", "agent-loop", minutes=5)
        # core invalid -> no evidence at all
        session = tempo.open_session(store, act, 10, "opening")
        bad = {"help_level": 9, "attempt": "nope"}
        out = apply(store, session, act, "非法块", bad)
        assert out["invalid"] is True
        assert not any(event["kind"] == "attempt" for event in store.journal.all())
        assert any(event["kind"] == "mentor_update_invalid" for event in store.journal.all())
        # missing block -> mentor_update_missing, no evidence
        act2 = activity_dict("recall-missing", "recall_card", "agent-loop", minutes=5)
        session2 = tempo.open_session(store, act2, 10, "opening")
        out2 = apply(store, session2, act2, "没有机器块", None, error="")
        assert out2["invalid"] is True
        assert any(event["kind"] == "mentor_update_missing" for event in store.journal.all())
        assert store.skill("agent-loop")["level"] == 0
        # extension invalid keeps the attempt but drops the card
        act3 = activity_dict("recall-ext", "recall_card", "agent-loop", minutes=5)
        session3 = tempo.open_session(store, act3, 10, "opening")
        payload = updates_for(act3, help_level=0, correct=True, mastery=1)
        payload["card"] = {"op": "create", "skill": "agent-loop", "kind": "recall", "front": "f", "back": "b", "tags": ["Bad Tag"]}
        out3 = apply(store, session3, act3, "答对但卡片非法", payload)
        assert store.skill("agent-loop")["level"] == 1
        assert out3["problems"]
        invalid_events = [event for event in store.journal.all() if event["kind"] == "mentor_update_invalid"]
        assert any(event["payload"].get("scope") == "extension" for event in invalid_events)
        assert not any(event["kind"] == "card_created" for event in store.journal.all())
        store.save()
    finally:
        clock.simulate(None)


# --------------------------------------------------------------------------------------
# tests: reliability / recovery / git
# --------------------------------------------------------------------------------------


def test_recovery_from_backup_and_torn_tail():
    proj = init_proj("recovery")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    run(["say", "循环的三种停止条件是：达成目标、轮次上限、连续两次没有新信息", "--project", str(proj)], proj)
    state_dir = proj / ".learnark" / "state"
    journal_path = proj / ".learnark" / "journal" / "events.jsonl"
    assert (state_dir / "skills.json.bak").exists()

    (state_dir / "skills.json").write_text("{ this is not json", encoding="utf-8")
    recovered = status_json(proj)
    assert recovered["recovery"], "status must report the backup repair"
    assert len(recovered["skills"]) == 10

    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write('{"torn":')
    still_ok = status_json(proj)
    assert still_ok["project"]["goal"]
    # a write after a torn tail must repair it instead of poisoning the journal
    run(["say", "连续两次没有新信息", "--project", str(proj)], proj)
    repaired = [event for event in journal(proj) if event["kind"] == "journal_repaired"]
    assert repaired, "torn journal tail must be repaired before the next append"
    assert any(event["kind"] == "turn" for event in journal(proj))

    (proj / ".learnark" / "journal" / "dedupe.json").write_text("{broken", encoding="utf-8")
    run(["say", "只有一刻钟", "--project", str(proj)], proj)
    rebuilt = read_json(proj / ".learnark" / "journal" / "dedupe.json")
    assert isinstance(rebuilt, dict) and rebuilt, "dedupe index must be rebuilt from the journal"

    (state_dir / "skills.json").unlink()
    (state_dir / "skills.json.bak").unlink()
    (state_dir / "skills.json").write_text("{ no backup either", encoding="utf-8")
    broken = run(["status", "--json", "--project", str(proj)], proj, expect=None)
    assert broken["code"] == 3, broken


def test_stale_write_is_rejected():
    proj = init_proj("cas")
    path = proj / ".learnark" / "state" / "skills.json"
    document = tempo.Document(path, tempo._skills_default)
    snapshot = document.load()
    snapshot_version = int(snapshot.get("version", 0))
    updated = document.load()
    updated["skills"][0]["level"] = 1
    document.save(updated)
    stale = document.load()
    stale["skills"][0]["level"] = 2
    try:
        document.save(stale, expected_version=snapshot_version)
        raise AssertionError("stale write was accepted")
    except StaleWrite:
        pass


def test_switch_and_handoff():
    proj = init_proj("switch")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    switched = run(["switch", "examiner", "--project", str(proj)], proj)
    assert "已切换导师" in switched["out"]
    handoff = (proj / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    assert "→ examiner" in handoff
    for field in ("上次停在哪", "试过什么", "哪里不稳", "下一步", "未决问题"):
        assert field in handoff
    found = kinds(proj)
    assert found["mentor_switch"] >= 1 and found["handoff"] >= 1
    unknown = run(["switch", "nobody", "--project", str(proj)], proj, expect=2)
    assert "coach" in unknown["err"] and "examiner" in unknown["err"]
    pause = run(["pause", "--project", str(proj)], proj)
    assert "下次开始" in pause["out"]
    state = status_json(proj)
    assert state["mentor"] in ("examiner", "trainer", "coach")


def test_git_remote_push_and_clone():
    work = fresh("git")
    bare = work / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    proj = init_proj("git-proj")
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=str(proj), check=True)
    sync = run(["sync", "--project", str(proj)], proj)
    assert "pushed=yes" in sync["out"], sync["out"]
    clone = work / "clone"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
    restored = status_json(clone)
    assert restored["project"]["goal"]
    assert restored["variant"] == "direction-d-tempo"
    run(["start", "--minutes", "10", "--project", str(clone)], clone)
    doctor = run(["doctor", "--project", str(clone)], clone)
    assert "0 项问题" in doctor["out"]
    # no remote branch: pushed must be reported honestly, never guessed
    status = status_json(proj)
    assert status["sync"]["pushed"] is True


def test_two_syncs_commit_modified_tracked_file():
    """Regression for core 1.0.1: the second sync of a *modified tracked* file must commit it."""
    work = fresh("git-two-sync")
    bare = work / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    proj = init_proj("git-two-sync-proj")
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=str(proj), check=True)
    first = run(["sync", "--project", str(proj)], proj)
    assert "pushed=yes" in first["out"], first["out"]
    marker = "-- two-sync regression marker"
    agents = proj / "AGENTS.md"
    with agents.open("a", encoding="utf-8") as handle:
        handle.write("\n" + marker + "\n")
    second = run(["sync", "--project", str(proj)], proj)
    assert "pushed=yes" in second["out"], second["out"]
    shown = subprocess.run(
        ["git", "-C", str(proj), "show", "HEAD:AGENTS.md"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert shown.returncode == 0 and marker in shown.stdout, shown.stderr
    state = status_json(proj)
    assert state["sync"]["clean"] is True and state["sync"]["pushed"] is True
    remote_show = subprocess.run(
        ["git", "-C", str(bare), "show", "HEAD:AGENTS.md"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert marker in remote_show.stdout, "modified tracked file must reach the remote"


def test_review_forces_due_and_exempts_repeat():
    proj = init_proj("review")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    run(["say", "连续两次没有新信息", "--project", str(proj)], proj)
    first = run(["review", "--project", str(proj)], proj)
    assert "强制到期复习" in first["out"]
    items = read_state(proj, "schedule")["today"]["items"]
    reviewed = items[-1]
    assert reviewed["activity_type"] == "recall_card", reviewed
    assert reviewed["activity_id"].startswith("recall-"), reviewed
    assert reviewed["skill"], reviewed
    # the reviewed card leaves the queue; the next explicit review must pick another due card
    cards_path = proj / ".learnark" / "state" / "cards.json"
    cards_data = read_json(cards_path)
    for card in cards_data["cards"]:
        if card["id"] == reviewed["activity_id"].replace("recall-", ""):
            card["due_at"] = clock.add_days(NOW0, 2)
        if card["id"] == "card-0002":
            card["due_at"] = NOW0
    write_json(cards_path, cards_data)
    # explicit review is exempt from the same-day repeat filters
    before_count = len(read_state(proj, "schedule")["today"]["items"])
    run(["review", "--project", str(proj)], proj)
    after_items = read_state(proj, "schedule")["today"]["items"]
    assert len(after_items) > before_count, after_items
    second = after_items[-1]
    assert second["activity_id"].startswith("recall-"), second
    assert second["activity_id"] != reviewed["activity_id"], second
    # no due cards -> explicit "no due" message, no new activity
    clock.simulate(NOW0)
    try:
        cards_path = proj / ".learnark" / "state" / "cards.json"
        data = read_json(cards_path)
        for card in data["cards"]:
            card["due_at"] = clock.add_days(NOW0, 5)
        write_json(cards_path, data)
        before = len(read_state(proj, "schedule")["today"]["items"])
        empty = run(["review", "--project", str(proj)], proj)
        assert "今天没有到期项" in empty["out"]
        assert len(read_state(proj, "schedule")["today"]["items"]) == before
    finally:
        clock.simulate(None)


def test_clean_copy_recovery():
    proj = init_proj("copy")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    run(["say", "循环的三种停止条件是：达成目标、轮次上限、连续两次没有新信息", "--project", str(proj)], proj)
    run(["pause", "--project", str(proj)], proj)
    clone = BASE / "copy-clone"
    shutil.rmtree(clone, ignore_errors=True)
    shutil.copytree(proj, clone)
    state = status_json(clone)
    assert any(skill["level"] == 1 for skill in state["skills"])
    assert state["next"]["activity_type"]
    started = run(["start", "--minutes", "10", "--project", str(clone)], clone)
    assert "上次停在哪" in started["out"]
    assert "离线" in started["out"]


def test_doctor_reports_problems():
    proj = init_proj("doctor")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    run(["say", "循环的三种停止条件是：达成目标、轮次上限、连续两次没有新信息", "--project", str(proj)], proj)
    run(["pause", "--project", str(proj)], proj)
    clean = run(["doctor", "--project", str(proj)], proj)
    assert "0 项问题" in clean["out"]
    (proj / ".learnark" / "journal" / "dedupe.json").write_text("{broken", encoding="utf-8")
    dirty = run(["doctor", "--project", str(proj)], proj, expect=3)
    assert "dedupe_index" in dirty["out"] and "FAIL" in dirty["out"]


# --------------------------------------------------------------------------------------
# tests: round-02 learner feedback regressions (v0.2.2)
# --------------------------------------------------------------------------------------


def test_echo_is_not_independent_correct():
    proj = init_proj("echo")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        example = "先固定 10 条问题，答对 7/10，记下基线；改完提示词再跑同一组，答对 8/10，才算更好。"
        act = activity_dict("concept-echo", "concept_block", "eval-harness", minutes=10)
        session = tempo.open_session(store, act, 20, "opening")
        learner = "先固定 10 条问题，答对 7/10，记下基线；改完提示词再跑同一组，答对 8/10，才算更好。"
        payload = updates_for(act, help_level=1, correct=True, mastery=1)
        out = apply(
            store,
            session,
            act,
            learner,
            payload,
            visible="复述准确，本次到此收尾。",
            previous_mentor=example,
        )
        assert out["echoed"] is True, out
        assert out["help_level"] >= 2, out
        skill = store.skill("eval-harness")
        assert skill["level"] == 0, skill
        assert not any(event["kind"] == "level_change" for event in store.journal.all())
        assert skill["last_help_level"] >= 2 and skill["last_evidence_kind"] == "echo"
        assert any(event["kind"] == "echoed_example" for event in store.journal.all())
        status = tempo.status_payload(store)
        assert status["last_turn"]["echoed"] is True and status["last_turn"]["assisted"] is True
        eval_skill = next(item for item in status["skills"] if item["id"] == "eval-harness")
        assert eval_skill["last_help_level"] >= 2
        # a genuinely independent answer on another skill still upgrades
        act2 = activity_dict("concept-independent", "concept_block", "grounding", minutes=10)
        session2 = tempo.open_session(store, act2, 20, "opening")
        independent = "我会准备同一套输入，先记录改之前的通过率，改完再跑一遍比较；只看感觉不算数。"
        out2 = apply(
            store,
            session2,
            act2,
            independent,
            updates_for(act2, help_level=0, correct=True, mastery=1),
            visible="对，复述准确。",
            previous_mentor=example,
        )
        assert out2["echoed"] is False, out2
        assert store.skill("grounding")["level"] == 1
        store.save()
    finally:
        clock.simulate(None)


def test_pure_question_turn_is_not_an_attempt():
    proj = init_proj("question-turn")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("recall-question", "recall_card", "agent-loop", minutes=5)
        session = tempo.open_session(store, act, 10, "opening")
        payload = updates_for(
            act,
            help_level=0,
            correct=True,
            mastery=1,
            card={"op": "create", "skill": "agent-loop", "kind": "recall", "front": "新问题？", "back": "答案", "tags": ["test"]},
        )
        out = apply(
            store,
            session,
            act,
            "那我下次到底先做什么？直接给我下一步的代码吧。",
            payload,
            visible="下一步建议……",
        )
        assert out["correct"] is None, out
        assert out["attempt_kind"] == "question"
        attempts = [event for event in store.journal.all() if event["kind"] == "attempt"]
        assert attempts[-1]["payload"]["correct"] is None
        assert any(event["kind"] == "turn_without_attempt" for event in store.journal.all())
        assert store.skill("agent-loop")["level"] == 0
        assert not any(event["kind"] == "card_created" for event in store.journal.all())
        assert store.schedule["last_turn"]["attempt_kind"] == "question"
        store.save()
    finally:
        clock.simulate(None)


def test_text_conflict_uses_block_and_is_logged():
    proj = init_proj("text-conflict")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("recall-conflict", "recall_card", "tool-calling", minutes=5)
        session = tempo.open_session(store, act, 10, "opening")
        payload = updates_for(
            act,
            help_level=1,
            correct=False,
            mastery=0,
            card={"op": "create", "skill": "tool-calling", "kind": "recall", "front": "冲突卡？", "back": "x", "tags": ["test"]},
        )
        out = apply(
            store,
            session,
            act,
            "工具报错后应该先看参数再重试",
            payload,
            visible="对。工具报错要作为观察结果回灌。",
        )
        assert out["text_conflict"] is True, out
        assert out["result"] == "conflict" and out["correct"] is None, out
        events = [event for event in store.journal.all() if event["kind"] == "mentor_text_conflict"]
        assert events and events[-1]["payload"]["decision"] == "no-evidence"
        assert store.skill("tool-calling")["level"] == 0
        assert not any(event["kind"] in ("level_change", "card_created") for event in store.journal.all())
        assert out["evidence"]["level"] == "none"
        assert any("不记对错" in note for note in out["notes"])
        store.save()
    finally:
        clock.simulate(None)


def test_partial_answer_is_not_question_and_gets_no_credit():
    proj = init_proj("partial")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("recall-partial", "recall_card", "agent-loop", minutes=5)
        session = tempo.open_session(store, act, 10, "opening")
        learner = (
            "四个阶段大概是：模型看当前对话和上一步结果，决定要不要调用工具，执行工具拿到返回，"
            "再把返回塞回对话让模型继续。停止条件我只记得两个：模型不再调用工具、直接给最终答案就停；"
            "还有达到最大轮数或工具一直报错也会停。"
        )
        assert tempo.looks_like_question(learner) is False
        payload = updates_for(
            act,
            help_level=0,
            correct=False,
            mastery=0,
            card={"op": "create", "skill": "agent-loop", "kind": "recall", "front": "部分卡？", "back": "x", "tags": ["test"]},
        )
        out = apply(
            store,
            session,
            act,
            learner,
            payload,
            visible="对：四个阶段你说全了（看上下文→决定调用→执行工具→回填结果）；停止条件漏了“连续没有新信息”这一条。",
        )
        assert out["attempt_kind"] == "answer", out
        assert out["result"] == "partial" and out["correct"] is None, out
        assert out["text_conflict"] is False, out
        assert any(event["kind"] == "turn_partial" for event in store.journal.all())
        attempts = [event for event in store.journal.all() if event["kind"] == "attempt"]
        assert attempts[-1]["payload"]["result"] == "partial" and attempts[-1]["payload"]["correct"] is None
        assert not any(event["kind"] in ("level_change", "card_created") for event in store.journal.all())
        assert store.skill("agent-loop")["level"] == 0
        assert store.schedule["last_turn"]["result"] == "partial"
        store.save()
    finally:
        clock.simulate(None)


def test_explicit_switch_is_sticky_for_next_start():
    proj = init_proj("switch-sticky")
    switched = run(["switch", "examiner", "--project", str(proj)], proj)
    assert "examiner" in switched["out"], switched["out"]
    state = status_json(proj)
    assert state["mentor_override"] == "examiner", state
    started = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    assert "switch 指定 examiner" in started["out"], started["out"]
    session = read_state(proj, "schedule")["current_session"]
    assert session["mentor"] == "examiner", session
    assert session["activity"]["activity_type"] in ("quiz", "recall_card"), session["activity"]
    assert status_json(proj)["mentor_override"] is None
    run(["pause", "--project", str(proj)], proj)
    run(["switch", "coach", "--project", str(proj)], proj)
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    session2 = read_state(proj, "schedule")["current_session"]
    assert session2["mentor"] == "coach", session2
    switches = [event for event in journal(proj) if event["kind"] == "mentor_switch"]
    assert [event["payload"]["to"] for event in switches][-2:] == ["examiner", "coach"]
    assert any(event["kind"] == "mentor_override_used" for event in journal(proj))


def test_handoff_captures_open_question_and_concrete_next():
    proj = init_proj("handoff-q")
    run(["start", "--minutes", "10", "--project", str(proj)], proj)
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        session = store.schedule["current_session"]
        tempo.append_session_turn(
            store,
            session,
            "我先答一部分",
            "对。那你觉得第二种停止条件是什么？",
            ["test: open question"],
        )
        store.save()
        summary = tempo.handoff_summary(store)
        assert any("导师追问" in question for question in summary["open_questions"]), summary["open_questions"]
        assert "重新调度" not in summary["next_step"], summary["next_step"]
        handoff = tempo.write_handoff(store, reason="open-question")
        assert "导师追问" in handoff["text"], handoff["text"]
        assert "下一步：" in handoff["text"]
    finally:
        clock.simulate(None)


def test_status_next_matches_start_and_five_minute_wording():
    proj = init_proj("next-consistency")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    run(["pause", "--project", str(proj)], proj)
    state = status_json(proj)
    nxt = state["next"]
    assert nxt["when"] == "now", nxt
    assert int(nxt["minutes"]) <= state["today"]["remaining_minutes"], (nxt, state["today"])
    started = run(["start", "--project", str(proj)], proj)
    session = read_state(proj, "schedule")["current_session"]
    assert session["activity"]["activity_id"] == nxt["activity_id"], (session["activity"], nxt)

    narrow = init_proj("five-minute-wording")
    run(["start", "--minutes", "10", "--project", str(narrow)], narrow)
    run(["pause", "--project", str(narrow)], narrow)
    five = status_json(narrow)
    assert five["today"]["remaining_minutes"] == 5
    human = run(["status", "--project", str(narrow)], narrow)
    assert "不足下一项" not in human["out"], human["out"]
    assert "模板/技能" in human["out"], human["out"]
    closed = run(["start", "--project", str(narrow)], narrow)
    assert "没有合适的新活动" in closed["out"], closed["out"]
    assert read_state(narrow, "schedule")["current_session"] is None


def test_unfinished_card_not_folded_and_first_next():
    proj = init_proj("fold-resume")
    clock.simulate(NOW0)
    try:
        cards_path = proj / ".learnark" / "state" / "cards.json"
        data = read_json(cards_path)
        for card in data["cards"]:
            card["due_at"] = NOW0
        extra = dict(data["cards"][0])
        extra.update({"id": "card-9998", "front": "折叠测试额外卡", "source_event": "test:seed"})
        data["cards"].append(extra)
        write_json(cards_path, data)
        run(["start", "--minutes", "20", "--project", str(proj)], proj)
        run(["pause", "--project", str(proj)], proj)
        resume = read_state(proj, "schedule").get("resume_activity") or {}
        resume_aid = resume.get("activity_id")
        assert resume_aid and resume_aid.startswith("recall-"), resume
        card_id = resume_aid.replace("recall-", "")
        day2 = clock.add_days(NOW0, 1)
        clock.simulate(day2)
        store = load_store(proj, day2)
        tempo.prepare_day(store, day2)
        card = store.card(card_id)
        assert card is not None and tempo.is_due(card["due_at"], day2), card
        due_ids = [item["id"] for item in store.due_cards()]
        assert card_id in due_ids, due_ids
        summary = tempo.handoff_summary(store)
        assert resume_aid in summary["next_step"], summary["next_step"]
        status = tempo.status_payload(store)
        assert status["next"]["activity_id"] == resume_aid, status["next"]
        store.save()
    finally:
        clock.simulate(None)


def test_remaining_minutes_one_source():
    proj = init_proj("remaining-source")
    started = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    assert "本次可用 20 分钟" in started["out"], started["out"]
    assert "本次放不下（剩余" not in started["out"], started["out"]
    state = status_json(proj)
    remaining = state["today"]["remaining_minutes"]
    nxt = state["next"]
    if nxt["when"] == "now":
        assert int(nxt["minutes"]) <= remaining, (nxt, remaining)
        assert "剩余" not in (nxt["reason"] or "") or f"可用 {remaining}" in (nxt["reason"] or ""), nxt["reason"]
    else:
        assert nxt["reason"].startswith("下次："), nxt["reason"]
    # cap branch: no "0 minutes but 20-minute activity can finish" contradiction
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    capped = status_json(proj)
    if capped["today"]["remaining_minutes"] == 0:
        assert capped["next"]["when"] == "next_session", capped["next"]
        assert capped["next"]["reason"].startswith("下次："), capped["next"]


def test_duplicate_card_fronts_merge():
    proj = init_proj("card-merge")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        out = {"cards": [], "notes": []}
        item = {
            "op": "create",
            "skill": "agent-loop",
            "kind": "recall",
            "front": "循环的停止条件是什么？",
            "back": "目标/轮次/无新信息",
            "tags": ["loop"],
        }
        tempo._apply_card_create(store, item, {}, "attempt:a", NOW0, out)
        item2 = dict(item)
        item2["front"] = "循环的停止条件是什么"
        item2["back"] = "目标、轮次上限、连续无新信息"
        item2["tags"] = ["stop"]
        tempo._apply_card_create(store, item2, {}, "attempt:b", NOW0, out)
        wanted = tempo.normalize_text("循环的停止条件是什么？")
        matches = [
            card
            for card in store.cards["cards"]
            if card["skill"] == "agent-loop" and tempo.normalize_text(card["front"]) == wanted
        ]
        assert len(matches) == 1, matches
        assert out["cards"][-1].get("merged") is True
        assert any(event["kind"] == "card_merged" for event in store.journal.all())
        skill = store.skill("agent-loop")
        out2 = {"cards": [], "notes": []}
        tempo._auto_misconception_card(store, skill, "把组件当循环", {}, "attempt:c", NOW0, out2)
        tempo._auto_misconception_card(store, skill, "漏了轮次上限", {}, "attempt:d", NOW0, out2)
        generic = [card for card in store.cards["cards"] if card["skill"] == "agent-loop" and card["front"].startswith("你上次把「")]
        assert len(generic) == 1, generic
        store.save()
    finally:
        clock.simulate(None)


def test_time_boxed_incomplete_and_replacement_noted():
    proj = init_proj("timebox")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("recall-timebox", "recall_card", "agent-loop", minutes=5)
        session = tempo.open_session(store, act, 10, "opening")
        payload = updates_for(act, help_level=0, correct=False, mastery=0)
        # premature mentor time-box: 0.2/5 minutes -> ignored, activity stays open
        out = apply(store, session, act, "我只答出一条", payload, visible="时间到，收尾。两问均未答全。")
        assert out["time_boxed"] is False, out
        assert any(event["kind"] == "time_box_ignored" for event in store.journal.all())
        assert not any(event["kind"] == "time_boxed_incomplete" for event in store.journal.all())
        # real elapsed >=60% -> time-boxed incomplete is recorded
        session["started_at"] = clock.add_days(NOW0, -4 / 1440)
        store.touch("schedule")
        out2 = apply(store, session, act, "我只答出两个", payload, visible="时间到，收尾。两问均未答全。")
        assert out2["time_boxed"] is True, out2
        events = [event for event in store.journal.all() if event["kind"] == "time_boxed_incomplete"]
        assert events and events[-1]["payload"]["planned_min"] == 5
        assert events[-1]["payload"]["elapsed_min"] >= 3
        assert not any(item["done"] for item in store.schedule["today"]["items"])
        assert any("时间到但活动未完成" in note for note in out2["notes"])
        store.save()
    finally:
        clock.simulate(None)
    second = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    assert "[未完成]" in second["out"], second["out"]
    assert any(event["kind"] == "activity_replaced" for event in journal(proj))
    run(["pause", "--project", str(proj)], proj)
    handoff = (proj / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    assert "未完成：" in handoff


# --------------------------------------------------------------------------------------
# tests: template portability, exit codes
# --------------------------------------------------------------------------------------


def _append_event(path: Path, event_id: str, kind: str = "test_marker") -> None:
    record = {
        "id": event_id,
        "seq": 9999,
        "at": "2026-11-04T20:00:00+08:00",
        "kind": kind,
        "actor": "test",
        "simulated": True,
        "dedupe_key": f"test:{event_id}",
        "payload": {"marker": event_id},
    }
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_email_core_writing_block_is_not_starved():
    proj = init_proj("email-core", template="email")
    started = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    session = read_state(proj, "schedule")["current_session"]
    assert session["activity"]["activity_type"] == "writing_block", session["activity"]
    assert session["activity"]["minutes"] == 12, session["activity"]
    assert "核心可交付块优先" in started["out"], started["out"]

    narrow = init_proj("email-core-narrow", template="email")
    run(["start", "--minutes", "10", "--project", str(narrow)], narrow)
    deferred = [event for event in journal(narrow) if event["kind"] == "core_block_deferred"]
    assert deferred, "a 12-min core block cannot fit a 10-min budget; defer it"
    assert deferred[-1]["payload"]["minutes"] == 12
    state = status_json(narrow)
    assert state["next"]["activity_type"] == "writing_block", state["next"]
    assert state["next"]["minutes"] == 12


def test_correct_answer_with_partial_word_in_prose_stays_correct():
    proj = init_proj("partial-word", template="email")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("concept-boundary", "concept_block", "structure-clarity", minutes=8)
        session = tempo.open_session(store, act, 10, "opening")
        out = apply(
            store,
            session,
            act,
            "一个主请求；背景只留必要；期限只出现一次；不相干请求另发。边界是合并请求要有同一收件人与同一目的。",
            updates_for(act, help_level=0, correct=True, mastery=1),
            visible="对，边界复述准确。本轮概念部分就到这里。",
        )
        assert out["result"] == "correct", out
        assert out["correct"] is True
        assert not any(event["kind"] == "turn_partial" for event in store.journal.all())
        assert any(event["kind"] == "level_change" for event in store.journal.all())
        store.save()
    finally:
        clock.simulate(None)


def test_say_answer_with_minutes_does_not_change_budget():
    proj = init_proj("say-budget")
    started = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    before = read_state(proj, "schedule")["today"]
    said = run(["say", "我还有七分钟，想现在练一下", "--offline", "--project", str(proj)], proj)
    after = read_state(proj, "schedule")["today"]
    assert before["minutes_budget"] == after["minutes_budget"] == 20, (before, after)
    assert "不改今日预算" in said["out"], said["out"]
    events = [event for event in journal(proj) if event["kind"] == "budget_ignored_in_answer"]
    assert events and events[-1]["payload"]["matched"] == "七分钟", events
    assert not any(
        event["kind"] == "budget_set" and event["payload"].get("source") == "say" for event in journal(proj)
    )


def test_writing_draft_in_concept_session_routes_to_writing_skill():
    proj = init_proj("writing-review", template="email")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        act = activity_dict("concept-write", "concept_block", "structure-clarity", minutes=8)
        session = tempo.open_session(store, act, 10, "opening")
        draft = "Hi Mark,\n\nI am writing to update you on the Atlas project. Delivery will be two days later, on November 12.\n\nThanks,\nTina"
        out = apply(
            store,
            session,
            act,
            draft,
            updates_for(act, help_level=0, correct=True, mastery=1),
            visible="改得对：寒暄删了，请求有明确期限。",
        )
        assert out["off_activity"] is True, out
        assert out["routed_skill"] == "language-accuracy", out
        attempts = [event for event in store.journal.all() if event["kind"] == "attempt"]
        assert attempts[-1]["payload"]["skill"] == "language-accuracy", attempts[-1]
        assert attempts[-1]["payload"]["activity_type"] == "writing_review"
        assert store.skill("structure-clarity")["level"] == 0
        assert store.skill("structure-clarity")["evidence_level"] == "self_report"
        assert not any(event["kind"] == "level_change" for event in store.journal.all())
        assert out["completed"] is False
        store.save()
    finally:
        clock.simulate(None)


def test_email_block_step2_is_a_writing_type():
    proj = init_proj("email-type", template="email")
    blocks = read_state(proj, "blocks")["blocks"]
    email_steps = [step for block in blocks for step in block.get("steps", []) if step.get("activity_type") == "writing_block"]
    assert email_steps, blocks
    assert not any(
        step.get("activity_type") == "code_kata" for block in blocks for step in block.get("steps", [])
    ), "email template must not use code_kata"


def test_sync_recover_unions_journals_and_snapshot_conflict_exits_3():
    work = fresh("sync-recover")
    bare = work / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
    proj = init_proj("sync-recover-proj")
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=str(proj), check=True)
    initial = run(["sync", "--project", str(proj)], proj)
    assert "pushed=yes" in initial["out"], initial["out"]
    clone_a, clone_b = work / "clone-a", work / "clone-b"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone_a)], check=True)
    subprocess.run(["git", "clone", "-q", str(bare), str(clone_b)], check=True)
    _append_event(clone_a / ".learnark" / "journal" / "events.jsonl", "ev_test_a")
    _append_event(clone_b / ".learnark" / "journal" / "events.jsonl", "ev_test_b")
    a = run(["sync", "--project", str(clone_a)], clone_a)
    assert "pushed=yes" in a["out"], a["out"]
    b = run(["sync", "--recover", "--project", str(clone_b)], clone_b)
    assert "pushed=yes" in b["out"], b["out"]
    assert "union" in b["out"] or "recover" in b["out"].lower(), b["out"]
    ids = {
        json.loads(line)["id"]
        for line in (clone_b / ".learnark" / "journal" / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert {"ev_test_a", "ev_test_b"} <= ids, sorted(ids)
    branch = subprocess.run(
        ["git", "-C", str(bare), "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    remote_events = subprocess.run(
        ["git", "-C", str(bare), "show", f"{branch}:.learnark/journal/events.jsonl"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    assert "ev_test_a" in remote_events and "ev_test_b" in remote_events

    # snapshot conflict: journals are fine, but state/skills.json conflicts
    clone_c, clone_d = work / "clone-c", work / "clone-d"
    subprocess.run(["git", "clone", "-q", str(bare), str(clone_c)], check=True)
    subprocess.run(["git", "clone", "-q", str(bare), str(clone_d)], check=True)
    for clone, level in ((clone_c, 1), (clone_d, 2)):
        path = clone / ".learnark" / "state" / "skills.json"
        data = read_json(path)
        data["skills"][0]["level"] = level
        data["version"] = int(data.get("version", 0)) + 1
        write_json(path, data)
    pushed = run(["sync", "--project", str(clone_c)], clone_c)
    assert "pushed=yes" in pushed["out"], pushed["out"]
    conflict = run(["sync", "--project", str(clone_d)], clone_d, expect=3)
    assert "conflict" in conflict["out"].lower(), conflict["out"]
    assert "skills.json" in conflict["out"], conflict["out"]
    assert "sync --recover" in conflict["out"], conflict["out"]
    state = status_json(clone_d)
    assert state["sync"]["diverged"] is True, state["sync"]
    assert state["sync"]["state"] == "conflict", state["sync"]
    assert "unmerged" in state["sync"]
    doctor = run(["doctor", "--project", str(clone_d)], clone_d, expect=3)
    assert "git_divergence" in doctor["out"], doctor["out"]


def test_email_template_no_programming_residue():
    proj = init_proj("email", template="email", minutes_per_week=180)
    skills = read_state(proj, "skills")["skills"]
    ids = {skill["id"] for skill in skills}
    assert ids == {"subject-line", "opening-purpose", "ask-clarity", "structure-clarity", "tone-register", "language-accuracy"}
    assert "agent-loop" not in ids
    assert not any("Agent" in (skill.get("title") or "") for skill in skills)
    started = run(["start", "--minutes", "15", "--project", str(proj)], proj)
    assert "[离线脚本导师]" in started["out"]
    assert any(word in started["out"] for word in ("写作", "句式", "要点", "回述", "小测", "整封邮件"))
    assert status_json(proj)["project"]["template_id"] == "email"
    run(["say", "只有一刻钟", "--project", str(proj)], proj)
    run(["pause", "--project", str(proj)], proj)
    export = proj / "artifacts" / "export.md"
    run(["export", "--out", str(export), "--project", str(proj)], proj)
    text = export.read_text(encoding="utf-8")
    assert "主题行" in text and "agent-loop" not in text


def test_exit_codes():
    work = fresh("exit-codes")
    run(["start", "--minutes", "abc"], work, expect=2)
    run(["init", "--goal", "x", "--dir", str(work / "p1"), "--template", "nope"], work, expect=2)
    run(["init", "--dir", str(work / "p2")], work, expect=2)
    run(["status"], work, expect=3)
    run(["export"], work, expect=2)
    run(["say"], work, expect=2)
    proj = init_proj("exit-project")
    run(["start", "--minutes", "0", "--project", str(proj)], proj, expect=2)


# --------------------------------------------------------------------------------------
# tests: round-01 learner feedback regressions (v0.2.1)
# --------------------------------------------------------------------------------------


def test_budget_same_day_carry_and_remaining():
    proj = init_proj("budget-carry")
    first = run(["start", "今天只有半小时", "--project", str(proj)], proj)
    assert "本次 30 分钟" in first["out"] and "剩余 30" in first["out"]
    run(["say", "连续两次没有新信息", "--project", str(proj)], proj)
    second = run(["start", "--project", str(proj)], proj)
    assert "沿用今天已定 30 分钟" in second["out"], second["out"]
    assert "已用 5" in second["out"] and "剩余 25" in second["out"], second["out"]
    state = read_state(proj, "schedule")["today"]
    assert state["minutes_budget"] == 30, state
    assert state["minutes_used"] == 15, state  # the newly scheduled 10-minute activity counts as used
    assert state["minutes_left"] == 15, state
    status = status_json(proj)
    assert status["today"]["minutes_budget"] == 30
    assert status["today"]["minutes_used"] == 15
    assert status["today"]["remaining_minutes"] == 15
    assert status["today"]["cap_reached"] is True
    assert status["next"]["when"] == "next_session"
    assert status["next"]["activity_id"] and status["next"]["activity_id"] != "next-due", status["next"]
    assert status["next"]["skill"], status["next"]
    assert status["next"]["activity_id"].split("-")[0] in ("recall", "block", "weak", "retest"), status["next"]["activity_id"]
    human = run(["status", "--project", str(proj)], proj)
    assert "剩余 15 分钟" in human["out"]
    assert "下一步（下次）" in human["out"]
    assert "· -" not in human["out"], human["out"]
    assert "今天已排满" in human["out"] or "预算" in human["out"]
    planned = run(["plan", "--json", "--project", str(proj)], proj)
    decision = json.loads(planned["out"])
    assert decision["for"] == "next_session" and decision["items"], decision
    assert all(item["skill"] for item in decision["items"]), decision


def test_missing_block_repaired_silently():
    proj = init_proj("repair")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    say = run(
        ["say", "无块测试", "--project", str(proj)],
        proj,
        env_extra={"LEARNARK_MOCK_SCRIPT": str(REPAIR_SCRIPT)},
    )
    assert "提示级别 0（独立完成）" in say["out"], say["out"]
    for internal in ("机器块", "重试", "mentor_update", "无证据", "补一次", "learn-update"):
        assert internal not in say["out"], (internal, say["out"])
    events = journal(proj)
    retried = [event for event in events if event["kind"] == "mentor_update_retried"]
    assert len(retried) == 1 and retried[0]["payload"]["ok"] is True
    assert sum(1 for event in events if event["kind"] == "attempt") == 1
    assert not any(event["kind"] == "mentor_update_missing" for event in events)


def test_artifact_required_blocks_completion_and_acknowledges_later():
    proj = init_proj("artifact")
    clock.simulate(NOW0)
    try:
        store = load_store(proj, NOW0)
        block = tempo.ensure_block(store, NOW0)
        block["steps"][0] = {
            "skill": "eval-harness",
            "activity_type": "code_kata",
            "minutes": 15,
            "done": False,
            "evidence_ref": "",
            "artifact": "",
            "required_artifact": "artifacts/eval-cases.json",
        }
        store.touch("blocks")
        act = activity_dict(
            "block-artifact-step",
            "code_kata",
            "eval-harness",
            minutes=15,
            block_id=block["id"],
            step_index=0,
        )
        act["requires_artifact"] = "artifacts/eval-cases.json"
        act["artifact_path"] = "artifacts/eval-cases.json"
        session = tempo.open_session(store, act, 20, "opening")
        payload = updates_for(act, help_level=0, correct=True, mastery=1)
        out = tempo.apply_turn(store, session, act, "我先把思路讲清楚", json.dumps(payload), payload, "", 0, "api")
        assert out["completed"] is False
        assert out["artifact_required"] == "artifacts/eval-cases.json"
        found = Counter(event["kind"] for event in store.journal.all())
        assert found["artifact_required"] == 1 and found["activity_completed"] == 0
        assert store.schedule["current_session"]["artifact_pending"] == "artifacts/eval-cases.json"
        store.save()
        # the learner writes the file afterwards; pause must acknowledge it
        (proj / "artifacts" / "eval-cases.json").write_text("{\"cases\": 10}\n", encoding="utf-8")
        pause = run(["pause", "--project", str(proj)], proj)
        assert "已确认产物" in pause["out"], pause["out"]
        events = journal(proj)
        found = Counter(event["kind"] for event in events)
        assert found["artifact_acknowledged"] >= 1
        assert found["activity_completed"] == 1
        handoff = (proj / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
        assert "artifacts/eval-cases.json" in handoff
    finally:
        clock.simulate(None)


def test_init_does_not_invent_self_report():
    proj = init_proj("self-report")
    meta = read_json(proj / ".learnark" / "project.json")
    learner = meta["learner"]
    assert learner["self_report"] == [], learner
    blob = json.dumps(learner, ensure_ascii=False)
    assert "RAG" not in blob and "API" not in blob, blob
    assert "尚未记录" in learner["note"]
    second = run(
        ["init", "--dir", str(proj), "--self-report", "我学过一点 Python，没写过 Agent"],
        proj,
    )
    assert second["code"] == 0
    learner = read_json(proj / ".learnark" / "project.json")["learner"]
    assert learner["self_report"] == ["我学过一点 Python，没写过 Agent"]
    assert "我学过一点 Python" in learner["note"]


def test_gitignore_covers_usage_and_doctor_reports_true_state():
    proj = init_proj("git-ignore")
    gitignore = (proj / ".gitignore").read_text(encoding="utf-8")
    assert "usage.jsonl" in gitignore and "sync-log.jsonl" in gitignore
    assert "*.lock" in gitignore
    attributes = (proj / ".gitattributes").read_text(encoding="utf-8")
    assert "* -text" in attributes
    (proj / ".learnark" / "usage.jsonl").write_text("{\"model\": \"mock\"}\n", encoding="utf-8")
    clean = run(["doctor", "--project", str(proj)], proj)
    assert "0 项问题" in clean["out"], clean["out"]
    # a stray unignored file must be reported, not called clean
    (proj / "notes.txt").write_text("x\n", encoding="utf-8")
    dirty = run(["doctor", "--project", str(proj)], proj)
    assert "个改动未提交" in dirty["out"], dirty["out"]
    assert "git_policy" in dirty["out"], dirty["out"]
    assert status_json(proj)["sync"]["clean"] is False


def test_model_label_records_actual_model():
    proj = init_proj("model-label")
    run(["start", "--minutes", "20", "--project", str(proj)], proj)
    run(["say", "连续两次没有新信息", "--project", str(proj)], proj)
    status = status_json(proj)
    assert status["offline"] is True
    assert status["model"]["last"] == "mock", status["model"]
    assert status["model"]["configured"] == "mock"
    human = run(["status", "--project", str(proj)], proj)["out"]
    assert "deepseek-chat" not in human


def test_mentor_switch_between_activities_is_announced():
    proj = init_proj("mentor-announce")
    first = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    assert "本次导师：trainer" in first["out"], first["out"]
    second = run(["start", "--minutes", "20", "--project", str(proj)], proj)
    assert "trainer → coach" in second["out"], second["out"]
    assert "按活动类型绑定导师" in second["out"], second["out"]


# --------------------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------------------


TESTS = [
    test_init_idempotent,
    test_offline_e2e,
    test_budget_parsing,
    test_d_s1_budget_changes_choice,
    test_d_s2_due_priority,
    test_d_s3_same_day_no_repeat,
    test_srs_ladder_and_lapse,
    test_srs_simulated_clock_cli,
    test_backlog_fold_and_session_cap,
    test_weekly_card_cap,
    test_idempotent_say,
    test_evidence_rules,
    test_l3_requires_artifact_and_delayed_retest,
    test_mentor_cannot_change_schedule,
    test_examiner_hint_leak,
    test_update_validation,
    test_recovery_from_backup_and_torn_tail,
    test_stale_write_is_rejected,
    test_switch_and_handoff,
    test_git_remote_push_and_clone,
    test_two_syncs_commit_modified_tracked_file,
    test_review_forces_due_and_exempts_repeat,
    test_clean_copy_recovery,
    test_doctor_reports_problems,
    test_email_template_no_programming_residue,
    test_exit_codes,
    test_budget_same_day_carry_and_remaining,
    test_missing_block_repaired_silently,
    test_artifact_required_blocks_completion_and_acknowledges_later,
    test_init_does_not_invent_self_report,
    test_gitignore_covers_usage_and_doctor_reports_true_state,
    test_model_label_records_actual_model,
    test_mentor_switch_between_activities_is_announced,
    test_echo_is_not_independent_correct,
    test_pure_question_turn_is_not_an_attempt,
    test_text_conflict_uses_block_and_is_logged,
    test_partial_answer_is_not_question_and_gets_no_credit,
    test_email_core_writing_block_is_not_starved,
    test_correct_answer_with_partial_word_in_prose_stays_correct,
    test_say_answer_with_minutes_does_not_change_budget,
    test_writing_draft_in_concept_session_routes_to_writing_skill,
    test_email_block_step2_is_a_writing_type,
    test_explicit_switch_is_sticky_for_next_start,
    test_handoff_captures_open_question_and_concrete_next,
    test_status_next_matches_start_and_five_minute_wording,
    test_duplicate_card_fronts_merge,
    test_time_boxed_incomplete_and_replacement_noted,
    test_unfinished_card_not_folded_and_first_next,
    test_remaining_minutes_one_source,
    test_sync_recover_unions_journals_and_snapshot_conflict_exits_3,
]


def main() -> int:
    print(f"Tempo tests · {len(TESTS)} cases · tmp={BASE}")
    failures = 0
    for test in TESTS:
        name = test.__name__
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - report every failure
            failures += 1
            RESULTS.append((name, False, str(exc)))
            print(f"[FAIL] {name}: {exc}")
            if os.environ.get("LEARNARK_DEBUG"):
                traceback.print_exc()
        else:
            RESULTS.append((name, True, ""))
            print(f"[ok  ] {name}")
    print()
    print(f"{len(RESULTS) - failures}/{len(RESULTS)} passed")
    if failures:
        print("\nfailures:")
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"- {name}: {detail}")
        print(f"\nartifacts kept for debugging: {BASE}")
        return 1
    shutil.rmtree(BASE, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
