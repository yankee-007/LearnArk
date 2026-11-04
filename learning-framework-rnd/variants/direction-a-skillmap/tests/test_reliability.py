#!/usr/bin/env python3
"""D-Reliability suite for SkillMap (direction A).

Standalone ``unittest`` suite: standard library only, deterministic mock mentor,
no network, one fresh temporary project per test.  It drives the *real* CLI as a
subprocess for state/journal/lock/git behaviour and uses ``learncore``'s CAS
primitives directly where a document-level assertion is clearer.

What is covered (see ``experiments/CP2-reliability.md`` for the matrix):

* interrupted / torn state — truncated snapshots, torn journal tail, ``.bak``
  recovery, stale lock files, clear failure when no backup exists;
* duplicate saves — replayed command checkpoint, duplicate attempts, duplicate
  pause / start / sync openings;
* concurrency — three processes writing at once, plus a held lock that must
  produce the documented exit-3 conflict instead of hanging;
* stale writes — ``Document`` CAS and the command-level stale-write message;
* git — journal-only divergence union merge, snapshot conflict exit 3 with the
  real file list, no force push, no secrets/locks committed, clean-clone resume;
* simulated clock — ``LEARNARK_NOW`` review scheduling with ``simulated`` events.

Run:  python tests/test_reliability.py [-v]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "runtime" / "learn.py"
RUNTIME = ROOT / "runtime"
DEFAULT_SCRIPT = ROOT / "tests" / "fixtures" / "mentor_script.jsonl"

if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from learncore.fsutil import StaleWrite, file_lock  # noqa: E402
from learncore.store import Document  # noqa: E402

GIT = shutil.which("git") is not None
GIT_SKIP = unittest.skipUnless(GIT, "git is required for this reliability test")


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def upd(
    *,
    help_level: int = 0,
    activity: str = "A1-explain",
    correct=None,
    misconception=None,
    next_text: str = "继续",
    mastery: int = 0,
    artifact=None,
    probe=None,
    diagnosis=None,
) -> dict:
    """A ``learn-update`` machine block, mirroring the mentor protocol."""
    return {
        "help_level": help_level,
        "attempt": {"activity_id": activity, "correct": correct},
        "probe": probe,
        "misconception": misconception,
        "next": next_text,
        "mastery_delta": mastery,
        "artifact": artifact,
        "diagnosis": diagnosis,
    }


def read_jsonl(path: Path) -> list[dict]:
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


class ReliabilityBase(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="skillmap-rel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.project = self.tmp / "proj"

    # -- environment -----------------------------------------------------
    def env(self, *, now: str | None = None, script: Path | None = None, extra: dict | None = None) -> dict:
        env = dict(os.environ)
        env.update({"LEARNARK_LLM": "mock", "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        for key in (
            "LEARNARK_NOW",
            "LEARNARK_PROJECT",
            "LEARNARK_MOCK_SCRIPT",
            "LEARNARK_LOCK_TIMEOUT",
            "DEEPSEEK_API_KEY",
            "LEARNARK_API_KEY",
        ):
            env.pop(key, None)
        env["LEARNARK_MOCK_SCRIPT"] = str(script or DEFAULT_SCRIPT)
        if now:
            env["LEARNARK_NOW"] = now
        env.update(extra or {})
        return env

    # -- CLI -------------------------------------------------------------
    def learn(
        self,
        args,
        *,
        expect=0,
        now: str | None = None,
        script: Path | None = None,
        extra: dict | None = None,
        cwd: Path | None = None,
        timeout: int = 180,
    ) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            [sys.executable, str(ENTRY), *[str(item) for item in args]],
            cwd=str(cwd or ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=self.env(now=now, script=script, extra=extra),
            timeout=timeout,
        )
        if expect is not None and proc.returncode != expect:
            self.fail(
                "`learn %s` -> exit %s (expected %s)\nstdout:\n%s\nstderr:\n%s"
                % (" ".join(str(a) for a in args), proc.returncode, expect, proc.stdout[-4000:], proc.stderr[-2000:])
            )
        return proc

    def run_json(self, args, **kwargs) -> dict:
        proc = self.learn([*args, "--json"], **kwargs)
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            self.fail(f"`learn {args} --json` did not return JSON: {exc}\n{proc.stdout[:3000]}\n{proc.stderr[:1000]}")

    # -- project scaffolding ---------------------------------------------
    def init(
        self,
        name: str = "proj",
        *,
        template: str = "agent-dev",
        goal: str = "可靠性测试：能独立设计与实现最小可用 Agent",
        now: str | None = None,
    ) -> Path:
        project = self.tmp / name
        self.learn(["init", "--goal", goal, "--dir", project, "--template", template], now=now)
        self.assertTrue((project / ".learnark" / "project.json").is_file())
        return project

    def skip_diagnosis(self, project: Path, *, now: str | None = None) -> None:
        self.learn(["diagnose", "--skip", "--project", project], now=now, expect=0)

    def start(self, project: Path, *extra_args, now: str | None = None, script: Path | None = None):
        return self.learn(["start", "--project", project, *extra_args], now=now, script=script, expect=0)

    # -- paths / state ---------------------------------------------------
    def journal_path(self, project: Path) -> Path:
        return project / ".learnark" / "journal" / "events.jsonl"

    def dedupe_path(self, project: Path) -> Path:
        return project / ".learnark" / "journal" / "dedupe.json"

    def map_path(self, project: Path) -> Path:
        return project / ".learnark" / "state" / "map.json"

    def plan_path(self, project: Path) -> Path:
        return project / ".learnark" / "state" / "plan.json"

    def read_json(self, path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def journal(self, project: Path) -> list[dict]:
        return read_jsonl(self.journal_path(project))

    def of_kind(self, project: Path, *kinds: str) -> list[dict]:
        wanted = set(kinds)
        return [event for event in self.journal(project) if event.get("kind") in wanted]

    def node(self, project: Path, node_id: str) -> dict:
        return next(node for node in self.read_json(self.map_path(project))["nodes"] if node["id"] == node_id)

    def edit_node(self, project: Path, node_id: str, **changes) -> None:
        data = self.read_json(self.map_path(project))
        for node in data["nodes"]:
            if node["id"] == node_id:
                node.update(changes)
        self.write_json(self.map_path(project), data)

    def force_stage(self, project: Path, node_id: str, stage: str, *, level: int | None = None) -> None:
        if level is not None:
            self.edit_node(project, node_id, level=level, level_source="test")
        data = self.read_json(self.plan_path(project))
        data.update(
            {
                "mode": "stage",
                "current_node": node_id,
                "stage": stage,
                "stage_progress": {"node": node_id, "stage": stage, "passed": False},
                "mentor_override": None,
            }
        )
        self.write_json(self.plan_path(project), data)

    def make_script(self, entries, *, name: str | None = None) -> Path:
        """Write a mock mentor script from ``(match, visible_text, update)``."""
        path = self.tmp / (name or f"script-{len(list(self.tmp.glob('script-*.jsonl')))}.jsonl")
        lines = []
        for match, text, update in entries:
            reply = text
            if update is not None:
                reply += "\n```learn-update\n" + json.dumps(update, ensure_ascii=False) + "\n```"
            lines.append(json.dumps({"match": match, "reply": reply}, ensure_ascii=False))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        return path

    # -- git -------------------------------------------------------------
    def git(self, cwd: Path, *args: str, expect=0) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if expect is not None and proc.returncode != expect:
            self.fail(f"git {' '.join(args)} -> {proc.returncode} (expected {expect})\n{proc.stderr}")
        return proc.stdout.strip()

    def make_remote(self, name: str = "remote.git") -> Path:
        bare = self.tmp / name
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, capture_output=True)
        return bare

    def clone(self, remote: Path, name: str, branch: str | None = None) -> Path:
        """Clone a local bare remote (``branch`` avoids init.defaultBranch drift)."""
        target = self.tmp / name
        args = ["git", "clone", "-q"]
        if branch:
            args += ["-b", branch]
        args += [str(remote), str(target)]
        subprocess.run(args, check=True, capture_output=True)
        self.git(target, "config", "user.name", "Test")
        self.git(target, "config", "user.email", "test@local")
        return target

    def git_commit_all(self, project: Path, message: str) -> None:
        self.git(project, "add", "-A")
        self.git(project, "-c", "user.name=Test", "-c", "user.email=test@local", "commit", "-q", "-m", message)

    def branch(self, project: Path) -> str:
        return self.git(project, "rev-parse", "--abbrev-ref", "HEAD")

    def append_journal_event(self, project: Path, event_id: str, at: str) -> None:
        events = self.journal(project)
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
        with self.journal_path(project).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 1. interrupted / torn state
# ---------------------------------------------------------------------------
class TornStateTests(ReliabilityBase):
    def test_truncated_map_snapshot_recovers_levels_from_bak(self) -> None:
        """A half-written map.json is restored from .bak; levels are not reset."""
        project = self.init()
        self.skip_diagnosis(project)
        map_path = self.map_path(project)
        data = self.read_json(map_path)
        for node in data["nodes"]:
            if node["id"] == "A1":
                node["level"] = 2
                node["level_source"] = "test"
        self.write_json(map_path, data)

        # A real command persists the snapshot (+ .bak) through the normal path.
        self.start(project)
        self.assertEqual(self.node(project, "A1")["level"], 2)
        self.assertTrue(map_path.with_name("map.json.bak").is_file())

        raw = map_path.read_text(encoding="utf-8")
        self.assertGreater(len(raw), 200)
        map_path.write_text(raw[: len(raw) // 2], encoding="utf-8")

        payload = self.run_json(["status", "--project", project])
        self.assertEqual(self.node(project, "A1")["level"], 2, "levels were silently lost")
        self.assertEqual(len(self.read_json(map_path)["nodes"]), 12)
        self.assertTrue(payload["repairs"], "a .bak recovery must be reported")
        self.assertTrue(any("map.json" in note and "recovered" in note for note in payload["repairs"]), payload["repairs"])
        self.learn(["doctor", "--project", project], expect=0)

    def test_missing_map_snapshot_recovers_levels_from_bak(self) -> None:
        """A lost (not merely truncated) map.json is restored from .bak."""
        project = self.init()
        self.skip_diagnosis(project)
        map_path = self.map_path(project)
        data = self.read_json(map_path)
        for node in data["nodes"]:
            if node["id"] == "A1":
                node["level"] = 2
                node["level_source"] = "test"
        self.write_json(map_path, data)
        self.start(project)
        self.assertEqual(self.node(project, "A1")["level"], 2)
        backup = map_path.with_name("map.json.bak")
        self.assertTrue(backup.is_file(), "a .bak snapshot should exist after a normal save")
        map_path.unlink()

        payload = self.run_json(["status", "--project", project])
        self.assertEqual(self.node(project, "A1")["level"], 2, "levels were lost when map.json was missing")
        self.assertEqual(len(self.read_json(map_path)["nodes"]), 12)
        self.assertTrue(any("map.json" in note and "恢复" in note for note in payload["repairs"]), payload["repairs"])
        self.learn(["doctor", "--project", project], expect=0)

    def test_missing_map_in_email_project_rebuilds_writing_map(self) -> None:
        """Rebuilding a lost map must use the project's template, not agent-dev."""
        project = self.init(template="email", goal="能写出可直接发送的英文工作邮件")
        self.skip_diagnosis(project)
        map_path = self.map_path(project)
        map_path.unlink()
        map_path.with_name("map.json.bak").unlink(missing_ok=True)

        payload = self.run_json(["status", "--project", project])
        ids = [node["id"] for node in payload["map"]["nodes"]]
        self.assertEqual(ids, ["W1", "W6", "W2", "W3", "W4", "W5"], "the rebuilt map used the wrong template")
        self.assertTrue(any("重建" in note for note in payload["repairs"]), payload["repairs"])

    def test_truncated_plan_snapshot_recovers_next_step(self) -> None:
        """A half-written plan.json is restored; the next step survives."""
        project = self.init()
        self.skip_diagnosis(project)
        self.start(project, "--minutes", "20")
        plan_path = self.plan_path(project)
        before = self.read_json(plan_path)
        self.assertEqual(before["current_node"], "A1")
        self.assertEqual(before["minutes_budget"], 20)

        raw = plan_path.read_text(encoding="utf-8")
        plan_path.write_text(raw[: len(raw) // 3], encoding="utf-8")

        payload = self.run_json(["status", "--project", project])
        self.assertTrue(payload["repairs"], payload["repairs"])
        plan = self.read_json(plan_path)
        self.assertEqual(plan["current_node"], "A1")
        self.assertEqual(plan["stage"], "explain")
        self.assertEqual(plan["minutes_budget"], 20)
        self.learn(["start", "--project", project], expect=0)

    def test_corrupt_snapshot_without_backup_fails_clearly(self) -> None:
        """With no usable .bak the CLI must say what is broken and not overwrite."""
        project = self.init()
        self.skip_diagnosis(project)
        map_path = self.map_path(project)
        map_path.write_text("{ this is not json", encoding="utf-8")
        map_path.with_name("map.json.bak").unlink(missing_ok=True)

        proc = self.learn(["status", "--project", project], expect=3)
        combined = proc.stdout + proc.stderr
        self.assertIn("map.json", combined)
        self.assertIn("not valid JSON", combined)
        self.assertEqual(map_path.read_text(encoding="utf-8"), "{ this is not json")

    def test_torn_journal_tail_is_repaired_before_append(self) -> None:
        """A torn tail is dropped, reported, and the next append stays valid."""
        project = self.init()
        self.skip_diagnosis(project)
        journal_path = self.journal_path(project)
        before = len(self.journal(project))
        last_event_id = self.journal(project)[-1]["id"]
        raw = journal_path.read_text(encoding="utf-8").rstrip("\n")
        self.assertGreater(len(raw), 80)
        journal_path.write_text(raw[:-45], encoding="utf-8")  # cut inside the last event

        payload = self.run_json(["status", "--project", project])
        self.assertTrue(payload["journal"]["events"] >= before - 1, payload["journal"])
        self.assertTrue(any("journal" in note for note in payload["repairs"]), payload["repairs"])
        repaired = self.journal(project)
        self.assertNotIn(last_event_id, {event["id"] for event in repaired}, "the torn event must be dropped")

        self.start(project)
        script = self.make_script([("尾行修复后继续", "记录收到。", upd(activity="A1-explain", correct=None))])
        self.learn(["say", "尾行修复后继续", "--project", project], script=script, expect=0)

        events = self.journal(project)
        self.assertGreaterEqual(len(events), len(repaired))
        for event in events:
            self.assertIn("kind", event)
            self.assertIn("id", event)
        self.learn(["status", "--project", project], expect=0)
        self.learn(["doctor", "--project", project], expect=0)

    def test_missing_trailing_newline_keeps_events_and_append_is_safe(self) -> None:
        """A complete last event without a newline must be kept, not merged."""
        project = self.init()
        self.skip_diagnosis(project)
        journal_path = self.journal_path(project)
        before = len(self.journal(project))
        before_ids = {event["id"] for event in self.journal(project)}
        raw = journal_path.read_text(encoding="utf-8").rstrip("\n")
        journal_path.write_text(raw, encoding="utf-8")

        payload = self.run_json(["status", "--project", project])
        self.assertTrue(payload["journal"]["events"] >= before, "a complete event was dropped")
        self.assertTrue(before_ids <= {event["id"] for event in self.journal(project)})

        script = self.make_script([("缺换行之后", "记录。", upd(activity="A1-explain", correct=None))])
        self.learn(["say", "缺换行之后", "--project", project], script=script, expect=0)

        events = self.journal(project)
        self.assertGreater(len(events), before)
        for event in events:
            self.assertIn("kind", event)
        self.assertEqual(events[-1]["payload"].get("learner_text"), "缺换行之后")

    def test_mid_journal_corruption_fails_loudly(self) -> None:
        """Only a torn *tail* is tolerable; damage in the middle must be reported."""
        project = self.init()
        self.skip_diagnosis(project)
        journal_path = self.journal_path(project)
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        self.assertGreater(len(lines), 3)
        lines.insert(2, "this is not json")
        journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        proc = self.learn(["status", "--project", project], expect=3)
        combined = proc.stdout + proc.stderr
        self.assertIn("not valid JSON", combined)
        self.assertIn("line 3", combined)

    def test_stale_lock_files_do_not_block_commands(self) -> None:
        """Leftover lock files (no live owner) must not lock the project out."""
        project = self.init()
        self.skip_diagnosis(project)
        self.start(project)
        stale = "pid=999999 at=0.000\n"
        for rel in (
            ".learnark/project.lock",
            ".learnark/state/state.lock",
            ".learnark/journal/journal.lock",
        ):
            path = project / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(stale, encoding="utf-8")

        self.start(project)
        script = self.make_script([("锁残留后照常写入", "记录。", upd(activity="A1-explain", correct=None))])
        said = self.learn(["say", "锁残留后照常写入", "--project", project], script=script, expect=0)
        self.assertIn("记录", said.stdout)
        self.learn(["status", "--project", project], expect=0)
        self.learn(["doctor", "--project", project], expect=0)


# ---------------------------------------------------------------------------
# 2. duplicate saves / idempotency
# ---------------------------------------------------------------------------
class DuplicateSaveTests(ReliabilityBase):
    def test_replay_after_lost_plan_checkpoint_is_idempotent(self) -> None:
        """A crash after the journal append but before the plan save must not redo."""
        project = self.init()
        self.skip_diagnosis(project)
        self.start(project)
        plan_path = self.plan_path(project)
        checkpoint = plan_path.read_bytes()
        script = self.make_script(
            [("同一答案", "复述到位。", upd(activity="A1-explain", correct=True, help_level=1))]
        )
        self.learn(["say", "同一答案", "--project", project], script=script, expect=0)
        self.assertEqual(self.node(project, "A1")["level"], 1)
        self.assertEqual(len(self.of_kind(project, "attempt")), 1)
        self.assertEqual(len(self.of_kind(project, "level_up")), 1)

        # Simulate "process killed after journal append, before plan checkpoint".
        plan_path.write_bytes(checkpoint)
        replay = self.learn(["say", "同一答案", "--project", project], script=script, expect=0)
        self.assertIn("已记录", replay.stdout)
        self.assertEqual(len(self.of_kind(project, "attempt")), 1, "a replay must not add an attempt")
        self.assertEqual(len(self.of_kind(project, "level_up")), 1, "a replay must not raise a level")
        self.assertEqual(self.node(project, "A1")["level"], 1)
        self.assertEqual(len(self.of_kind(project, "mentor_turn")), 1)
        session = next((project / "sessions").glob("*.md"))
        self.assertEqual(session.read_text(encoding="utf-8").count("## 学习者"), 1)

    def test_same_drill_answer_never_passes_twice(self) -> None:
        """Repeating one correct drill answer cannot fake the 2-streak rule."""
        project = self.init()
        self.skip_diagnosis(project)
        self.force_stage(project, "A1", "drill", level=1)
        script = self.make_script(
            [("同一道题", "对的。", upd(activity="A1-drill", correct=True, help_level=0))]
        )
        for _ in range(3):
            self.learn(["say", "同一道题", "--project", project], script=script, expect=0)

        attempts = [event for event in self.of_kind(project, "attempt") if event["payload"].get("activity_id") == "A1-drill"]
        self.assertEqual(len(attempts), 1, "the same answer was counted more than once")
        plan = self.read_json(self.plan_path(project))
        self.assertEqual(plan["stage"], "drill", "a replayed answer advanced the stage")
        self.assertEqual(int(plan["stage_progress"].get("drill_streak") or 0), 1)
        self.assertEqual(self.node(project, "A1")["level"], 1)

    def test_duplicate_pause_writes_one_handoff(self) -> None:
        project = self.init()
        self.skip_diagnosis(project)
        self.start(project)
        self.learn(["pause", "--project", project], expect=0)
        second = self.learn(["pause", "--project", project], expect=0)
        self.assertEqual(len(self.of_kind(project, "handoff")), 1)
        self.assertIn("已存在", second.stdout)
        self.assertEqual(len(list((project / ".learnark" / "handoff").glob("*.md"))), 2)  # latest + 1 archive

    def test_repeated_start_does_not_duplicate_session_opening(self) -> None:
        """`start` is idempotent: no session block without a matching event."""
        project = self.init()
        self.skip_diagnosis(project)
        for _ in range(3):
            self.start(project)
        sessions = list((project / "sessions").glob("*.md"))
        self.assertEqual(len(sessions), 1, sessions)
        text = sessions[0].read_text(encoding="utf-8")
        opened = self.of_kind(project, "session_opened")
        self.assertEqual(len(opened), 2, [event["payload"].get("trigger") for event in opened])
        self.assertEqual(text.count("## 系统"), len(opened), "a duplicated opening exists in the session file")


# ---------------------------------------------------------------------------
# 3. concurrency / locks
# ---------------------------------------------------------------------------
class ConcurrencyTests(ReliabilityBase):
    def test_two_processes_writing_are_serialised(self) -> None:
        """Three simultaneous writers: no lost events, no double counting."""
        project = self.init()
        self.skip_diagnosis(project)
        self.start(project)
        script = self.make_script(
            [
                ("并发甲", "甲记录。", upd(activity="A1-explain", correct=None)),
                ("并发乙", "乙记录。", upd(activity="A1-explain", correct=None)),
                ("并发丙", "丙记录。", upd(activity="A1-explain", correct=None)),
            ]
        )
        env = self.env(script=script)
        procs = []
        for text in ("并发甲", "并发乙", "并发丙"):
            procs.append(
                subprocess.Popen(
                    [sys.executable, str(ENTRY), "say", text, "--project", str(project)],
                    cwd=str(ROOT),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            )
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=180)
            results.append((proc.returncode, out, err))
        self.assertEqual([item[0] for item in results], [0, 0, 0], results)

        turns = self.of_kind(project, "mentor_turn")
        self.assertEqual(len(turns), 3, [(e["payload"].get("turn_index"), e["payload"].get("learner_text")) for e in turns])
        self.assertEqual(sorted(event["payload"]["turn_index"] for event in turns), [1, 2, 3])
        self.assertEqual(len(self.of_kind(project, "attempt")), 0, "correct=null turns must not create attempts")
        self.assertEqual(self.node(project, "A1")["level"], 0)
        self.assertEqual(int(self.read_json(self.plan_path(project))["turn_index"]), 3)

        session = next((project / "sessions").glob("*.md"))
        self.assertEqual(session.read_text(encoding="utf-8").count("## 学习者"), 3)
        keys = [event.get("dedupe_key") for event in self.journal(project) if event.get("dedupe_key")]
        self.assertEqual(len(keys), len(set(keys)), "duplicate dedupe keys in journal")
        self.learn(["doctor", "--project", project], expect=0)

    def test_held_lock_reports_conflict_exit_3(self) -> None:
        """A lock held by another process = clear exit-3 conflict, not a silent wait."""
        project = self.init()
        self.skip_diagnosis(project)
        self.start(project)
        journal_before = len(self.journal(project))

        with file_lock(project / ".learnark" / "project.lock", timeout=5):
            proc = self.learn(
                ["say", "被锁住的回答", "--project", project],
                expect=3,
                extra={"LEARNARK_LOCK_TIMEOUT": "0.3"},
                timeout=60,
            )
        combined = proc.stdout + proc.stderr
        self.assertIn("another LearnArk process", combined)
        self.assertIn("state changed concurrently", combined)
        self.assertEqual(len(self.journal(project)), journal_before, "a blocked command must not write")
        self.assertNotIn("被锁住的回答", json.dumps(self.journal(project), ensure_ascii=False))

        script = self.make_script([("锁已释放", "记录。", upd(activity="A1-explain", correct=None))])
        self.learn(["say", "锁已释放", "--project", project], script=script, expect=0)
        self.assertGreater(len(self.journal(project)), journal_before)


# ---------------------------------------------------------------------------
# 4. stale writes (CAS)
# ---------------------------------------------------------------------------
class StaleWriteTests(ReliabilityBase):
    def test_document_cas_rejects_stale_write(self) -> None:
        path = self.tmp / "doc.json"
        doc = Document(path, dict)
        self.assertEqual(doc.load().get("version"), 0)
        saved = doc.save({"value": "first"}, expected_version=0)
        self.assertEqual(saved["version"], 1)

        stale = doc.load()
        stale["value"] = "silent-overwrite"
        with self.assertRaises(StaleWrite):
            doc.save(stale, expected_version=0)

        on_disk = self.read_json(path)
        self.assertEqual(on_disk["value"], "first", "a stale writer overwrote newer data")
        self.assertEqual(on_disk["version"], 1)

        updated = doc.update(lambda current: current.update({"value": "second"}))
        self.assertEqual(updated["value"], "second")
        self.assertEqual(updated["version"], 2)

    def test_command_reports_stale_write_instead_of_overwriting(self) -> None:
        """Inject a second writer between read and save; the CLI must exit 3."""
        project = self.init()
        self.skip_diagnosis(project)
        self.start(project)
        plan_path = self.plan_path(project)
        helper = self.tmp / "race_writer.py"
        helper.write_text(
            textwrap.dedent(
                f"""
                import json
                import sys
                from pathlib import Path

                sys.path.insert(0, {str(RUNTIME)!r})
                import learn
                import sm_state

                original = sm_state.Project.save_plan

                def racing_save(self, data):
                    path = self.plan_path
                    current = json.loads(path.read_text(encoding="utf-8"))
                    current["version"] = int(current.get("version", 0)) + 1
                    current["session_goal"] = "另一个进程的写入"
                    path.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
                    return original(self, data)

                sm_state.Project.save_plan = racing_save
                raise SystemExit(learn.main(sys.argv[1:]))
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        proc = subprocess.run(
            [sys.executable, str(helper), "say", "命令级过期写入", "--project", str(project), "--offline"],
            cwd=str(ROOT),
            env=self.env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        self.assertEqual(proc.returncode, 3, proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("state changed concurrently", combined)
        self.assertIn("changed since it was read", combined)

        self.assertEqual(self.read_json(plan_path)["session_goal"], "另一个进程的写入")
        payload = self.run_json(["status", "--project", project])
        self.assertEqual(payload["plan"]["session_goal"], "另一个进程的写入")


# ---------------------------------------------------------------------------
# 5. git sync / recovery
# ---------------------------------------------------------------------------
class GitReliabilityTests(ReliabilityBase):
    def _origin_with_remote(self, name: str = "origin", remote_name: str = "remote.git"):
        remote = self.make_remote(remote_name)
        project = self.init(name)
        self.git(project, "remote", "add", "origin", str(remote))
        return project, remote

    @GIT_SKIP
    def test_sync_without_remote_reports_no_remote(self) -> None:
        project = self.init()
        out = self.learn(["sync", "--project", project], expect=0).stdout
        self.assertIn("no-remote", out)
        self.assertIn("committed: yes", out)
        self.assertIn("pushed: no", out)
        self.assertIn("无远程", out)
        self.assertEqual(len(self.git(project, "log", "--oneline").splitlines()), 1)
        self.assertEqual(self.run_json(["status", "--project", project])["sync"]["state"], "clean")

    @GIT_SKIP
    def test_journal_only_divergence_recovers_by_union_and_pushes(self) -> None:
        project, remote = self._origin_with_remote()
        self.learn(["sync", "--project", project], expect=0)
        branch = self.branch(project)
        clone = self.clone(remote, "clone", branch)

        self.append_journal_event(project, "ev_rel_origin", "2026-11-04T04:00:01+08:00")
        self.git_commit_all(project, "origin marker")
        self.append_journal_event(clone, "ev_rel_clone", "2026-11-04T04:00:02+08:00")
        self.git_commit_all(clone, "clone marker")
        self.git(clone, "push", "-q", "origin", f"HEAD:{branch}")
        self.git(project, "fetch", "-q", "origin")
        remote_before = self.git(remote, "rev-parse", f"refs/heads/{branch}")

        recovered = self.learn(["sync", "--recover", "--project", project], expect=0).stdout
        self.assertIn("pushed: yes", recovered)
        self.assertNotIn("force", recovered.lower())
        events = {event.get("id") for event in self.journal(project)}
        self.assertTrue({"ev_rel_origin", "ev_rel_clone"} <= events, events)
        # The remote tip from before recovery is still an ancestor: no force push.
        self.git(project, "merge-base", "--is-ancestor", remote_before, "HEAD", expect=0)

        third = self.clone(remote, "third", branch)
        third_events = {event.get("id") for event in self.journal(third)}
        self.assertTrue({"ev_rel_origin", "ev_rel_clone"} <= third_events, "recovered events were not pushed")
        # The dedupe index is rebuilt during recovery and must be usable.
        dedupe = self.read_json(self.dedupe_path(project))
        self.assertIsInstance(dedupe, dict)
        self.assertTrue(any(key.startswith("test:ev_rel") for key in dedupe))

    @GIT_SKIP
    def test_snapshot_conflict_exits_3_with_files_and_keeps_local_work(self) -> None:
        project, remote = self._origin_with_remote(name="origin2", remote_name="remote2.git")
        self.learn(["sync", "--project", project], expect=0)
        branch = self.branch(project)
        clone = self.clone(remote, "clone2", branch)

        (project / "README.md").write_text("# origin changed this\n", encoding="utf-8")
        self.git_commit_all(project, "origin readme")
        (clone / "README.md").write_text("# clone changed this too\n", encoding="utf-8")
        self.git_commit_all(clone, "clone readme")
        self.git(clone, "push", "-q", "origin", f"HEAD:{branch}")
        self.git(project, "fetch", "-q", "origin")
        remote_before = self.git(remote, "rev-parse", f"refs/heads/{branch}")
        local_sha = self.git(project, "rev-parse", "HEAD")

        blocked = self.learn(["sync", "--recover", "--project", project], expect=3)
        combined = blocked.stdout + blocked.stderr
        self.assertIn("README.md", combined)
        self.assertIn("file: README.md", blocked.stdout)
        self.assertIn("conflict", blocked.stdout.lower())
        self.assertIn("恢复未完成", blocked.stdout)
        self.assertNotIn("--force", blocked.stdout)

        # Nothing was overwritten or rewritten: remote untouched, local commit kept.
        self.assertEqual(self.git(remote, "rev-parse", f"refs/heads/{branch}"), remote_before)
        self.assertEqual(self.git(project, "rev-parse", "HEAD"), local_sha)
        self.assertEqual(self.git(project, "show", "HEAD:README.md"), "# origin changed this")
        rebase_merge = self.git(project, "rev-parse", "--git-path", "rebase-merge")
        self.assertFalse((project / rebase_merge).exists(), f"rebase was left in progress: {rebase_merge}")

        doctor = self.learn(["doctor", "--project", project], expect=None)
        self.assertNotEqual(doctor.returncode, 0, "doctor must fail while histories are diverged")
        self.assertIn("sync --recover", doctor.stdout)

    @GIT_SKIP
    def test_secrets_usage_and_locks_are_never_committed(self) -> None:
        project = self.init()
        fake = "sk-learnark-fake-4f9a2c7e1d8b"
        (project / ".env").write_text(f"DEEPSEEK_API_KEY={fake}\n", encoding="utf-8")
        (project / "notes_token.txt").write_text(f"token={fake}\n", encoding="utf-8")
        (project / "debug.log").write_text(f"api key {fake}\n", encoding="utf-8")
        (project / "artifacts").mkdir(exist_ok=True)
        (project / "artifacts" / "debug.log").write_text(f"{fake}\n", encoding="utf-8")
        (project / ".learnark" / "usage.jsonl").write_text(
            json.dumps({"model": "deepseek-chat", "usage": {"prompt_tokens": 11, "completion_tokens": 7}, "key": fake}) + "\n",
            encoding="utf-8",
        )
        (project / ".learnark" / "project.lock").write_text("pid=123 at=1.000\n", encoding="utf-8")

        out = self.learn(["sync", "--project", project], expect=0).stdout
        self.assertIn("committed: yes", out)
        tracked = set(self.git(project, "ls-files").splitlines())
        for rel in (
            ".env",
            "notes_token.txt",
            "debug.log",
            "artifacts/debug.log",
            ".learnark/usage.jsonl",
            ".learnark/project.lock",
        ):
            self.assertNotIn(rel, tracked, f"{rel} was committed")
        history = self.git(project, "log", "--all", "-p")
        self.assertNotIn(fake, history, "an API key leaked into the commit history")
        self.assertNotIn("prompt_tokens", history, "the usage log leaked into the commit history")

        export = self.tmp / "export.md"
        self.learn(["export", "--out", export, "--project", project], extra={"DEEPSEEK_API_KEY": fake}, expect=0)
        self.assertNotIn(fake, export.read_text(encoding="utf-8"))

    @GIT_SKIP
    def test_clean_clone_recovers_next_step_in_a_new_process(self) -> None:
        project, remote = self._origin_with_remote(name="origin3", remote_name="remote3.git")
        self.skip_diagnosis(project)
        self.force_stage(project, "A1", "drill", level=1)
        self.start(project, "--minutes", "20")
        self.learn(["sync", "--project", project], expect=0)

        branch = self.branch(project)
        clone = self.clone(remote, "clone3", branch)
        self.assertTrue((clone / ".learnark" / "journal" / "events.jsonl").is_file())
        status = self.run_json(["status", "--project", clone])
        self.assertEqual(status["current"]["node"], "A1")
        self.assertEqual(status["current"]["stage"], "drill")
        self.assertEqual(status["current"]["activity_id"], "A1-drill")
        self.assertGreater(status["journal"]["events"], 0)

        started = self.start(clone, "--minutes", "20").stdout
        self.assertIn("A1-drill", started)
        self.assertIn("离线脚本导师", started)
        self.learn(["doctor", "--project", clone], expect=0)

        script = self.make_script([("克隆后回答", "记录。", upd(activity="A1-drill", correct=None))])
        self.learn(["say", "克隆后回答", "--project", clone], script=script, expect=0)
        self.assertGreater(len(self.journal(clone)), status["journal"]["events"])


# ---------------------------------------------------------------------------
# 6. simulated clock / index repair
# ---------------------------------------------------------------------------
class SimulatedClockTests(ReliabilityBase):
    def test_simulated_clock_schedules_review_and_tags_events(self) -> None:
        today = "2026-11-04T19:00:00+08:00"
        project = self.init(now=today)
        self.skip_diagnosis(project, now=today)
        data = self.read_json(self.map_path(project))
        for node in data["nodes"]:
            if node["id"] == "A1":
                node["level"] = 2
                node["level_source"] = "test"
                node["review"] = {"interval_index": 1, "due": "2026-11-10", "lapses": 0, "last_review_at": None}
        self.write_json(self.map_path(project), data)

        early = self.learn(["review", "--project", project], now="2026-11-09T19:00:00+08:00", expect=0).stdout
        self.assertIn("0 个到期复习", early)
        self.assertIn("2026-11-10", early)

        due_day = "2026-11-10T09:00:00+08:00"
        due = self.learn(["review", "--project", project], now=due_day, expect=0).stdout
        self.assertIn("复习队列", due)
        self.assertIn("A1", due)
        plan = self.read_json(self.plan_path(project))
        self.assertEqual(plan["mode"], "review")
        self.assertEqual(plan["review_queue"], ["A1"])

        script = self.make_script([("复习零提示", "答对。", upd(activity="review", correct=True, help_level=0))])
        self.learn(["say", "复习零提示", "--project", project], now=due_day, script=script, expect=0)

        node = self.node(project, "A1")
        self.assertEqual(node["level"], 2)
        self.assertEqual(node["review"]["interval_index"], 2)
        self.assertEqual(node["review"]["due"], "2026-11-17")

        events = self.journal(project)
        self.assertTrue(events)
        self.assertTrue(all(event.get("simulated") is True for event in events), "simulated clock not tagged")
        results = [event for event in events if event.get("kind") == "review_result"]
        self.assertTrue(results and results[-1]["payload"]["passed"] is True)
        self.assertTrue(results[-1]["simulated"])


class DedupeIndexTests(ReliabilityBase):
    def test_corrupt_dedupe_index_is_rebuilt_without_double_counting(self) -> None:
        project = self.init()
        self.skip_diagnosis(project)
        self.force_stage(project, "A1", "drill", level=1)
        script = self.make_script(
            [
                ("重复题", "对的。", upd(activity="A1-drill", correct=True, help_level=0)),
                ("新回合", "继续。", upd(activity="A1-drill", correct=None, help_level=0)),
            ]
        )
        self.learn(["say", "重复题", "--project", project], script=script, expect=0)
        attempts = lambda: [
            event for event in self.of_kind(project, "attempt") if event["payload"].get("activity_id") == "A1-drill"
        ]
        self.assertEqual(len(attempts()), 1)

        dedupe_path = self.dedupe_path(project)
        self.assertTrue(dedupe_path.is_file())
        dedupe_path.write_text("{ this is not json", encoding="utf-8")
        self.learn(["say", "重复题", "--project", project], script=script, expect=0)
        self.assertEqual(len(attempts()), 1, "a corrupt dedupe index must not double-count")
        plan = self.read_json(self.plan_path(project))
        self.assertEqual(int(plan["stage_progress"].get("drill_streak") or 0), 1)

        self.learn(["say", "新回合", "--project", project], script=script, expect=0)
        rebuilt = json.loads(dedupe_path.read_text(encoding="utf-8"))
        self.assertIsInstance(rebuilt, dict)
        self.assertTrue(any(key.startswith("attempt:") for key in rebuilt), rebuilt)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    verbosity = 2 if "-v" in argv else 1
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    print(f"\n{passed}/{result.testsRun} reliability tests passed")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
