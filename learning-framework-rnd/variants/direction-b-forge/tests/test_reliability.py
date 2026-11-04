#!/usr/bin/env python3
"""Forge 可靠性与记忆测试（标准库 unittest；默认 mock LLM；无网络）。

运行：
    python tests/test_reliability.py -v
    python -m unittest tests.test_reliability -v

覆盖：中断/半写（快照 .bak、journal 尾行、事件已落盘但快照未落盘）、重复
artifact/review/defense、两进程并发、文档与命令级 CAS、Git 分叉恢复/快照冲突/
无远程/干净克隆/密钥与锁、模拟时钟、秘密审计。

所有测试使用独立临时目录与 `LEARNARK_LLM=mock`；不读真实 API key、不联网。
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
ENTRY = RUNTIME / "learn.py"
PY = sys.executable
GIT = shutil.which("git")

sys.path.insert(0, str(RUNTIME))
import learn as learn_mod  # noqa: E402
import forge_state as fs  # noqa: E402
from learncore import cli as core_cli  # noqa: E402
from learncore.fsutil import StaleWrite  # noqa: E402
from learncore.store import Document  # noqa: E402

SECRET = "sk-test-SECRET-1234567890"


def _force_remove(func, path, exc_info=None):
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass
    try:
        func(path)
    except OSError:
        pass


def _rmtree(path: Path) -> None:
    try:
        shutil.rmtree(path, onexc=_force_remove)
    except TypeError:  # Python < 3.12
        shutil.rmtree(path, onerror=_force_remove)
    except OSError:
        pass


def update_block(update: dict, text: str = "导师回复正文。") -> str:
    return text + "\n\n```learn-update\n" + json.dumps(update, ensure_ascii=False) + "\n```"


def coach_update(next_text: str = "继续当前任务") -> dict:
    return {
        "mentor": "coach",
        "help_level": 0,
        "attempt": {},
        "misconception": None,
        "next": next_text,
        "mastery_delta": 0,
    }


def critic_update(scores: dict[str, int] | None = None) -> dict:
    scores = scores or {"runnability": 3, "contract": 3, "robustness": 3, "explainability": 3}
    rubric = [
        {"dim": dim, "score": int(score), "note": f"{dim} 证据见第 {index + 5} 行"}
        for index, (dim, score) in enumerate(scores.items())
    ]
    return {
        "mentor": "critic",
        "help_level": 1,
        "attempt": {"activity_id": "m1-artifact-review", "correct": False},
        "misconception": None,
        "next": "按缺口改一处再 review",
        "mastery_delta": 0,
        "artifact": "artifacts/M1/agent.py",
        "milestone": "M1",
        "rubric": rubric,
        "gap": [],
    }


def defense_update(ok: bool = True) -> dict:
    questions = [
        {
            "qid": "m1-q1",
            "dim": "contract",
            "question": "如果模型不支持 tool_calls，你的循环怎么改？",
            "answer": "把 tool_calls 解析抽成适配层，退化到纯 JSON 协议" if ok else "我理解了设计",
            "evidence_line": 6 if ok else 1,
            "ok": ok,
        },
        {
            "qid": "m1-q2",
            "dim": "runnability",
            "question": "把输入文件换成不存在的路径，这版会发生什么？",
            "answer": "工具返回 error observation 回填给模型，循环不崩" if ok else "我理解了设计",
            "evidence_line": 9 if ok else 1,
            "ok": ok,
        },
        {
            "qid": "m1-q3",
            "dim": "explainability",
            "question": "为什么步数上限是六而不是无限循环？",
            "answer": "用步数兜住模型反复调同一工具，超过就交回人工" if ok else "我理解了设计",
            "evidence_line": 12 if ok else 1,
            "ok": ok,
        },
    ]
    return {
        "mentor": "critic",
        "help_level": 0,
        "attempt": {},
        "misconception": None,
        "next": "进入 M2",
        "mastery_delta": 0,
        "defense": {"questions": questions},
    }


class ForgeReliabilityTest(unittest.TestCase):
    """Each test gets a fresh temp project and never touches the workspace."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-rel-"))
        self.proj = self.tmp / "proj"
        self._scripts = 0
        self._children: list[subprocess.Popen] = []
        self.addCleanup(self._cleanup)

    # ------------------------------------------------------------------ #
    # infrastructure
    # ------------------------------------------------------------------ #
    def _cleanup(self) -> None:
        for child in self._children:
            if child.poll() is None:
                child.kill()
            try:
                child.communicate(timeout=10)
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass
        _rmtree(self.tmp)

    def env(self, script: Path | None = None, extra: dict | None = None) -> dict:
        env = os.environ.copy()
        env.update({"LEARNARK_LLM": "mock", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
        for key in ("LEARNARK_NOW", "LEARNARK_MOCK_SCRIPT", "LEARNARK_LOCK_TIMEOUT"):
            env.pop(key, None)
        for key in ("DEEPSEEK_API_KEY", "LEARNARK_API_KEY"):
            env.pop(key, None)
        if script is not None:
            env["LEARNARK_MOCK_SCRIPT"] = str(script)
        if extra:
            for key, value in extra.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = str(value)
        env.setdefault("GIT_TERMINAL_PROMPT", "0")
        return env

    def run_cli(
        self,
        *args,
        cwd: Path | None = None,
        script: Path | None = None,
        extra_env: dict | None = None,
        input_text: str | None = None,
        timeout: int = 180,
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            [PY, str(ENTRY), *[str(arg) for arg in args]],
            cwd=str(cwd or self.tmp),
            env=self.env(script, extra_env),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=input_text,
            timeout=timeout,
        )

    def spawn(
        self,
        *args,
        cwd: Path | None = None,
        script: Path | None = None,
        extra_env: dict | None = None,
    ) -> subprocess.Popen:
        child = subprocess.Popen(
            [PY, str(ENTRY), *[str(arg) for arg in args]],
            cwd=str(cwd or self.tmp),
            env=self.env(script, extra_env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._children.append(child)
        return child

    def wait(self, child: subprocess.Popen, timeout: int = 120) -> tuple[int, str, str]:
        stdout, stderr = child.communicate(timeout=timeout)
        return child.returncode, stdout or "", stderr or ""

    def git(self, *args, cwd: Path | None = None) -> subprocess.CompletedProcess:
        assert GIT, "git is required for these tests"
        return subprocess.run(
            [GIT, *[str(arg) for arg in args]],
            cwd=str(cwd or self.tmp),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    def script(self, entries: list[tuple[str, str]]) -> Path:
        self._scripts += 1
        path = self.tmp / f"script-{self._scripts}.jsonl"
        lines = [json.dumps({"match": match, "reply": reply}, ensure_ascii=False) for match, reply in entries]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    # ------------------------------------------------------------------ #
    # project fixtures
    # ------------------------------------------------------------------ #
    def init(self, name: str = "proj", template: str = "agent-dev", goal: str = "Agent 开发") -> subprocess.CompletedProcess:
        proc = self.run_cli("init", "--goal", goal, "--dir", name, "--template", template)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return proc

    def start(self, cwd: Path | None = None, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        proc = self.run_cli("start", "--offline", cwd=cwd or self.proj, extra_env=extra_env)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        return proc

    def source(self, name: str = "agent.py", tag: str = "v1") -> Path:
        path = self.tmp / name
        lines = [f"# synthetic artifact {tag}"]
        lines += [f'STEP_{index} = "{tag}-{index}"' for index in range(1, 45)]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def add_artifact(self, name: str = "agent.py", tag: str = "v1", *, cwd: Path | None = None) -> subprocess.CompletedProcess:
        path = self.source(name, tag)
        return self.run_cli("artifact", "add", str(path), cwd=cwd or self.proj)

    def review(self, cwd: Path | None = None, scores: dict[str, int] | None = None, extra_env: dict | None = None) -> subprocess.CompletedProcess:
        return self.run_cli(
            "review",
            cwd=cwd or self.proj,
            script=self.script([("", update_block(critic_update(scores)))]),
            extra_env=extra_env,
        )

    def pass_m1(self, *, cwd: Path | None = None, extra_env: dict | None = None) -> dict:
        cwd = cwd or self.proj
        proc = self.review(cwd=cwd, extra_env=extra_env)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        proc = self.run_cli(
            "say",
            "我解释完了",
            cwd=cwd,
            script=self.script([("我解释完了", update_block(defense_update(True)))]),
            extra_env=extra_env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        status = self.run_cli("status", "--json", cwd=cwd, extra_env=extra_env)
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        return json.loads(status.stdout)

    # ------------------------------------------------------------------ #
    # state helpers
    # ------------------------------------------------------------------ #
    def read_json(self, rel: str, cwd: Path | None = None) -> dict:
        return json.loads(((cwd or self.proj) / rel).read_text(encoding="utf-8"))

    def journal(self, cwd: Path | None = None) -> list[dict]:
        path = (cwd or self.proj) / ".learnark/journal/events.jsonl"
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def events(self, kind: str | None = None, cwd: Path | None = None) -> list[dict]:
        events = self.journal(cwd)
        return [event for event in events if kind is None or event.get("kind") == kind]

    def append_raw_event(self, root: Path, event_id: str, marker: str) -> None:
        path = root / ".learnark/journal/events.jsonl"
        event = {
            "id": event_id,
            "seq": 9999,
            "at": "2026-11-04T03:00:00+08:00",
            "kind": "test_marker",
            "actor": "test",
            "simulated": True,
            "dedupe_key": f"test:{marker}",
            "payload": {"marker": marker},
        }
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    def make_remote(self) -> tuple[Path, Path, Path]:
        assert GIT, "git is required"
        bare = self.tmp / "bare.git"
        self.assertEqual(self.git("init", "--bare", str(bare)).returncode, 0)
        self.assertEqual(self.git("-C", str(self.proj), "remote", "add", "origin", str(bare)).returncode, 0)
        synced = self.run_cli("sync", "--message", "learn: initial", cwd=self.proj)
        self.assertEqual(synced.returncode, 0, synced.stderr + synced.stdout)
        clones = []
        for name in ("c1", "c2"):
            target = self.tmp / name
            proc = self.git("clone", str(bare), str(target))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.git("-C", str(target), "config", "user.email", "t@example.com")
            self.git("-C", str(target), "config", "user.name", "Tester")
            clones.append(target)
        return bare, clones[0], clones[1]

    # ------------------------------------------------------------------ #
    # 1. interrupted / torn state
    # ------------------------------------------------------------------ #
    def test_snapshot_torn_write_recovers_from_backup(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.add_artifact().returncode, 0)
        path = self.proj / ".learnark/state/artifacts.json"
        self.assertTrue(path.with_name("artifacts.json.bak").is_file(), "每次原子写都应保留 .bak")
        path.write_text('{"schema_version": 1, "items": [{"id": "a-M1-', encoding="utf-8")
        proc = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("恢复", proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["artifacts"]["count"], 1)
        json.loads(path.read_text(encoding="utf-8"))  # repaired in place
        doctor = self.run_cli("doctor", cwd=self.proj)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)

    def test_torn_journal_tail_is_ignored_and_next_append_survives(self) -> None:
        self.init()
        self.start()
        journal = self.proj / ".learnark/journal/events.jsonl"
        before = len(self.events())

        # (a) classic half line: no trailing newline.
        with open(journal, "a", encoding="utf-8") as handle:
            handle.write('{"id": "torn-event", "kind": "artifact_added", "seq"')
        proc = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        said = self.run_cli(
            "say",
            "撕裂后还能继续",
            cwd=self.proj,
            script=self.script([("撕裂后还能继续", update_block(coach_update("继续改作品")))]),
        )
        self.assertEqual(said.returncode, 0, said.stderr + said.stdout)
        events = self.journal()
        self.assertEqual(len(events), before + 2, "半行应被丢弃；say 应完整写入 learner_say + mentor_turn")
        self.assertTrue(any(event["kind"] == "learner_say" for event in events))
        self.assertFalse(any(event.get("id") == "torn-event" for event in events))
        index = json.loads((self.proj / ".learnark/journal/dedupe.json").read_text(encoding="utf-8"))
        self.assertTrue(any(key.startswith("say:") for key in index))

        # (b) invalid line *with* a trailing newline: same repair must apply.
        with open(journal, "a", encoding="utf-8") as handle:
            handle.write('{"kind": "torn", "seq":\n')
        artifact = self.source("after-torn.py", "after")
        proc = self.run_cli("artifact", "add", str(artifact), cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        status = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        events = self.journal()
        self.assertEqual(json.loads(status.stdout)["artifacts"]["count"], 1)
        self.assertTrue(all(event.get("kind") for event in events))
        doctor = self.run_cli("doctor", cwd=self.proj)
        self.assertEqual(doctor.returncode, 0, doctor.stdout + doctor.stderr)

    def test_corrupt_snapshot_without_backup_reports(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.add_artifact().returncode, 0)
        path = self.proj / ".learnark/state/artifacts.json"
        backup = path.with_name("artifacts.json.bak")
        if backup.exists():
            backup.unlink()
        path.write_text("{ definitely not json", encoding="utf-8")
        proc = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(proc.returncode, 3, proc.stderr + proc.stdout)
        self.assertIn("not valid JSON", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        started = self.run_cli("start", "--offline", cwd=self.proj)
        self.assertEqual(started.returncode, 3, started.stderr + started.stdout)
        self.assertIn("not valid JSON", started.stderr)

    def test_event_written_without_snapshot_is_replayed(self) -> None:
        """Simulate SIGKILL between artifact_added and artifacts.json save."""
        self.init()
        self.start()
        self.assertEqual(self.add_artifact("a.py", "a").returncode, 0)
        data = b"# ghost artifact\n" + b"x = 1\n" * 20
        sha = hashlib.sha256(data).hexdigest()
        dest = self.proj / "artifacts/M1/ghost.py"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        artifacts = self.read_json(".learnark/state/artifacts.json")
        artifacts["items"] = [item for item in artifacts["items"] if item["sha256"] != sha]
        artifacts["version"] = int(artifacts.get("version", 0)) + 1
        (self.proj / ".learnark/state/artifacts.json").write_text(
            json.dumps(artifacts, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        event = {
            "id": "ev_ghost",
            "seq": len(self.journal()) + 1,
            "at": "2026-11-04T12:00:00+08:00",
            "kind": "artifact_added",
            "actor": "runtime",
            "simulated": False,
            "dedupe_key": f"artifact:M1:{sha}",
            "payload": {
                "milestone": "M1",
                "sha256": sha,
                "size": len(data),
                "path": "ghost.py",
                "dest": "artifacts/M1/ghost.py",
                "source_path": "",
                "assisted_level": 0,
                "offline": True,
            },
        }
        with open(self.proj / ".learnark/journal/events.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        proc = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("恢复", proc.stderr)
        items = self.read_json(".learnark/state/artifacts.json")["items"]
        ghost = [item for item in items if item["sha256"] == sha]
        self.assertEqual(len(ghost), 1, "journal 中已落盘的作品必须回到快照")
        self.assertTrue(ghost[0].get("recovered"))
        self.assertEqual(ghost[0]["path"], "artifacts/M1/ghost.py")

    def test_review_written_without_snapshot_is_replayed(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.add_artifact().returncode, 0)
        self.assertEqual(self.review().returncode, 0)
        reviews_path = self.proj / ".learnark/state/reviews.json"
        for path in (reviews_path, reviews_path.with_name("reviews.json.bak")):
            if path.exists():
                path.unlink()
        proc = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("恢复", proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["reviews"]["count"], 1, "评审事件必须能重放出评审快照")
        self.assertTrue(payload["reviews"]["latest"]["id"].startswith("r-M1-"))
        self.assertEqual(payload["next"]["action"], "defend")
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    def test_unrecoverable_event_is_reported_not_silent(self) -> None:
        self.init()
        self.start()
        sha = hashlib.sha256(b"no such artifact").hexdigest()
        event = {
            "id": "ev_missing",
            "seq": len(self.journal()) + 1,
            "at": "2026-11-04T12:00:00+08:00",
            "kind": "artifact_added",
            "actor": "runtime",
            "simulated": False,
            "dedupe_key": f"artifact:M1:{sha}",
            "payload": {
                "milestone": "M1",
                "sha256": sha,
                "size": 15,
                "path": "missing.py",
                "dest": "artifacts/M1/missing.py",
                "source_path": str(self.tmp / "gone.py"),
                "assisted_level": 0,
            },
        }
        with open(self.proj / ".learnark/journal/events.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        status = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        self.assertIn("找不到", status.stderr)
        self.assertEqual(json.loads(status.stdout)["artifacts"]["count"], 0)
        doctor = self.run_cli("doctor", cwd=self.proj)
        self.assertEqual(doctor.returncode, 3, doctor.stdout + doctor.stderr)
        self.assertIn("journal/作品", doctor.stdout)

    def test_corrupt_dedupe_index_rebuilds(self) -> None:
        self.init()
        self.start()
        index = self.proj / ".learnark/journal/dedupe.json"
        index.write_text('{"broken":', encoding="utf-8")
        proc = self.run_cli(
            "say",
            "索引坏了也要能继续",
            cwd=self.proj,
            script=self.script([("索引坏了", update_block(coach_update()))]),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        data = json.loads(index.read_text(encoding="utf-8"))
        self.assertIsInstance(data, dict)
        self.assertGreater(len(data), 0)
        keys = [event.get("dedupe_key") for event in self.journal() if event.get("dedupe_key")]
        self.assertEqual(len(keys), len(set(keys)), "去重键不能重复")
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    # ------------------------------------------------------------------ #
    # 2. duplicates
    # ------------------------------------------------------------------ #
    def test_duplicate_artifact_add_is_idempotent(self) -> None:
        self.init()
        first = self.add_artifact()
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        for _ in range(2):
            again = self.add_artifact()
            self.assertEqual(again.returncode, 0, again.stderr + again.stdout)
            self.assertIn("已记录", again.stdout)
        artifacts = self.read_json(".learnark/state/artifacts.json")["items"]
        self.assertEqual(len(artifacts), 1)
        self.assertEqual(len(self.events("artifact_added")), 1)
        brief = self.read_json(".learnark/state/brief.json")
        self.assertEqual(len(brief["milestones"][0]["artifact_ids"]), 1)

    def test_duplicate_review_does_not_rescore(self) -> None:
        self.init()
        self.add_artifact()
        first = self.review()
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        review = self.read_json(".learnark/state/reviews.json")["items"][0]
        scores = {dim["dim"]: dim["score"] for dim in review["rubric"]}
        for _ in range(2):
            again = self.run_cli("review", cwd=self.proj)
            self.assertEqual(again.returncode, 0, again.stderr + again.stdout)
            self.assertIn("已记录", again.stdout)
        reviews = self.read_json(".learnark/state/reviews.json")["items"]
        self.assertEqual(len(reviews), 1)
        self.assertEqual(len(self.events("review_recorded")), 1)
        self.assertEqual({dim["dim"]: dim["score"] for dim in reviews[0]["rubric"]}, scores)
        event = self.events("review_recorded")[0]
        self.assertIn("review", event["payload"], "评审事件应携带完整快照以便重放")
        self.assertEqual(event["payload"]["review"]["id"], reviews[0]["id"])
        nxt = json.loads(self.run_cli("next", "--json", cwd=self.proj).stdout)
        self.assertEqual(nxt["action"], "defend")

    def test_duplicate_defense_does_not_double_pass(self) -> None:
        self.init()
        self.start()
        self.add_artifact()
        self.assertEqual(self.review().returncode, 0)
        script = self.script([("我解释完了", update_block(defense_update(True)))] * 3)
        for _ in range(3):
            proc = self.run_cli("say", "我解释完了", cwd=self.proj, script=script)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(len(self.events("defense_recorded")), 1)
        self.assertEqual(len(self.events("milestone_passed")), 1, "同一里程碑不能重复通过")
        data = json.loads(self.run_cli("status", "--json", cwd=self.proj).stdout)
        m1, m2 = data["milestones"][0], data["milestones"][1]
        self.assertEqual(m1["status"], "passed")
        self.assertEqual(m2["status"], "active")
        self.assertEqual(data["current_milestone"], "M2")
        self.assertEqual(len(self.read_json(".learnark/state/reviews.json")["items"]), 1)
        self.assertEqual(len(data["artifacts"]["items"]), 1)
        evidence = m1["pass_evidence"]
        self.assertTrue(evidence.get("artifact_id") and evidence.get("review_id") and evidence.get("defense_id"))
        self.assertEqual(len({evidence["artifact_id"], evidence["review_id"], evidence["defense_id"]}), 3)

    def test_defense_snapshot_behind_journal_is_replayed(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.add_artifact().returncode, 0)
        self.assertEqual(self.review().returncode, 0)
        failed = self.run_cli(
            "say",
            "我解释完了",
            cwd=self.proj,
            script=self.script([("我解释完了", update_block(defense_update(False)))]),
        )
        self.assertEqual(failed.returncode, 0, failed.stderr + failed.stdout)
        defense_path = self.proj / ".learnark/state/defense.json"
        stale = defense_path.read_bytes()
        passed = self.run_cli(
            "say",
            "我解释完了",
            cwd=self.proj,
            script=self.script([("我解释完了", update_block(defense_update(True)))]),
        )
        self.assertEqual(passed.returncode, 0, passed.stderr + passed.stdout)
        defense_path.write_bytes(stale)  # simulate crash before the passing defense was saved
        proc = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("恢复防御", proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["milestones"][0]["status"], "passed")
        self.assertEqual(payload["milestones"][0]["defense"]["status"], "passed", "journal 中较新的 defense 判定必须重放")
        self.assertEqual(payload["milestones"][0]["defense"]["ok_count"], 3)
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    def test_closed_gap_snapshot_behind_journal_is_replayed(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.add_artifact("v1.py", "v1").returncode, 0)
        first = self.review(scores={"runnability": 3, "contract": 2, "robustness": 3, "explainability": 3})
        self.assertEqual(first.returncode, 0, first.stderr + first.stdout)
        gaps_path = self.proj / ".learnark/state/gaps.json"
        stale = gaps_path.read_bytes()
        self.assertEqual(self.add_artifact("v2.py", "v2").returncode, 0)
        second = self.review()
        self.assertEqual(second.returncode, 0, second.stderr + second.stdout)
        closed = [gap for gap in self.read_json(".learnark/state/gaps.json")["items"] if gap["status"] == "closed"]
        self.assertTrue(closed, "第二次评审应关闭缺口")
        gaps_path.write_bytes(stale)  # simulate crash before the closure was saved
        proc = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("恢复缺口卡", proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["gaps"]["closed_count"], 1, "journal 已关闭的缺口不能被旧快照复活")
        card = next(gap for gap in self.read_json(".learnark/state/gaps.json")["items"] if gap["gap_id"] == "g-M1-contract")
        self.assertEqual(card["status"], "closed")
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    def test_session_turn_counter_behind_journal_is_replayed(self) -> None:
        self.init()
        self.start()
        script = self.script([
            ("第一次", update_block(coach_update("继续一"))),
            ("第二次", update_block(coach_update("继续二"))),
            ("第三次", update_block(coach_update("继续三"))),
        ])
        self.assertEqual(self.run_cli("say", "第一次", cwd=self.proj, script=script).returncode, 0)
        session_path = self.proj / ".learnark/state/session.json"
        stale = session_path.read_bytes()
        self.assertEqual(self.run_cli("say", "第二次", cwd=self.proj, script=script).returncode, 0)
        session_path.write_bytes(stale)  # simulate crash before the second say saved the session
        status = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        self.assertIn("会话语轮次", status.stderr)
        self.assertEqual(json.loads(status.stdout)["last_session"]["turns"], 3)
        self.assertEqual(self.read_json(".learnark/state/session.json")["turn_index"], 3)
        third = self.run_cli("say", "第三次", cwd=self.proj, script=script)
        self.assertEqual(third.returncode, 0, third.stderr + third.stdout)
        turns = [event["payload"].get("turn") for event in self.events("mentor_turn")]
        self.assertEqual(turns, [1, 2, 3, 4], "恢复后新回合必须使用新轮次，不能被去重索引吞掉")
        self.assertEqual(self.read_json(".learnark/state/session.json")["turn_index"], 4)

    # ------------------------------------------------------------------ #
    # 3. concurrency
    # ------------------------------------------------------------------ #
    def test_concurrent_artifact_adds_keep_both(self) -> None:
        self.init()
        one = self.source("one.py", "one")
        two = self.source("two.md", "two")
        p1 = self.spawn("artifact", "add", str(one), cwd=self.proj)
        p2 = self.spawn("artifact", "add", str(two), cwd=self.proj)
        code1, out1, err1 = self.wait(p1)
        code2, out2, err2 = self.wait(p2)
        self.assertEqual((code1, code2), (0, 0), f"并发登记应串行成功：\n{err1}\n{err2}")
        artifacts = self.read_json(".learnark/state/artifacts.json")["items"]
        self.assertEqual(len(artifacts), 2, "不能丢作品")
        self.assertEqual({item["sha256"] for item in artifacts}, {hashlib.sha256(one.read_bytes()).hexdigest(), hashlib.sha256(two.read_bytes()).hexdigest()})
        self.assertEqual(len(self.events("artifact_added")), 2)
        for item in artifacts:
            self.assertTrue((self.proj / item["path"]).is_file())
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    def test_concurrent_duplicate_artifact_add_counts_once(self) -> None:
        self.init()
        source = self.source("same.py", "same")
        p1 = self.spawn("artifact", "add", str(source), cwd=self.proj)
        p2 = self.spawn("artifact", "add", str(source), cwd=self.proj)
        code1, _, err1 = self.wait(p1)
        code2, _, err2 = self.wait(p2)
        self.assertEqual((code1, code2), (0, 0), f"{err1}\n{err2}")
        self.assertEqual(len(self.read_json(".learnark/state/artifacts.json")["items"]), 1)
        self.assertEqual(len(self.events("artifact_added")), 1)

    def test_concurrent_says_serialize(self) -> None:
        self.init()
        script = self.script([
            ("并发甲", update_block(coach_update("处理并发甲"))),
            ("并发乙", update_block(coach_update("处理并发乙"))),
        ])
        p1 = self.spawn("say", "并发甲", cwd=self.proj, script=script)
        p2 = self.spawn("say", "并发乙", cwd=self.proj, script=script)
        code1, out1, err1 = self.wait(p1)
        code2, out2, err2 = self.wait(p2)
        self.assertEqual((code1, code2), (0, 0), f"并发 say 应串行：\n{err1}\n{err2}")
        self.assertEqual(len(self.events("mentor_turn")), 2)
        self.assertEqual(len(self.events("learner_say")), 2)
        session = self.read_json(".learnark/state/session.json")
        self.assertEqual(session["turn_index"], 2)
        session_text = "".join(path.read_text(encoding="utf-8") for path in (self.proj / "sessions").glob("*.md"))
        self.assertEqual(session_text.count("## 学习者\n并发甲"), 1, "会话记录不能出现幽灵回合")
        self.assertEqual(session_text.count("## 学习者\n并发乙"), 1)
        keys = [event.get("dedupe_key") for event in self.journal() if event.get("dedupe_key")]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    def test_concurrent_artifact_add_and_review(self) -> None:
        self.init()
        self.assertEqual(self.add_artifact("first.py", "first").returncode, 0)
        second = self.source("second.py", "second")
        review_script = self.script([("", update_block(critic_update()))])
        p1 = self.spawn("artifact", "add", str(second), cwd=self.proj)
        p2 = self.spawn("review", cwd=self.proj, script=review_script)
        code1, out1, err1 = self.wait(p1)
        code2, out2, err2 = self.wait(p2)
        self.assertEqual(code1, 0, err1)
        self.assertEqual(code2, 0, err2)
        artifacts = self.read_json(".learnark/state/artifacts.json")["items"]
        self.assertEqual(len(artifacts), 2, "review 与 add 并发不能吞掉作品")
        reviews = self.read_json(".learnark/state/reviews.json")["items"]
        self.assertEqual(len(reviews), 1)
        reviewed_ids = set(reviews[0].get("artifact_ids") or [reviews[0].get("artifact_id")])
        self.assertTrue(reviewed_ids <= {item["id"] for item in artifacts})
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    def test_lock_timeout_is_clear_and_non_destructive(self) -> None:
        self.init()
        self.start()
        before = len(self.journal())
        ready = self.tmp / "lock-ready"
        holder = self.tmp / "hold_lock.py"
        holder.write_text(
            "import sys, time\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(RUNTIME)!r})\n"
            "from learncore.fsutil import file_lock\n"
            "with file_lock(sys.argv[1], timeout=10):\n"
            "    Path(sys.argv[2]).write_text('locked', encoding='utf-8')\n"
            "    time.sleep(1.8)\n",
            encoding="utf-8",
        )
        child = subprocess.Popen(
            [PY, str(holder), str(self.proj / ".learnark/write.lock"), str(ready)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._children.append(child)
        deadline = time.time() + 10
        while time.time() < deadline and not ready.exists():
            time.sleep(0.05)
        self.assertTrue(ready.exists(), "锁持有进程没有启动")
        blocked = self.run_cli(
            "status",
            "--json",
            cwd=self.proj,
            extra_env={"LEARNARK_LOCK_TIMEOUT": "0.3"},
        )
        self.assertEqual(blocked.returncode, 3, blocked.stderr + blocked.stdout)
        self.assertIn("another LearnArk process is writing", blocked.stderr)
        self.assertEqual(len(self.journal()), before, "拿不到锁时不能写状态")
        child.wait(timeout=20)
        after = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(after.returncode, 0, after.stderr + after.stdout)
        self.assertEqual(self.run_cli("doctor", cwd=self.proj).returncode, 0)

    # ------------------------------------------------------------------ #
    # 4. stale writes (CAS)
    # ------------------------------------------------------------------ #
    def test_document_cas_rejects_stale_save(self) -> None:
        path = self.tmp / "cas.json"
        document = Document(path, dict)
        document.save({"value": 1})
        document.save({"value": 2})
        with self.assertRaises(StaleWrite) as caught:
            document.save({"value": 3}, expected_version=1)
        self.assertIn("changed since it was read", str(caught.exception))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["value"], 2, "过期写入不能覆盖新值")
        self.assertEqual(data["version"], 2)

    def test_command_stale_write_aborts_and_journal_replays(self) -> None:
        self.init()
        self.assertEqual(self.add_artifact("a1.py", "a1").returncode, 0)
        project = fs.Project.find(str(self.proj))
        stale = learn_mod.load(project)
        self.assertEqual(self.add_artifact("a2.py", "a2").returncode, 0)  # another process wins
        third = self.source("a3.py", "a3")
        stderr = io.StringIO()
        with mock.patch.object(learn_mod, "load", lambda _project: stale):
            with contextlib.redirect_stderr(stderr):
                code = core_cli.main(lambda _argv: learn_mod.cmd_artifact(project, ["add", str(third)], True))
        self.assertEqual(code, 3, stderr.getvalue())
        self.assertIn("state changed concurrently", stderr.getvalue())
        self.assertIn("Re-run", stderr.getvalue())
        self.assertEqual(len(self.read_json(".learnark/state/artifacts.json")["items"]), 2)
        recovered = self.run_cli("status", "--json", cwd=self.proj)
        self.assertEqual(recovered.returncode, 0, recovered.stderr + recovered.stdout)
        self.assertIn("恢复", recovered.stderr)
        items = self.read_json(".learnark/state/artifacts.json")["items"]
        self.assertEqual(len(items), 3, "命令因 CAS 中止，但已落的 journal 事件必须在下次读到后补齐")
        self.assertTrue(any(item["path"].endswith("a3.py") and item.get("recovered") for item in items))
        self.assertTrue(any(item["path"].endswith("a2.py") for item in items), "外部写入不能被覆盖")

    # ------------------------------------------------------------------ #
    # 5. git
    # ------------------------------------------------------------------ #
    @unittest.skipUnless(GIT, "git not installed")
    def test_git_journal_divergence_recovers_without_force(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.run_cli("pause", "--note", "base", cwd=self.proj).returncode, 0)
        bare, c1, c2 = self.make_remote()
        self.append_raw_event(c1, "ev_c1_only", "c1")
        self.assertEqual(self.git("-C", str(c1), "add", ".learnark/journal/events.jsonl").returncode, 0)
        self.assertEqual(self.git("-C", str(c1), "commit", "-m", "c1 event").returncode, 0)
        self.assertEqual(self.git("-C", str(c1), "push").returncode, 0)
        c1_sha = self.git("-C", str(bare), "rev-parse", "HEAD").stdout.strip()
        self.append_raw_event(c2, "ev_c2_only", "c2")
        self.assertEqual(self.git("-C", str(c2), "add", ".learnark/journal/events.jsonl").returncode, 0)
        self.assertEqual(self.git("-C", str(c2), "commit", "-m", "c2 event").returncode, 0)
        proc = self.run_cli("sync", "--recover", cwd=c2)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertIn("recover=yes", proc.stdout)
        self.assertIn("pushed=yes", proc.stdout)
        remote = self.git("-C", str(bare), "show", "HEAD:.learnark/journal/events.jsonl")
        self.assertEqual(remote.returncode, 0, remote.stderr)
        self.assertIn("ev_c1_only", remote.stdout)
        self.assertIn("ev_c2_only", remote.stdout)
        seqs = [json.loads(line)["seq"] for line in remote.stdout.splitlines() if line.strip()]
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)), "合并后 seq 必须连续")
        ancestor = self.git("-C", str(bare), "merge-base", "--is-ancestor", c1_sha, "HEAD")
        self.assertEqual(ancestor.returncode, 0, "远程历史被重写（疑似 force push）")

    @unittest.skipUnless(GIT, "git not installed")
    def test_git_snapshot_conflict_exit3_lists_files_and_keeps_local(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.run_cli("pause", "--note", "base", cwd=self.proj).returncode, 0)
        bare, c1, c2 = self.make_remote()
        self.assertEqual(self.run_cli("say", "克隆一的发言", cwd=c1).returncode, 0)
        self.assertEqual(self.run_cli("sync", cwd=c1).returncode, 0)
        remote_head = self.git("-C", str(bare), "rev-parse", "HEAD").stdout.strip()
        self.assertEqual(self.run_cli("say", "克隆二的发言", cwd=c2).returncode, 0)
        conflict = self.run_cli("sync", cwd=c2)
        self.assertEqual(conflict.returncode, 3, conflict.stderr + conflict.stdout)
        combined = conflict.stdout + conflict.stderr
        self.assertIn("conflict", conflict.stdout.lower())
        self.assertIn("冲突文件", combined)
        self.assertTrue("session" in combined or "state/" in combined or "state\\" in combined)
        self.assertEqual(self.git("-C", str(bare), "rev-parse", "HEAD").stdout.strip(), remote_head)
        local_log = self.git("-C", str(c2), "log", "--format=%s", "-5").stdout
        self.assertIn("learn(", local_log, "本地提交被丢弃")
        recover = self.run_cli("sync", "--recover", cwd=c2)
        self.assertEqual(recover.returncode, 3, recover.stderr + recover.stdout)
        self.assertIn("session.json", recover.stdout + recover.stderr, "快照冲突必须列出真实文件")
        status = self.run_cli("status", "--json", cwd=c2)
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        self.assertTrue(json.loads(status.stdout)["sync"]["diverged"])
        self.assertEqual(self.git("-C", str(bare), "rev-parse", "HEAD").stdout.strip(), remote_head)
        self.assertIn("learn(", self.git("-C", str(c2), "log", "--format=%s", "-5").stdout)
        self.assertEqual(self.run_cli("doctor", cwd=c2).returncode, 3)

    @unittest.skipUnless(GIT, "git not installed")
    def test_git_no_remote_reports_and_commits_locally(self) -> None:
        self.init()
        self.start()
        proc = self.run_cli("sync", cwd=self.proj)
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        text = proc.stdout.lower()
        self.assertIn("no-remote", text)
        self.assertIn("written=yes", text)
        self.assertIn("committed=yes", text)
        self.assertIn("pushed=no", text)
        log = self.git("-C", str(self.proj), "log", "--format=%s", "-1")
        self.assertEqual(log.returncode, 0, log.stderr)
        self.assertIn("learn(", log.stdout)
        ignore = (self.proj / ".gitignore").read_text(encoding="utf-8")
        for pattern in ("*.lock", "usage.jsonl", "sync-log.jsonl", ".env"):
            self.assertIn(pattern, ignore)
        attributes = (self.proj / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("* -text", attributes)

    @unittest.skipUnless(GIT, "git not installed")
    def test_clean_clone_recovers_m1_evidence_and_crlf_safe_sha(self) -> None:
        self.init()
        self.start()
        self.assertEqual(self.add_artifact().returncode, 0)
        data = self.pass_m1()
        self.assertEqual(data["milestones"][0]["status"], "passed")
        original = self.proj / "artifacts/M1/agent.py"
        original_sha = hashlib.sha256(original.read_bytes()).hexdigest()
        bare = self.tmp / "bare.git"
        self.assertEqual(self.git("init", "--bare", str(bare)).returncode, 0)
        self.assertEqual(self.git("-C", str(self.proj), "remote", "add", "origin", str(bare)).returncode, 0)
        synced = self.run_cli("sync", "--message", "learn: m1", cwd=self.proj)
        self.assertEqual(synced.returncode, 0, synced.stderr + synced.stdout)
        self.assertIn("pushed=yes", synced.stdout)
        clone = self.tmp / "clean-clone"
        cloned = self.git("-c", "core.autocrlf=true", "clone", str(bare), str(clone))
        self.assertEqual(cloned.returncode, 0, cloned.stderr)
        clone_artifact = clone / "artifacts/M1/agent.py"
        self.assertTrue(clone_artifact.is_file(), "克隆后缺少作品")
        self.assertEqual(hashlib.sha256(clone_artifact.read_bytes()).hexdigest(), original_sha, "克隆后作品 sha 变化（CRLF）")
        status = self.run_cli("status", "--json", cwd=clone)
        self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
        payload = json.loads(status.stdout)
        m1 = payload["milestones"][0]
        self.assertEqual(m1["status"], "passed", "克隆后里程碑证据丢失")
        self.assertEqual(m1["defense"]["status"], "passed")
        self.assertTrue(m1["pass_evidence"].get("artifact_id"))
        self.assertTrue(m1["pass_evidence"].get("review_id"))
        self.assertTrue(m1["pass_evidence"].get("defense_id"))
        self.assertEqual(payload["current_milestone"], "M2")
        self.assertTrue((clone / "sessions").is_dir() and list((clone / "sessions").glob("*.md")))
        nxt = json.loads(self.run_cli("next", "--json", cwd=clone).stdout)
        self.assertEqual((nxt["action"], nxt["milestone"]), ("do_task", "M2"))
        self.assertEqual(self.run_cli("doctor", cwd=clone).returncode, 0)

    @unittest.skipUnless(GIT, "git not installed")
    def test_git_commits_no_secrets_locks_or_usage_logs(self) -> None:
        self.init()
        self.start(extra_env={"DEEPSEEK_API_KEY": SECRET})
        said = self.run_cli(
            "say",
            "离线也要审查提交内容",
            cwd=self.proj,
            script=self.script([("离线", update_block(coach_update()))]),
            extra_env={"DEEPSEEK_API_KEY": SECRET},
        )
        self.assertEqual(said.returncode, 0, said.stderr + said.stdout)
        (self.proj / ".env").write_text(f"DEEPSEEK_API_KEY={SECRET}\n", encoding="utf-8")
        (self.proj / ".learnark/usage.jsonl").write_text(
            '{"prompt_sha256": "deadbeef", "note": "usage log must not be committed"}\n', encoding="utf-8"
        )
        (self.proj / ".learnark/state/evil.lock").write_text("lock\n", encoding="utf-8")
        sync = self.run_cli("sync", cwd=self.proj, extra_env={"DEEPSEEK_API_KEY": SECRET})
        self.assertEqual(sync.returncode, 0, sync.stderr + sync.stdout)
        tracked = self.git("-C", str(self.proj), "ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines()
        self.assertTrue(tracked)
        for forbidden in (".env", "usage.jsonl", ".lock", ".bak", "__pycache__"):
            self.assertFalse(
                any(forbidden in path for path in tracked),
                f"{forbidden} 不应进入提交：{tracked}",
            )
        grep = self.git("-C", str(self.proj), "grep", "-I", "-n", SECRET, "HEAD")
        self.assertEqual(grep.returncode, 1, f"提交中出现密钥：{grep.stdout}")
        self.assertEqual(grep.stdout.strip(), "")
        hits = []
        for path in self.proj.rglob("*"):
            if not path.is_file() or ".git" in path.parts or path.name == ".env":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if SECRET in text:
                hits.append(str(path.relative_to(self.proj)))
        self.assertEqual(hits, [], f"项目文件中出现密钥：{hits}")
        exported = self.tmp / "archive.md"
        export = self.run_cli("export", "--out", str(exported), cwd=self.proj, extra_env={"DEEPSEEK_API_KEY": SECRET})
        self.assertEqual(export.returncode, 0, export.stderr + export.stdout)
        self.assertNotIn(SECRET, exported.read_text(encoding="utf-8"))
        self.assertFalse((self.proj / ".env").name in "\n".join(tracked))

    # ------------------------------------------------------------------ #
    # 6. simulated clock
    # ------------------------------------------------------------------ #
    def test_simulated_clock_marks_events_and_keeps_gating(self) -> None:
        sim_time = "2026-12-25T09:00:00+08:00"
        sim_env = {"LEARNARK_NOW": sim_time}

        def gate(project: Path, extra: dict | None) -> dict:
            proc = self.run_cli("init", "--goal", "时钟验证", "--dir", str(project), extra_env=extra)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            proc = self.run_cli("start", "--offline", cwd=project, extra_env=extra)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            source = self.tmp / f"{project.name}.py"
            source.write_text("\n".join(f'STEP_{i} = "{i}"' for i in range(1, 45)) + "\n", encoding="utf-8")
            proc = self.run_cli("artifact", "add", str(source), cwd=project, extra_env=extra)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            review_script = self.script([("", update_block(critic_update()))])
            proc = self.run_cli("review", cwd=project, script=review_script, extra_env=extra)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            defense_script = self.script([("我解释完了", update_block(defense_update(True)))])
            proc = self.run_cli("say", "我解释完了", cwd=project, script=defense_script, extra_env=extra)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            status = self.run_cli("status", "--json", cwd=project, extra_env=extra)
            self.assertEqual(status.returncode, 0, status.stderr + status.stdout)
            return json.loads(status.stdout)

        simulated = gate(self.tmp / "sim", sim_env)
        real = gate(self.tmp / "real", None)
        sim_events = self.journal(self.tmp / "sim")
        real_events = self.journal(self.tmp / "real")
        self.assertTrue(sim_events)
        self.assertTrue(all(event.get("simulated") is True for event in sim_events), "模拟时钟事件必须全部标 simulated")
        self.assertTrue(all(str(event.get("at", "")).startswith("2026-12-25") for event in sim_events))
        self.assertTrue(real_events)
        self.assertTrue(all(event.get("simulated") is False for event in real_events))
        self.assertFalse(any(str(event.get("at", "")).startswith("2026-12-25") for event in real_events))
        for payload in (simulated, real):
            m1, m2 = payload["milestones"][0], payload["milestones"][1]
            self.assertEqual(m1["status"], "passed")
            self.assertEqual(m1["defense"]["status"], "passed")
            self.assertEqual(m2["status"], "active")
            self.assertEqual(payload["current_milestone"], "M2")
            self.assertEqual(payload["next"]["action"], "do_task")
        self.assertEqual(
            {dim["dim"]: dim["score"] for dim in simulated["milestones"][0]["rubric"]},
            {dim["dim"]: dim["score"] for dim in real["milestones"][0]["rubric"]},
        )
        self.assertEqual(
            simulated["milestones"][0]["defense"]["ok_count"],
            real["milestones"][0]["defense"]["ok_count"],
        )

    # ------------------------------------------------------------------ #
    # 7. secrets audit (local records, independent of git)
    # ------------------------------------------------------------------ #
    def test_secret_never_written_to_project_state(self) -> None:
        self.init()
        self.start(extra_env={"DEEPSEEK_API_KEY": SECRET, "LEARNARK_API_KEY": SECRET})
        said = self.run_cli(
            "say",
            "离线记录不应包含密钥",
            cwd=self.proj,
            script=self.script([("离线记录", update_block(coach_update()))]),
            extra_env={"DEEPSEEK_API_KEY": SECRET, "LEARNARK_API_KEY": SECRET},
        )
        self.assertEqual(said.returncode, 0, said.stderr + said.stdout)
        for path in self.proj.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            self.assertNotIn(SECRET, text, f"密钥写入了 {path.relative_to(self.proj)}")
        status = self.run_cli("status", "--json", cwd=self.proj, extra_env={"DEEPSEEK_API_KEY": SECRET})
        self.assertEqual(status.returncode, 0)
        self.assertNotIn(SECRET, status.stdout)
        self.assertNotIn(SECRET, status.stderr)
        exported = self.tmp / "audit.md"
        self.assertEqual(self.run_cli("export", "--out", str(exported), cwd=self.proj).returncode, 0)
        self.assertNotIn(SECRET, exported.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
