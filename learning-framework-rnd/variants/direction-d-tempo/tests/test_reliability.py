"""Reliability / memory-discipline tests for Tempo (direction D).

Standalone, standard library only::

    python tests/test_reliability.py -v
    python -m unittest discover -s tests -p "test_reliability.py"

Every command runs against a fresh unique temporary directory with the offline
scripted mentor (``LEARNARK_LLM=mock``); nothing touches the network. Git tests use
local bare repositories only. Simulated time always goes through
``learncore.clock`` + ``LEARNARK_NOW`` and the assertion messages name it, so
simulated scheduling evidence cannot be mistaken for real elapsed learning.

Covered here (see ``experiments/CP2-reliability.md`` for the matrix and for the
untested list): torn/interrupted state and ``.bak`` recovery, duplicate saves,
two-process concurrency, document- and command-level stale writes, git divergence
recovery / snapshot conflicts / secret exclusion / clean-clone recovery /
CRLF-safe artifacts, simulated-clock SRS, and a secrets audit.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
ENTRY = RUNTIME / "learn.py"
sys.path.insert(0, str(RUNTIME))

import learn  # noqa: E402  (only used for the command-level stale-write test)
import tempo  # noqa: E402
from learncore import clock  # noqa: E402
from learncore.fsutil import LockTimeout, StaleWrite, file_lock, write_json  # noqa: E402

NOW0 = "2026-11-04T19:00:00+08:00"
READ_ANSWER = "停止条件有三个：达成目标、轮次上限、连续两次没有新信息。"
READ_ANSWER_2 = "我会先记录当前轮次，再看是否连续两次没有新信息，最后决定停。"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Tempo Reliability",
    "GIT_AUTHOR_EMAIL": "tempo-reliability@example.invalid",
    "GIT_COMMITTER_NAME": "Tempo Reliability",
    "GIT_COMMITTER_EMAIL": "tempo-reliability@example.invalid",
}


# --------------------------------------------------------------------------------------
# harness
# --------------------------------------------------------------------------------------


def day(offset: int) -> str:
    return clock.add_days(NOW0, offset)


def make_env(now: str | None = NOW0, extra: dict | None = None) -> dict:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("LEARNARK_") and key not in ("DEEPSEEK_API_KEY", "LEARNARK_API_KEY")
    }
    env.update(
        {
            "LEARNARK_LLM": "mock",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            **GIT_ENV,
        }
    )
    if now:
        env["LEARNARK_NOW"] = now
    if extra:
        env.update(extra)
    return env


class ReliabilityBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = Path(tempfile.mkdtemp(prefix="tempo-reliability-"))

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.base, ignore_errors=True)

    # -- filesystem ------------------------------------------------------
    def fresh(self, name: str) -> Path:
        path = self.base / name
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def init_project(
        self,
        name: str,
        *,
        template: str = "agent-dev",
        now: str = NOW0,
        extra: dict | None = None,
    ) -> Path:
        work = self.fresh(name)
        proj = work / "proj"
        self.cli(["init", "--goal", "可靠性测试目标", "--dir", str(proj), "--template", template], work, now=now, extra=extra)
        return proj

    # -- commands --------------------------------------------------------
    def cli(
        self,
        args: list[str],
        cwd: Path,
        *,
        now: str | None = NOW0,
        extra: dict | None = None,
        expect: int | None = 0,
        timeout: int = 240,
    ) -> dict:
        command = [sys.executable, str(ENTRY), *args, "--offline"]
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            env=make_env(now, extra),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        out, err = proc.stdout or "", proc.stderr or ""
        if expect is not None:
            self.assertEqual(
                proc.returncode,
                expect,
                f"command {' '.join(args)} exited {proc.returncode}, expected {expect}\n"
                f"--- stdout ---\n{out[-3000:]}\n--- stderr ---\n{err[-2000:]}",
            )
        return {"code": proc.returncode, "out": out, "err": err, "text": out + err}

    def spawn(self, args: list[str], cwd: Path, *, now: str = NOW0, extra: dict | None = None) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, str(ENTRY), *args, "--offline"],
            cwd=str(cwd),
            env=make_env(now, extra),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    @staticmethod
    def wait(proc: subprocess.Popen, timeout: float) -> bool:
        """Return True when the process finished within ``timeout`` seconds."""
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    @staticmethod
    def collect(proc: subprocess.Popen) -> dict:
        out, err = proc.communicate(timeout=240)
        return {"code": proc.returncode, "out": out or "", "err": err or "", "text": (out or "") + (err or "")}

    # -- state helpers ---------------------------------------------------
    def status_json(self, proj: Path, *, now: str = NOW0) -> dict:
        result = self.cli(["status", "--json", "--project", str(proj)], proj, now=now)
        text = result["out"].strip()
        return json.loads(text[text.find("{") :])

    def read_state(self, proj: Path, name: str) -> dict:
        path = proj / ".learnark" / "state" / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def journal(self, proj: Path) -> list[dict]:
        path = proj / ".learnark" / "journal" / "events.jsonl"
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    def kinds(self, proj: Path) -> Counter:
        return Counter(event.get("kind") for event in self.journal(proj))

    def assert_journal_healthy(self, proj: Path) -> list[dict]:
        events = self.journal(proj)
        seqs = [event.get("seq") for event in events]
        self.assertEqual(seqs, sorted(seqs), "journal seq must be monotonic")
        self.assertEqual(len(seqs), len(set(seqs)), "journal seq must be unique")
        ids = [event.get("id") for event in events]
        self.assertEqual(len(ids), len(set(ids)), "journal event ids must be unique")
        return events

    def git(self, *args: str, cwd: Path, expect: int = 0) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=make_env(None),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(proc.returncode, expect, f"git {' '.join(args)} failed: {proc.stderr or proc.stdout}")
        return proc.stdout or ""

    def make_bare(self, work: Path, name: str = "remote.git") -> Path:
        bare = work / name
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True, env=make_env(None))
        return bare

    def write_script(self, work: Path, name: str, match: str, visible: str, update: dict) -> Path:
        path = work / f"{name}.jsonl"
        reply = visible + "\n\n```learn-update\n" + json.dumps(update, ensure_ascii=False) + "\n```"
        path.write_text(json.dumps({"match": match, "reply": reply}, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


# --------------------------------------------------------------------------------------
# 1. interrupted / torn state
# --------------------------------------------------------------------------------------


class InterruptedStateTests(ReliabilityBase):
    def test_torn_snapshot_recovers_from_bak_and_reports(self):
        proj = self.init_project("torn-snapshot")
        self.cli(["start", "--minutes", "20"], proj)
        self.cli(["say", READ_ANSWER], proj)
        state = proj / ".learnark" / "state"
        self.assertTrue((state / "schedule.json.bak").exists(), "a successful save must keep a .bak")

        # a torn write: the main file is cut in half, the backup is complete
        raw = (state / "schedule.json").read_bytes()
        (state / "schedule.json").write_bytes(raw[: len(raw) // 2])
        payload = self.status_json(proj)
        self.assertTrue(
            any("schedule.json" in note and "backup" in note for note in payload["recovery"]),
            payload["recovery"],
        )
        self.assertEqual(len(payload["skills"]), 10)
        self.assertGreaterEqual(payload["today"]["items_started"], 1)

        # a second document: the repair report must also come from `start`
        started = self.cli(["start", "--minutes", "10"], proj)
        self.assertGreaterEqual(len(self.read_state(proj, "schedule")["today"]["items"]), 1)

        cards = state / "cards.json"
        cards.write_text("[]\n", encoding="utf-8")
        recovered_start = self.cli(["start", "--minutes", "10"], proj)
        self.assertIn("[恢复]", recovered_start["out"], recovered_start["out"])
        self.assertIn("cards.json", recovered_start["out"], recovered_start["out"])
        self.assertGreaterEqual(len(self.read_state(proj, "cards")["cards"]), 10)

        cards.unlink()
        (state / "cards.json.bak").unlink()
        cards.write_text("[]\n", encoding="utf-8")
        broken = self.cli(["status"], proj, expect=3)
        self.assertIn("cards.json", broken["err"], broken["err"])
        self.assertIn("JSON", broken["err"], broken["err"])

    def test_torn_journal_tail_usage_and_midfile_corruption(self):
        proj = self.init_project("torn-journal")
        self.cli(["start", "--minutes", "20"], proj)
        self.cli(["say", READ_ANSWER], proj)
        journal_path = proj / ".learnark" / "journal" / "events.jsonl"
        with journal_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write('{"torn": "interrupted')
        usage = proj / ".learnark" / "usage.jsonl"
        usage.write_text('{"model": "x", "usage":', encoding="utf-8")

        # a torn tail is harmless for readers, and a torn usage file is not read by commands
        payload = self.status_json(proj)
        self.assertEqual(payload["project"]["goal"], "可靠性测试目标")
        self.assertGreater(payload["journal"]["events"], 0)

        # the next write repairs the tail instead of poisoning the log
        second = self.cli(["say", READ_ANSWER_2], proj)
        self.assertEqual(second["code"], 0)
        repaired = [event for event in self.journal(proj) if event["kind"] == "journal_repaired"]
        self.assertEqual(len(repaired), 1, repaired)
        attempted = [event for event in self.journal(proj) if event["kind"] == "attempt"]
        self.assertEqual(len(attempted), 2, "both answers must survive exactly once")
        answers = {event["payload"]["answer_sha"] for event in attempted}
        self.assertEqual(len(answers), 2)
        self.assert_journal_healthy(proj)

        # corruption *inside* the journal must be reported (exit 3), never silently skipped
        lines = journal_path.read_text(encoding="utf-8").splitlines()
        lines.insert(max(1, len(lines) // 2), "this-is-not-json")
        journal_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        broken = self.cli(["status"], proj, expect=3)
        self.assertIn("not valid JSON", broken["err"], broken["err"])

    def test_corrupt_project_json_recovered_and_reported(self):
        proj = self.init_project("meta-backup")
        self.cli(["start", "--minutes", "20"], proj)
        meta = proj / ".learnark" / "project.json"
        self.assertTrue((proj / ".learnark" / "project.json.bak").exists())
        meta.write_text("{ broken", encoding="utf-8")

        human = self.cli(["status"], proj)
        self.assertIn("恢复", human["out"], human["out"])
        self.assertIn("project.json", human["out"], human["out"])
        # the main file is rewritten from the backup, so the next raw read is valid JSON
        self.assertEqual(json.loads(meta.read_text(encoding="utf-8"))["goal"], "可靠性测试目标")
        payload = self.status_json(proj)
        self.assertEqual(payload["project"]["goal"], "可靠性测试目标")

    def test_corrupt_dedupe_index_is_rebuilt_on_next_write(self):
        proj = self.init_project("dedupe-rebuild")
        self.cli(["start", "--minutes", "20"], proj)
        index = proj / ".learnark" / "journal" / "dedupe.json"
        index.write_text("{broken", encoding="utf-8")

        self.cli(["start", "--minutes", "10"], proj)
        rebuilt = json.loads(index.read_text(encoding="utf-8"))
        self.assertIsInstance(rebuilt, dict)
        self.assertTrue(rebuilt, "the rebuilt index must contain the journal dedupe keys")
        kinds = self.kinds(proj)
        self.assertEqual(kinds["journal_index_rebuilt"], 1, kinds)
        doctor = self.cli(["doctor"], proj)
        self.assertIn("0 项问题", doctor["out"], doctor["out"])

    def test_atomic_write_residue_is_reported_not_fatal(self):
        proj = self.init_project("residue")
        self.cli(["start", "--minutes", "20"], proj)
        (proj / ".learnark" / "state" / "orphan.json.tmp").write_text("{half", encoding="utf-8")
        (proj / ".learnark" / "state" / "old.lock").write_text("pid=1\n", encoding="utf-8")
        doctor = self.cli(["doctor"], proj)
        self.assertIn("interrupted_writes", doctor["out"], doctor["out"])
        self.assertIn("锁文件", doctor["out"], doctor["out"])
        self.assertIn("0 项问题", doctor["out"], doctor["out"])
        self.assertEqual(self.status_json(proj)["project"]["slug"], "proj")

    def test_interrupted_turn_credit_is_rebuilt_from_journal(self):
        """A crash between the journal append and the snapshot save must not lose credit."""
        proj = self.init_project("interrupted-credit")
        clock.simulate(NOW0)
        try:
            store = tempo.Store(proj).load()
            activity = {
                "activity_id": "recall-card-0003",
                "activity_type": "recall_card",
                "template": "recall_card",
                "skill": "tool-contract",
                "skill_title": "工具契约",
                "minutes": 5,
                "level": 0,
                "mentor": "trainer",
                "tier": 1,
                "source": "due_card",
                "card_id": "card-0003",
                "card_ids": ["card-0003"],
                "block_id": None,
                "step_index": None,
                "task": "测试",
            }
            session = tempo.open_session(store, activity, 20, "（测试开场）")
            store.save()  # session + item are on disk; the turn is not yet
            payload = {
                "help_level": 0,
                "attempt": {"activity_id": "recall-card-0003", "correct": True},
                "misconception": None,
                "next": "下一次复测（建议）",
                "mastery_delta": 1,
                "card": {"op": "review", "id": "card-0003", "grade": "good"},
            }
            tempo.apply_turn(
                store,
                session,
                activity,
                READ_ANSWER,
                json.dumps(payload, ensure_ascii=False),
                payload,
                "",
                0,
                "api",
            )
            # simulate the crash: nothing in memory is persisted
            before_cards = self.read_state(proj, "cards")
            card_before = next(card for card in before_cards["cards"] if card["id"] == "card-0003")
            self.assertEqual(card_before["step"], 0)
            skills_before = {skill["id"]: skill["level"] for skill in self.read_state(proj, "skills")["skills"]}
            self.assertEqual(skills_before["tool-contract"], 0)
        finally:
            clock.simulate(None)

        healed = self.cli(["start", "--minutes", "10"], proj)
        self.assertIn("[恢复]", healed["out"], healed["out"])
        self.assertIn("卡片复习", healed["out"], healed["out"])
        card = next(card for card in self.read_state(proj, "cards")["cards"] if card["id"] == "card-0003")
        self.assertEqual(card["step"], 1, "the reviewed step must be replayed from the journal")
        skill = next(skill for skill in self.read_state(proj, "skills")["skills"] if skill["id"] == "tool-contract")
        self.assertEqual(skill["level"], 1, "the level change must be replayed from the journal")
        item = next(
            item for item in self.read_state(proj, "schedule")["today"]["items"] if item["activity_id"] == "recall-card-0003"
        )
        self.assertTrue(item["done"], "the completion mark must be replayed from the journal")
        self.assertEqual(self.kinds(proj)["card_reviewed"], 1, "replay must not duplicate the event")


# --------------------------------------------------------------------------------------
# 2. duplicate saves
# --------------------------------------------------------------------------------------


class DuplicateSaveTests(ReliabilityBase):
    def test_duplicate_say_is_idempotent(self):
        proj = self.init_project("dup-say")
        self.cli(["start", "--minutes", "20"], proj)
        self.cli(["say", READ_ANSWER], proj)
        before = self.kinds(proj)
        skills_before = {skill["id"]: skill["level"] for skill in self.read_state(proj, "skills")["skills"]}
        cards_before = {card["id"]: card["step"] for card in self.read_state(proj, "cards")["cards"]}

        again = self.cli(["say", READ_ANSWER], proj)
        self.assertIn("重复执行", again["out"], again["out"])
        after = self.kinds(proj)
        for kind in ("turn", "attempt", "card_reviewed", "level_change", "activity_completed"):
            self.assertEqual(after[kind], before[kind], f"{kind} must not be double counted")
        self.assertEqual(
            {skill["id"]: skill["level"] for skill in self.read_state(proj, "skills")["skills"]}, skills_before
        )
        self.assertEqual({card["id"]: card["step"] for card in self.read_state(proj, "cards")["cards"]}, cards_before)
        learner_blocks = sum(
            path.read_text(encoding="utf-8").count("## 学习者") for path in (proj / "sessions").glob("*.md")
        )
        self.assertEqual(learner_blocks, 1, "a replay must not append a second learner block to the session")
        self.assert_journal_healthy(proj)

    def test_duplicate_attempt_and_card_review_items_do_not_double_apply(self):
        proj = self.init_project("dup-turn")
        clock.simulate(NOW0)
        try:
            store = tempo.Store(proj).load()
            activity = {
                "activity_id": "recall-card-0001",
                "activity_type": "recall_card",
                "template": "recall_card",
                "skill": "agent-loop",
                "skill_title": "Agent 循环",
                "minutes": 5,
                "level": 0,
                "mentor": "trainer",
                "tier": 1,
                "source": "due_card",
                "card_id": "card-0001",
                "card_ids": ["card-0001"],
                "block_id": None,
                "step_index": None,
                "task": "测试",
            }
            session = tempo.open_session(store, activity, 20, "（测试开场）")
            card = store.card("card-0001")
            self.assertEqual(card["step"], 0)
            payload = {
                "help_level": 0,
                "attempt": {"activity_id": "recall-card-0001", "correct": True},
                "misconception": None,
                "next": "下一张卡（建议）",
                "mastery_delta": 1,
                "card": [
                    {"op": "review", "id": "card-0001", "grade": "good"},
                    {"op": "review", "id": "card-0001", "grade": "good"},
                ],
            }
            out = tempo.apply_turn(
                store,
                session,
                activity,
                READ_ANSWER,
                json.dumps(payload, ensure_ascii=False),
                payload,
                "",
                0,
                "api",
            )
            self.assertEqual(card["step"], 1, "two identical review items in one turn must grade once")
            self.assertEqual(card["ease"], 1.15)
            self.assertTrue(any("重复条目已忽略" in note for note in out["notes"]), out["notes"])
            reviewed = [event for event in store.events("card_reviewed") if event["payload"]["card"] == "card-0001"]
            self.assertEqual(len(reviewed), 1)

            # replaying the *whole* turn (same answer text) must not change anything
            again = tempo.apply_turn(
                store,
                session,
                activity,
                READ_ANSWER,
                json.dumps(payload, ensure_ascii=False),
                payload,
                "",
                1,
                "api",
            )
            self.assertEqual(card["step"], 1)
            self.assertEqual(len([e for e in store.events("card_reviewed") if e["payload"]["card"] == "card-0001"]), 1)
            self.assertTrue(any("不重复计数" in note for note in again["notes"]), again["notes"])

            # duplicate create items in one turn: one card, one merge, no double count
            create = {"op": "create", "skill": "agent-loop", "kind": "recall", "front": "重复卡正面？", "back": "答案", "tags": ["dup"]}
            payload2 = {
                "help_level": 0,
                "attempt": {"activity_id": "recall-card-0001", "correct": True},
                "misconception": None,
                "next": "下一张卡（建议）",
                "mastery_delta": 0,
                "card": [dict(create), dict(create)],
            }
            out2 = tempo.apply_turn(
                store,
                session,
                activity,
                READ_ANSWER_2,
                json.dumps(payload2, ensure_ascii=False),
                payload2,
                "",
                2,
                "api",
            )
            created = [
                c for c in store.cards["cards"] if tempo.normalize_text(c["front"]) == tempo.normalize_text(create["front"])
            ]
            self.assertEqual(len(created), 1)
            self.assertEqual(created[0].get("merge_count"), 1)
            self.assertEqual(out2["cards"][0]["op"], "create")
            store.save()
        finally:
            clock.simulate(None)


# --------------------------------------------------------------------------------------
# 3. stale writes / CAS
# --------------------------------------------------------------------------------------


class StaleWriteTests(ReliabilityBase):
    def test_document_cas_rejects_stale_save(self):
        proj = self.init_project("cas-doc")
        path = proj / ".learnark" / "state" / "skills.json"
        document = tempo.Document(path, tempo._skills_default)
        snapshot = document.load()
        stale_version = int(snapshot["version"])

        newer = document.load()
        newer["skills"][0]["level"] = 1
        document.save(newer)

        stale = document.load()
        stale["skills"][0]["level"] = 9
        with self.assertRaises(StaleWrite):
            document.save(stale, expected_version=stale_version)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["skills"][0]["level"], 1)

    def test_store_save_rejects_snapshot_based_on_old_version(self):
        proj = self.init_project("cas-store")
        clock.simulate(NOW0)
        try:
            stale = tempo.Store(proj).load()
            # another writer commits a newer skills.json while `stale` is open
            document = tempo.Document(proj / ".learnark" / "state" / "skills.json", tempo._skills_default)
            current = document.load()
            current["skills"][0]["level"] = 2
            document.save(current)

            stale.skills["skills"][0]["level"] = 9
            stale.touch("skills")
            with self.assertRaises(StaleWrite):
                stale.save()
            on_disk = json.loads((proj / ".learnark" / "state" / "skills.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk["skills"][0]["level"], 2, "a stale Store.save must not overwrite newer state")
        finally:
            clock.simulate(None)

    def test_command_level_stale_write_reports_refresh_instead_of_overwriting(self):
        proj = self.init_project("cas-command")
        clock.simulate(NOW0)
        try:
            stale = tempo.Store(proj).load()
        finally:
            clock.simulate(None)
        # a second writer advances schedule.json (e.g. another terminal ran start)
        document = tempo.Document(proj / ".learnark" / "state" / "schedule.json", tempo._schedule_default)
        document.save(document.load())
        before = json.loads((proj / ".learnark" / "state" / "schedule.json").read_text(encoding="utf-8"))["version"]

        original = learn.load_store
        learn.load_store = lambda root, offline, reconcile=True: stale  # noqa: ARG005
        stdout, stderr = io.StringIO(), io.StringIO()
        clock.simulate(day(1))  # the next day forces prepare_day to touch schedule.json
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = learn.handler(["due", "--project", str(proj)])
        finally:
            learn.load_store = original
            clock.simulate(None)
        self.assertEqual(code, 3, f"stale command must exit 3, stdout={stdout.getvalue()} stderr={stderr.getvalue()}")
        self.assertIn("已被另一个进程更新", stderr.getvalue())
        self.assertIn("重跑", stderr.getvalue())
        after = json.loads((proj / ".learnark" / "state" / "schedule.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(after, before, "the rejected command must not bump the snapshot version")


# --------------------------------------------------------------------------------------
# 4. concurrency
# --------------------------------------------------------------------------------------


class ConcurrencyTests(ReliabilityBase):
    def test_two_concurrent_starts_serialize_without_losing_items(self):
        proj = self.init_project("conc-start")
        first = self.spawn(["start", "--minutes", "20"], proj)
        second = self.spawn(["start", "--minutes", "20"], proj)
        results = [self.collect(first), self.collect(second)]
        self.assertEqual([result["code"] for result in results], [0, 0], [result["text"] for result in results])

        schedule = self.read_state(proj, "schedule")
        items = schedule["today"]["items"]
        self.assertEqual(len(items), 2, f"two serialised starts must leave two items, got {items}")
        self.assertEqual(len({item["activity_id"] for item in items}), 2, items)
        self.assertEqual(len({item["skill"] for item in items}), 2, items)

        sessions = list((proj / "sessions").glob("*.md"))
        self.assertEqual(len(sessions), 2, [str(path) for path in sessions])
        opened = [event for event in self.journal(proj) if event["kind"] == "session_opened"]
        self.assertEqual(len(opened), 2, "both sessions must be recorded in the journal")
        decisions = [event for event in self.journal(proj) if event["kind"] == "schedule_decision"]
        self.assertEqual(len(decisions), 2)
        chosen = {event["payload"]["chosen"] for event in decisions}
        self.assertEqual(chosen, {item["activity_id"] for item in items}, "scheduler decisions must match the items")
        self.assertIsNotNone(schedule["current_session"])
        self.assertIn(schedule["current_session"]["activity"]["activity_id"], {item["activity_id"] for item in items})
        for item in items:
            self.assertFalse(item["done"])
        self.assert_journal_healthy(proj)

    def test_two_concurrent_says_keep_both_attempts_and_card_reviews(self):
        proj = self.init_project("conc-say")
        self.cli(["start", "--minutes", "20"], proj)
        session = self.read_state(proj, "schedule")["current_session"]
        activity_id = session["activity"]["activity_id"]
        answer_a = "停止条件之一是达成目标，另外还有轮次上限，以及连续两次没有新信息。"
        answer_b = "我的理解是：先记录轮次，再看是否连续两次没有新信息，必要时按轮次上限停。"

        scripts = {}
        for name, answer, card_id in (("a", answer_a, "card-0001"), ("b", answer_b, "card-0002")):
            update = {
                "help_level": 0,
                "attempt": {"activity_id": activity_id, "correct": True},
                "misconception": None,
                "next": "下一次复测（建议）",
                "mastery_delta": 1,
                "card": {"op": "review", "id": card_id, "grade": "good"},
            }
            scripts[name] = self.write_script(proj.parent, f"conc-{name}-{proj.name}", answer, "这轮已记录。", update)

        procs = [
            self.spawn(["say", answer, "--project", str(proj)], proj, extra={"LEARNARK_MOCK_SCRIPT": str(scripts[name])})
            for name, answer in (("a", answer_a), ("b", answer_b))
        ]
        results = [self.collect(proc) for proc in procs]
        self.assertEqual([result["code"] for result in results], [0, 0], [result["text"] for result in results])

        attempts = [event for event in self.journal(proj) if event["kind"] == "attempt"]
        self.assertEqual(len(attempts), 2, "no attempt may be lost when two processes write concurrently")
        self.assertEqual(len({event["payload"]["answer_sha"] for event in attempts}), 2)
        reviewed = [event for event in self.journal(proj) if event["kind"] == "card_reviewed"]
        self.assertEqual(len(reviewed), 2, reviewed)
        self.assertEqual({event["payload"]["card"] for event in reviewed}, {"card-0001", "card-0002"})
        cards = {card["id"]: card for card in self.read_state(proj, "cards")["cards"]}
        self.assertEqual(cards["card-0001"]["step"], 1, "the first card review must survive the other writer")
        self.assertEqual(cards["card-0002"]["step"], 1, "the second card review must survive the other writer")

        skill_levels = {skill["id"]: skill["level"] for skill in self.read_state(proj, "skills")["skills"]}
        activity_skill = session["activity"]["skill"]
        self.assertEqual(skill_levels[activity_skill], 1, "same skill, same day: at most +1 level")
        level_changes = [event for event in self.journal(proj) if event["kind"] == "level_change"]
        self.assertEqual(len(level_changes), 1, level_changes)
        self.assert_journal_healthy(proj)

    def test_project_lock_timeout_is_a_clear_exit_3(self):
        proj = self.init_project("lock-timeout")
        self.cli(["start", "--minutes", "20"], proj)
        lock_path = proj / ".learnark" / "project.lock"
        events_before = len(self.journal(proj))
        with file_lock(lock_path, timeout=10.0):
            blocked = self.cli(
                ["status"],
                proj,
                extra={"LEARNARK_LOCK_TIMEOUT": "0.4"},
                expect=3,
                timeout=60,
            )
        self.assertIn("另一个进程正在写", blocked["err"], blocked["err"])
        self.assertIn("锁超时", blocked["err"], blocked["err"])
        self.assertIn("没有写入", blocked["err"], blocked["err"])
        self.assertEqual(len(self.journal(proj)), events_before, "a blocked command must not write events")

    def test_journal_repair_waits_for_the_journal_lock(self):
        proj = self.init_project("journal-lock")
        self.cli(["start", "--minutes", "20"], proj)
        journal_path = proj / ".learnark" / "journal" / "events.jsonl"
        with journal_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write('{"torn":')
        lock_path = proj / ".learnark" / "journal" / "journal.lock"
        proc = None
        with file_lock(lock_path, timeout=10.0):
            proc = self.spawn(["say", READ_ANSWER_2, "--project", str(proj)], proj)
            finished_while_locked = self.wait(proc, 1.5)
            if finished_while_locked:
                proc.communicate(timeout=30)
        self.assertFalse(finished_while_locked, "the torn-tail repair must hold journal.lock instead of rewriting it under a writer")
        result = self.collect(proc)
        self.assertEqual(result["code"], 0, result["text"])
        kinds = self.kinds(proj)
        self.assertEqual(kinds["journal_repaired"], 1, kinds)
        self.assertEqual(kinds["attempt"], 1, kinds)
        self.assert_journal_healthy(proj)


# --------------------------------------------------------------------------------------
# 5. git: divergence, conflicts, secrets, clone, CRLF
# --------------------------------------------------------------------------------------


class GitReliabilityTests(ReliabilityBase):
    def _append_event(self, proj: Path, event_id: str) -> None:
        record = {
            "id": event_id,
            "seq": 9999,
            "at": NOW0,
            "kind": "test_marker",
            "actor": "test",
            "simulated": True,
            "dedupe_key": f"test:{event_id}",
            "payload": {"marker": event_id},
        }
        with (proj / ".learnark" / "journal" / "events.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def test_journal_divergence_recovers_by_union_without_force_push(self):
        work = self.fresh("git-divergence-work")
        bare = self.make_bare(work)
        proj = self.init_project("git-divergence-proj", extra=None)
        self.git("remote", "add", "origin", str(bare), cwd=proj)
        first = self.cli(["sync", "--project", str(proj)], proj)
        self.assertIn("pushed=yes", first["out"], first["out"])

        clone_a = work / "clone-a"
        clone_b = work / "clone-b"
        self.git("clone", "-q", str(bare), str(clone_a), cwd=work)
        self.git("clone", "-q", str(bare), str(clone_b), cwd=work)
        self._append_event(clone_a, "ev_test_a")
        self._append_event(clone_b, "ev_test_b")

        pushed_a = self.cli(["sync", "--project", str(clone_a)], clone_a)
        self.assertIn("pushed=yes", pushed_a["out"], pushed_a["out"])
        a_head = self.git("rev-parse", "HEAD", cwd=clone_a).strip()

        recovered = self.cli(["sync", "--recover", "--project", str(clone_b)], clone_b)
        self.assertIn("pushed=yes", recovered["out"], recovered["out"])
        self.assertIn("union", recovered["out"].lower(), recovered["out"])

        events = self.journal(clone_b)
        ids = {event["id"] for event in events}
        self.assertIn("ev_test_a", ids, "remote-side journal events must be preserved")
        self.assertIn("ev_test_b", ids)
        self.assert_journal_healthy(clone_b)
        dedupe = json.loads((clone_b / ".learnark" / "journal" / "dedupe.json").read_text(encoding="utf-8"))
        self.assertIn("test:ev_test_a", dedupe)
        self.assertIn("test:ev_test_b", dedupe)

        # no force push: clone A's pushed commit is still an ancestor of the remote tip
        ancestor = subprocess.run(
            ["git", "-C", str(clone_b), "merge-base", "--is-ancestor", a_head, "HEAD"],
            env=make_env(None),
            capture_output=True,
        )
        self.assertEqual(ancestor.returncode, 0, "recovery must not rewrite/force-push history")
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=bare).strip()
        remote_events = self.git("show", f"{branch}:.learnark/journal/events.jsonl", cwd=bare)
        self.assertIn("ev_test_a", remote_events)
        self.assertIn("ev_test_b", remote_events)
        status = self.status_json(clone_b)
        self.assertEqual(status["sync"]["state"], "pushed", status["sync"])
        self.assertTrue(status["sync"]["clean"], status["sync"])

        # the core sync implementation must not call push/add with a force flag
        source = (RUNTIME / "learncore" / "sync.py").read_text(encoding="utf-8")
        push_calls = [line for line in source.splitlines() if 'self.run("push"' in line]
        self.assertTrue(push_calls, "expected the push plumbing to be present")
        for line in push_calls:
            self.assertNotIn('"--force"', line, line)
            self.assertNotIn('"-f"', line, line)
        self.assertNotIn('reset", "--hard"', source, "no reset --hard path is allowed")

    def test_snapshot_conflict_exits_3_lists_files_and_keeps_local_commit(self):
        work = self.fresh("git-conflict-work")
        bare = self.make_bare(work)
        proj = self.init_project("git-conflict-proj")
        self.cli(["start", "--minutes", "20"], proj)
        self.cli(["say", READ_ANSWER], proj)
        self.cli(["pause"], proj)
        self.git("remote", "add", "origin", str(bare), cwd=proj)
        self.assertIn("pushed=yes", self.cli(["sync", "--project", str(proj)], proj)["out"])

        clone_c = work / "clone-c"
        clone_d = work / "clone-d"
        self.git("clone", "-q", str(bare), str(clone_c), cwd=work)
        self.git("clone", "-q", str(bare), str(clone_d), cwd=work)

        # pick a skill without level-change events so journal replay cannot mask the edit
        changed_skills = {
            (event.get("payload") or {}).get("skill")
            for event in self.journal(proj)
            if event["kind"] in ("level_change", "decayed", "l3_granted")
        }
        base = json.loads((clone_c / ".learnark" / "state" / "skills.json").read_text(encoding="utf-8"))
        target = next(skill["id"] for skill in base["skills"] if skill["id"] not in changed_skills)
        for clone, level in ((clone_c, 1), (clone_d, 2)):
            path = clone / ".learnark" / "state" / "skills.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            next(skill for skill in data["skills"] if skill["id"] == target)["level"] = level
            data["version"] = int(data.get("version", 0)) + 1
            write_json(path, data)

        self.assertIn("pushed=yes", self.cli(["sync", "--project", str(clone_c)], clone_c)["out"])
        d_head_before = self.git("rev-parse", "HEAD", cwd=clone_d).strip()
        conflict = self.cli(["sync", "--project", str(clone_d)], clone_d, expect=3)
        self.assertIn("conflict", conflict["out"].lower(), conflict["out"])
        self.assertIn("skills.json", conflict["out"], conflict["out"])
        self.assertIn("sync --recover", conflict["out"], conflict["out"])
        self.assertIn("force push", conflict["out"], conflict["out"])

        # the local commit and its data are preserved; the remote keeps the other side
        d_head_after = self.git("rev-parse", "HEAD", cwd=clone_d).strip()
        self.assertNotEqual(d_head_after, d_head_before, "sync must commit the local change before pulling")
        ancestor = subprocess.run(
            ["git", "-C", str(clone_d), "merge-base", "--is-ancestor", d_head_before, "HEAD"],
            env=make_env(None),
            capture_output=True,
        )
        self.assertEqual(ancestor.returncode, 0, "the pre-sync local history must still be an ancestor")
        local_head = json.loads(self.git("show", "HEAD:.learnark/state/skills.json", cwd=clone_d))
        self.assertEqual(next(skill for skill in local_head["skills"] if skill["id"] == target)["level"], 2)
        branch = self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=bare).strip()
        remote_head = json.loads(self.git("show", f"{branch}:.learnark/state/skills.json", cwd=bare))
        self.assertEqual(next(skill for skill in remote_head["skills"] if skill["id"] == target)["level"], 1)
        unmerged = self.git("diff", "--name-only", "--diff-filter=U", cwd=clone_d).strip()
        self.assertEqual(unmerged, "", "the rebase must be aborted, not left half-merged")

        status = self.status_json(clone_d)
        self.assertEqual(status["sync"]["state"], "conflict", status["sync"])
        self.assertTrue(status["sync"]["diverged"])
        doctor = self.cli(["doctor", "--project", str(clone_d)], clone_d, expect=3)
        self.assertIn("git_divergence", doctor["out"], doctor["out"])

    def test_sync_excludes_secrets_locks_usage_and_logs(self):
        proj = self.init_project("git-secrets")
        secret = "sk-reliability-should-never-be-committed"
        (proj / ".env").write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
        (proj / "credentials.json").write_text(f'{{"token": "{secret}"}}\n', encoding="utf-8")
        (proj / "api.key").write_text(secret + "\n", encoding="utf-8")
        (proj / ".learnark" / "usage.jsonl").write_text(f'{{"note": "{secret}"}}\n', encoding="utf-8")
        (proj / "sessions" / "debug.log").write_text(secret + "\n", encoding="utf-8")
        (proj / ".learnark" / "state" / "custom.lock").write_text("pid=1\n", encoding="utf-8")
        (proj / "artifacts").mkdir(exist_ok=True)
        (proj / "artifacts" / "notes.md").write_text("legit artifact\n", encoding="utf-8")

        self.cli(["start", "--minutes", "20"], proj)
        sync = self.cli(["sync", "--project", str(proj)], proj)
        self.assertIn("written=yes", sync["out"], sync["out"])
        tracked = self.git("ls-files", cwd=proj).splitlines()
        self.assertIn("artifacts/notes.md", tracked)
        self.assertIn(".learnark/journal/events.jsonl", tracked)
        for forbidden in (".env", "credentials.json", "api.key", "usage.jsonl", "debug.log", "custom.lock", "project.lock"):
            self.assertFalse(
                any(path == forbidden or path.endswith("/" + forbidden) for path in tracked),
                f"{forbidden} must never be committed (tracked: {tracked})",
            )
        for path in tracked:
            blob = subprocess.run(
                ["git", "-C", str(proj), "show", f"HEAD:{path}"],
                env=make_env(None),
                capture_output=True,
            )
            self.assertEqual(blob.returncode, 0, path)
            self.assertNotIn(secret.encode(), blob.stdout, f"secret leaked into tracked file {path}")
        gitignore = (proj / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("usage.jsonl", "*.lock", "*.log", ".env"):
            self.assertIn(pattern, gitignore)

    def test_clean_clone_restores_skills_cards_and_next_step(self):
        work = self.fresh("git-clone-work")
        bare = self.make_bare(work)
        proj = self.init_project("git-clone-proj")
        self.cli(["start", "--minutes", "20"], proj)
        self.cli(["say", READ_ANSWER], proj)
        self.cli(["pause"], proj)
        self.git("remote", "add", "origin", str(bare), cwd=proj)
        self.assertIn("pushed=yes", self.cli(["sync", "--project", str(proj)], proj)["out"])

        expected_skills = {skill["id"]: skill["level"] for skill in self.read_state(proj, "skills")["skills"]}
        expected_cards = {card["id"]: card["step"] for card in self.read_state(proj, "cards")["cards"]}
        expected_next = self.status_json(proj)["next"]

        clone = work / "clone"
        self.git("clone", "-q", str(bare), str(clone), cwd=work)
        restored = self.status_json(clone)
        self.assertEqual(restored["variant"], "direction-d-tempo")
        self.assertEqual({skill["id"]: skill["level"] for skill in restored["skills"]}, expected_skills)
        self.assertEqual({card["id"]: card["step"] for card in self.read_state(clone, "cards")["cards"]}, expected_cards)
        self.assertTrue(restored["next"]["activity_type"], restored["next"])
        self.assertEqual(restored["next"]["activity_id"], expected_next["activity_id"])
        self.assertTrue(restored["handoff"].get("next"), restored["handoff"])

        started = self.cli(["start", "--minutes", "10", "--project", str(clone)], clone)
        self.assertIn("上次停在哪", started["out"], started["out"])
        after = self.status_json(clone)
        self.assertGreaterEqual(after["today"]["items_started"], 1)
        self.assertIn(after["sync"]["state"], ("written", "pushed", "committed-local", "no-remote", "clean"))

    def test_crlf_artifact_bytes_survive_sync_and_clone(self):
        work = self.fresh("git-crlf-work")
        bare = self.make_bare(work)
        proj = self.init_project("git-crlf-proj")
        payload = "# 笔记\r\nline one\r\n中文行\r\nlast line without newline"
        artifact = proj / "artifacts" / "notes-crlf.md"
        artifact.write_bytes(payload.encode("utf-8"))
        self.git("remote", "add", "origin", str(bare), cwd=proj)
        self.assertIn("pushed=yes", self.cli(["sync", "--project", str(proj)], proj)["out"])

        clone = work / "clone"
        self.git("clone", "-q", str(bare), str(clone), cwd=work)
        self.assertEqual((clone / "artifacts" / "notes-crlf.md").read_bytes(), payload.encode("utf-8"))
        self.assertIn("* -text", (proj / ".gitattributes").read_text(encoding="utf-8"))
        self.assertIn("* -text", (clone / ".gitattributes").read_text(encoding="utf-8"))
        blob = subprocess.run(
            ["git", "-C", str(clone), "show", "HEAD:artifacts/notes-crlf.md"],
            env=make_env(None),
            capture_output=True,
        )
        self.assertEqual(blob.stdout, payload.encode("utf-8"), "CRLF/UTF-8 bytes must be stored verbatim")


# --------------------------------------------------------------------------------------
# 6. simulated clock: SRS due / leech / backlog / determinism
# --------------------------------------------------------------------------------------


class SimulatedClockTests(ReliabilityBase):
    def test_srs_due_leech_simulated_and_leech_filtered_from_short_budget(self):
        proj = self.init_project("srs")
        clock.simulate(NOW0)
        try:
            store = tempo.Store(proj).load()
            card = store.card("card-0001")
            card.update(
                {"step": 3, "ease": 1.0, "due_at": NOW0, "lapses": 0, "consecutive_lapses": 0, "leech": False}
            )
            store.touch("cards")
            first = tempo.grade_card(card, "again", NOW0)
            self.assertEqual(first["step"], 1)
            self.assertEqual(card["due_at"], day(1))
            self.assertEqual(card["lapses"], 1)
            self.assertFalse(card["leech"])
            second = tempo.grade_card(card, "again", day(1))
            self.assertTrue(card["leech"] and card["needs_rewrite"])
            self.assertTrue(second["new_leech"])
            self.assertEqual(card["due_at"], day(2))
            self.assertEqual(card["consecutive_lapses"], 2)
            store.save()

            candidate = tempo.candidate(
                activity_id="recall-card-0001",
                activity_type="recall_card",
                skill="agent-loop",
                skill_title="Agent 循环",
                skill_level=2,
                minutes=5,
                tier=1,
                source="due_card",
                template_id="agent-dev",
                label="到期卡",
                task="复习",
                due_at=day(1),
                overdue=1,
                leech=True,
                card_id="card-0001",
            )
            short = tempo.select_activities([dict(candidate)], 5)
            self.assertTrue(short["fallback"], short)
            self.assertTrue(any("leech" in row["reason"] for row in short["rows"]), short["rows"])
            long = tempo.select_activities([dict(candidate)], 10)
            self.assertEqual(long["chosen"]["activity_id"], "recall-card-0001", long)

            store.append("reliability_probe", {"note": "simulated clock"}, dedupe_key="probe:simulated:1")
            event = store.events("reliability_probe")[-1]
            self.assertTrue(event["simulated"], "events written under LEARNARK_NOW must be marked simulated")

            clock.simulate(day(3))
            later = tempo.Store(proj).load()
            due_ids = [item["id"] for item in later.due_cards()]
            self.assertIn("card-0001", due_ids, "the lapsed card must be due again by day 3")
            overdue = next(item for item in later.due_cards() if item["id"] == "card-0001")
            self.assertGreaterEqual(tempo.overdue_days(overdue["due_at"]), 1)
            self.assertTrue(all(event["simulated"] for event in later.events()), "every simulated event must stay marked")
        finally:
            clock.simulate(None)

    def test_backlog_folding_is_deterministic_under_simulated_clock(self):
        proj = self.init_project("backlog")
        copy = self.base / "backlog-copy"
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(proj, copy)
        for target in (proj, copy):
            path = target / ".learnark" / "state" / "cards.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            for card in data["cards"]:
                card["due_at"] = day(-1)
            extra = dict(data["cards"][0])
            extra.update({"id": "card-9998", "front": "额外积压卡", "source_event": "test:seed"})
            data["cards"].append(extra)
            write_json(path, data)

        results = []
        clock.simulate(NOW0)
        try:
            for target in (proj, copy):
                store = tempo.Store(target).load()
                day_state = tempo.prepare_day(store)
                store.save()
                folded = [
                    (event["payload"]["card"], event["payload"]["due_at"])
                    for event in store.events("backlog_folded")
                ]
                due_after = [card["id"] for card in store.due_cards()]
                results.append((sorted(folded), sorted(due_after), day_state["notes"]))
        finally:
            clock.simulate(None)

        self.assertEqual(results[0][0], results[1][0], "the same state must fold exactly the same cards")
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(len(results[0][0]), 1, results[0][0])
        self.assertLessEqual(len(results[0][1]), 12)
        self.assertTrue(any("顺延 3 天" in note for note in results[0][2]), results[0][2])
        events = [event for event in self.journal(proj) if event["kind"] == "backlog_folded"]
        self.assertTrue(events and all(event["simulated"] for event in events))

    def test_two_identical_copies_schedule_byte_identically(self):
        proj = self.init_project("determinism")
        self.cli(["start", "--minutes", "20"], proj)
        self.cli(["pause"], proj)
        clone_a = self.base / "determinism-a"
        clone_b = self.base / "determinism-b"
        for target in (clone_a, clone_b):
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(proj, target)
        a = self.cli(["start", "--minutes", "20", "--project", str(clone_a)], clone_a, now=NOW0)
        b = self.cli(["start", "--minutes", "20", "--project", str(clone_b)], clone_b, now=NOW0)
        self.assertEqual(a["out"], b["out"], "identical state + clock must produce identical scheduling output")
        session_a = self.read_state(clone_a, "schedule")["current_session"]
        session_b = self.read_state(clone_b, "schedule")["current_session"]
        self.assertEqual(session_a["activity"], session_b["activity"])
        decisions_a = [e["payload"] for e in self.journal(clone_a) if e["kind"] == "schedule_decision"][-1]
        decisions_b = [e["payload"] for e in self.journal(clone_b) if e["kind"] == "schedule_decision"][-1]
        self.assertEqual(decisions_a["decision_id"], decisions_b["decision_id"])
        self.assertEqual(decisions_a["chosen"], decisions_b["chosen"])


# --------------------------------------------------------------------------------------
# 7. secrets audit
# --------------------------------------------------------------------------------------


class SecretsAuditTests(ReliabilityBase):
    def test_api_key_never_persisted_in_project_or_archive(self):
        secret = "sk-audit-1234567890-should-not-persist"
        extra = {"DEEPSEEK_API_KEY": secret, "LEARNARK_API_KEY": ""}
        proj = self.init_project("secrets", extra=extra)
        self.cli(["start", "--minutes", "20"], proj, extra=extra)
        self.cli(["say", READ_ANSWER], proj, extra=extra)
        self.cli(["pause"], proj, extra=extra)
        self.cli(["sync", "--project", str(proj)], proj, extra=extra)
        archive = self.base / "secrets-export.md"
        self.cli(["export", "--out", str(archive), "--project", str(proj)], proj, extra=extra)
        payload = self.status_json(proj)
        self.assertTrue(payload["offline"], payload)
        self.assertEqual(payload["model"]["last"], "mock")

        for path in proj.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            self.assertNotIn(secret.encode(), path.read_bytes(), f"API key leaked into {path}")
        self.assertNotIn(secret.encode(), archive.read_bytes(), "API key leaked into the exported archive")

        for tracked in self.git("ls-files", cwd=proj).splitlines():
            blob = subprocess.run(
                ["git", "-C", str(proj), "show", f"HEAD:{tracked}"],
                env=make_env(None),
                capture_output=True,
            )
            self.assertNotIn(secret.encode(), blob.stdout, f"API key leaked into committed file {tracked}")

    def test_token_named_artifacts_are_committed_but_secrets_stay_blocked(self):
        """Regression for core C1 (fixed in vendored core 1.0.4).

        Core 1.0.2 matched ``token``/``secret`` anywhere in a path, so legitimate
        learned artifacts such as ``artifacts/token-budget.md`` were silently never
        committed. 1.0.4 narrows SECRET_PATTERNS to credential-shaped basenames; this
        test pins both halves: token-named *documents* sync, credentials do not.
        """
        secret = "sk-core104-token-artifact-audit"
        proj = self.init_project("token-artifact")
        (proj / "artifacts").mkdir(exist_ok=True)
        (proj / "artifacts" / "token-budget.md").write_text("token budget notes\n", encoding="utf-8")
        (proj / "artifacts" / "token-usage-notes.md").write_text("legit token notes\n", encoding="utf-8")
        (proj / ".env").write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
        (proj / "api.key").write_text(secret + "\n", encoding="utf-8")
        (proj / ".learnark" / "usage.jsonl").write_text(f'{{"note": "{secret}"}}\n', encoding="utf-8")

        sync = self.cli(["sync", "--project", str(proj)], proj)
        self.assertIn("committed=yes", sync["out"], sync["out"])
        tracked = self.git("ls-files", cwd=proj).splitlines()
        self.assertIn("artifacts/token-budget.md", tracked, "token-named docs must be committable")
        self.assertIn("artifacts/token-usage-notes.md", tracked)
        for forbidden in (".env", "api.key", "usage.jsonl"):
            self.assertFalse(
                any(path == forbidden or path.endswith("/" + forbidden) for path in tracked),
                f"{forbidden} must stay blocked, tracked={tracked}",
            )
        for path in tracked:
            blob = subprocess.run(
                ["git", "-C", str(proj), "show", f"HEAD:{path}"],
                env=make_env(None),
                capture_output=True,
            )
            self.assertNotIn(secret.encode(), blob.stdout, f"secret leaked into {path}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
