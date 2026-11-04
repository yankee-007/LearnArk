#!/usr/bin/env python3
"""Deterministic, offline test suite for the Atelier variant.

Run:
    python tests/run_tests.py

Every test uses ``LEARNARK_LLM=mock`` and the variant's own fixture (or a
temporary script).  No network access is required or performed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "runtime" / "learn.py"
FIXTURE = ROOT / "tests" / "fixtures" / "mentor_script.jsonl"
MENTORS = ["planner", "concept", "coach", "examiner", "reviewer"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def base_env(script: Path | None = None, now: str | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["LEARNARK_LLM"] = "mock"
    env["LEARNARK_MOCK_SCRIPT"] = str(script or FIXTURE)
    env.pop("LEARNARK_NOW", None)
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("LEARNARK_API_KEY", None)
    env.pop("LEARNARK_PROJECT", None)
    if now:
        env["LEARNARK_NOW"] = now
    return env


def run(args, cwd=None, script: Path | None = None, now: str | None = None, stdin: str | None = None):
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        cwd=str(cwd or ROOT),
        env=base_env(script, now),
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )


def block(payload: dict, text: str = "好的，见下面的机器块。") -> str:
    return text + "\n\n```learn-update\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def handoff(
    why="继续下一步",
    what_tried=None,
    open_loops=None,
    next_="下一步做练习",
    to_hint=None,
    auto=False,
    extra=None,
):
    payload = {
        "why": why,
        "what_tried": what_tried or ["本轮做了一次尝试"],
        "open_loops": open_loops
        if open_loops is not None
        else [{"id": "OL-0", "owner": "coach", "due": "2026-11-06", "text": "按计划继续", "blocking": False}],
        "next": next_,
    }
    if to_hint:
        payload["to_hint"] = to_hint
    if auto:
        payload["auto"] = True
    if extra:
        payload.update(extra)
    return payload


def update(
    help_level=0,
    activity=None,
    correct=None,
    next_="继续",
    plan_change=None,
    verdict=None,
    handoff_value=None,
    analogy=None,
    mastery_delta=0,
    misconception=None,
    review_note=None,
    do_not_redo=None,
):
    payload = {
        "help_level": help_level,
        "attempt": {"activity_id": activity, "correct": correct},
        "misconception": misconception,
        "next": next_,
        "mastery_delta": mastery_delta,
    }
    if plan_change is not None:
        payload["plan_change"] = plan_change
    if verdict is not None:
        payload["verdict"] = verdict
    if handoff_value is not None:
        payload["handoff"] = handoff_value
    if analogy is not None:
        payload["analogy"] = analogy
    if review_note is not None:
        payload["review_note"] = review_note
    if do_not_redo is not None:
        payload["do_not_redo"] = do_not_redo
    return payload


def write_script(directory: Path, entries: list[dict]) -> Path:
    path = Path(directory) / "script.jsonl"
    path.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n", encoding="utf-8")
    return path


def events(project: Path) -> list[dict]:
    path = project / ".learnark" / "journal" / "events.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def kinds(project: Path) -> list[str]:
    return [event.get("kind") for event in events(project)]


def events_of(project: Path, kind: str) -> list[dict]:
    return [event for event in events(project) if event.get("kind") == kind]


def studio(project: Path) -> dict:
    return json.loads((project / ".learnark" / "state" / "studio.json").read_text(encoding="utf-8"))


def project_state(project: Path) -> dict:
    return json.loads((project / ".learnark" / "project.json").read_text(encoding="utf-8"))


def state_session(project: Path) -> dict:
    return json.loads((project / ".learnark" / "state" / "session.json").read_text(encoding="utf-8"))


def capability(project: Path) -> dict:
    return json.loads((project / ".learnark" / "state" / "capability.json").read_text(encoding="utf-8"))


def node_level(project: Path, node_id: str) -> int:
    for node in capability(project).get("nodes", []):
        if node.get("id") == node_id:
            return int(node.get("level") or 0)
    return 0


def latest_handoff_block(project: Path) -> dict:
    text = (project / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    marker = "```handoff"
    start = text.index(marker) + len(marker)
    body = text[start:].split("```", 1)[0].strip()
    return json.loads(body)


def handoff_files(project: Path) -> list[Path]:
    folder = project / ".learnark" / "handoff"
    return sorted(path for path in folder.glob("*.md") if path.name != "latest.md") if folder.exists() else []


class AtelierTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atelier-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    # -- fixtures ---------------------------------------------------------
    def init(self, template="agent-dev", extra=None, name=None) -> Path:
        project = self.tmp / (name or "proj")
        args = ["init", "--goal", "Agent 开发", "--dir", str(project), "--template", template]
        if extra:
            args += extra
        result = run(args, cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return project

    def say(self, project: Path, text: str, script: Path | None = None, expect: int = 0):
        result = run(["say", text, "--offline"], cwd=project, script=script)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def start(self, project: Path, script: Path | None = None, expect: int = 0):
        result = run(["start", "--offline"], cwd=project, script=script)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def switch(self, project: Path, mentor: str, extra=None, expect: int = 0):
        args = ["switch", mentor] + (extra or [])
        result = run(args, cwd=project)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def coach_setup(self, reply: dict | None = None, script_entries: list[dict] | None = None):
        """planner turn -> handoff -> coach turn. Returns (project, script)."""
        project = self.init()
        planner_block = block(
            update(
                handoff_value=handoff(
                    why="诊断结束，交给 coach 练习",
                    what_tried=["问了三个诊断问题"],
                    open_loops=[{"id": "OL-1", "owner": "coach", "due": "2026-11-05", "text": "做一次小练习", "blocking": False}],
                    next_="coach 带一次小练习",
                )
            ),
            text="先做一个最小的练习，做完我们再判断。",
        )
        entries = [
            {"match": "帮我定这周计划", "reply": planner_block},
            {"match": "开始练习", "reply": block(reply or update(help_level=0, activity="w1-agent-loop-ex1", correct=True), text="先写出循环四要素，然后我们对答案。")},
        ]
        if script_entries:
            entries.extend(script_entries)
        script = write_script(self.tmp, entries)
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "coach")
        return project, script


# ---------------------------------------------------------------------------
# init and generated project documents
# ---------------------------------------------------------------------------
class InitTests(AtelierTestCase):
    def test_init_creates_contract_files(self):
        project = self.init()
        self.assertTrue((project / ".learnark" / "project.json").exists())
        self.assertTrue((project / "README.md").exists())
        self.assertTrue((project / "AGENTS.md").exists())
        self.assertTrue((project / ".gitignore").exists())
        self.assertTrue((project / ".gitattributes").exists())
        attributes = (project / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("* -text", attributes)
        ignore = (project / ".gitignore").read_text(encoding="utf-8")
        for pattern in (".learnark/**/*.lock", "usage.jsonl", "sync-log.jsonl"):
            self.assertIn(pattern, ignore)
        self.assertEqual(len(list((project / ".learnark" / "state" / "mentors").glob("*.json"))), 5)
        data = studio(project)
        self.assertEqual(data["current_mentor"], "planner")
        self.assertEqual(len(data["plan"]["steps"]), 10)
        agents = (project / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("start", agents)
        self.assertIn("handoff", agents)
        readme = (project / "README.md").read_text(encoding="utf-8")
        self.assertIn("learn.cmd start", readme)
        self.assertTrue((project / ".git").exists())

    def test_init_is_repeatable_and_keeps_state(self):
        project = self.init()
        before = (project / ".learnark" / "project.json").read_text(encoding="utf-8")
        result = run(["init", "--goal", "换个目标", "--dir", str(project)], cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = (project / ".learnark" / "project.json").read_text(encoding="utf-8")
        self.assertEqual(before, after)
        self.assertEqual(len(events_of(project, "project_created")), 1)
        self.assertEqual(len(events_of(project, "plan_created")), 1)

    def test_version_manifest_matches_runtime(self):
        manifest = json.loads((ROOT / "version-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], "0.2.4")
        self.assertEqual(manifest["core_version"], "1.0.4")
        start_here = (ROOT / "START_HERE.md").read_text(encoding="utf-8")
        self.assertIn("0.2.4", start_here)

    def test_minutes_per_week_uses_hours_for_display(self):
        project = self.init(extra=["--minutes-per-week", "60"])
        self.assertEqual(project_state(project)["learner"]["minutes_per_week"], 60)
        text = run(["start"], cwd=project).stdout
        self.assertIn("1 小时", text)
        self.assertNotIn("60 小时", text)
        project2 = self.init(name="proj600", extra=["--minutes-per-week", "600"])
        self.assertEqual(project_state(project2)["learner"]["minutes_per_week"], 600)
        self.assertIn("10 小时", run(["start"], cwd=project2).stdout)

    def test_email_project_docs_are_writing_specific(self):
        project = self.init(template="email")
        for name in ("README.md", "AGENTS.md"):
            text = (project / name).read_text(encoding="utf-8").lower()
            for banned in ("agent", "json", "help_level", "tool call", "工具调用"):
                self.assertNotIn(banned, text, f"{name} contains {banned}")

    def test_email_template_has_no_programming_residue(self):
        project = self.init(template="email")
        plan = studio(project)["plan"]
        self.assertEqual(plan["minutes_per_week"], 180)
        text = json.dumps(plan, ensure_ascii=False)
        self.assertNotIn("Agent", text)
        activities = [step.get("activity_id", "") for step in plan["steps"]]
        self.assertTrue(any(activity.startswith("em-") for activity in activities))
        self.start(project)


# ---------------------------------------------------------------------------
# offline end-to-end flow
# ---------------------------------------------------------------------------
class FlowTests(AtelierTestCase):
    def test_end_to_end_offline(self):
        project = self.init()
        self.start(project)
        first = self.say(project, "帮我定这周计划")
        self.assertIn("[离线脚本导师]", first.stdout)
        second = self.say(project, "今天只有二十分钟")
        self.assertIn("计划：已按 planner 的变更更新。", second.stdout)
        status = run(["status", "--json"], cwd=project)
        self.assertEqual(status.returncode, 0, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["current_mentor"], "planner")
        self.assertIn("next", payload)
        self.switch(project, "concept")
        self.say(project, "RAG 和 Agent 记忆有什么区别")
        studio_result = run(["studio"], cwd=project)
        self.assertEqual(studio_result.returncode, 0, studio_result.stderr)
        for mentor in MENTORS:
            self.assertIn(mentor, studio_result.stdout)
        pause = run(["pause", "--note", "测试收工"], cwd=project)
        self.assertEqual(pause.returncode, 0, pause.stderr)
        self.assertGreaterEqual(len(handoff_files(project)), 2)
        sync = run(["sync"], cwd=project)
        self.assertEqual(sync.returncode, 0, sync.stderr)
        for word in ("written=", "committed=", "pushed="):
            self.assertIn(word, sync.stdout)
        doctor = run(["doctor"], cwd=project)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)
        export = run(["export", "--out", str(self.tmp / "export.md")], cwd=project)
        self.assertEqual(export.returncode, 0, export.stderr)
        text = (self.tmp / "export.md").read_text(encoding="utf-8")
        self.assertGreater(len(text), 100)
        self.assertIn("离线/合成", text)
        self.assertTrue((project / "sessions").exists())
        self.assertTrue(list((project / "sessions").glob("*.md")))
        self.assertIn("mentor_turn", kinds(project))
        self.assertIn("context_manifest", kinds(project))

    def test_say_is_idempotent_for_the_same_input(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [{"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))}],
        )
        self.say(project, "帮我定这周计划", script=script)
        second = self.say(project, "帮我定这周计划", script=script)
        self.assertIn("已记录", second.stdout)
        self.assertEqual(len(events_of(project, "mentor_turn")), 1)
        self.assertEqual(len(events_of(project, "context_manifest")), 1)

    def test_say_reads_stdin(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [{"match": "从标准输入来的话", "reply": block(update(handoff_value=handoff()))}],
        )
        result = run(["say", "-", "--offline"], cwd=project, script=script, stdin="从标准输入来的话")
        self.assertEqual(result.returncode, 0, result.stderr)
        session_files = list((project / "sessions").glob("*.md"))
        self.assertTrue(session_files)
        self.assertIn("从标准输入来的话", session_files[0].read_text(encoding="utf-8"))

    def test_restore_from_copied_project(self):
        project = self.init()
        self.start(project)
        self.say(project, "帮我定这周计划")
        pause = run(["pause"], cwd=project)
        self.assertEqual(pause.returncode, 0, pause.stderr)
        copy = self.tmp / "moved"
        shutil.copytree(project, copy)
        result = run(["start", "--project", str(copy)], cwd=self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("上次停在哪", result.stdout)
        status = run(["status", "--json", "--project", str(copy)], cwd=self.tmp)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertTrue(json.loads(status.stdout)["last_handoff"])

    def test_torn_journal_tail_is_tolerated(self):
        project = self.init()
        self.say(project, "帮我定这周计划")
        journal = project / ".learnark" / "journal" / "events.jsonl"
        with journal.open("a", encoding="utf-8") as handle:
            handle.write('{"kind": "mentor_turn", "payload": {')
        result = run(["status", "--json"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("current_mentor", json.loads(result.stdout))

    def test_corrupt_snapshot_recovers_from_backup(self):
        project = self.init()
        self.say(project, "帮我定这周计划")
        studio_path = project / ".learnark" / "state" / "studio.json"
        self.assertTrue((project / ".learnark" / "state" / "studio.json.bak").exists())
        studio_path.write_text("{ not json", encoding="utf-8")
        result = run(["status", "--json"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["recovered"])
        self.assertTrue(studio(project)["plan"]["steps"])

    def test_start_is_read_only_and_does_not_invent_history(self):
        project = self.init()
        studio_before = (project / ".learnark" / "state" / "studio.json").read_text(encoding="utf-8")
        first = run(["start", "--offline"], cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        second = run(["start", "--offline"], cwd=project)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(handoff_files(project), [])
        self.assertEqual(
            (project / ".learnark" / "state" / "studio.json").read_text(encoding="utf-8"),
            studio_before,
        )
        status = subprocess.run(["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(status.stdout.strip(), "", status.stdout)
        self.assertEqual(len(events_of(project, "session_opened")), 1)
        self.assertNotIn("超过 7 天", first.stderr + second.stderr)

    def test_auto_transition_from_mentor_proposal(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {
                    "match": "自动交接",
                    "reply": block(
                        update(
                            help_level=1,
                            activity="w1-agent-loop-ex1",
                            correct=True,
                            handoff_value=handoff(
                                why="仅在一级提示下通过，需独立验证",
                                to_hint="examiner",
                                auto=True,
                                next_="examiner 用新题考一次",
                            ),
                        )
                    ),
                },
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "coach")
        result = self.say(project, "自动交接", script=script)
        self.assertIn("[自动交接]", result.stdout)
        self.assertEqual(studio(project)["current_mentor"], "examiner")
        switches = events_of(project, "mentor_switch")
        self.assertTrue(any(event["payload"].get("source") == "auto" for event in switches))

    def test_same_text_after_pause_is_a_new_attempt(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [{"match": "同样的话", "reply": block(update(handoff_value=handoff()), text="记下了。")}],
        )
        self.say(project, "同样的话", script=script)
        self.assertEqual(run(["pause"], cwd=project).returncode, 0)
        self.say(project, "同样的话", script=script)
        self.assertEqual(len(events_of(project, "mentor_turn")), 2)

    def test_say_keeps_turn_when_auto_handoff_is_incomplete(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "我今天想继续",
                    "reply": block(
                        update(help_level=0, next_="继续说", handoff_value={"auto": True}),
                        text="我想换人，但没说清找谁。",
                    ),
                }
            ],
        )
        result = self.say(project, "我今天想继续", script=script)
        self.assertIn("你的消息已保存", result.stdout)
        session_files = list((project / "sessions").glob("*.md"))
        self.assertTrue(session_files)
        content = session_files[0].read_text(encoding="utf-8")
        self.assertIn("我今天想继续", content)
        self.assertIn("我想换人", content)
        self.assertTrue(events_of(project, "handoff_rejected"))
        self.assertEqual(studio(project)["current_mentor"], "planner")
        self.assertEqual(len(events_of(project, "mentor_turn")), 1)

    def test_three_failed_proposals_leave_three_audit_events(self):
        project = self.init()
        entries = [
            {
                "match": f"失败提案{index}",
                "reply": block(update(next_="继续", handoff_value={"auto": True}), text=f"第 {index} 次。"),
            }
            for index in range(1, 4)
        ]
        script = write_script(self.tmp, entries)
        for index in range(1, 4):
            self.say(project, f"失败提案{index}", script=script)
        attempts = events_of(project, "say_attempt")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(len({event["payload"]["attempt_id"] for event in attempts}), 3)
        self.assertEqual(len(events_of(project, "handoff_rejected")), 3)
        self.assertEqual(len(events_of(project, "mentor_turn")), 3)

    def test_mentioning_planner_does_not_switch_sessions(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {
                    "match": "上次我跟 planner",
                    "reply": block(update(next_="继续复述四要素"), text="好，我们继续刚才的概念。"),
                },
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "concept")
        before = len(events_of(project, "mentor_switch"))
        result = self.say(project, "start 让我来找你。上次我跟 planner 说四要素是模型、工具、观察、停止。", script=script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(studio(project)["current_mentor"], "concept")
        self.assertEqual(len(events_of(project, "mentor_switch")), before)
        self.assertTrue(events_of(project, "mentor_turn"))

    def test_switch_plan_is_rejected_with_candidates(self):
        project = self.init()
        result = self.switch(project, "plan", expect=2)
        self.assertIn("planner", result.stderr)
        self.assertEqual(studio(project)["current_mentor"], "planner")

    def test_learner_time_is_persisted_and_displayed(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "每周", "reply": block(update(next_="继续"))}])
        result = self.say(project, "我每周 1–2 小时，今天只有 20 分钟。", script=script)
        self.assertIn("已记录你的时间", result.stdout)
        self.assertEqual(project_state(project)["learner"]["minutes_per_week"], 120)
        self.assertEqual(project_state(project)["learner"]["weekly_range_minutes"], [60, 120])
        plan = studio(project)["plan"]
        self.assertEqual(plan["minutes_per_week"], 120)
        self.assertEqual(plan["weekly_range_minutes"], [60, 120])
        started = run(["start", "--offline"], cwd=project).stdout
        self.assertIn("1–2 小时", started)
        planned = run(["plan"], cwd=project).stdout
        self.assertIn("1–2 小时", planned)

    def test_promised_next_becomes_open_loop_with_time_estimate(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [{"match": "开始", "reply": block(update(next_="下一轮让 concept 用十分钟讲状态与记忆"), text="好，先到这。")}],
        )
        self.say(project, "开始", script=script)
        self.assertTrue(events_of(project, "mentor_next_observed"))
        status = json.loads(run(["status", "--json"], cwd=project).stdout)
        self.assertEqual(status["next"]["mentor"], "concept")
        self.assertIn("状态", status["next"]["action"])
        self.assertEqual(status["next"]["est_minutes"], 10)
        self.assertIn("concept", run(["start", "--offline"], cwd=project).stdout)

    def test_session_clock_and_probes_are_real(self):
        project = self.init()
        started = run(
            ["start", "--minutes", "20", "--offline"],
            cwd=project,
            now="2026-11-04T19:00:00+08:00",
        )
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn("剩余 20 分钟", started.stdout)
        script = write_script(self.tmp, [{"match": "继续", "reply": block(update(next_="继续"))}])
        mid = run(
            ["say", "继续", "--offline"],
            cwd=project,
            script=script,
            now="2026-11-04T19:05:00+08:00",
        )
        self.assertIn("剩余 15 分钟", mid.stdout)
        self.assertFalse(state_session(project).get("ended_at"))
        late = run(
            ["say", "继续", "--offline"],
            cwd=project,
            script=script,
            now="2026-11-04T19:40:00+08:00",
        )
        self.assertIn("预算已到", late.stdout)
        self.assertFalse(state_session(project).get("ended_at"))

    def test_planner_must_use_two_probes_before_diagnosis_done(self):
        project = self.init()
        start = run(["start", "--offline"], cwd=project)
        self.assertIn("probe-d1", start.stdout)
        first_script = write_script(self.tmp, [{"match": "先说", "reply": block(update(next_="继续"), text="先说说你之前做过什么。")}])
        self.say(project, "先说", script=first_script)
        self.assertEqual((studio(project).get("flags") or {}).get("plan_state"), "diagnosing")
        second_script = write_script(
            self.tmp,
            [{"match": "回答", "reply": block(update(next_="继续"), text="probe-d1：工具失败先看什么？probe-d2：检索和记忆差在哪？")}],
        )
        self.say(project, "回答", script=second_script)
        self.assertEqual((studio(project).get("flags") or {}).get("plan_state"), "confirmed")
        self.assertGreaterEqual(len((studio(project).get("flags") or {}).get("probes_asked") or []), 2)

    def test_handoff_aggregates_attempts_across_sessions(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "第一次尝试",
                    "reply": block(
                        update(activity="w1-agent-loop-ex1", correct=None, next_="已经过了，去做 ex1"),
                        text="先记下这次尝试。",
                    ),
                },
                {
                    "match": "第二次尝试",
                    "reply": block(
                        update(activity="w2-tools-ex1", correct=None, next_="继续"),
                        text="再记一次。",
                    ),
                },
            ],
        )
        self.say(project, "第一次尝试", script=script)
        self.assertEqual(run(["pause"], cwd=project).returncode, 0)
        self.switch(project, "concept")
        self.say(project, "第二次尝试", script=script)
        self.assertEqual(run(["pause"], cwd=project).returncode, 0)
        payload = latest_handoff_block(project)
        joined = "；".join(payload["what_tried"])
        self.assertIn("w1-agent-loop-ex1", joined)
        self.assertIn("w2-tools-ex1", joined)
        self.assertIn("上次会话", joined)
        step = next(item for item in studio(project)["plan"]["steps"] if item["step_id"] == "w1-agent-loop-ex1")
        self.assertNotEqual(step["status"], "done")
        status = json.loads(run(["status", "--json"], cwd=project).stdout)
        self.assertEqual(status["plan"]["steps_done"], 0)

    def test_explanation_does_not_create_false_misconception(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "讲讲工具",
                    "reply": block(
                        update(next_="继续"),
                        text="反例提醒：如果工具返回错误，模型应该先观察再决定，而不是直接重试。",
                    ),
                }
            ],
        )
        self.say(project, "讲讲工具", script=script)
        self.assertFalse(events_of(project, "misconception_observed"))
        node = next((item for item in capability(project)["nodes"] if item["id"] == "w2-tools"), None)
        self.assertTrue(node is None or node.get("last_fail") is None)

    def test_mentor_mention_is_recorded_without_switching(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {"match": "上次 planner", "reply": block(update(next_="继续复述"), text="好，我们接着来。")},
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "concept")
        before = len(events_of(project, "mentor_switch"))
        result = self.say(project, "上次 planner 让我先讲区别，我们继续。", script=script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(studio(project)["current_mentor"], "concept")
        self.assertEqual(len(events_of(project, "mentor_switch")), before)
        self.assertTrue(events_of(project, "mentor_mentioned"))

    def test_handoff_what_tried_has_real_attempt_and_no_invented_dnr(self):
        project, script = self.coach_setup(
            update(
                help_level=0,
                activity="w1-agent-loop-ex1",
                correct=True,
                handoff_value=handoff(why="练习完成，交给概念"),
            )
        )
        self.say(project, "开始练习", script=script)
        result = run(["pause"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = latest_handoff_block(project)
        joined = "；".join(payload["what_tried"])
        self.assertIn("w1-agent-loop-ex1", joined)
        self.assertEqual(payload["do_not_redo"], [])
        self.assertNotIn("RAG 就是长期记忆", joined)
        self.assertNotIn("框架三行代码", joined)


    def test_coach_exam_request_creates_pending_exam_and_examine_next(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {
                    "match": "开始练习",
                    "reply": block(
                        update(help_level=1, activity="w1-agent-loop-ex1", correct=None, next_="等 examiner 用独立题验"),
                        text="四句先到这里，等 examiner 用独立题验一次。",
                    ),
                },
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "coach")
        self.say(project, "开始练习", script=script)
        pending = capability(project).get("pending_exam")
        self.assertTrue(pending)
        self.assertEqual(pending["status"], "open")
        status = json.loads(run(["status", "--json"], cwd=project).stdout)
        self.assertEqual(status["next"]["mentor"], "examiner")
        self.assertEqual(status["next"]["command"], "learn.cmd examine")
        start = run(["start"], cwd=project).stdout
        self.assertIn("learn.cmd examine", start)
        self.assertEqual(run(["examine"], cwd=project).returncode, 0)

    def test_planner_diagnosis_triggers_handoff(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "三个都能答",
                    "reply": block(
                        update(help_level=0, next_="先纠正误解"),
                        text="我看到两处误解：工具结果当成用户消息，RAG 就是记忆。这两条都需要先讲清，不能按自述跳过。",
                    ),
                }
            ],
        )
        self.say(project, "三个都能答", script=script)
        self.assertTrue(events_of(project, "diagnosis_handoff_requested"))
        self.assertIn(studio(project)["current_mentor"], ("concept", "coach"))
        payload = latest_handoff_block(project)
        for field in ("why", "known", "what_tried", "open_loops", "next"):
            self.assertTrue(payload[field], field)
        switch = events_of(project, "mentor_switch")[-1]["payload"]
        self.assertEqual(switch["source"], "diagnosis")


# ---------------------------------------------------------------------------
# evidence rules
# ---------------------------------------------------------------------------
class EvidenceTests(AtelierTestCase):
    def test_coach_correct_claim_is_practice_only(self):
        project, script = self.coach_setup()
        self.say(project, "开始练习", script=script)
        self.assertEqual(node_level(project, "w1-agent-loop-ex1"), 0)
        practice = events_of(project, "practice_attempt")
        self.assertTrue(practice)
        self.assertIsNone(practice[-1]["payload"]["correct"])
        self.assertTrue(practice[-1]["payload"]["claimed_correct"])
        self.assertFalse(events_of(project, "capability_upgrade"))
        evidence = [
            entry
            for node in capability(project)["nodes"]
            for entry in node.get("evidence", [])
            if entry.get("source") == "observed"
        ]
        self.assertTrue(evidence)
        self.assertTrue(all(entry["counts_for_level"] is False for entry in evidence))

    def test_coach_conflict_marks_not_correct(self):
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, next_="继续"),
        )
        # Replace the coach reply text with praise + correction.
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {
                    "match": "开始练习",
                    "reply": block(
                        update(help_level=0, activity="w1-agent-loop-ex1", correct=True, next_="继续"),
                        text="四句都在点上，你抓住了关键；不过第 4 句写错了，工具结果要回到循环而不是当用户消息。",
                    ),
                },
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "coach")
        self.say(project, "开始练习", script=script)
        self.assertEqual(node_level(project, "w1-agent-loop-ex1"), 0)
        self.assertTrue(events_of(project, "mentor_verdict_conflict"))

    def test_help_level_2_does_not_upgrade(self):
        project, script = self.coach_setup(
            update(help_level=2, activity="w1-agent-loop-ex1", correct=True, next_="分步引导后重做")
        )
        self.say(project, "开始练习", script=script)
        self.assertEqual(node_level(project, "w1-agent-loop-ex1"), 0)
        self.assertTrue(events_of(project, "assisted"))
        self.assertFalse(events_of(project, "capability_upgrade"))

    def test_help_level_3_does_not_upgrade(self):
        project, script = self.coach_setup(
            update(help_level=3, activity="w1-agent-loop-ex1", correct=True, next_="受助完成")
        )
        self.say(project, "开始练习", script=script)
        self.assertEqual(node_level(project, "w1-agent-loop-ex1"), 0)
        self.assertTrue(events_of(project, "assisted"))

    def test_mentor_mastery_delta_is_ignored(self):
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, mastery_delta=1, next_="算你掌握了")
        )
        self.say(project, "开始练习", script=script)
        violations = events_of(project, "authority_violation")
        self.assertTrue(any(event["payload"].get("kind") == "mastery_delta_requested" for event in violations))
        self.assertEqual(node_level(project, "w1-agent-loop-ex1"), 0)

    def test_verdict_outside_examiner_is_ignored(self):
        project, script = self.coach_setup(
            update(
                help_level=0,
                activity="w1-agent-loop-ex1",
                correct=True,
                verdict={"activity_id": "w1-agent-loop-ex1", "result": "pass", "basis": "原话", "rubric": {"correctness": 2, "reasoning": 1, "max": 4, "pass_line": 2}},
            )
        )
        self.say(project, "开始练习", script=script)
        violations = events_of(project, "authority_violation")
        self.assertTrue(any(event["payload"].get("kind") == "verdict_outside_examiner" for event in violations))
        self.assertEqual(node_level(project, "w1-agent-loop-ex1"), 0)

    def test_self_report_never_upgrades(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "我做过 RAG",
                    "reply": block(update(next_="用一道口头题校准"), text="自述只能算线索。"),
                }
            ],
        )
        self.say(project, "我做过 RAG，也用过 API", script=script)
        self.assertTrue(events_of(project, "self_report"))
        self.assertFalse(events_of(project, "capability_upgrade"))
        self.assertEqual(node_level(project, "w1-agent-loop"), 0)

    def test_invalid_machine_block_retries_once_then_hides_jargon(self):
        project = self.init()
        before_version = studio(project)["plan"]["version"]
        script = write_script(
            self.tmp,
            [{"match": "没有机器块", "reply": "这是纯文本回复，忘了给出格式。"}],
        )
        result = self.say(project, "没有机器块", script=script)
        self.assertNotIn("机器块", result.stdout)
        self.assertIn("本轮没有形成可记录的证据", result.stdout)
        retries = events_of(project, "mentor_update_retried")
        self.assertTrue(retries)
        self.assertFalse(retries[-1]["payload"]["repaired"])
        invalid = events_of(project, "mentor_update_invalid")
        self.assertTrue(invalid)
        self.assertTrue(invalid[-1]["payload"]["raw_sha256"])
        self.assertEqual(studio(project)["plan"]["version"], before_version)
        self.assertFalse(events_of(project, "capability_upgrade"))
        turn = events_of(project, "mentor_turn")[-1]["payload"]
        self.assertTrue(turn["invalid"])
        self.assertEqual(turn["mode"], "mock")
        status = run(["status"], cwd=project).stdout
        self.assertIn("未标注", status, status)

    def test_missing_machine_block_is_repaired_silently(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "需要修复", "reply": "先给正文，但我忘了格式。"},
                {"match": "", "reply": block(update(help_level=1, next_="继续"), text="补好了，继续。")},
            ],
        )
        result = self.say(project, "需要修复", script=script)
        self.assertNotIn("机器块", result.stdout)
        retries = events_of(project, "mentor_update_retried")
        self.assertTrue(retries)
        self.assertTrue(retries[-1]["payload"]["repaired"])
        self.assertFalse(events_of(project, "mentor_update_invalid"))
        self.assertEqual(events_of(project, "mentor_turn")[-1]["payload"]["help_level"], 1)

    def test_misconception_is_recorded_as_weakness_with_source(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {
                    "match": "开始练习",
                    "reply": block(
                        update(help_level=1, activity="w1-agent-loop-ex1", correct=None),
                        text="RAG 是按需检索外部文档，不是记忆；你把文档塞进向量库，模型下次不知道上一轮做了什么。",
                    ),
                },
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "coach")
        self.say(project, "开始练习", script=script)
        observed = events_of(project, "misconception_observed")
        self.assertTrue(observed)
        self.assertEqual(observed[-1]["payload"]["node"], "w3-memory")
        node = next(item for item in capability(project)["nodes"] if item["id"] == "w3-memory")
        self.assertTrue(node["last_fail"]["misconception"])
        self.assertTrue(node["last_fail"]["source_event"])
        status = run(["status"], cwd=project).stdout
        self.assertIn("薄弱/误解", status)
        self.assertIn("w3-memory", status)
        self.assertIn(node["last_fail"]["source_event"], status)

    def test_evidence_artifact_must_exist(self):
        project, script = self.coach_setup()
        self.say(project, "开始练习", script=script)
        entries = [
            entry
            for node in capability(project)["nodes"]
            for entry in node.get("evidence", [])
        ]
        self.assertTrue(entries)
        for entry in entries:
            artifact = entry.get("artifact")
            self.assertTrue(artifact is None or (project / artifact).exists(), artifact)
            self.assertFalse(entry.get("artifact_verified", False))
        missing = events_of(project, "evidence_artifact_missing")
        self.assertTrue(missing)
        self.assertTrue(missing[-1]["payload"]["expected"].startswith("artifacts/"))

    def test_three_question_exam_is_resumable_and_artifacts_verified(self):
        project, script = self.coach_setup()
        self.say(project, "开始练习", script=script)
        examine = run(["examine"], cwd=project)
        self.assertEqual(examine.returncode, 0, examine.stdout + examine.stderr)
        pending = capability(project)["pending_exam"]
        questions = list(pending["questions"])
        self.assertEqual(len(questions), 3)
        studio_data = studio(project)
        studio_data["mentors"].setdefault("coach", {}).setdefault("open_loops", []).append(
            {"id": "OL-stale", "owner": "coach", "due": "2026-11-05", "text": "完成 " + questions[0].rsplit("-q", 1)[0], "blocking": True, "status": "open"}
        )
        (project / ".learnark" / "state" / "studio.json").write_text(json.dumps(studio_data, ensure_ascii=False), encoding="utf-8")
        for index, question in enumerate(questions):
            exam_script = write_script(
                self.tmp,
                [
                    {
                        "match": f"答题 {index}",
                        "reply": block(
                            update(
                                help_level=0,
                                activity=question,
                                correct=True,
                                verdict={
                                    "activity_id": question,
                                    "result": "pass",
                                    "basis": "答对",
                                    "rubric": {"correctness": 3, "reasoning": 2, "max": 5, "pass_line": 3},
                                },
                                next_="下一题",
                            ),
                            text="pass",
                        ),
                    }
                ],
            )
            self.say(project, f"答题 {index}", script=exam_script)
            cap = capability(project)
            if index < 2:
                self.assertIsNotNone(cap.get("pending_exam"))
                self.assertEqual(len(cap["pending_exam"]["remaining_questions"]), 2 - index)
                status = json.loads(run(["status", "--json"], cwd=project).stdout)
                self.assertEqual(status["next"]["command"], "learn.cmd examine")
            else:
                self.assertIsNone(cap.get("pending_exam"))
        artifact = project / "artifacts" / (questions[0] + ".md")
        self.assertTrue(artifact.exists(), artifact)
        node = next(item for item in capability(project)["nodes"] if item["id"] == "w1-agent-loop")
        self.assertTrue(any(entry.get("artifact_verified") for entry in node.get("evidence", [])))
        self.assertTrue(events_of(project, "open_loop_closed"))

    def test_examiner_pass_writes_verified(self):
        project, script = self.coach_setup(
            update(
                help_level=1,
                activity="w1-agent-loop-ex1",
                correct=True,
                handoff_value=handoff(
                    why="一级提示下通过，需要独立验证",
                    what_tried=["w1-agent-loop-ex1 在提示下通过"],
                    open_loops=[{"id": "OL-7", "owner": "examiner", "due": "2026-11-05", "text": "独立完成一次迁移题", "blocking": True}],
                    next_="examiner 用新题考一次",
                ),
                next_="换场景考一次",
            )
        )
        self.say(project, "开始练习", script=script)
        exam_script = write_script(
            self.tmp,
            [
                {
                    "match": "我选 B",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=True,
                            mastery_delta=1,
                            next_="进入下一题",
                            verdict={
                                "activity_id": "exam-a",
                                "result": "pass",
                                "basis": "原话：检索只是把文档临时塞进上下文",
                                "rubric": {"correctness": 2, "reasoning": 1, "max": 4, "pass_line": 2},
                            },
                        )
                    ),
                },
                {
                    "match": "开始练习",
                    "reply": block(update(help_level=1, activity="w1-agent-loop-ex1", correct=True)),
                },
                {
                    "match": "帮我定这周计划",
                    "reply": block(update(handoff_value=handoff())),
                },
            ],
        )
        examine = run(["examine"], cwd=project)
        self.assertEqual(examine.returncode, 0, examine.stderr)
        self.assertEqual(studio(project)["current_mentor"], "examiner")
        result = run(["say", "我选 B", "--offline"], cwd=project, script=exam_script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertGreaterEqual(node_level(project, "w1-agent-loop"), 4)
        exam_events = events_of(project, "exam")
        self.assertEqual(exam_events[-1]["payload"]["verdict"], "pass")
        self.assertTrue(exam_events[-1]["payload"]["evidence_event_ids"])
        verified = [
            entry
            for node in capability(project)["nodes"]
            for entry in node.get("evidence", [])
            if entry.get("source") == "verified"
        ]
        self.assertTrue(verified)

    def test_examiner_fail_downgrades_with_reason(self):
        project, script = self.coach_setup(
            update(
                help_level=0,
                activity="w1-agent-loop-ex1",
                correct=True,
                handoff_value=handoff(),
                next_="进入考核",
            )
        )
        self.say(project, "开始练习", script=script)
        # first pass -> verified
        pass_script = write_script(
            self.tmp,
            [
                {
                    "match": "答对了",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=True,
                            verdict={"activity_id": "exam-a", "result": "pass", "basis": "原话：四要素齐全", "rubric": {"correctness": 2, "reasoning": 2, "max": 4, "pass_line": 2}},
                        )
                    ),
                },
                {"match": "开始练习", "reply": block(update(handoff_value=handoff()))},
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
            ],
        )
        self.assertEqual(run(["examine"], cwd=project).returncode, 0)
        run(["say", "答对了", "--offline"], cwd=project, script=pass_script)
        self.assertGreaterEqual(node_level(project, "w1-agent-loop"), 4)
        # then retest fail
        self.assertEqual(run(["examine", "--fill-missing"], cwd=project).returncode, 0)
        fail_script = write_script(
            self.tmp,
            [
                {
                    "match": "忘了",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=False,
                            next_="回看",
                            misconception="把记忆当成检索",
                            verdict={"activity_id": "exam-a", "result": "fail", "basis": "原话：忘了", "rubric": {"correctness": 0, "reasoning": 0, "max": 4, "pass_line": 2}},
                        )
                    ),
                }
            ],
        )
        run(["say", "忘了", "--offline"], cwd=project, script=fail_script)
        self.assertLessEqual(node_level(project, "w1-agent-loop"), 3)
        decay = events_of(project, "capability_decay")
        self.assertTrue(decay)
        self.assertTrue(decay[-1]["payload"]["reason"])

    def test_examiner_help_discards_verdict(self):
        project, script = self.coach_setup(
            update(
                help_level=0,
                activity="w1-agent-loop-ex1",
                correct=True,
                handoff_value=handoff(why="需要独立验证"),
            )
        )
        self.say(project, "开始练习", script=script)
        self.assertEqual(run(["examine"], cwd=project).returncode, 0)
        help_script = write_script(
            self.tmp,
            [
                {
                    "match": "随便说说",
                    "reply": block(
                        update(
                            help_level=1,
                            activity="exam-a",
                            correct=True,
                            verdict={"activity_id": "exam-a", "result": "pass", "basis": "我帮你补全", "rubric": {"correctness": 2, "reasoning": 2, "max": 4, "pass_line": 2}},
                        ),
                        text="我提示一下：先想循环四个部分。",
                    ),
                }
            ],
        )
        result = run(["say", "随便说说", "--offline"], cwd=project, script=help_script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(events_of(project, "examiner_help_violation"))
        self.assertFalse([event for event in events_of(project, "capability_upgrade") if event["payload"].get("source") == "verified"])
        self.assertEqual(node_level(project, "w1-agent-loop"), 0)
        self.assertEqual(capability(project)["pending_exam"]["status"], "reask")

    def test_examiner_hint_request_is_refused(self):
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, handoff_value=handoff())
        )
        self.say(project, "开始练习", script=script)
        self.assertEqual(run(["examine"], cwd=project).returncode, 0)
        hint_script = write_script(
            self.tmp,
            [
                {
                    "match": "给点提示",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=None,
                            verdict={"activity_id": "exam-a", "result": "pending", "basis": "未作答", "rubric": {"correctness": 0, "reasoning": 0, "max": 4, "pass_line": 2}},
                        ),
                        text="考核中不给提示：按现在理解作答，或说跳过。",
                    ),
                }
            ],
        )
        result = run(["say", "给点提示", "--offline"], cwd=project, script=hint_script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(events_of(project, "hint_refused"))
        self.assertFalse(events_of(project, "examiner_help_violation"))


# ---------------------------------------------------------------------------
# examiner isolation
# ---------------------------------------------------------------------------
class ExaminerIsolationTests(AtelierTestCase):
    def _to_examiner(self):
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, handoff_value=handoff(why="需要独立验证"))
        )
        self.say(project, "开始练习", script=script)
        self.assertEqual(run(["examine"], cwd=project).returncode, 0)
        exam_script = write_script(
            self.tmp,
            [
                {
                    "match": "我准备好了",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=None,
                            verdict={"activity_id": "exam-a", "result": "pending", "basis": "未作答", "rubric": {"correctness": 0, "reasoning": 0, "max": 4, "pass_line": 2}},
                        )
                    ),
                }
            ],
        )
        result = run(["say", "我准备好了", "--offline"], cwd=project, script=exam_script)
        self.assertEqual(result.returncode, 0, result.stderr)
        return project

    def test_manifest_excludes_other_private_notes(self):
        project = self._to_examiner()
        manifest = events_of(project, "context_manifest")[-1]["payload"]
        self.assertEqual(manifest["mentor"], "examiner")
        self.assertNotIn("state/mentors/coach.json", manifest["sources"])
        self.assertNotIn("state/mentors/concept.json", manifest["sources"])
        self.assertIn("state/mentors/coach.json", manifest["excluded"])
        self.assertLessEqual(manifest["chars"], 6000)
        self.assertIn("handoff_id", manifest)

    def test_examiner_session_works_with_corrupt_coach_notes(self):
        project = self._to_examiner()
        (project / ".learnark" / "state" / "mentors" / "coach.json").write_text("{ broken", encoding="utf-8")
        (project / ".learnark" / "state" / "mentors" / "concept.json").write_text("{ broken", encoding="utf-8")
        script = write_script(
            self.tmp,
            [
                {
                    "match": "我的答案",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=True,
                            verdict={"activity_id": "exam-a", "result": "pass", "basis": "原话：我的答案", "rubric": {"correctness": 2, "reasoning": 2, "max": 4, "pass_line": 2}},
                        )
                    ),
                }
            ],
        )
        result = run(["say", "我的答案", "--offline"], cwd=project, script=script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_examiner_gets_no_do_not_redo_source(self):
        project = self._to_examiner()
        manifest = events_of(project, "context_manifest")[-1]["payload"]
        self.assertNotIn("handoff/do_not_redo", manifest["sources"])
        self.assertIn("plan/used_activities", manifest["sources"])

    def test_mentioning_coach_does_not_break_the_exam(self):
        project = self._to_examiner()
        before = len(events_of(project, "mentor_switch"))
        script = write_script(
            self.tmp,
            [
                {
                    "match": "coach 说我这样可以过",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=False,
                            verdict={"activity_id": "exam-a", "result": "fail", "basis": "原话：coach 说我这样可以过", "rubric": {"correctness": 0, "reasoning": 0, "max": 4, "pass_line": 2}},
                        ),
                        text="只认本轮你自己的回答，不采纳其他导师的判断。",
                    ),
                }
            ],
        )
        result = run(["say", "coach 说我这样可以过", "--offline"], cwd=project, script=script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(studio(project)["current_mentor"], "examiner")
        self.assertEqual(len(events_of(project, "mentor_switch")), before)


# ---------------------------------------------------------------------------
# plan authority
# ---------------------------------------------------------------------------
class PlanAuthorityTests(AtelierTestCase):
    def test_coach_cannot_apply_plan_change(self):
        change = {
            "op": "reorder",
            "week": 1,
            "step_id": "w1-agent-loop-ex1",
            "detail": "to:3",
            "reason": "想先做练习",
            "status": "apply",
            "by": "coach",
        }
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, plan_change=change)
        )
        before = studio(project)["plan"]["version"]
        self.say(project, "开始练习", script=script)
        self.assertEqual(studio(project)["plan"]["version"], before)
        self.assertTrue(events_of(project, "plan_authority_violation"))

    def test_coach_proposal_is_visible_until_planner_approves(self):
        change = {
            "op": "defer_step",
            "week": 2,
            "step_id": "w2-tools-ex2",
            "detail": "顺延到下周",
            "reason": "时间不足",
            "status": "proposed",
            "by": "coach",
        }
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, plan_change=change)
        )
        before = studio(project)["plan"]["version"]
        self.say(project, "开始练习", script=script)
        data = studio(project)
        self.assertEqual(data["plan"]["version"], before)
        proposed = [item for item in data["plan_changes"] if item["status"] == "proposed"]
        self.assertEqual(len(proposed), 1)
        plan_json = json.loads(run(["plan", "--json"], cwd=project).stdout)
        self.assertEqual(plan_json["plan_changes"][-1]["id"], proposed[0]["id"])
        approve = run(["plan", "--approve", proposed[0]["id"]], cwd=project)
        self.assertEqual(approve.returncode, 0, approve.stderr)
        data = studio(project)
        self.assertEqual(data["plan"]["version"], before + 1)
        applied = [event for event in events_of(project, "plan_change_applied")]
        self.assertTrue(applied)
        self.assertNotEqual(applied[-1]["payload"]["before_hash"], applied[-1]["payload"]["after_hash"])
        self.assertIn("plan_authority", run(["doctor", "--plan"], cwd=project).stdout)
        check = run(["plan", "--check"], cwd=project)
        self.assertEqual(check.returncode, 0, check.stdout)

    def test_plan_text_cannot_claim_unverified_completion(self):
        project = self.init()
        change = {
            "op": "replan_week",
            "week": 1,
            "step_id": "w1-agent-loop",
            "detail": "第 1 周：①四要素（今天 30 分钟已完成）",
            "reason": "压缩范围",
            "status": "apply",
            "by": "planner",
        }
        script = write_script(
            self.tmp,
            [{"match": "帮我定这周计划", "reply": block(update(plan_change=change, handoff_value=handoff()))}],
        )
        self.say(project, "帮我定这周计划", script=script)
        plan_out = run(["plan"], cwd=project).stdout
        self.assertIn("进行中（待证据）", plan_out)
        self.assertNotIn("已完成", plan_out)
        status = json.loads(run(["status", "--json"], cwd=project).stdout)
        data = studio(project)
        done = len([step for step in data["plan"]["steps"] if step.get("status") == "done"])
        self.assertEqual(status["plan"]["steps_done"], done)
        self.assertEqual(status["plan"]["steps_done"], 0)
        self.assertEqual(status["plan"]["steps_total"], len(data["plan"]["steps"]))

    def test_pending_plan_change_renders_non_empty_and_hint_uses_its_id(self):
        change = {
            "op": "defer_step",
            "week": 2,
            "step_id": "w2-tools-ex2",
            "detail": "顺延到下次前 20 分钟",
            "reason": "时间不足",
            "status": "proposed",
            "by": "coach",
        }
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, plan_change=change)
        )
        self.say(project, "开始练习", script=script)
        pending = [item for item in studio(project)["plan_changes"] if item["status"] == "proposed"]
        self.assertEqual(len(pending), 1)
        self.assertTrue(pending[0]["detail"])
        self.assertTrue(pending[0]["reason"])
        plan_out = run(["plan"], cwd=project).stdout
        self.assertIn(pending[0]["id"], plan_out)
        self.assertIn("顺延到下次前 20 分钟", plan_out)
        self.assertIn(f"plan --approve {pending[0]['id']}", plan_out)

    def test_op_none_does_not_create_empty_pending_change(self):
        project = self.init()
        change = {
            "op": "none",
            "week": 1,
            "step_id": "w1-agent-loop",
            "detail": "",
            "reason": "",
            "status": "apply",
            "by": "planner",
        }
        script = write_script(
            self.tmp,
            [{"match": "帮我定这周计划", "reply": block(update(plan_change=change, handoff_value=handoff()))}],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.assertEqual(studio(project)["plan_changes"], [])
        self.assertNotIn("待批准", run(["plan"], cwd=project).stdout)

    def test_silent_plan_edit_is_detected(self):
        project = self.init()
        path = project / ".learnark" / "state" / "studio.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["version"] = int(data.get("version") or 0)
        data["plan"]["steps"][0]["text"] = "被静默改掉的步骤"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        (project / ".learnark" / "state" / "studio.json.bak").unlink(missing_ok=True)
        result = run(["doctor", "--plan"], cwd=project)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("plan_authority", result.stdout)
        check = run(["plan", "--check"], cwd=project)
        self.assertEqual(check.returncode, 3)


# ---------------------------------------------------------------------------
# handoff contract
# ---------------------------------------------------------------------------
class HandoffTests(AtelierTestCase):
    def _planner_with(self, handoff_value):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "帮我定这周计划",
                    "reply": block(update(handoff_value=handoff_value), text="交接提案见机器块。"),
                }
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        return project

    def test_strict_incomplete_handoff_is_rejected_without_side_effects(self):
        project = self._planner_with({"known": ["能写 tool schema"]})
        result = self.switch(project, "concept", extra=["--strict"], expect=3)
        self.assertIn("why", result.stdout)
        self.assertEqual(len(handoff_files(project)), 0)
        self.assertEqual(studio(project)["current_mentor"], "planner")
        invalid = events_of(project, "handoff_invalid")
        self.assertEqual(len(invalid), 1)
        self.assertEqual(set(invalid[0]["payload"]["missing"]), {"why", "what_tried", "open_loops", "next"})

    def test_switch_without_mentor_proposal_succeeds_and_composes_everything(self):
        project = self.init()
        result = self.switch(project, "concept")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = latest_handoff_block(project)
        self.assertEqual(payload["from"], "planner")
        self.assertEqual(payload["to"], "concept")
        for field in ("why", "what_tried", "open_loops", "next"):
            self.assertTrue(payload[field], field)
        self.assertTrue((project / ".learnark" / "handoff" / "latest.md").exists())
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertEqual(studio(project)["current_mentor"], "concept")

    def test_fill_missing_degrades_explicitly_under_strict(self):
        project = self._planner_with({"known": ["能写 tool schema"]})
        result = self.switch(project, "concept", extra=["--strict", "--fill-missing"])
        self.assertIn("运行时按记录补齐", result.stdout)
        payload = latest_handoff_block(project)
        self.assertTrue(payload["degraded"])
        self.assertEqual(set(payload["filled"]), {"why", "what_tried", "open_loops", "next"})
        self.assertTrue(events_of(project, "handoff_degraded"))
        check = run(["handoff", "--check"], cwd=project)
        self.assertEqual(check.returncode, 0, check.stdout)

    def test_explicit_do_not_redo_is_capped_and_logged(self):
        project = self.init()
        items = [f"不要重讲第 {index} 个类比" for index in range(8)]
        script = write_script(
            self.tmp,
            [
                {
                    "match": "帮我定这周计划",
                    "reply": block(update(do_not_redo=items, handoff_value=handoff()), text="记下这些不要重做。"),
                }
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "concept")
        payload = latest_handoff_block(project)
        self.assertLessEqual(len(payload["do_not_redo"]), 6)
        self.assertTrue(payload["do_not_redo"])
        self.assertTrue(events_of(project, "handoff_truncated"))

    def test_pause_after_turn_without_proposal_still_writes_complete_handoff(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "先记一下", "reply": block(update(next_="下次继续"))}])
        self.say(project, "先记一下", script=script)
        result = run(["pause"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = latest_handoff_block(project)
        self.assertFalse(payload["degraded"])
        self.assertEqual(payload["from"], payload["to"])
        for field in ("why", "known", "what_tried", "open_loops", "next"):
            self.assertTrue(payload[field], field)
        self.assertIsInstance(payload["do_not_redo"], list)

    def test_pause_empty_session_writes_no_handoff(self):
        project = self.init()
        self.assertEqual(run(["pause"], cwd=project).returncode, 0)
        self.assertEqual(handoff_files(project), [])
        self.assertTrue(events_of(project, "pause_no_handoff"))

    def test_unknown_mentor_exits_two_and_lists_options(self):
        project = self.init()
        result = self.switch(project, "魔法师", expect=2)
        for mentor in MENTORS:
            self.assertIn(mentor, result.stderr)

    def test_handoff_check_detects_corruption(self):
        project = self.init()
        run(["pause"], cwd=project)
        bad = project / ".learnark" / "handoff" / "20260101T000000-planner-to-coach.md"
        bad.write_text("# 没有机器块的交接\n", encoding="utf-8")
        result = run(["handoff", "--check"], cwd=project)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("机器块", result.stdout)

    def test_handoff_why_from_named_mentor(self):
        project, script = self.coach_setup(
            update(help_level=0, activity="w1-agent-loop-ex1", correct=True, handoff_value=handoff(why="交给考核"))
        )
        self.say(project, "开始练习", script=script)
        named_script = write_script(
            self.tmp,
            [
                {
                    "match": "现在让 examiner 考我",
                    "reply": block(
                        update(
                            help_level=0,
                            activity="exam-a",
                            correct=None,
                            verdict={"activity_id": "exam-a", "result": "pending", "basis": "未作答", "rubric": {"correctness": 0, "reasoning": 0, "max": 4, "pass_line": 2}},
                        )
                    ),
                }
            ],
        )
        result = run(["say", "现在让 examiner 考我", "--offline"], cwd=project, script=named_script)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(studio(project)["current_mentor"], "examiner")
        payload = latest_handoff_block(project)
        self.assertIn("用户点名", payload["why"])
        named = events_of(project, "mentor_named")
        self.assertTrue(named)
        self.assertEqual(named[-1]["payload"]["named_by"], "user")


# ---------------------------------------------------------------------------
# context budget, notes, repeat detection
# ---------------------------------------------------------------------------
class ContextTests(AtelierTestCase):
    def test_context_is_bounded_and_uses_handoff_dnr(self):
        project = self.init()
        entries = [
            {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
            {
                "match": "讲个概念",
                "reply": block(
                    update(
                        help_level=2,
                        next_="复述一遍",
                        analogy="检索是现查现用",
                        do_not_redo=["不要重讲「现查现用 / 写下来下次还在」这个类比"],
                        handoff_value=handoff(why="概念讲完，交给教练做练习", next_="动手做三栏标注"),
                    ),
                    text="检索是现查现用，记忆是写下来下次还在。",
                ),
            },
        ]
        for index in range(1, 9):
            entries.append(
                {
                    "match": f"coach-turn-{index}",
                    "reply": block(update(help_level=1, next_=f"下一小步 {index}"), text=f"第 {index} 次提示。"),
                }
            )
        entries.append(
            {
                "match": "回到教练",
                "reply": block(
                    update(help_level=0, activity="w1-agent-loop-ex1", correct=True, handoff_value=handoff(why="回到练习", next_="继续练习")),
                    text="继续。",
                ),
            }
        )
        script = write_script(self.tmp, entries)
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "concept")
        self.say(project, "讲个概念", script=script)
        self.switch(project, "coach")
        for index in range(1, 9):
            self.say(project, f"coach-turn-{index}", script=script)
        self.say(project, "回到教练", script=script)
        manifests = [event["payload"] for event in events_of(project, "context_manifest") if event["payload"]["mentor"] == "coach"]
        self.assertTrue(manifests)
        for manifest in manifests:
            self.assertLessEqual(manifest["chars"], 6000)
            self.assertNotIn("journal/full", manifest["sources"])
            for other in ("concept", "examiner", "planner", "reviewer"):
                self.assertNotIn(f"state/mentors/{other}.json", manifest["sources"])
        first_coach = manifests[0]
        self.assertIn("handoff/do_not_redo", first_coach["sources"])
        self.assertIn("handoff/latest", first_coach["sources"])
        self.assertTrue(first_coach["handoff_id"])
        self.assertLessEqual(manifests[-1]["chars"], max(1800, int(first_coach["chars"] * 1.4)))

    def test_long_what_tried_is_cut_on_a_boundary(self):
        project = self.init()
        long_activity = "w1-agent-loop-ex1" + "（第一段说明。第二段说明。第三段说明。第四段说明。第五段说明。）" * 3
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {
                    "match": "开始练习",
                    "reply": block(
                        update(help_level=1, activity=long_activity, correct=None),
                        text="记录一次练习。",
                    ),
                },
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "coach")
        self.say(project, "开始练习", script=script)
        self.assertEqual(run(["pause"], cwd=project).returncode, 0)
        payload = latest_handoff_block(project)
        item = next(item for item in payload["what_tried"] if "第一段说明" in item)
        self.assertLessEqual(len(item), 120)
        self.assertTrue(item.endswith("…"))
        self.assertIn(item[-2], "。；，、 ")
        self.assertTrue(events_of(project, "handoff_truncated"))

    def test_prompt_forbids_inventing_history_and_context_has_no_fake_error(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [{"match": "帮我定这周计划", "reply": block(update(next_="继续"))}],
        )
        self.say(project, "帮我定这周计划", script=script)
        sys.path.insert(0, str(ROOT / "runtime"))
        from atelier.context import build_context, system_prompt
        from atelier import state as st
        from atelier.handoff import latest_handoff_payload

        self.assertIn("不要虚构", system_prompt("coach"))
        paths = st.open_paths(str(project))
        context = build_context(
            paths,
            st.project_doc(paths).load(),
            st.studio_doc(paths).load(),
            st.capability_doc(paths).load(),
            "coach",
            latest_handoff_payload(paths),
        )
        self.assertNotIn("报错", context["text"])

    def test_private_notes_stay_short(self):
        project, script = self.coach_setup()
        for index in range(1, 11):
            self.say(project, f"coach-turn-{index}", script=script)
        notes = json.loads((project / ".learnark" / "state" / "mentors" / "coach.json").read_text(encoding="utf-8"))
        self.assertLessEqual(len(notes["notes"]), 8)
        self.assertEqual(notes["turns"], 10)
        self.assertTrue(notes["taught"])

    def test_repeat_detection_for_analogy_and_activity(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "帮我定这周计划", "reply": block(update(handoff_value=handoff()))},
                {
                    "match": "讲概念",
                    "reply": block(
                        update(help_level=2, next_="复述", analogy="现查现用的检索", handoff_value=handoff(why="交给教练", next_="动手")),
                        text="检索是现查现用。",
                    ),
                },
                {
                    "match": "开始练习",
                    "reply": block(
                        update(help_level=1, activity="w1-agent-loop-ex1", correct=False, analogy="现查现用的检索", misconception="混淆检索与记忆"),
                        text="再想一次。",
                    ),
                },
            ],
        )
        self.say(project, "帮我定这周计划", script=script)
        self.switch(project, "concept")
        self.say(project, "讲概念", script=script)
        self.switch(project, "coach")
        self.say(project, "开始练习", script=script)
        repeats = events_of(project, "repeat_detected")
        self.assertTrue(repeats)
        self.assertEqual(repeats[-1]["payload"]["kind"], "analogy")


# ---------------------------------------------------------------------------
# git, export, doctor
# ---------------------------------------------------------------------------
class GitTests(AtelierTestCase):
    def _diverged_clones(self):
        project = self.init()
        remote = self.tmp / "remote-div.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=project, check=True)
        first = run(["sync"], cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        clone = self.tmp / "clone-div"
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
        return project, remote, clone

    def test_sync_to_bare_remote_and_clone(self):
        project = self.init()
        run(["pause"], cwd=project)
        remote = self.tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=project, check=True)
        result = run(["sync"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pushed=yes", result.stdout)
        clone = self.tmp / "clone"
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
        status = run(["status", "--json", "--project", str(clone)], cwd=self.tmp)
        self.assertEqual(status.returncode, 0, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["project"]["slug"], "proj")
        self.assertTrue(payload["plan"]["version"] >= 1)

    def test_two_syncs_with_modified_tracked_file(self):
        """Regression for core 1.0.1: porcelain rows keep their leading status space."""
        project = self.init()
        remote = self.tmp / "remote2.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=project, check=True)
        first = run(["sync"], cwd=project)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("pushed=yes", first.stdout)
        note = project / "artifacts" / "note.md"
        note.write_text("v1\n", encoding="utf-8")
        second = run(["sync"], cwd=project)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn("committed=yes", second.stdout)
        self.assertIn("pushed=yes", second.stdout)
        note.write_text("v2\n", encoding="utf-8")
        third = run(["sync"], cwd=project)
        self.assertEqual(third.returncode, 0, third.stderr)
        self.assertIn("committed=yes", third.stdout)
        self.assertIn("pushed=yes", third.stdout)
        clone = self.tmp / "clone2"
        subprocess.run(["git", "clone", "-q", str(remote), str(clone)], check=True)
        self.assertEqual((clone / "artifacts" / "note.md").read_text(encoding="utf-8"), "v2\n")

    def _state_diverged_clones(self):
        project, remote, clone = self._diverged_clones()
        script = write_script(
            self.tmp,
            [
                {"match": "A 端事件", "reply": block(update(next_="A 端继续", handoff_value=handoff()))},
                {"match": "B 端事件", "reply": block(update(next_="B 端继续", handoff_value=handoff()))},
            ],
        )
        self.say(project, "A 端事件", script=script)
        self.assertEqual(run(["sync"], cwd=project).returncode, 0)
        self.say(clone, "B 端事件", script=script)
        return project, remote, clone

    def test_recover_prefer_local_keeps_local_state_and_both_journals(self):
        project, remote, clone = self._state_diverged_clones()
        conflict = run(["sync"], cwd=clone)
        self.assertEqual(conflict.returncode, 3, conflict.stdout + conflict.stderr)
        result = run(["sync", "--recover", "--prefer", "local"], cwd=clone)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pushed=yes", result.stdout)
        self.assertIn("恢复选择：local", result.stdout)
        self.assertIn("studio.json", result.stdout)
        session_text = (clone / ".learnark" / "state" / "session.json").read_text(encoding="utf-8")
        self.assertIn("B 端事件", session_text)
        choices = events_of(clone, "recover_choice")
        self.assertTrue(choices)
        self.assertEqual(choices[-1]["payload"]["prefer"], "local")
        final = self.tmp / "final-local"
        subprocess.run(["git", "clone", "-q", str(remote), str(final)], check=True)
        self.assertGreaterEqual(len(events_of(final, "say_attempt")), 2)
        self.assertEqual(len(events_of(final, "recover_choice")), 1)

    def test_recover_prefer_remote_takes_remote_state_and_keeps_journal(self):
        project, remote, clone = self._state_diverged_clones()
        self.assertEqual(run(["sync"], cwd=clone).returncode, 3)
        result = run(["sync", "--recover", "--prefer", "remote"], cwd=clone)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pushed=yes", result.stdout)
        self.assertIn("恢复选择：remote", result.stdout)
        self.assertIn("studio.json", result.stdout)
        session_text = (clone / ".learnark" / "state" / "session.json").read_text(encoding="utf-8")
        self.assertIn("A 端事件", session_text)
        choices = events_of(clone, "recover_choice")
        self.assertTrue(choices)
        self.assertEqual(choices[-1]["payload"]["prefer"], "remote")
        final = self.tmp / "final-remote"
        subprocess.run(["git", "clone", "-q", str(remote), str(final)], check=True)
        self.assertGreaterEqual(len(events_of(final, "say_attempt")), 2)

    def test_two_clone_journal_divergence_is_union_merged(self):
        project, remote, clone = self._diverged_clones()
        script = write_script(
            self.tmp,
            [
                {"match": "A 端事件", "reply": block(update(next_="A 端继续", handoff_value=handoff()))},
                {"match": "B 端事件", "reply": block(update(next_="B 端继续", handoff_value=handoff()))},
            ],
        )
        self.say(project, "A 端事件", script=script)
        self.assertEqual(run(["sync"], cwd=project).returncode, 0)
        self.say(clone, "B 端事件", script=script)
        # Keep only journal changes on B: snapshots/sessions are state conflicts.
        subprocess.run(["git", "checkout", "--", ".learnark/state"], cwd=clone, check=True)
        subprocess.run(["git", "clean", "-fdq", "sessions"], cwd=clone, check=True)
        merged = run(["sync"], cwd=clone)
        self.assertEqual(merged.returncode, 0, merged.stdout + merged.stderr)
        self.assertIn("pushed=yes", merged.stdout)
        final = self.tmp / "final-div"
        subprocess.run(["git", "clone", "-q", str(remote), str(final)], check=True)
        attempts = events_of(final, "say_attempt")
        self.assertGreaterEqual(len(attempts), 2)
        self.assertGreaterEqual(len({event["payload"]["attempt_id"] for event in attempts}), 2)
        recovered = run(["sync", "--recover", "--prefer", "local"], cwd=final)
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertIn("recover", recovered.stdout)

    def test_snapshot_conflict_exits_three_and_doctor_flags_diverged(self):
        project, remote, clone = self._diverged_clones()
        script = write_script(
            self.tmp,
            [
                {"match": "A 端事件", "reply": block(update(next_="A 端继续", handoff_value=handoff()))},
                {"match": "B 端事件", "reply": block(update(next_="B 端继续", handoff_value=handoff()))},
            ],
        )
        self.say(project, "A 端事件", script=script)
        self.assertEqual(run(["sync"], cwd=project).returncode, 0)
        self.say(clone, "B 端事件", script=script)
        conflict = run(["sync"], cwd=clone)
        self.assertEqual(conflict.returncode, 3, conflict.stdout + conflict.stderr)
        self.assertIn("studio.json", conflict.stdout)
        recover = run(["sync", "--recover"], cwd=clone)
        self.assertEqual(recover.returncode, 3, recover.stdout + recover.stderr)
        self.assertIn("studio.json", recover.stdout)
        self.assertIn("written=no", recover.stdout)
        self.assertIn("branch=master", recover.stdout)
        self.assertNotIn("remote=（无）", recover.stdout)
        status = json.loads(run(["status", "--json"], cwd=clone).stdout)
        self.assertTrue(status["sync"]["diverged"])
        doctor = run(["doctor"], cwd=clone)
        self.assertEqual(doctor.returncode, 3, doctor.stdout)
        self.assertIn("diverged=True", doctor.stdout)

    def test_pause_leaves_git_tree_clean_with_remote(self):
        project = self.init()
        remote = self.tmp / "remote-clean.git"
        subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
        subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=project, check=True)
        self.assertEqual(run(["sync"], cwd=project).returncode, 0)
        script = write_script(self.tmp, [{"match": "保存一下", "reply": block(update(next_="下次继续"))}])
        self.say(project, "保存一下", script=script)
        pause = run(["pause"], cwd=project)
        self.assertEqual(pause.returncode, 0, pause.stdout + pause.stderr)
        self.assertIn("committed=yes", pause.stdout)
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=project, capture_output=True, text=True, encoding="utf-8"
        )
        self.assertEqual(status.stdout.strip(), "", status.stdout)

    def test_sync_without_remote_reports_honestly(self):
        project = self.init()
        result = run(["sync"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pushed=no", result.stdout)
        self.assertIn("written=yes", result.stdout)
        self.assertIn("（无）", result.stdout)


class DoctorTests(AtelierTestCase):
    def test_healthy_project_passes(self):
        project = self.init()
        run(["pause"], cwd=project)
        result = run(["doctor"], cwd=project)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("未发现问题", result.stdout)

    def test_doctor_reports_missing_handoff_after_turns(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "帮我定这周计划", "reply": block(update())}])
        self.say(project, "帮我定这周计划", script=script)
        result = run(["doctor"], cwd=project)
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("handoff_present", result.stdout)


class ExportTests(AtelierTestCase):
    def test_export_contains_evidence_and_honesty_note(self):
        project, script = self.coach_setup()
        self.say(project, "开始练习", script=script)
        out = self.tmp / "archive.md"
        result = run(["export", "--out", str(out)], cwd=project)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = out.read_text(encoding="utf-8")
        self.assertIn("synthetic", text)
        self.assertIn("能力证据", text)
        self.assertIn("计划", text)
        self.assertNotIn("sk-", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)

