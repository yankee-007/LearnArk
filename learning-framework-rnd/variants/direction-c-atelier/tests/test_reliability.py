#!/usr/bin/env python3
"""Standalone reliability test suite for the Atelier variant (direction C).

Run:
    python tests/test_reliability.py
    python tests/test_reliability.py -v

Everything is local and deterministic:
* ``LEARNARK_LLM=mock`` + a per-test JSONL script, so no network is used;
* every test builds its own project in a fresh temporary directory;
* two-process tests use ``subprocess.Popen`` (stdlib only, Windows-stable);
* git tests use a local bare repository (no GitHub, no credentials).

The suite is intentionally separate from ``tests/run_tests.py``: it targets the
reliability contract (torn writes, idempotency, locking, divergence recovery,
context budgets, secrets) rather than the product flow.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "runtime" / "learn.py"
RUNTIME = ROOT / "runtime"
FIXTURE = ROOT / "tests" / "fixtures" / "mentor_script.jsonl"

GIT_AVAILABLE = shutil.which("git") is not None


# ---------------------------------------------------------------------------
# process / file helpers
# ---------------------------------------------------------------------------
def base_env(script: Path | None = None, now: str | None = None, extra: dict | None = None) -> dict:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["LEARNARK_LLM"] = "mock"
    env["LEARNARK_MOCK_SCRIPT"] = str(script or FIXTURE)
    for key in (
        "LEARNARK_NOW",
        "LEARNARK_PROJECT",
        "DEEPSEEK_API_KEY",
        "LEARNARK_API_KEY",
        "LEARNARK_LOCK_TIMEOUT",
        "LEARNARK_DEBUG",
    ):
        env.pop(key, None)
    if now:
        env["LEARNARK_NOW"] = now
    if extra:
        env.update(extra)
    return env


def run(
    args,
    cwd,
    *,
    script: Path | None = None,
    now: str | None = None,
    extra: dict | None = None,
    stdin: str | None = None,
    timeout: int = 120,
):
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        cwd=str(cwd),
        env=base_env(script, now, extra),
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def spawn(args, cwd, *, script: Path | None = None, now: str | None = None, extra: dict | None = None):
    return subprocess.Popen(
        [sys.executable, str(ENTRY), *args],
        cwd=str(cwd),
        env=base_env(script, now, extra),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def git(args, cwd, *, timeout: int = 120):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def block(payload: dict, text: str = "好的，见下面的机器块。") -> str:
    return text + "\n\n```learn-update\n" + json.dumps(payload, ensure_ascii=False) + "\n```"


def update(
    *,
    help_level=0,
    activity=None,
    correct=None,
    next_="继续下一步",
    plan_change=None,
    verdict=None,
    handoff_value=None,
    misconception=None,
    do_not_redo=None,
    analogy=None,
    mastery_delta=0,
) -> dict:
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
    if do_not_redo is not None:
        payload["do_not_redo"] = do_not_redo
    if analogy is not None:
        payload["analogy"] = analogy
    return payload


def write_script(directory: Path, entries: list[dict]) -> Path:
    path = Path(directory) / f"script-{uuid.uuid4().hex[:8]}.jsonl"
    path.write_text("\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n", encoding="utf-8")
    return path


def tolerant_events(project: Path) -> list[dict]:
    path = project / ".learnark" / "journal" / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def strict_events(project: Path) -> list[dict]:
    """Read the journal without tolerating a torn line (fails loudly)."""
    path = project / ".learnark" / "journal" / "events.jsonl"
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def events_of(project: Path, kind: str) -> list[dict]:
    return [event for event in tolerant_events(project) if event.get("kind") == kind]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def handoff_files(project: Path) -> list[Path]:
    folder = project / ".learnark" / "handoff"
    return sorted(path for path in folder.glob("*.md") if path.name != "latest.md") if folder.exists() else []


def latest_handoff_block(project: Path) -> dict:
    text = (project / ".learnark" / "handoff" / "latest.md").read_text(encoding="utf-8")
    marker = "```handoff"
    start = text.index(marker) + len(marker)
    body = text[start:].split("```", 1)[0].strip()
    return json.loads(body)


# ---------------------------------------------------------------------------
# base test case
# ---------------------------------------------------------------------------
class ReliabilityCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="atelier-rel-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    # -- project fixtures -------------------------------------------------
    def init(self, template="agent-dev", name="proj", now=None, extra_env=None) -> Path:
        project = self.tmp / name
        result = run(
            ["init", "--goal", "Agent 开发", "--dir", str(project), "--template", template],
            self.tmp,
            now=now,
            extra=extra_env,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return project

    def say(self, project, text, *, script=None, now=None, extra=None, expect=0):
        result = run(["say", text, "--offline"], project, script=script, now=now, extra=extra)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def pause(self, project, *, script=None, now=None, extra=None, expect=0):
        result = run(["pause"], project, script=script, now=now, extra=extra)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def status(self, project, *, now=None, extra=None, expect=0):
        result = run(["status", "--json"], project, now=now, extra=extra)
        self.assertEqual(result.returncode, expect, result.stdout + result.stderr)
        return result

    def status_payload(self, project, **kwargs) -> dict:
        result = self.status(project, **kwargs)
        return json.loads(result.stdout)

    def studio(self, project) -> dict:
        return load_json(project / ".learnark" / "state" / "studio.json")

    def capability(self, project) -> dict:
        return load_json(project / ".learnark" / "state" / "capability.json")

    def assert_no_traceback(self, result):
        combined = result.stdout + result.stderr
        self.assertNotIn("Traceback (most recent call last)", combined)
        self.assertNotIn("未预期的错误", combined)

    # -- git fixtures -----------------------------------------------------
    def bare_remote(self, name="remote.git") -> Path:
        remote = self.tmp / name
        result = git(["init", "--bare", "-q", str(remote)], self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        return remote

    def add_remote(self, project: Path, remote: Path) -> None:
        result = git(["remote", "add", "origin", str(remote)], project)
        self.assertEqual(result.returncode, 0, result.stderr)

    def clone(self, remote: Path, name: str) -> Path:
        target = self.tmp / name
        result = git(["clone", "-q", str(remote), str(target)], self.tmp)
        self.assertEqual(result.returncode, 0, result.stderr)
        return target

    def head(self, repo: Path) -> str:
        return git(["rev-parse", "HEAD"], repo).stdout.strip()


# ---------------------------------------------------------------------------
# 1. interrupted / torn state, .bak recovery, CAS
# ---------------------------------------------------------------------------
class InterruptedStateTests(ReliabilityCase):
    def test_snapshot_recovers_from_bak_and_status_reports_it(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "第一轮", "reply": block(update(next_="继续"))}])
        self.say(project, "第一轮", script=script)
        studio_path = project / ".learnark" / "state" / "studio.json"
        backup = studio_path.with_name("studio.json.bak")
        self.assertTrue(backup.exists(), "a successful save must keep a .bak")
        expected = load_json(backup)
        studio_path.write_text('{"schema_version": 1, "current_mentor": "co', encoding="utf-8")

        result = run(["status", "--json"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("recovered studio.json from backup", result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["recovered"])
        self.assertEqual(load_json(studio_path)["current_mentor"], expected["current_mentor"])
        self.assert_no_traceback(result)

    def test_start_after_snapshot_recovery_reaches_the_handoff(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [{"match": "第一轮", "reply": block(update(next_="下次继续"))}],
        )
        self.say(project, "第一轮", script=script)
        self.pause(project)
        handoff_id = latest_handoff_block(project)["handoff_id"]

        studio_path = project / ".learnark" / "state" / "studio.json"
        studio_path.write_text("not-json-at-all", encoding="utf-8")
        result = run(["start", "--offline"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("recovered studio.json from backup", result.stderr)
        self.assertIn(handoff_id, result.stdout)
        self.assert_no_traceback(result)

    def test_torn_journal_tail_is_ignored_and_repaired_before_next_append(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "第一问", "reply": block(update(activity="w1-agent-loop-ex1", correct=None))},
                {"match": "第二问", "reply": block(update(activity="w1-agent-loop-ex1", correct=None))},
            ],
        )
        self.say(project, "第一问", script=script)
        journal = project / ".learnark" / "journal" / "events.jsonl"
        with journal.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write('{"id": "ev_torn", "kind": "mentor_tu')

        # Reading still works: a torn final line is crash residue, not corruption.
        result = run(["status", "--json"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        # The next real write must not concatenate onto the torn line.
        self.say(project, "第二问", script=script)
        events = strict_events(project)  # every line must parse now
        self.assertEqual(len(events_of(project, "say_attempt")), 2)
        self.assertEqual(len(events_of(project, "mentor_turn")), 2)
        self.assertTrue(any(event["kind"] == "journal_tail_repaired" for event in events))
        self.assertTrue(journal.read_text(encoding="utf-8").endswith("\n"))
        # Sequence numbers stay monotonic after the repair.
        seqs = [event["seq"] for event in events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_corrupt_snapshot_without_backup_is_reported_as_state_error(self):
        project = self.init()
        studio_path = project / ".learnark" / "state" / "studio.json"
        studio_path.with_name("studio.json.bak").unlink()
        studio_path.write_text("{broken", encoding="utf-8")
        result = run(["status"], project)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("studio.json", result.stderr)
        self.assertIn("JSON", result.stderr)
        self.assert_no_traceback(result)

    def test_doctor_reports_corrupt_studio_with_fail_rows(self):
        project = self.init()
        studio_path = project / ".learnark" / "state" / "studio.json"
        studio_path.with_name("studio.json.bak").unlink()
        studio_path.write_text("{broken", encoding="utf-8")
        result = run(["doctor"], project)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("[FAIL] studio_readable", result.stdout)
        self.assertIn("studio.json", result.stdout)
        # doctor must keep checking and printing the rest, not abort at the first damage.
        self.assertIn("journal_integrity", result.stdout)
        self.assertIn("project_readable", result.stdout)
        self.assert_no_traceback(result)

    def test_doctor_flags_journal_ahead_of_snapshot(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "一轮", "reply": block(update(next_="继续"))}])
        self.say(project, "一轮", script=script)
        self.pause(project)
        if str(RUNTIME) not in sys.path:
            sys.path.insert(0, str(RUNTIME))
        from atelier.state import Paths, journal as project_journal

        # Simulate a crash after the journal append but before snapshot saves.
        project_journal(Paths(project)).append(
            "mentor_turn",
            {"mentor": "coach", "session_id": "S-crash", "turn": 9, "help_level": 0},
        )
        result = run(["doctor"], project)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("[FAIL] snapshot_drift", result.stdout)
        self.assertIn("journal mentor_turn=2", result.stdout)
        self.assert_no_traceback(result)

    def test_complete_event_without_trailing_newline_is_preserved(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "第一问", "reply": block(update(next_="继续"))},
                {"match": "第二问", "reply": block(update(next_="继续"))},
            ],
        )
        self.say(project, "第一问", script=script)
        journal = project / ".learnark" / "journal" / "events.jsonl"
        seed = strict_events(project)[-1]
        extra = {
            "id": "ev_restored_no_newline",
            "seq": seed["seq"] + 1,
            "at": seed["at"],
            "kind": "mentor_turn",
            "actor": "runtime",
            "simulated": True,
            "dedupe_key": None,
            "payload": {"mentor": "planner", "session_id": "S-restored", "turn": 7, "help_level": 0},
        }
        with journal.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(extra, ensure_ascii=False))
        self.say(project, "第二问", script=script)
        ids = {event["id"] for event in strict_events(project)}
        self.assertIn("ev_restored_no_newline", ids, "a complete event must not be truncated")
        self.assertFalse(any(event["kind"] == "journal_tail_repaired" for event in tolerant_events(project)))

    def test_wrong_json_shape_is_reported_not_a_crash(self):
        project = self.init()
        studio_path = project / ".learnark" / "state" / "studio.json"
        studio_path.with_name("studio.json.bak").unlink()
        studio_path.write_text("[]\n", encoding="utf-8")
        result = run(["status"], project)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("studio.json", result.stderr)
        self.assert_no_traceback(result)

    def test_corrupt_dedupe_index_is_rebuilt_from_journal(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "甲", "reply": block(update(next_="甲"))},
                {"match": "乙", "reply": block(update(next_="乙"))},
            ],
        )
        self.say(project, "甲", script=script)
        dedupe = project / ".learnark" / "journal" / "dedupe.json"
        dedupe.write_text("{ this is not json", encoding="utf-8")
        self.say(project, "乙", script=script)
        index = load_json(dedupe)
        self.assertIsInstance(index, dict)
        keys = {event["dedupe_key"] for event in tolerant_events(project) if event.get("dedupe_key")}
        self.assertEqual(set(index), keys)
        self.assertGreaterEqual(len(index), 3)

    def test_residual_lock_file_does_not_block_commands(self):
        project = self.init()
        for relative in (
            ".learnark/project.lock",
            ".learnark/state/state.lock",
            ".learnark/journal/journal.lock",
        ):
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("pid=999999 at=0\n", encoding="ascii")
        script = write_script(self.tmp, [{"match": "锁残留", "reply": block(update(next_="继续"))}])
        self.say(project, "锁残留", script=script)
        self.assertEqual(len(events_of(project, "mentor_turn")), 1)
        _ = self.status_payload(project)

    def test_stale_document_write_is_rejected_by_cas(self):
        project = self.init()
        if str(RUNTIME) not in sys.path:
            sys.path.insert(0, str(RUNTIME))
        from learncore.fsutil import StaleWrite
        from learncore.store import Document

        doc = Document(project / ".learnark" / "state" / "studio.json")
        stale = doc.load()
        stale_version = int(stale["version"])

        script = write_script(self.tmp, [{"match": "并发前", "reply": block(update(next_="继续"))}])
        self.say(project, "并发前", script=script)
        after_say = load_json(project / ".learnark" / "state" / "studio.json")
        self.assertGreater(after_say["version"], stale_version)

        with self.assertRaises(StaleWrite):
            doc.save(stale, expected_version=stale_version)
        on_disk = load_json(project / ".learnark" / "state" / "studio.json")
        self.assertEqual(on_disk["version"], after_say["version"])
        self.assertEqual(on_disk["mentors"]["planner"]["turns"], after_say["mentors"]["planner"]["turns"])


# ---------------------------------------------------------------------------
# 2. duplicate commands: no double turn / handoff / plan change
# ---------------------------------------------------------------------------
class DuplicateCommandTests(ReliabilityCase):
    def test_duplicate_say_does_not_double_turn_plan_or_evidence(self):
        project = self.init()
        proposal = {
            "op": "add_step",
            "step_id": "new:extra-step",
            "week": 1,
            "detail": "加一个额外练习",
            "reason": "诊断发现需要更多练习",
            "status": "proposed",
        }
        script = write_script(
            self.tmp,
            [
                {
                    "match": "同一个问题",
                    "reply": block(
                        update(activity="w1-agent-loop-ex1", correct=True, plan_change=proposal, next_="继续"),
                        text="先记下这个练习，下一步我们继续。",
                    ),
                }
            ],
        )
        self.say(project, "同一个问题", script=script)
        before = self.studio(project)
        plan_version = before["plan"]["version"]
        evidence_count = [
            node for node in self.capability(project)["nodes"] if node["id"] == "w1-agent-loop-ex1"
        ][0]["evidence"]
        self.assertEqual(len(before["plan_changes"]), 1)

        second = self.say(project, "同一个问题", script=script)
        self.assertIn("重复", second.stdout)
        after = self.studio(project)
        self.assertEqual(after["plan"]["version"], plan_version)
        self.assertEqual(len(after["plan_changes"]), 1)
        self.assertEqual(len(events_of(project, "mentor_turn")), 1)
        attempts = events_of(project, "say_attempt")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len({event["payload"]["attempt_id"] for event in attempts}), 2)
        self.assertEqual(len(events_of(project, "plan_change_proposed")), 1)
        node_evidence = [
            node for node in self.capability(project)["nodes"] if node["id"] == "w1-agent-loop-ex1"
        ][0]["evidence"]
        self.assertEqual(len(node_evidence), len(evidence_count))
        session = load_json(project / ".learnark" / "state" / "session.json")
        self.assertEqual(len([turn for turn in session["turns"] if turn["role"] == "learner"]), 1)

    def test_switch_to_same_mentor_twice_writes_one_handoff(self):
        project = self.init()
        first = run(["switch", "coach"], project)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        second = run(["switch", "coach"], project)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("当前已经是", second.stdout)
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertEqual(len(events_of(project, "handoff")), 1)
        self.assertEqual(self.studio(project)["current_mentor"], "coach")

    def test_pause_twice_does_not_duplicate_the_handoff(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "做完了", "reply": block(update(next_="下次继续"))}])
        self.say(project, "做完了", script=script)
        first = self.pause(project)
        self.assertIn("已保存", first.stdout)
        first_payload = latest_handoff_block(project)
        second = self.pause(project)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertEqual(len(events_of(project, "handoff")), 1)
        self.assertEqual(latest_handoff_block(project)["handoff_id"], first_payload["handoff_id"])
        self.assertIn("已经保存", second.stdout)

    def test_examine_twice_does_not_duplicate_handoff_or_exam(self):
        project = self.init()
        first = run(["examine"], project)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(self.studio(project)["current_mentor"], "examiner")
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertEqual(len(events_of(project, "exam_started")), 1)
        pending = self.capability(project)["pending_exam"]
        self.assertIsNotNone(pending)
        self.assertEqual(pending["status"], "open")

        second = run(["examine"], project)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertEqual(len(events_of(project, "handoff")), 1)
        self.assertEqual(len(events_of(project, "exam_started")), 1)
        self.assertEqual(self.capability(project)["pending_exam"]["status"], "open")


# ---------------------------------------------------------------------------
# 3. concurrency: serialized writes or a clear lock error, nothing lost
# ---------------------------------------------------------------------------
class ConcurrencyTests(ReliabilityCase):
    def _start_and_wait(self, procs):
        outputs = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=120)
            outputs.append((proc.returncode, stdout or "", stderr or ""))
        return outputs

    def test_two_concurrent_says_keep_both_messages_and_turns(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {"match": "并发甲", "reply": block(update(activity="w1-agent-loop-ex1", correct=None, next_="甲继续"))},
                {"match": "并发乙", "reply": block(update(activity="w1-agent-loop-ex1", correct=None, next_="乙继续"))},
            ],
        )
        procs = [
            spawn(["say", "并发甲", "--offline"], project, script=script),
            spawn(["say", "并发乙", "--offline"], project, script=script),
        ]
        outputs = self._start_and_wait(procs)
        for code, stdout, stderr in outputs:
            self.assertEqual(code, 0, stdout + stderr)
        attempts = events_of(project, "say_attempt")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len({event["payload"]["attempt_id"] for event in attempts}), 2)
        self.assertEqual(len(events_of(project, "mentor_turn")), 2)
        session = load_json(project / ".learnark" / "state" / "session.json")
        texts = [turn["text"] for turn in session["turns"] if turn["role"] == "learner"]
        self.assertEqual(sorted(texts), sorted(["并发甲", "并发乙"]))
        self.assertEqual(session["turn_index"], 2)
        seqs = [event["seq"] for event in strict_events(project)]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))
        # Both messages must survive in the rendered session markdown too.
        session_md = "\n".join(
            path.read_text(encoding="utf-8") for path in (project / "sessions").glob("*.md")
        )
        self.assertIn("并发甲", session_md)
        self.assertIn("并发乙", session_md)

    def test_concurrent_say_and_pause_lose_nothing(self):
        project = self.init()
        setup = write_script(self.tmp, [{"match": "开始", "reply": block(update(next_="继续"))}])
        self.say(project, "开始", script=setup)
        script = write_script(self.tmp, [{"match": "并发消息", "reply": block(update(next_="并发继续"))}])
        procs = [
            spawn(["say", "并发消息", "--offline"], project, script=script),
            spawn(["pause"], project, script=script),
        ]
        outputs = self._start_and_wait(procs)
        for code, stdout, stderr in outputs:
            self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(len(events_of(project, "say_attempt")), 2)
        self.assertEqual(len(events_of(project, "mentor_turn")), 2)
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertEqual(len(events_of(project, "handoff")), 1)
        session_md = "\n".join(
            path.read_text(encoding="utf-8") for path in (project / "sessions").glob("*.md")
        )
        self.assertIn("开始", session_md)
        self.assertIn("并发消息", session_md)

    def test_lock_timeout_is_reported_without_partial_writes(self):
        project = self.init()
        if str(RUNTIME) not in sys.path:
            sys.path.insert(0, str(RUNTIME))
        from learncore.fsutil import file_lock

        lock_path = project / ".learnark" / "project.lock"
        before = len(events_of(project, "say_attempt"))
        script = write_script(self.tmp, [{"match": "被锁住", "reply": block(update(next_="继续"))}])
        with file_lock(lock_path, timeout=5):
            started = time.monotonic()
            result = run(["say", "被锁住", "--offline"], project, script=script, extra={"LEARNARK_LOCK_TIMEOUT": "0.4"})
            elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("并发", result.stderr)
        self.assertLess(elapsed, 20, "lock timeout must not wait for the default 60s")
        self.assertEqual(len(events_of(project, "say_attempt")), before)
        self.assertEqual(len(events_of(project, "mentor_turn")), 0)
        self.assert_no_traceback(result)

        # Releasing the lock (or leaving a stale file behind) must not block a retry.
        self.say(project, "被锁住", script=script)
        self.assertEqual(len(events_of(project, "say_attempt")), before + 1)

    def test_concurrent_switch_same_target_writes_one_handoff(self):
        project = self.init()
        procs = [spawn(["switch", "coach"], project), spawn(["switch", "coach"], project)]
        outputs = self._start_and_wait(procs)
        for code, stdout, stderr in outputs:
            self.assertEqual(code, 0, stdout + stderr)
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertEqual(len(events_of(project, "handoff")), 1)
        self.assertEqual(self.studio(project)["current_mentor"], "coach")


# ---------------------------------------------------------------------------
# 4. strict handoff contract
# ---------------------------------------------------------------------------
class StrictHandoffTests(ReliabilityCase):
    def _project_with_incomplete_proposal(self) -> Path:
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "定计划",
                    "reply": block(update(handoff_value={"known": ["能写 tool schema"]}), text="交接提案见机器块。"),
                }
            ],
        )
        self.say(project, "定计划", script=script)
        return project

    def test_strict_incomplete_handoff_exits_three_without_side_effects(self):
        project = self._project_with_incomplete_proposal()
        result = run(["switch", "concept", "--strict"], project)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        for field in ("why", "what_tried", "open_loops", "next"):
            self.assertIn(field, result.stdout)
        self.assertEqual(handoff_files(project), [])
        self.assertEqual(self.studio(project)["current_mentor"], "planner")
        session = load_json(project / ".learnark" / "state" / "session.json")
        self.assertEqual(session["mentor"], "planner")
        invalid = events_of(project, "handoff_invalid")
        self.assertEqual(len(invalid), 1)
        self.assertEqual(set(invalid[0]["payload"]["missing"]), {"why", "what_tried", "open_loops", "next"})
        self.assertIsNotNone(invalid[0]["payload"]["raw_sha256"])

    def test_strict_is_reproducible(self):
        project = self._project_with_incomplete_proposal()
        first = run(["switch", "concept", "--strict"], project)
        second = run(["switch", "concept", "--strict"], project)
        self.assertEqual(first.returncode, 3, first.stdout + first.stderr)
        self.assertEqual(second.returncode, 3, second.stdout + second.stderr)
        self.assertEqual(handoff_files(project), [])
        self.assertEqual(self.studio(project)["current_mentor"], "planner")
        events = events_of(project, "handoff_invalid")
        self.assertTrue(events, "a rejected strict handoff must be audited")
        self.assertEqual(set(events[-1]["payload"]["missing"]), {"why", "what_tried", "open_loops", "next"})
        self.assertRegex(events[-1]["payload"]["raw_sha256"], r"^[0-9a-f]{64}$")
        # The second attempt must not be silently dropped: it returns the same
        # code and the same reproducible hash for the same proposal.
        self.assertIn("why", second.stdout)

    def test_default_switch_composes_a_valid_handoff(self):
        project = self.init()
        result = run(["switch", "concept"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = latest_handoff_block(project)
        self.assertEqual(payload["from"], "planner")
        self.assertEqual(payload["to"], "concept")
        self.assertFalse(payload["degraded"])
        for field in ("why", "known", "what_tried", "do_not_redo", "open_loops", "next", "handoff_id", "created_at"):
            self.assertIn(field, payload)
        self.assertTrue(payload["known"])
        self.assertTrue(payload["next"])
        self.assertEqual(len(handoff_files(project)), 1)
        check = run(["handoff", "--check"], project)
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)

    def test_strict_fill_missing_is_explicitly_degraded(self):
        project = self._project_with_incomplete_proposal()
        result = run(["switch", "concept", "--strict", "--fill-missing"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = latest_handoff_block(project)
        self.assertTrue(payload["degraded"])
        self.assertEqual(set(payload["filled"]), {"why", "what_tried", "open_loops", "next"})
        self.assertEqual(len(handoff_files(project)), 1)
        self.assertTrue(events_of(project, "handoff_degraded"))


# ---------------------------------------------------------------------------
# 5. git: divergence, conflicts, no force push, clean start, secrets
# ---------------------------------------------------------------------------
@unittest.skipUnless(GIT_AVAILABLE, "git is required for the sync contract")
class GitReliabilityTests(ReliabilityCase):
    def _diverged_journal_clones(self):
        """A and B both add journal events; B's state is reset so only journal diverges."""
        project = self.init(name="a")
        remote = self.bare_remote()
        self.add_remote(project, remote)
        first = run(["sync"], project)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        clone = self.clone(remote, "b")
        script = write_script(
            self.tmp,
            [
                {"match": "A端事件", "reply": block(update(next_="A端继续"))},
                {"match": "B端事件", "reply": block(update(next_="B端继续"))},
            ],
        )
        self.say(project, "A端事件", script=script)
        pushed = run(["sync"], project)
        self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
        self.say(clone, "B端事件", script=script)
        # Keep only journal changes on B: snapshots/sessions would be state conflicts.
        git(["checkout", "--", ".learnark/state"], clone)
        git(["clean", "-fdq", "sessions"], clone)
        return project, remote, clone

    def _diverged_state_clones(self):
        """A and B both produce state changes, so snapshots really conflict."""
        project = self.init(name="a")
        remote = self.bare_remote()
        self.add_remote(project, remote)
        first = run(["sync"], project)
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        clone = self.clone(remote, "b")
        script = write_script(
            self.tmp,
            [
                {"match": "A端事件", "reply": block(update(next_="A端继续"))},
                {"match": "B端事件", "reply": block(update(next_="B端继续"))},
            ],
        )
        self.say(project, "A端事件", script=script)
        self.assertEqual(run(["sync"], project).returncode, 0)
        self.say(clone, "B端事件", script=script)
        return project, remote, clone

    def test_journal_divergence_recover_prefer_local_keeps_both_sides(self):
        _project, remote, clone = self._diverged_journal_clones()
        result = run(["sync", "--recover", "--prefer", "local"], clone)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pushed=yes", result.stdout)
        self.assertIn("恢复选择：local", result.stdout)
        self.assertNotIn("--force", result.stdout + result.stderr)
        self.assertTrue(events_of(clone, "recover_choice"))
        final = self.clone(remote, "final-local")
        attempts = events_of(final, "say_attempt")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len({event["payload"]["attempt_id"] for event in attempts}), 2)
        self.assertEqual(len(events_of(final, "recover_choice")), 1)

    def test_journal_divergence_recover_prefer_remote_keeps_both_sides(self):
        _project, remote, clone = self._diverged_journal_clones()
        result = run(["sync", "--recover", "--prefer", "remote"], clone)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pushed=yes", result.stdout)
        self.assertIn("恢复选择：remote", result.stdout)
        final = self.clone(remote, "final-remote")
        attempts = events_of(final, "say_attempt")
        self.assertEqual(len(attempts), 2)
        self.assertEqual(len({event["payload"]["attempt_id"] for event in attempts}), 2)

    def test_snapshot_conflict_exits_three_and_keeps_local_commit(self):
        _project, remote, clone = self._diverged_state_clones()
        remote_before = git(["rev-parse", "HEAD"], remote).stdout.strip()
        head_before = self.head(clone)
        conflict = run(["sync"], clone)
        self.assertEqual(conflict.returncode, 3, conflict.stdout + conflict.stderr)
        self.assertIn("studio.json", conflict.stdout)
        self.assertNotIn("--force", conflict.stdout + conflict.stderr)
        # The local commit is kept (fast-forward from the old head), and nothing
        # reaches the remote while the conflict is unresolved.
        ancestry = git(["merge-base", "--is-ancestor", head_before, "HEAD"], clone)
        self.assertEqual(ancestry.returncode, 0, ancestry.stderr)
        self.assertEqual(git(["rev-parse", "HEAD"], remote).stdout.strip(), remote_before)

        recovered = run(["sync", "--recover", "--prefer", "local"], clone)
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertIn("pushed=yes", recovered.stdout)
        self.assertIn("恢复选择：local", recovered.stdout)
        final = self.clone(remote, "final-state-local")
        session_text = (final / ".learnark" / "state" / "session.json").read_text(encoding="utf-8")
        self.assertIn("B端事件", session_text)
        self.assertEqual(len(events_of(final, "say_attempt")), 2)
        # No force push: the old remote head must still be an ancestor.
        ancestor = git(["merge-base", "--is-ancestor", remote_before, "HEAD"], final)
        self.assertEqual(ancestor.returncode, 0, ancestor.stderr)

    def test_snapshot_conflict_prefer_remote_takes_remote_state(self):
        _project, remote, clone = self._diverged_state_clones()
        self.assertEqual(run(["sync"], clone).returncode, 3)
        recovered = run(["sync", "--recover", "--prefer", "remote"], clone)
        self.assertEqual(recovered.returncode, 0, recovered.stdout + recovered.stderr)
        self.assertIn("恢复选择：remote", recovered.stdout)
        final = self.clone(remote, "final-state-remote")
        session_text = (final / ".learnark" / "state" / "session.json").read_text(encoding="utf-8")
        self.assertIn("A端事件", session_text)
        self.assertEqual(len(events_of(final, "say_attempt")), 2)

    def test_recover_without_preference_refuses_without_writing(self):
        _project, remote, clone = self._diverged_state_clones()
        self.assertEqual(run(["sync"], clone).returncode, 3)
        head_before = self.head(clone)
        remote_before = git(["rev-parse", "HEAD"], remote).stdout.strip()
        result = run(["sync", "--recover"], clone)
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("written=no", result.stdout)
        self.assertIn("prefer", result.stdout)
        self.assertEqual(self.head(clone), head_before)
        self.assertEqual(git(["rev-parse", "HEAD"], remote).stdout.strip(), remote_before)
        self.assertFalse(events_of(clone, "recover_choice"))

    def test_start_leaves_a_clean_worktree(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "先做一轮", "reply": block(update(next_="继续"))}])
        self.say(project, "先做一轮", script=script)
        self.pause(project)
        status = git(["status", "--porcelain"], project)
        self.assertEqual(status.stdout.strip(), "", status.stdout)
        result = run(["start", "--offline"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        after = git(["status", "--porcelain"], project)
        self.assertEqual(after.stdout.strip(), "", after.stdout)
        self.assertFalse(events_of(project, "sync_recover"))

    def test_secrets_locks_and_usage_logs_never_enter_commits(self):
        project = self.init()
        (project / ".env").write_text("DEEPSEEK_API_KEY=sk-test-SECRET-123\n", encoding="utf-8")
        (project / ".env.local").write_text("LEARNARK_API_KEY=sk-local-SECRET-456\n", encoding="utf-8")
        (project / "artifacts" / "answer.md").write_text("我的答案\n", encoding="utf-8")
        (project / ".learnark" / "usage.jsonl").write_text(
            json.dumps({"model": "mock", "api_key": "sk-test-SECRET-123"}) + "\n", encoding="utf-8"
        )
        (project / ".learnark" / "sync-log.jsonl").write_text("{}\n", encoding="utf-8")
        (project / ".learnark" / "project.lock").write_text("pid=1\n", encoding="ascii")
        (project / ".learnark" / "state" / "state.lock").write_text("pid=1\n", encoding="ascii")
        (project / ".learnark" / "journal" / "journal.lock").write_text("pid=1\n", encoding="ascii")
        (project / "notes.log").write_text("sk-test-SECRET-123\n", encoding="utf-8")

        result = run(["sync"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        tracked = git(["ls-files"], project).stdout.splitlines()
        self.assertIn(".gitignore", tracked)
        self.assertIn(".gitattributes", tracked)
        self.assertIn("artifacts/answer.md", tracked)
        forbidden = (".env", ".env.local", "usage.jsonl", "sync-log.jsonl", ".lock", ".log")
        for path in tracked:
            for marker in forbidden:
                self.assertNotIn(marker, path, f"{path} must not be committed")
        grep = git(["grep", "-I", "-n", "-e", "sk-test", "-e", "sk-local", "HEAD"], project)
        self.assertEqual(grep.returncode, 1, grep.stdout)
        committed_text = git(["show", "HEAD:.learnark/project.json"], project).stdout
        self.assertNotIn("sk-test", committed_text)
        self.assertNotIn("SECRET", committed_text)

    def test_clean_clone_restores_plan_mentor_and_handoff(self):
        project = self.init()
        script = write_script(self.tmp, [{"match": "先练一轮", "reply": block(update(activity="w1-agent-loop-ex1", correct=None, next_="继续"))}])
        self.say(project, "先练一轮", script=script)
        switch = run(["switch", "coach"], project)
        self.assertEqual(switch.returncode, 0, switch.stdout + switch.stderr)
        self.pause(project)
        expected_handoff = latest_handoff_block(project)["handoff_id"]
        expected_version = self.studio(project)["plan"]["version"]
        remote = self.bare_remote()
        self.add_remote(project, remote)
        pushed = run(["sync"], project)
        self.assertEqual(pushed.returncode, 0, pushed.stdout + pushed.stderr)
        clone = self.clone(remote, "fresh-clone")

        status = run(["status", "--json"], clone)
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual(payload["current_mentor"], "coach")
        self.assertEqual(payload["plan"]["version"], expected_version)
        self.assertEqual(payload["last_handoff"]["id"], expected_handoff)
        self.assertEqual(len(payload["mentors"]), 5)

        start = run(["start", "--offline"], clone)
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        self.assertIn(expected_handoff, start.stdout)
        studio_view = run(["studio"], clone)
        self.assertEqual(studio_view.returncode, 0, studio_view.stdout + studio_view.stderr)
        for mentor in ("planner", "concept", "coach", "examiner", "reviewer"):
            self.assertIn(mentor, studio_view.stdout)

    def test_no_remote_is_explicit_and_commit_is_local(self):
        project = self.init()
        result = run(["sync"], project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no-remote", result.stdout)
        self.assertIn("written=yes", result.stdout)
        self.assertIn("committed=yes", result.stdout)
        self.assertIn("pushed=no", result.stdout)
        self.assertIn("（无）", result.stdout)
        log = git(["log", "-1", "--oneline"], project)
        self.assertEqual(log.returncode, 0, log.stderr)
        self.assertIn("learn(", log.stdout)


# ---------------------------------------------------------------------------
# 6. context manifest: isolation, budget, simulated clock
# ---------------------------------------------------------------------------
class ContextManifestTests(ReliabilityCase):
    def _build_context(self, project: Path, mentor: str, payload: dict | None, notes_inject: dict | None = None):
        if str(RUNTIME) not in sys.path:
            sys.path.insert(0, str(RUNTIME))
        from atelier.context import build_context
        from atelier.state import Paths, capability_doc, load_with_repair, project_doc, studio_doc

        paths = Paths(project)
        project_data, _ = load_with_repair(project_doc(paths))
        studio_data, _ = load_with_repair(studio_doc(paths))
        capability_data, _ = load_with_repair(capability_doc(paths))
        for who, notes in (notes_inject or {}).items():
            target = project / ".learnark" / "state" / "mentors" / f"{who}.json"
            target.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return paths, studio_data, capability_data, project_data, build_context

    def test_context_budget_is_enforced_with_hostile_inputs(self):
        project = self.init()
        payload = {
            "handoff_id": "H-9999",
            "from": "coach",
            "to": "concept",
            "why": "x" * 5000,
            "known": ["y" * 400 for _ in range(50)],
            "what_tried": ["z" * 400 for _ in range(50)],
            "do_not_redo": [],
            "open_loops": [
                {"id": f"OL-{index}", "owner": "coach", "due": "2026-11-05", "text": "w" * 400, "blocking": False}
                for index in range(50)
            ],
            "next": "n" * 3000,
            "created_at": "2026-11-04T20:00:00+08:00",
        }
        huge_notes = {
            "schema_version": 1,
            "mentor": "coach",
            "notes": ["私有笔记 " + "很长的内容" * 200 for _ in range(60)],
            "taught": [{"item": "类比" * 200, "activity_id": "a", "at": "2026-11-04T20:00:00+08:00", "depth": 1} for _ in range(50)],
            "avoid": ["避免 " * 200 for _ in range(30)],
            "conclusions": [],
            "style": "",
            "next_suggestion": "建议" * 500,
            "turns": 99,
        }
        paths, studio_data, capability_data, project_data, build_context = self._build_context(
            project, "coach", payload, {"coach": huge_notes}
        )
        context = build_context(paths, project_data, studio_data, capability_data, "coach", payload)
        self.assertLessEqual(context["chars"], 6000)
        self.assertEqual(context["chars"], len(context["text"]))
        self.assertNotIn("journal/full", context["sources"])
        self.assertNotIn("state/mentors/examiner.json", context["sources"])

    def test_examiner_context_never_opens_coach_private_notes(self):
        project = self.init()
        coach_sentinel = "COACH_PRIVATE_SENTINEL_7f3a"
        hint_sentinel = "COACH_HINT_SENTINEL_91bc"
        dnr_sentinel = "DNR_SENTINEL_44de"
        exam_sentinel = "EXAMINER_OWN_NOTE_2231"
        payload = {
            "handoff_id": "H-1000",
            "from": "coach",
            "to": "examiner",
            "why": "需要独立验证",
            "known": ["能写 tool schema"],
            "what_tried": [hint_sentinel],
            "do_not_redo": [dnr_sentinel],
            "open_loops": [{"id": "OL-1", "owner": "examiner", "due": "2026-11-05", "text": "独立完成迁移题", "blocking": True}],
            "next": "换场景考一次",
            "created_at": "2026-11-04T20:00:00+08:00",
        }
        notes = {
            "coach": {
                "schema_version": 1,
                "mentor": "coach",
                "notes": [coach_sentinel],
                "taught": [{"item": hint_sentinel, "activity_id": "a", "at": "2026-11-04T20:00:00+08:00", "depth": 1}],
                "avoid": [dnr_sentinel],
                "conclusions": [],
                "style": "",
                "next_suggestion": "",
                "turns": 3,
            },
            "examiner": {
                "schema_version": 1,
                "mentor": "examiner",
                "notes": [exam_sentinel],
                "taught": [],
                "avoid": [],
                "conclusions": [],
                "style": "",
                "next_suggestion": "",
                "turns": 1,
            },
        }
        paths, studio_data, capability_data, project_data, build_context = self._build_context(
            project, "examiner", payload, notes
        )
        context = build_context(paths, project_data, studio_data, capability_data, "examiner", payload)
        self.assertNotIn(coach_sentinel, context["text"])
        self.assertNotIn(hint_sentinel, context["text"])
        self.assertNotIn(dnr_sentinel, context["text"])
        self.assertIn(exam_sentinel, context["text"])
        self.assertNotIn("state/mentors/coach.json", context["sources"])
        self.assertIn("state/mentors/coach.json", context["excluded"])
        self.assertIn("handoff/what_tried", context["excluded"])
        self.assertNotIn("handoff/do_not_redo", context["sources"])

    def test_cli_context_manifest_is_bounded_and_examiner_isolated(self):
        project = self.init()
        script = write_script(
            self.tmp,
            [
                {
                    "match": "请考我",
                    "reply": block(
                        update(
                            activity="exam-transfer-1",
                            verdict={
                                "activity_id": "exam-transfer-1",
                                "result": "pending",
                                "basis": "未作答",
                                "rubric": {"correctness": 0, "reasoning": 0, "max": 4, "pass_line": 2},
                            },
                        )
                    ),
                }
            ],
        )
        examine = run(["examine"], project)
        self.assertEqual(examine.returncode, 0, examine.stdout + examine.stderr)
        self.say(project, "请考我", script=script)
        manifests = events_of(project, "context_manifest")
        self.assertTrue(manifests)
        examiner_manifest = [event for event in manifests if event["payload"].get("mentor") == "examiner"][-1]
        self.assertLessEqual(examiner_manifest["payload"]["chars"], 6000)
        self.assertNotIn("state/mentors/coach.json", examiner_manifest["payload"]["sources"])
        self.assertIn("state/mentors/coach.json", examiner_manifest["payload"]["excluded"])
        self.assertNotIn("handoff/do_not_redo", examiner_manifest["payload"]["sources"])

    def test_simulated_clock_tags_events_and_drives_schedule(self):
        now = "2026-11-20T19:00:00+08:00"
        project = self.init(now=now)
        script = write_script(
            self.tmp,
            [
                {
                    "match": "模拟一轮",
                    "reply": block(
                        update(
                            activity="w1-agent-loop-ex1",
                            correct=False,
                            misconception="把 RAG 检索当成长期记忆",
                            next_="下次再练一次",
                        )
                    ),
                }
            ],
        )
        self.say(project, "模拟一轮", script=script, now=now)
        self.pause(project, now=now)

        events = tolerant_events(project)
        self.assertTrue(events)
        self.assertTrue(all(event.get("simulated") is True for event in events), "all events must be tagged simulated")
        self.assertTrue(all(str(event.get("at", "")).startswith("2026-11-20") for event in events))
        payload = latest_handoff_block(project)
        self.assertTrue(payload["created_at"].startswith("2026-11-20"))
        node = [item for item in self.capability(project)["nodes"] if item["id"] == "w1-agent-loop-ex1"][0]
        self.assertTrue(node["review_due"].startswith("2026-11-22"), node["review_due"])
        self.assertEqual(node["last_fail"]["misconception"], "把 RAG 检索当成长期记忆")

        later = "2026-11-23T08:00:00+08:00"
        status = run(["status"], project, now=later)
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        self.assertIn("2 d ago", status.stdout)
        start = run(["start", "--offline"], project, now=later)
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        new_events = tolerant_events(project)
        self.assertTrue(all(event.get("simulated") is True for event in new_events))
        self.assertTrue(any(str(event.get("at", "")).startswith("2026-11-23") for event in new_events))


if __name__ == "__main__":
    unittest.main(verbosity=2)
