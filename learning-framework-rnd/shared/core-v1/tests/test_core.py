"""Core self-tests: durability, dedupe, CAS, locks, git states, mentor block parsing.

Run: python shared/core-v1/tests/test_core.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))

from learncore import clock, events, fsutil, llm, mentor, store, sync  # noqa: E402


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.journal = events.Journal(self.root / ".learnark" / "journal" / "events.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_dedupe_prevents_double_count(self):
        first = self.journal.append("attempt", {"score": 1}, dedupe_key="attempt:abc")
        second = self.journal.append("attempt", {"score": 1}, dedupe_key="attempt:abc")
        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(self.journal.of_kind("attempt")), 1)
        self.assertEqual(first["seq"], 1)

    def test_sequence_increases_and_integrity_ok(self):
        for i in range(3):
            self.journal.append("note", {"i": i})
        integrity = self.journal.integrity()
        self.assertEqual(integrity["events"], 3)
        self.assertEqual(integrity["problems"], [])

    def test_torn_tail_is_ignored(self):
        self.journal.append("note", {"i": 1})
        path = self.root / ".learnark" / "journal" / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"id": "x", "kind": "no')
        self.assertEqual(len(self.journal.all()), 1)

    def test_corrupt_dedupe_index_is_rebuilt(self):
        self.journal.append("attempt", {"n": 1}, dedupe_key="k1")
        index = self.root / ".learnark" / "journal" / "dedupe.json"
        index.write_text("{not json", encoding="utf-8")
        duplicate = self.journal.append("attempt", {"n": 1}, dedupe_key="k1")
        self.assertIsNone(duplicate)
        self.assertEqual(len(self.journal.all()), 1)

    def test_append_after_torn_tail_keeps_new_event(self):
        """Regression: a partial last line must not swallow the next append."""
        self.journal.append("note", {"i": 1})
        path = self.root / ".learnark" / "journal" / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write('{"id": "torn", "kind": "no')
        event = self.journal.append("note", {"i": 2}, dedupe_key="after-torn")
        self.assertIsNotNone(event)
        events = self.journal.all()
        self.assertEqual([e["payload"]["i"] for e in events], [1, 2])
        self.assertEqual(events[-1]["dedupe_key"], "after-torn")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "plan.json"
        self.doc = store.Document(self.path, lambda: {"items": []})

    def tearDown(self):
        self.tmp.cleanup()

    def test_version_bumps(self):
        saved = self.doc.save({"items": ["a"]}, expected_version=0)
        self.assertEqual(saved["version"], 1)
        self.assertEqual(self.doc.version(), 1)

    def test_stale_write_rejected(self):
        self.doc.save({"items": ["a"]}, expected_version=0)
        with self.assertRaises(fsutil.StaleWrite):
            self.doc.save({"items": ["b"]}, expected_version=0)

    def test_corrupt_document_recovers_from_backup(self):
        self.doc.save({"items": ["a"]}, expected_version=0)
        self.doc.save({"items": ["b"]}, expected_version=1)
        self.path.write_text("{broken", encoding="utf-8")
        value = self.doc.load()
        self.assertEqual(value["items"], ["b"])
        self.assertTrue(self.doc.repair_note())

    def test_atomic_write_never_leaves_temp_files(self):
        self.doc.save({"items": ["x"]}, expected_version=0)
        leftovers = [p.name for p in self.path.parent.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])


class ClockTests(unittest.TestCase):
    def tearDown(self):
        clock.simulate(None)

    def test_simulation_is_flagged(self):
        clock.simulate("2026-01-01T20:00:00+08:00")
        self.assertTrue(clock.is_simulated())
        self.assertTrue(clock.now_iso().startswith("2026-01-01T20:00"))
        clock.simulate(None)
        self.assertFalse(clock.is_simulated())


class MentorTests(unittest.TestCase):
    def test_extract_valid_block(self):
        raw = 'Good try.\n```learn-update\n{"help_level": 2, "attempt": {"correct": false}}\n```'
        text, updates, err = mentor.extract_update(raw)
        self.assertEqual(err, "")
        self.assertEqual(updates["help_level"], 2)
        self.assertNotIn("learn-update", text)

    def test_extract_invalid_block_is_reported(self):
        raw = "ok\n```learn-update\n{help_level: 2,}\n```"
        text, updates, err = mentor.extract_update(raw)
        self.assertIsNone(updates)
        self.assertIn("invalid", err)

    def test_no_block(self):
        text, updates, err = mentor.extract_update("plain reply")
        self.assertEqual((text, updates, err), ("plain reply", None, ""))

    def test_validate_help_level(self):
        self.assertTrue(mentor.validate_updates({"help_level": 9}))
        self.assertEqual(mentor.validate_updates({"help_level": 1}), [])


class MockLLMTests(unittest.TestCase):
    def test_scripted_replies(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        script = Path(tmp.name) / "script.jsonl"
        script.write_text(
            json.dumps({"match": "hello", "reply": "first"}) + "\n" + json.dumps({"reply": "second"}) + "\n",
            encoding="utf-8",
        )
        mock = llm.MockLLM(script)
        self.assertEqual(mock.chat([{"role": "user", "content": "hello there"}]).text, "first")
        self.assertEqual(mock.chat([{"role": "user", "content": "again"}]).text, "second")
        self.assertEqual(mock.chat([{"role": "user", "content": "x"}]).mode, "mock")


class GitSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "proj"
        self.remote = Path(self.tmp.name) / "remote.git"
        self.root.mkdir()
        (self.root / "notes").mkdir()
        (self.root / "notes" / "a.md").write_text("hello", encoding="utf-8")
        (self.root / ".env").write_text("SECRET=1", encoding="utf-8")
        self.git = sync.GitSync(self.root, include=["."])

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *args, cwd=None):
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd or self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    def test_subprocess_does_not_require_remote(self):
        self.git.ensure_repository()
        self.assertTrue(self.git.is_repo())

    def test_secrets_never_staged(self):
        self.git.ensure_repository()
        report = self.git.sync("first")
        self.assertEqual(report.state, "no-remote")
        self.assertTrue(report.committed)
        staged = self._git("ls-files").stdout
        self.assertIn("notes/a.md", staged)
        self.assertNotIn(".env", staged)

    def test_local_remote_push_and_clean_clone(self):
        bare = self.remote
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        self.git.ensure_repository()
        self._git("remote", "add", "origin", str(bare))
        report = self.git.sync("round1")
        self.assertEqual(report.state, "pushed", msg=report.recovery)
        self.assertTrue(report.pushed)
        clone = Path(self.tmp.name) / "clone"
        subprocess.run(["git", "clone", "-q", str(bare), str(clone)], check=True)
        self.assertTrue((clone / "notes" / "a.md").exists())

    def test_second_sync_is_clean(self):
        bare = self.remote
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        self.git.ensure_repository()
        self._git("remote", "add", "origin", str(bare))
        self.git.sync("one")
        second = self.git.sync("two")
        self.assertIn(second.state, ("pushed", "clean"))
        self.assertFalse(second.committed)

    def test_modified_file_paths_keep_status_column(self):
        """Regression: porcelain ' M path' must not lose its leading space."""
        self.git.ensure_repository()
        self._git("add", "-A")
        self._git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
        (self.root / "notes" / "a.md").write_text("changed", encoding="utf-8")
        changed = self.git.changed_paths()
        self.assertIn("notes/a.md", changed)
        bare = self.remote
        subprocess.run(["git", "init", "--bare", "-q", str(bare)], check=True)
        self._git("remote", "add", "origin", str(bare))
        self.git.sync("first")
        (self.root / "notes" / "a.md").write_text("changed again", encoding="utf-8")
        second = self.git.sync("second")
        self.assertIn(second.state, ("pushed",), msg=second.recovery)
        self.assertIn("notes/a.md", second.files)


class GitDivergenceTests(unittest.TestCase):
    """Two devices appending to the same journal must be mergeable without data loss."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.remote = base / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        self.a = base / "device-a"
        self.b = base / "device-b"
        self.a.mkdir()
        (self.a / ".learnark" / "journal").mkdir(parents=True)
        (self.a / "notes.md").write_text("start", encoding="utf-8")
        self.git_a = sync.GitSync(self.a, include=["."])
        self.git_a.ensure_repository()
        self.git_a.run("config", "user.name", "A")
        self.git_a.run("config", "user.email", "a@example.com")
        self._append(self.a, {"id": "ev_a1", "seq": 1, "at": "2026-01-01T10:00:00+08:00", "kind": "note", "dedupe_key": "k1", "payload": {}})
        self.git_a.run("add", "-A")
        self.git_a.run("commit", "-q", "-m", "base")
        self.git_a.run("remote", "add", "origin", str(self.remote))
        self.git_a.run("push", "-u", "origin", "HEAD")
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.b)], check=True)
        self.git_b = sync.GitSync(self.b, include=["."])
        self.git_b.run("config", "user.name", "B")
        self.git_b.run("config", "user.email", "b@example.com")

    def tearDown(self):
        self.tmp.cleanup()

    def _append(self, root: Path, event: dict) -> None:
        path = root / ".learnark" / "journal" / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _events(self, root: Path) -> list[dict]:
        path = root / ".learnark" / "journal" / "events.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def test_diverged_journals_union_merge_and_push(self):
        self._append(self.a, {"id": "ev_a2", "seq": 2, "at": "2026-01-02T10:00:00+08:00", "kind": "note", "dedupe_key": "k2", "payload": {"device": "a"}})
        report_a = self.git_a.sync("a second")
        self.assertEqual(report_a.state, "pushed", msg=report_a.recovery)
        self._append(self.b, {"id": "ev_b2", "seq": 2, "at": "2026-01-02T11:00:00+08:00", "kind": "note", "dedupe_key": "k3", "payload": {"device": "b"}})
        report_b = self.git_b.sync("b second")
        self.assertEqual(report_b.state, "pushed", msg=(report_b.recovery, report_b.detail))
        ids = {event["id"] for event in self._events(self.b)}
        self.assertEqual(ids, {"ev_a1", "ev_a2", "ev_b2"})
        # dedupe index rebuilt and consistent
        index = json.loads((self.b / ".learnark" / "journal" / "dedupe.json").read_text(encoding="utf-8"))
        self.assertEqual(set(index), {"k1", "k2", "k3"})
        # the other device can pull the merged history
        pull = self.git_a.pull_rebase()
        self.assertTrue(pull["ok"], msg=pull)
        self.assertEqual({event["id"] for event in self._events(self.a)}, {"ev_a1", "ev_a2", "ev_b2"})

    def test_recover_reports_conflict_on_state_file(self):
        (self.a / ".learnark" / "state").mkdir(parents=True, exist_ok=True)
        (self.a / ".learnark" / "state" / "plan.json").write_text('{"version": 1, "step": "a"}\n', encoding="utf-8")
        self.git_a.run("add", "-A")
        self.git_a.run("commit", "-q", "-m", "state a")
        self.git_a.run("push")
        (self.b / ".learnark" / "state").mkdir(parents=True, exist_ok=True)
        (self.b / ".learnark" / "state" / "plan.json").write_text('{"version": 1, "step": "b"}\n', encoding="utf-8")
        self.git_b.run("add", "-A")
        self.git_b.run("commit", "-q", "-m", "state b")
        (self.a / ".learnark" / "state" / "plan.json").write_text('{"version": 2, "step": "a2"}\n', encoding="utf-8")
        self.git_a.run("add", "-A")
        self.git_a.run("commit", "-q", "-m", "state a2")
        self.git_a.run("push")
        report = self.git_b.sync("b conflict")
        self.assertEqual(report.state, "conflict", msg=report.detail)
        self.assertIn("plan.json", (report.detail or "") + (report.recovery or ""))
        self.assertFalse(report.pushed)

    def test_gitignore_and_attributes_prevent_dirty_tree(self):
        self.git_a.ensure_repository()
        attributes = (self.a / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("-text", attributes)
        (self.a / ".learnark" / "state.lock").write_text("pid", encoding="utf-8")
        (self.a / ".learnark" / "usage.jsonl").write_text("{}\n", encoding="utf-8")
        changed = self.git_a.changed_paths()
        self.assertNotIn(".learnark/state.lock", changed)
        self.assertNotIn(".learnark/usage.jsonl", changed)
        staged = self.git_a.commit("locks should not be staged")
        self.assertFalse(staged.get("committed"), msg=staged)

    def test_secret_patterns_match_credentials_not_content_words(self):
        blocked = [".env", ".env.local", "state/credentials.json", "notes/secret-plan.md", "keys/id.key", "api-token", "artifacts/usage.jsonl", "notes_token.txt", "tokens.json"]
        allowed = ["README.md", "artifacts/token-budget.md", "notes/tokenization.md", "sessions/2026-01-01.md", "artifacts/sauce-recipe.md"]
        for path in blocked:
            self.assertTrue(self.git_a.blocked(path), msg=f"should be blocked: {path}")
        for path in allowed:
            self.assertFalse(self.git_a.blocked(path), msg=f"should be allowed: {path}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
