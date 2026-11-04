#!/usr/bin/env python3
"""Forge 确定性测试（默认离线 mock，无网络）。

运行：python tests/run_tests.py [--keep] [--filter 名称]

覆盖：init 幂等、离线 E2E、B-S1 无作品拒绝、B-S2 评分驱动下一步、B-S3 幂等、
B-S4 防御造假、B-S5 clamp/整次拒绝、缺口三条关闭路径、损坏恢复、git 同步与克隆、
email 模板迁移、next --json 可复现、switch 交接字段。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
import forge_mentor  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ENTRY = ROOT / "runtime" / "learn.py"
PY = sys.executable
JOURNAL = Path(".learnark/journal/events.jsonl")


# --------------------------------------------------------------------------- #
# 基础设施
# --------------------------------------------------------------------------- #
def _env(script: Path | None) -> dict:
    env = os.environ.copy()
    env.update({"LEARNARK_LLM": "mock", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    env.pop("LEARNARK_NOW", None)
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("LEARNARK_API_KEY", None)
    if script is not None:
        env["LEARNARK_MOCK_SCRIPT"] = str(script)
    else:
        env.pop("LEARNARK_MOCK_SCRIPT", None)
    return env


def check(condition, message: str, proc: subprocess.CompletedProcess | None = None) -> None:
    if condition:
        return
    detail = ""
    if proc is not None:
        detail = (
            f"\n  exit={proc.returncode}\n  stdout={proc.stdout[-2000:]}\n  stderr={proc.stderr[-2000:]}"
        )
    raise AssertionError(message + detail)


def artifact_text(extra: str = "") -> str:
    lines = ["# synthetic m1/agent.py — offline test data, not real learning evidence"]
    for index in range(1, 60):
        lines.append(f'STEP_{index} = "line {index}"  # synthetic {extra}'.rstrip())
    return "\n".join(lines) + "\n"


def note_for(dim: str, score: int, line: int = 3) -> str:
    return f"{dim} 证据见第 {line} 行，分数 {score}"


def rubric(entries: list[tuple[str, int]]) -> list[dict]:
    return [{"dim": dim, "score": score, "note": note_for(dim, score, index + 5)} for index, (dim, score) in enumerate(entries)]


def update_block(update: dict, text: str = "导师回复正文。") -> str:
    return text + "\n\n```learn-update\n" + json.dumps(update, ensure_ascii=False) + "\n```"


def critic_update(
    entries: list[tuple[str, int]],
    *,
    gap: list[dict] | None = None,
    defense: dict | None = None,
    raw_rubric: list[dict] | None = None,
    help_level: int = 1,
) -> str:
    update = {
        "mentor": "critic",
        "help_level": help_level,
        "attempt": {"activity_id": "m1-artifact-review", "correct": False},
        "misconception": None,
        "next": "按缺口改一处再 review",
        "mastery_delta": 0,
        "artifact": "artifacts/M1/agent.py",
        "milestone": "M1",
        "rubric": raw_rubric if raw_rubric is not None else rubric(entries),
        "gap": gap or [],
        "defense": defense,
    }
    return update_block(update)


def defense_block(ok: bool) -> dict:
    return {
        "questions": [
            {
                "qid": "m1-q1",
                "dim": "contract",
                "question": "如果模型不支持 tool_calls，你的循环怎么改？",
                "answer": "把 tool_calls 解析抽成适配层，退化到纯 JSON 协议" if ok else "我理解了设计",
                "evidence_line": 38 if ok else 1,
                "ok": ok,
            },
            {
                "qid": "m1-q2",
                "dim": "runnability",
                "question": "把输入文件换成不存在的路径，这版会发生什么？",
                "answer": "工具返回 error observation 回填给模型，循环不崩" if ok else "我理解了设计",
                "evidence_line": 27 if ok else 1,
                "ok": ok,
            },
            {
                "qid": "m1-q3",
                "dim": "explainability",
                "question": "为什么步数上限是六而不是无限循环？",
                "answer": "用步数兜住模型反复调同一工具，超过就交回人工" if ok else "我理解了设计",
                "evidence_line": 41 if ok else 1,
                "ok": ok,
            },
        ]
    }


class Case:
    def __init__(self, name: str):
        self.name = name
        self.root = Path(tempfile.mkdtemp(prefix=f"forge-{name}-"))
        self.proj = self.root / "proj"
        self._scripts = 0

    # -- process ---------------------------------------------------------
    def run(self, *args, script: Path | None = None, cwd: Path | None = None, input_text: str | None = None):
        return subprocess.run(
            [PY, str(ENTRY), *[str(a) for a in args]],
            cwd=str(cwd or self.root),
            env=_env(script),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            input=input_text,
            timeout=180,
        )

    def script(self, entries: list[tuple[str, str]]) -> Path:
        self._scripts += 1
        path = self.root / f"script-{self._scripts}.jsonl"
        lines = [json.dumps({"match": match, "reply": reply}, ensure_ascii=False) for match, reply in entries]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    # -- fixtures --------------------------------------------------------
    def init(self, template: str = "agent-dev", goal: str = "Agent 开发"):
        proc = self.run("init", "--goal", goal, "--dir", "proj", "--template", template)
        check(proc.returncode == 0, "init 失败", proc)
        return proc

    def artifact(self, name: str = "agent.py", extra: str = "") -> subprocess.CompletedProcess:
        path = self.root / name
        path.write_text(artifact_text(extra), encoding="utf-8")
        return self.run("artifact", "add", path, "--project", "proj")

    def add_artifact(self, name: str, extra: str) -> subprocess.CompletedProcess:
        return self.artifact(name=name, extra=extra)

    def read(self, rel: str):
        return json.loads((self.proj / rel).read_text(encoding="utf-8"))

    def journal_kinds(self) -> list[str]:
        path = self.proj / JOURNAL
        if not path.is_file():
            return []
        kinds = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                kinds.append(json.loads(line).get("kind", ""))
            except json.JSONDecodeError:
                break
        return kinds

    def events(self, kind: str) -> list[dict]:
        path = self.proj / JOURNAL
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("kind") == kind:
                out.append(event)
        return out

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


# --------------------------------------------------------------------------- #
# 用例
# --------------------------------------------------------------------------- #
def test_init_idempotent(case: Case) -> None:
    proc = case.init()
    check("已创建" in proc.stdout, "init 未报告创建", proc)
    for rel in (".learnark/project.json", ".learnark/state/brief.json", "README.md", "AGENTS.md", ".gitignore", ".gitattributes"):
        check((case.proj / rel).exists(), f"init 缺少 {rel}")
    attributes = (case.proj / ".gitattributes").read_text(encoding="utf-8")
    check("* -text" in attributes, "缺少 * -text（克隆后 sha 会变）")
    gitignore = (case.proj / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.lock", "usage.jsonl", "sync-log.jsonl"):
        check(pattern in gitignore, f".gitignore 缺少 {pattern}")
    brief = case.read(".learnark/state/brief.json")
    check([m["id"] for m in brief["milestones"]] == ["M1", "M2", "M3"], "里程碑 id 不是 M1/M2/M3")
    check(brief["milestones"][0]["status"] == "active", "M1 应为 active")
    check(brief["milestones"][1]["status"] == "locked", "M2 应为 locked")
    for milestone in brief["milestones"]:
        check(sum(d["weight"] for d in milestone["rubric"]) == 100, "rubric 权重之和不是 100")
        check(all(isinstance(d["threshold"], int) and 1 <= d["threshold"] <= 4 for d in milestone["rubric"]), "阈值异常")
    second = case.init(goal="新的目标")
    check(second.returncode == 0 and "已存在" in second.stdout, "重复 init 不幂等", second)
    project = case.read(".learnark/project.json")
    check(project["goal"] == "新的目标", "显式 --goal 未更新 project.json")
    check(project["learner_profile"]["self_report"] == {}, "init 预置了学习者没说过的话")
    brief2 = case.read(".learnark/state/brief.json")
    check(len(brief2["milestones"]) == 3 and brief2["current_milestone"] == "M1", "重复 init 破坏了里程碑")
    check(len(case.events("init")) == 1, "init 事件被重复记录")
    agents = (case.proj / "AGENTS.md").read_text(encoding="utf-8")
    check("start" in agents and "artifact" in agents, "AGENTS.md 未说明入口")


def test_offline_e2e(case: Case) -> None:
    case.init()
    proc = case.run("start", "--project", "proj", "--offline")
    check(proc.returncode == 0 and "[离线脚本导师]" in proc.stdout, "start 未标注离线导师", proc)
    proc = case.run("say", "我写不出来", "--project", "proj", "--offline")
    check(proc.returncode == 0 and "[离线脚本导师]" in proc.stdout, "say 失败", proc)
    proc = case.run("status", "--project", "proj", "--json")
    check(proc.returncode == 0, "status --json 失败", proc)
    data = json.loads(proc.stdout)
    check(data["status"] == "active" and data["current_milestone"] == "M1", "status 状态不对")
    check(data["next"]["action"] == "do_task", "首次无作品应为 do_task")
    for command in (("task",), ("milestones",), ("artifact", "list")):
        proc = case.run(*command, "--project", "proj")
        check(proc.returncode == 0 and proc.stdout.strip(), f"{command} 输出为空", proc)
    proc = case.run("pause", "--project", "proj", "--note", "E2E 冒烟")
    check(proc.returncode == 0, "pause 失败", proc)
    check((case.proj / ".learnark/handoff/latest.md").is_file(), "pause 没写 handoff/latest.md")
    proc = case.run("sync", "--project", "proj")
    text = (proc.stdout + proc.stderr).lower()
    check(proc.returncode == 0 and all(word in text for word in ("written", "committed", "pushed")), "sync 三态不全", proc)
    proc = case.run("doctor", "--project", "proj")
    check(proc.returncode == 0, "doctor 报告问题", proc)
    proc = case.run("export", "--out", "archive.md", "--project", "proj")
    check(proc.returncode == 0 and (case.root / "archive.md").stat().st_size > 200, "export 失败", proc)
    sessions = list((case.proj / "sessions").glob("*.md"))
    check(len(sessions) >= 1, "没有会话文件")
    kinds = set(case.journal_kinds())
    check({"mentor_turn", "learner_say", "handoff"} <= kinds, f"journal 缺少关键事件：{kinds}")


def test_claim_without_artifact(case: Case) -> None:
    """B-S1：只说“我做完了”必须被拒绝。"""
    case.init()
    case.run("start", "--project", "proj", "--offline")
    proc = case.run("say", "我做完了", "--project", "proj", "--offline")
    check(proc.returncode == 0, "claim 应返回 0", proc)
    check("未登记作品" in proc.stdout, "没有提示未登记作品", proc)
    check("claim_without_artifact" in case.journal_kinds(), "没有写 claim_without_artifact 事件")
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    check(data["status"] == "active", "里程碑被口头声明通过了")
    check(data["claim_without_artifact"] is True, "status 未标记 claim")
    check(data["artifacts"]["count"] == 0, "不应产生作品")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] == "artifact_required", f"next 应为 artifact_required，实际 {nxt['action']}")


def test_review_drives_gap(case: Case) -> None:
    """B-S2：低分维度决定下一步微课。"""
    case.init()
    case.artifact()
    script = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
    proc = case.run("review", "--project", "proj", script=script)
    check(proc.returncode == 0 and "r-M1-" in proc.stdout, "review 失败", proc)
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] == "gap_learn", f"next 应为 gap_learn，实际 {nxt['action']}")
    check(nxt["ref"] == "g-M1-contract" and nxt["dim"] == "contract", f"缺口维度不对：{nxt}")
    gaps = case.read(".learnark/state/gaps.json")["items"]
    card = next(g for g in gaps if g["gap_id"] == "g-M1-contract")
    check(card["source_review"].startswith("r-M1-"), "缺口卡缺 source_review")
    check(card["score"] == 2 and card["threshold"] == 3 and card["weight"] == 30, "缺口卡分数/阈值/权重不对")
    # next --json 可复现（同一状态两次输出一致）
    first = case.run("next", "--project", "proj", "--json").stdout
    second = case.run("next", "--project", "proj", "--json").stdout
    check(first == second, "next --json 两次输出不一致")


def test_duplicate_artifact_and_review(case: Case) -> None:
    """B-S3：同 sha 重复登记/评审不重复计分。"""
    case.init()
    first = case.artifact()
    check(first.returncode == 0, "第一次登记失败", first)
    second = case.artifact()
    check(second.returncode == 0 and "已记录" in second.stdout, "重复登记未提示已记录", second)
    artifacts = case.read(".learnark/state/artifacts.json")["items"]
    check(len(artifacts) == 1, f"重复登记产生了 {len(artifacts)} 条作品")
    script = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    one = case.run("review", "--project", "proj", script=script)
    check(one.returncode == 0, "第一次评审失败", one)
    two = case.run("review", "--project", "proj", script=script)
    check(two.returncode == 0 and "已记录" in two.stdout, "重复评审未提示已记录", two)
    reviews = case.read(".learnark/state/reviews.json")["items"]
    check(len(reviews) == 1, f"重复评审产生了 {len(reviews)} 次评审")
    check(len(case.events("review_recorded")) == 1, "review_recorded 事件重复")
    check(len(case.events("artifact_added")) == 1, "artifact_added 事件重复")


def test_clamp_and_reject(case: Case) -> None:
    """B-S5：越界 clamp；缺维/多维/改权重整次拒绝。"""
    case.init()
    case.artifact("a1.py", "one")
    raw = [
        {"dim": "runnability", "score": 9, "note": note_for("runnability", 9)},
        {"dim": "contract", "score": -3, "note": note_for("contract", -3)},
        {"dim": "robustness", "score": "高", "note": note_for("robustness", 0)},
        {"dim": "explainability", "score": 4, "note": note_for("explainability", 4)},
    ]
    script = case.script([("", critic_update([], raw_rubric=raw))])
    proc = case.run("review", "--project", "proj", script=script)
    check(proc.returncode == 0, "越界分数应被 clamp 而不是拒绝", proc)
    review = case.read(".learnark/state/reviews.json")["items"][-1]
    scores = {d["dim"]: d["score"] for d in review["rubric"]}
    check(scores == {"runnability": 4, "contract": 1, "robustness": 1, "explainability": 4}, f"clamp 结果不对：{scores}")
    check(len(review["clamped"]) == 3, "clamped 记录数不对")

    cases = {
        "missing": [
            {"dim": "runnability", "score": 3, "note": note_for("runnability", 3)},
            {"dim": "contract", "score": 3, "note": note_for("contract", 3)},
            {"dim": "robustness", "score": 3, "note": note_for("robustness", 3)},
        ],
        "extra": [
            {"dim": "runnability", "score": 3, "note": note_for("runnability", 3)},
            {"dim": "contract", "score": 3, "note": note_for("contract", 3)},
            {"dim": "robustness", "score": 3, "note": note_for("robustness", 3)},
            {"dim": "explainability", "score": 3, "note": note_for("explainability", 3)},
            {"dim": "speed", "score": 4, "note": "第 9 行"},
        ],
        "weight": [
            {"dim": "runnability", "score": 3, "weight": 99, "note": note_for("runnability", 3)},
            {"dim": "contract", "score": 3, "note": note_for("contract", 3)},
            {"dim": "robustness", "score": 3, "note": note_for("robustness", 3)},
            {"dim": "explainability", "score": 3, "note": note_for("explainability", 3)},
        ],
    }
    for index, (label, entries) in enumerate(cases.items(), start=2):
        case.artifact(f"a{index}.py", label)
        bad = case.script([("", critic_update([], raw_rubric=entries))])
        proc = case.run("review", "--project", "proj", script=bad)
        check(proc.returncode == 3, f"{label} 应整次拒绝且退出码 3", proc)
        check("review_invalid" in proc.stdout or "拒绝" in proc.stdout, f"{label} 未提示拒绝", proc)
        check(len(case.read(".learnark/state/reviews.json")["items"]) == 1, f"{label} 不应写入评审")
    invalid = [e for e in case.events("review_invalid")]
    check(len(invalid) == 3, f"review_invalid 事件数 {len(invalid)}")
    check(all("raw_sha256" in e["payload"] for e in invalid), "review_invalid 缺 raw_sha256")


def test_defense_fake_rejected(case: Case) -> None:
    """B-S4：三问全填空话必须判 failed，不能通过。"""
    case.init()
    case.artifact()
    review_script = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    proc = case.run("review", "--project", "proj", script=review_script)
    check(proc.returncode == 0, "review 失败", proc)
    fake = {"mentor": "critic", "help_level": 0, "attempt": {}, "misconception": None, "next": "再答一次",
            "mastery_delta": 0, "defense": defense_block(ok=False)}
    say_script = case.script([("我解释完了", update_block(fake))])
    proc = case.run("say", "我解释完了", "--project", "proj", script=say_script)
    check(proc.returncode == 0, "say 失败", proc)
    check("failed" in proc.stdout, "假答案未判 failed", proc)
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    check(data["status"] == "active", "假防御让里程碑通过了")
    check(data["defense"]["passed"] is False, "defense 不应 passed")
    check(data["defense"]["ok_count"] == 0, "空话不应算通过")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] == "defend", f"next 应为 defend，实际 {nxt['action']}")
    defense_events = case.events("defense_recorded")
    check(defense_events and defense_events[-1]["payload"]["status"] == "failed", "defense 事件状态不对")


def test_defense_pass_and_milestone(case: Case) -> None:
    case.init()
    case.artifact()
    review_script = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=review_script).returncode == 0, "review 失败")
    ok = {"mentor": "critic", "help_level": 0, "attempt": {}, "misconception": None, "next": "进入 M2",
          "mastery_delta": 0, "defense": defense_block(ok=True)}
    say_script = case.script([("我解释完了", update_block(ok))])
    proc = case.run("say", "我解释完了", "--project", "proj", script=say_script)
    check(proc.returncode == 0, "defense say 失败", proc)
    check("通过" in proc.stdout, "未报告里程碑通过", proc)
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    m1, m2 = data["milestones"][0], data["milestones"][1]
    check(m1["status"] == "passed", f"M1 状态 {m1['status']}")
    check(m1["pass_evidence"].get("artifact_id") and m1["pass_evidence"].get("review_id") and m1["pass_evidence"].get("defense_id"), "pass_evidence 缺三元组")
    check(data["current_milestone"] == "M2" and m2["status"] == "active", "没有激活 M2")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] == "do_task" and nxt["milestone"] == "M2", f"下一步应推进 M2：{nxt}")
    check("passed" in case.run("milestones", "--project", "proj").stdout, "milestones 未显示通过")


def test_gap_close_paths(case: Case) -> None:
    """缺口三条路径：复评达标关闭 / 微练习未复验 / drop 记 stale。"""
    case.init()
    case.artifact("v1.py", "v1")
    script_one = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=script_one).returncode == 0, "review1 失败")
    gaps = case.read(".learnark/state/gaps.json")["items"]
    check(any(g["gap_id"] == "g-M1-contract" and g["status"] == "open" for g in gaps), "缺口卡未创建")

    # (b) 微课 + 微练习 help_level<=1 -> 未在作品复验
    gap_script = case.script([("gap learn", update_block({"mentor": "guide", "help_level": 2, "attempt": {}, "misconception": None,
                                                          "next": "改 calc 校验", "mastery_delta": 0,
                                                          "gap": [{"dim": "contract", "note": "已讲工具契约与参数校验"}]}))])
    proc = case.run("gap", "learn", "g-M1-contract", "--project", "proj", script=gap_script)
    check(proc.returncode == 0, "gap learn 失败", proc)
    gap = next(g for g in case.read(".learnark/state/gaps.json")["items"] if g["gap_id"] == "g-M1-contract")
    check(gap["status"] == "learning", "gap learn 未推进到 learning")
    coach = {"mentor": "coach", "help_level": 1, "attempt": {"activity_id": "m1-micro-practice", "correct": True},
             "misconception": None, "next": "改一处再 review", "mastery_delta": 0}
    say_script = case.script([("我把校验改好了", update_block(coach))])
    proc = case.run("say", "我把校验改好了", "--project", "proj", script=say_script)
    check(proc.returncode == 0, "微练习 say 失败", proc)
    gap = next(g for g in case.read(".learnark/state/gaps.json")["items"] if g["gap_id"] == "g-M1-contract")
    check(gap["unverified"] is True and gap["status"] != "closed", "微练习不应关闭缺口，只应标未复验")

    # (a) 复评达标 -> closed
    case.artifact("v2.py", "v2")
    script_two = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    proc = case.run("review", "--project", "proj", script=script_two)
    check(proc.returncode == 0, "review2 失败", proc)
    gap = next(g for g in case.read(".learnark/state/gaps.json")["items"] if g["gap_id"] == "g-M1-contract")
    check(gap["status"] == "closed" and gap["closed_by"] == "review", f"复评未关闭缺口：{gap['status']}")
    proc = case.run("doctor", "--project", "proj")
    check(proc.returncode == 0, "关闭缺口后 doctor 报错", proc)
    check("未修改即关闭" not in proc.stdout, "doctor 误报未修改即关闭")


def test_gap_drop_stale(case: Case) -> None:
    case.init()
    for index in range(1, 4):
        case.artifact(f"v{index}.py", f"v{index}")
        script = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
        proc = case.run("review", "--project", "proj", script=script)
        check(proc.returncode == 0, f"review{index} 失败", proc)
    gap = next(g for g in case.read(".learnark/state/gaps.json")["items"] if g["gap_id"] == "g-M1-contract")
    check(gap["attempts"] >= 3, f"attempts 未累计：{gap['attempts']}")
    proc = case.run("gap", "drop", "g-M1-contract", "--project", "proj")
    check(proc.returncode == 0, "三次重开仍不能 drop", proc)
    gap = next(g for g in case.read(".learnark/state/gaps.json")["items"] if g["gap_id"] == "g-M1-contract")
    check(gap["status"] == "stale", "drop 未记 stale")
    check(abs(gap["stale_drops"] - 1.0) < 1e-9, "stale_drops 未记录")
    doctor = case.run("doctor", "--project", "proj")
    check(doctor.returncode == 0, "stale 不应让 doctor 失败", doctor)
    check("g-M1-contract" in doctor.stdout and "stale" in doctor.stdout, "doctor 未列出 stale 缺口", doctor)


def test_gap_drop_guard(case: Case) -> None:
    case.init()
    case.artifact()
    script = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=script).returncode == 0, "review 失败")
    proc = case.run("gap", "drop", "g-M1-contract", "--project", "proj")
    check(proc.returncode == 3, "只失败一次就允许 drop 了", proc)
    check("至少" in proc.stdout, "未说明至少三次", proc)


def test_recovery(case: Case) -> None:
    case.init()
    case.run("start", "--project", "proj", "--offline")
    brief_path = case.proj / ".learnark/state/brief.json"
    check(brief_path.with_name("brief.json.bak").is_file(), "没有 .bak 备份")
    brief_path.write_text("{ this is not json", encoding="utf-8")
    proc = case.run("status", "--project", "proj", "--offline")
    check(proc.returncode == 0, "损坏后 status 失败", proc)
    check("恢复" in (proc.stdout + proc.stderr), "未提示从 .bak 恢复", proc)
    json.loads(brief_path.read_text(encoding="utf-8"))
    # 日志尾部半行应被忽略
    with open(case.proj / JOURNAL, "a", encoding="utf-8") as handle:
        handle.write('{"broken": ')
    proc = case.run("status", "--project", "proj")
    check(proc.returncode == 0, "半行日志导致失败", proc)
    proc = case.run("doctor", "--project", "proj")
    check(proc.returncode == 0, "doctor 因半行日志失败", proc)


def test_artifact_tamper(case: Case) -> None:
    """B-S6：作品被改回/篡改后 doctor 必须报错。"""
    case.init()
    case.artifact()
    review_script = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=review_script).returncode == 0, "review 失败")
    copy = next((case.proj / "artifacts").glob("M1/*.py"))
    copy.write_text("# 回退到旧版本\n", encoding="utf-8")
    proc = case.run("doctor", "--project", "proj")
    check(proc.returncode == 3, "作品 sha 不一致时 doctor 应返回 3", proc)
    check("sha256" in proc.stdout, "doctor 未报告 sha 不一致", proc)


def test_assisted_level(case: Case) -> None:
    """design §8：assisted_level>=2 的作品通过时只能记 passed_assisted / observed。"""
    case.init()
    coach = {"mentor": "coach", "help_level": 2, "attempt": {}, "misconception": None,
             "next": "先跑通一次", "mastery_delta": 0}
    script = case.script([("给我一步步", update_block(coach))])
    proc = case.run("say", "给我一步步", "--project", "proj", script=script)
    check(proc.returncode == 0, "say 失败", proc)
    proc = case.artifact()
    check(proc.returncode == 0 and "assisted_level=2" in proc.stdout, "未按上件以来最大 help_level 记 assisted_level", proc)
    review_script = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=review_script).returncode == 0, "review 失败")
    ok = {"mentor": "critic", "help_level": 0, "attempt": {}, "misconception": None, "next": "进入 M2",
          "mastery_delta": 0, "defense": defense_block(ok=True)}
    say_script = case.script([("我解释完了", update_block(ok))])
    check(case.run("say", "我解释完了", "--project", "proj", script=say_script).returncode == 0, "defense 失败")
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    milestone = data["milestones"][0]
    check(milestone["status"] == "passed_assisted", f"应记 passed_assisted，实际 {milestone['status']}")
    check(milestone["pass_evidence"].get("evidence_level") == "observed", "证据等级应为 observed")


def test_git_sync_and_clone(case: Case) -> None:
    case.init()
    case.run("start", "--project", "proj", "--offline")
    proc = case.run("pause", "--project", "proj")
    check(proc.returncode == 0, "pause 失败", proc)
    proc = case.run("sync", "--project", "proj")
    text = (proc.stdout + proc.stderr).lower()
    check(proc.returncode == 0 and all(word in text for word in ("written", "committed", "pushed")), "sync 三态不全", proc)
    check((case.proj / ".git").is_dir(), "init 没有建立 git 仓库")
    bare = case.root / "bare.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(case.proj), "remote", "add", "origin", str(bare)], check=True, capture_output=True)
    proc = case.run("sync", "--project", "proj")
    check(proc.returncode == 0 and "pushed=yes" in proc.stdout, "配置远程后未推送", proc)
    clone = case.root / "clone"
    subprocess.run(["git", "clone", str(bare), str(clone)], check=True, capture_output=True)
    proc = subprocess.run(
        [PY, str(ENTRY), "status", "--json"], cwd=str(clone), env=_env(None), capture_output=True, text=True, encoding="utf-8"
    )
    check(proc.returncode == 0, "克隆后 status 失败", proc)
    data = json.loads(proc.stdout)
    check(data["current_milestone"] == "M1" and data["status"] == "active", "克隆后状态不对")
    check(data["goal"] == "Agent 开发", "克隆后目标丢失")
    nxt = subprocess.run(
        [PY, str(ENTRY), "next", "--json"], cwd=str(clone), env=_env(None), capture_output=True, text=True, encoding="utf-8"
    )
    check(nxt.returncode == 0, "克隆后 next 失败", nxt)
    check(json.loads(nxt.stdout)["action"] == "do_task", "克隆后无法定位下一步", nxt)


def test_git_second_sync(case: Case) -> None:
    """回归：第一次 push 后修改已跟踪文件，第二次 sync 必须提交并推送该文件。

    core 1.0.0 的 ``GitSync.run`` 会 strip 掉 ``git status --porcelain`` 首行的
    前导空格，第二个变更路径因此少一个字符、``git add`` 失败；1.0.1 修复。
    """
    case.init()
    case.run("start", "--project", "proj", "--offline")
    bare = case.root / "bare2.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(case.proj), "remote", "add", "origin", str(bare)], check=True, capture_output=True)
    first = case.run("sync", "--project", "proj")
    check(first.returncode == 0 and "pushed=yes" in first.stdout, "第一次同步未推送", first)
    readme = case.proj / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n<!-- second sync -->\n", encoding="utf-8")
    second = case.run("sync", "--project", "proj")
    check(second.returncode == 0, "第二次 sync 失败（porcelain 首列被吞的回归）", second)
    check("committed=yes" in second.stdout, "第二次 sync 未提交修改", second)
    check("pushed=yes" in second.stdout, "第二次 sync 未推送", second)
    log = subprocess.run(
        ["git", "-C", str(bare), "log", "--oneline", "-1", "--stat"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    check("README.md" in (log.stdout or ""), "远程最新提交不含 README.md", None)


def test_profile_answers(case: Case) -> None:
    """round-01 #1：三问必须可补答并落库；init 不得预置 self_report。"""
    case.init()
    project = case.read(".learnark/project.json")
    check(project["learner_profile"]["self_report"] == {}, "init 预置了学习者没说过的话")
    check("none" in project["learner_profile"]["source"], "source 应标明尚未提供自述")
    proc = case.run("start", "--project", "proj", "--offline")
    check(proc.returncode == 0, "start 失败", proc)
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    check(data["start_profile"]["answered"] is False, "非交互 start 不应假装已回答")
    check(data["start_profile"]["answers"] == {"api": "未回答", "tools": "未回答", "mode": "未回答"}, "未回答档位不对")
    # 补答：--ask --answers 必须写入 start_profile
    proc = case.run(
        "start", "--project", "proj", "--offline", "--ask",
        "--answers", "不确定,没有,二十分钟见到东西",
    )
    check(proc.returncode == 0, "start --ask --answers 失败", proc)
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    profile = data["start_profile"]
    check(profile["answered"] is True, f"补答后 answered 仍为 {profile['answered']}")
    check(
        profile["answers"] == {"api": "不确定", "tools": "没有", "mode": "二十分钟见到东西"},
        f"答案未持久化: {profile['answers']}",
    )
    check(profile["mapped_start"] == "M1-first", f"起点映射不对: {profile['mapped_start']}")
    check(profile["strictness"] == "standard" and profile["slice_minutes"] == 20, "档位/切片不对")
    check(len(case.events("start_profile_recorded")) >= 1, "没有 start_profile_recorded 事件")
    # 交互式 --ask 从 stdin 读取
    case.run("init", "--goal", "交互目标", "--dir", "proj-int")
    proc = case.run("start", "--project", "proj-int", "--offline", "--ask", input_text="2\n3\n1\n")
    check(proc.returncode == 0, "交互式 --ask 失败", proc)
    data = json.loads(case.run("status", "--project", "proj-int", "--json").stdout)
    check(
        data["start_profile"]["answers"] == {"api": "不确定", "tools": "没有", "mode": "二十分钟见到东西"},
        f"交互答案未落库: {data['start_profile']['answers']}",
    )
    # 显式自述只记录明说的内容
    case.run("init", "--goal", "自述目标", "--dir", "proj-self", "--self-report", "python=会一点,api=调用过")
    project = json.loads((case.root / "proj-self/.learnark/project.json").read_text(encoding="utf-8"))
    check(project["learner_profile"]["self_report"] == {"python": "会一点", "api": "调用过"}, "self-report 未按明说内容记录")
    check("learner_stated" in project["learner_profile"]["source"], "source 未标 learner_stated")


def _guide_reply(help_level: int) -> str:
    return update_block(
        {
            "mentor": "guide",
            "help_level": help_level,
            "attempt": {},
            "misconception": None,
            "next": "改一处后重新 artifact add + review",
            "mastery_delta": 0,
            "gap": [{"dim": "contract", "note": "已讲契约与参数校验，待复评"}],
        },
        "这张卡只讲 contract：工具定义是给模型看的契约。",
    )


def _review_only(case: Case) -> None:
    case.init()
    case.artifact()
    script = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
    proc = case.run("review", "--project", "proj", script=script)
    check(proc.returncode == 0, "review 失败", proc)


def _review_then_gap(case: Case) -> None:
    case.init()
    case.artifact()
    script = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
    proc = case.run("review", "--project", "proj", script=script)
    check(proc.returncode == 0, "review 失败", proc)
    gap_script = case.script([("gap learn", _guide_reply(3))])
    proc = case.run("gap", "learn", "g-M1-contract", "--project", "proj", script=gap_script)
    check(proc.returncode == 0, "gap learn 失败", proc)


def _finish_milestone(case: Case) -> dict:
    case.artifact("v2.py", "v2")
    review_script = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    proc = case.run("review", "--project", "proj", script=review_script)
    check(proc.returncode == 0, "复评失败", proc)
    ok = {
        "mentor": "critic",
        "help_level": 0,
        "attempt": {},
        "misconception": None,
        "next": "进入 M2",
        "mastery_delta": 0,
        "defense": defense_block(ok=True),
    }
    say_script = case.script([("我解释完了", update_block(ok))])
    proc = case.run("say", "我解释完了", "--project", "proj", script=say_script)
    check(proc.returncode == 0, "defense 失败", proc)
    return json.loads(case.run("status", "--project", "proj", "--json").stdout)


def test_guide_not_assisted(case: Case) -> None:
    """round-01 #2：guide 微课不计入 assisted_level，独立改完仍可 verified。"""
    _review_then_gap(case)
    case.artifact("fixed.py", "fixed")
    artifacts = case.read(".learnark/state/artifacts.json")["items"]
    check(artifacts[-1]["assisted_level"] == 0, f"guide 微课被算进 assisted_level: {artifacts[-1]['assisted_level']}")
    data = _finish_milestone(case)
    milestone = data["milestones"][0]
    check(milestone["status"] == "passed", f"应 verified passed，实际 {milestone['status']}")
    check(milestone["pass_evidence"].get("evidence_level") == "verified", "证据等级应为 verified")


def test_coach_help_counts(case: Case) -> None:
    """round-01 #2 反向：coach 的分步帮助仍应记入 assisted_level。"""
    _review_then_gap(case)
    coach = {
        "mentor": "coach",
        "help_level": 2,
        "attempt": {},
        "misconception": None,
        "next": "按三步改完",
        "mastery_delta": 0,
    }
    say_script = case.script([("给我分步", update_block(coach, "按三步改：一、二、三。"))])
    proc = case.run("say", "给我分步", "--project", "proj", script=say_script)
    check(proc.returncode == 0, "coach say 失败", proc)
    case.artifact("v2.py", "v2")
    artifacts = case.read(".learnark/state/artifacts.json")["items"]
    check(artifacts[-1]["assisted_level"] == 2, f"coach help 未计入: {artifacts[-1]['assisted_level']}")
    review_script = case.script([("", critic_update([("runnability", 3), ("contract", 3), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=review_script).returncode == 0, "复评失败")
    ok = {"mentor": "critic", "help_level": 0, "attempt": {}, "misconception": None, "next": "进入 M2",
          "mastery_delta": 0, "defense": defense_block(ok=True)}
    say_script = case.script([("我解释完了", update_block(ok))])
    check(case.run("say", "我解释完了", "--project", "proj", script=say_script).returncode == 0, "defense 失败")
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    check(data["milestones"][0]["status"] == "passed_assisted", "应记 passed_assisted")
    check(data["milestones"][0]["pass_evidence"].get("evidence_level") == "observed", "证据等级应为 observed")


def test_runtime_next_authoritative(case: Case) -> None:
    """round-01 #3：导师上下文必须带 runtime_next，且动作与它一致。"""
    _review_only(case)
    coach = {
        "mentor": "coach",
        "help_level": 1,
        "attempt": {},
        "misconception": None,
        "next": "新建 m1/agent_v2.py 独立重写",
        "mastery_delta": 0,
    }
    script = case.script(
        [("我接下来做什么", update_block(coach, "先独立重写一份 m1/agent_v2.py 吧，脱离现在的文件。"))]
    )
    proc = case.run("say", "我接下来做什么", "--project", "proj", script=script)
    check(proc.returncode == 0, "say 失败", proc)
    check("▶ 唯一动作：gap_learn" in proc.stdout, "输出未提示权威动作", proc)
    turns = [event for event in case.events("mentor_turn") if event["payload"].get("mentor") == "coach"]
    check(turns, "没有 coach mentor_turn 事件")
    runtime_next = turns[-1]["payload"].get("runtime_next") or {}
    check(runtime_next.get("action") == "gap_learn", f"权威动作不是 gap_learn: {runtime_next}")
    check(runtime_next.get("ref") == "g-M1-contract", f"权威 ref 不对: {runtime_next.get('ref')}")
    session_files = sorted((case.proj / "sessions").glob("*.md"))
    session_text = session_files[-1].read_text(encoding="utf-8")
    check("runtime_next: gap_learn" in session_text, "会话记录未写 runtime_next")


def test_unevidenced_lowers(case: Case) -> None:
    """round-01 #4：达阈值但无 evidence_line/evidence_path -> 降到 threshold-1。"""
    case.init()
    case.artifact()
    raw = [
        {"dim": "runnability", "score": 3, "note": "看起来能跑，但没在干净目录验证"},
        {"dim": "contract", "score": 2, "note": "参数校验缺失"},
        {"dim": "robustness", "score": 2, "note": "坏路径直接崩"},
        {"dim": "explainability", "score": 1, "note": "无设计说明"},
    ]
    script = case.script([("", critic_update([], raw_rubric=raw))])
    proc = case.run("review", "--project", "proj", script=script)
    check(proc.returncode == 0, "缺证据应降分而不是拒绝", proc)
    review = case.read(".learnark/state/reviews.json")["items"][-1]
    scores = {d["dim"]: d["score"] for d in review["rubric"]}
    check(scores["runnability"] == 2, f"缺证据的达标分应降为 2: {scores}")
    check(review["unevidenced"] and review["unevidenced"][0]["dim"] == "runnability", "unevidenced 未记录")
    check(len(case.events("rubric_unevidenced")) == 1, "rubric_unevidenced 事件缺失")
    gaps = {g["gap_id"] for g in case.read(".learnark/state/gaps.json")["items"]}
    check("g-M1-runnability" in gaps, "降分后应生成 runnability 缺口卡")
    # 带 evidence_line / evidence_path 的达标分保留原分
    case.artifact("v2.py", "v2")
    raw2 = [
        {"dim": "runnability", "score": 3, "note": "一条命令跑通", "evidence_line": 12},
        {"dim": "contract", "score": 3, "note": "工具 schema 与解析一致", "evidence_path": "m1/agent.py:9"},
        {"dim": "robustness", "score": 3, "note": "异常回填见第 40 行"},
        {"dim": "explainability", "score": 3, "note": "docs/m1-design.md 第 3 段"},
    ]
    script2 = case.script([("", critic_update([], raw_rubric=raw2))])
    proc = case.run("review", "--project", "proj", script=script2)
    check(proc.returncode == 0, "带证据的评审失败", proc)
    review2 = case.read(".learnark/state/reviews.json")["items"][-1]
    scores2 = {d["dim"]: d["score"] for d in review2["rubric"]}
    check(scores2 == {"runnability": 3, "contract": 3, "robustness": 3, "explainability": 3}, f"带证据分数被误降: {scores2}")
    check(not review2["unevidenced"], "带证据不应记 unevidenced")
    # 反例：note 明说“无行号级证据”不能当作证据（真实 API 轮次里出现过）
    case.artifact("v3.py", "v3")
    raw3 = [
        {"dim": "runnability", "score": 3, "note": "一条命令跑通", "evidence_line": 12},
        {"dim": "contract", "score": 3, "note": "工具 schema 与解析一致", "evidence_path": "m1/agent.py:9"},
        {"dim": "robustness", "score": 3, "note": "异常回填见第 40 行"},
        {"dim": "explainability", "score": 2, "note": "无 docs/m1-design.md，也无行号级证据"},
    ]
    script3 = case.script([("", critic_update([], raw_rubric=raw3))])
    proc = case.run("review", "--project", "proj", script=script3)
    check(proc.returncode == 0, "否定式 note 评审失败", proc)
    review3 = case.read(".learnark/state/reviews.json")["items"][-1]
    scores3 = {d["dim"]: d["score"] for d in review3["rubric"]}
    check(scores3["explainability"] == 1, f"“无行号级证据”被当成证据: {scores3}")
    check(
        any(item["dim"] == "explainability" for item in review3["unevidenced"]),
        "explainability 应记 unevidenced",
    )
    check(len(case.events("rubric_unevidenced")) == 2, "rubric_unevidenced 事件数不对")


def test_help_level_inferred(case: Case) -> None:
    """round-02 #1：导师没写 help_level 时按骨架/答案证据推断并落账。"""
    case.init()
    plain = {"mentor": "coach", "help_level": 1, "attempt": {}, "misconception": None,
             "next": "先读需求", "mastery_delta": 0}
    script = case.script([("我先想想", update_block(plain, "先读一遍需求，再决定下一步。"))])
    proc = case.run("say", "我先想想", "--project", "proj", script=script)
    check(proc.returncode == 0, "say 失败", proc)
    check(not case.events("help_level_inferred"), "没有骨架时不应推断")
    # 学习者明确要答案 + 导师给 4 步骨架，机器块省略 help_level
    skeleton = (
        "好，按四步走：一，定义 TOOLS；二，解析 tool_calls；三，执行工具；四，把结果回填后再请求。"
        "这是骨架，不算你的作品。"
    )
    ask = {"mentor": "coach", "attempt": {}, "misconception": None, "next": "按骨架填", "mastery_delta": 0}
    script = case.script([("直接把答案", update_block(ask, skeleton))])
    proc = case.run("say", "别绕了，直接把答案/代码给我吧", "--project", "proj", script=script)
    check(proc.returncode == 0, "ask say 失败", proc)
    check("help_level_inferred" in proc.stdout, "未提示帮助等级推断", proc)
    turns = [event for event in case.events("mentor_turn") if event["payload"].get("mentor") == "coach"]
    last = turns[-1]["payload"]
    check(last.get("help_level") == 3, f"应推断 L3，实际 {last.get('help_level')}")
    check(last.get("help_level_inferred") is True, "mentor_turn 未标记推断")
    inferred = case.events("help_level_inferred")
    check(inferred and inferred[-1]["payload"]["inferred"] == 3, "help_level_inferred 事件不对")
    session_text = sorted((case.proj / "sessions").glob("*.md"))[-1].read_text(encoding="utf-8")
    check("help_level: 3" in session_text, "会话记录未写 help_level 3")
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    check(data["last_help_level"] == 3 and data["max_help_level"] == 3, "status 未暴露帮助等级")
    check("帮助等级" in case.run("status", "--project", "proj").stdout, "人读 status 未显示帮助等级")
    proc = case.artifact()
    check("assisted_level=3" in proc.stdout, "assisted_level 未反映 L3", proc)


def test_authority_and_conflict(case: Case) -> None:
    """round-02 #2：▶ 唯一动作 + 冲突记录。"""
    _review_only(case)
    coach = {
        "mentor": "coach",
        "help_level": 1,
        "attempt": {},
        "misconception": None,
        "next": "先 review 一次",
        "mastery_delta": 0,
    }
    script = case.script([("我接下来做什么", update_block(coach, "先 review 一次，再考虑微课。"))])
    proc = case.run("say", "我接下来做什么", "--project", "proj", script=script)
    check(proc.returncode == 0, "say 失败", proc)
    check("▶ 唯一动作：gap_learn" in proc.stdout, "未打印权威动作", proc)
    conflicts = case.events("mentor_next_conflict")
    check(conflicts, "没有记录 mentor_next_conflict")
    payload = conflicts[-1]["payload"]
    check(payload.get("runtime_action") == "gap_learn", f"runtime_action 不对: {payload}")
    check(payload.get("mentioned") == "review", f"mentioned 不对: {payload}")
    session_text = sorted((case.proj / "sessions").glob("*.md"))[-1].read_text(encoding="utf-8")
    check("runtime_next: gap_learn" in session_text, "会话未记录 runtime_next")
    check("conflict" in session_text, "会话未记录冲突")


def test_slice_persisted(case: Case) -> None:
    """round-02 #3：--minutes 必须持久化到 start_profile 并贯穿后续 next。"""
    case.init()
    proc = case.run(
        "start", "--project", "proj", "--offline", "--ask",
        "--answers", "能,没做过,一次做完一个项目", "--minutes", "20",
    )
    check(proc.returncode == 0, "start 失败", proc)
    data = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    check(data["start_profile"]["slice_minutes"] == 20, f"slice 未持久化: {data['start_profile']}")
    check(data["start_profile"]["slice_source"] == "--minutes", "slice 来源未记录")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["slice"] == 20, f"next 用了 {nxt['slice']} 分钟")
    overridden = json.loads(case.run("next", "--project", "proj", "--json", "--minutes", "60").stdout)
    check(overridden["slice"] == 60, "单次 --minutes 未覆盖")
    again = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(again["slice"] == 20, "单次 --minutes 不应改持久切片")


def test_multi_path_artifact(case: Case) -> None:
    """round-02 #4：一次登记多个交付物；critic 能看到已登记集合。"""
    case.init()
    docs = case.root / "docs"
    docs.mkdir(exist_ok=True)
    code = case.root / "agent.py"
    code.write_text(artifact_text("code"), encoding="utf-8")
    design = docs / "m1-design.md"
    design.write_text("# m1 设计说明\n工具切分与结果回填见第 3 段。\n" * 3, encoding="utf-8")
    proc = case.run("artifact", "add", code, design, "--project", "proj")
    check(proc.returncode == 0, "多文件登记失败", proc)
    artifacts = case.read(".learnark/state/artifacts.json")["items"]
    check(len(artifacts) == 2, f"只登记了 {len(artifacts)} 件")
    paths = {item["path"] for item in artifacts}
    check(any(path.endswith("agent.py") for path in paths), "agent.py 未登记")
    check(any(path.endswith("m1-design.md") for path in paths), "设计说明未登记")
    review_script = case.script(
        [("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 2)]))]
    )
    proc = case.run("review", "--project", "proj", script=review_script)
    check(proc.returncode == 0, "review 失败", proc)
    recorded = case.events("review_recorded")[-1]["payload"]
    registered = set(recorded.get("registered_paths") or [])
    check(any(path.endswith("m1-design.md") for path in registered), f"评审未拿到已登记集合: {registered}")
    check(not case.events("review_note_conflict"), "正常评审不应报冲突")
    # 另一件作品 + note 声称已登记的设计说明缺失 -> 记录 conflict
    case.artifact("v2.py", "v2")
    raw = [
        {"dim": "runnability", "score": 3, "note": "第 12 行跑通"},
        {"dim": "contract", "score": 2, "note": "参数校验缺失"},
        {"dim": "robustness", "score": 2, "note": "异常未回填"},
        {"dim": "explainability", "score": 1, "note": "无 docs/m1-design.md，缺少设计说明"},
    ]
    script = case.script([("", critic_update([], raw_rubric=raw))])
    proc = case.run("review", "--project", "proj", script=script)
    check(proc.returncode == 0, "review2 失败", proc)
    conflicts = case.events("review_note_conflict")
    check(conflicts, "未记录 review_note_conflict")
    check("m1-design.md" in json.dumps(conflicts[-1]["payload"], ensure_ascii=False), "冲突未指向设计说明")
    # --note 与多路径混用要报用法错误
    proc = case.run("artifact", "add", code, design, "--note", "x", "--project", "proj")
    check(proc.returncode == 2, "--note 与多路径应报用法错误", proc)


def test_say_stdin(case: Case) -> None:
    """round-02 #5：文档化的 say - 从 stdin 读。"""
    case.init()
    proc = case.run("say", "-", "--project", "proj", "--offline", input_text="我从标准输入发言\n")
    check(proc.returncode == 0, "say - 失败", proc)
    session_text = sorted((case.proj / "sessions").glob("*.md"))[-1].read_text(encoding="utf-8")
    check("我从标准输入发言" in session_text, "stdin 内容未写入会话")


def _git(args: list[str], cwd: Path):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _append_raw_event(clone: Path, event_id: str, marker: str) -> None:
    """Simulate another device appending one journal event (journal-only divergence)."""
    path = clone / ".learnark/journal/events.jsonl"
    event = {
        "id": event_id,
        "seq": 9999,
        "at": "2026-11-04T04:00:00+08:00",
        "kind": "test_marker",
        "actor": "test",
        "simulated": True,
        "dedupe_key": f"test:{marker}",
        "payload": {"marker": marker},
    }
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _clone_pair(case: Case) -> tuple[Path, Path, Path]:
    bare = case.root / "bare.git"
    check(_git(["init", "--bare", str(bare)], case.root).returncode == 0, "bare 仓库创建失败")
    check(
        _git(["-C", str(case.proj), "remote", "add", "origin", str(bare)], case.root).returncode == 0,
        "添加远程失败",
    )
    first = case.run("sync", "--project", "proj")
    check(first.returncode == 0 and "pushed=yes" in first.stdout, "初始推送失败", first)
    clones = []
    for name in ("c1", "c2"):
        target = case.root / name
        result = _git(["clone", str(bare), str(target)], case.root)
        check(result.returncode == 0, f"{name} 克隆失败: {result.stderr}")
        _git(["-C", str(target), "config", "user.email", "t@example.com"], case.root)
        _git(["-C", str(target), "config", "user.name", "Tester"], case.root)
        clones.append(target)
    return bare, clones[0], clones[1]


def test_sync_recover_journal(case: Case) -> None:
    """core 1.0.2：两个克隆各追加事件 -> sync --recover 并集合并并推送。"""
    case.init()
    case.run("start", "--project", "proj", "--offline")
    case.run("pause", "--project", "proj")
    bare, c1, c2 = _clone_pair(case)
    _append_raw_event(c1, "ev_c1_only", "c1")
    _append_raw_event(c2, "ev_c2_only", "c2")
    check(
        _git(["-C", str(c1), "add", ".learnark/journal/events.jsonl"], case.root).returncode == 0,
        "c1 add 失败",
    )
    check(_git(["-C", str(c1), "commit", "-m", "c1 event"], case.root).returncode == 0, "c1 commit 失败")
    check(_git(["-C", str(c1), "push"], case.root).returncode == 0, "c1 push 失败")
    check(
        _git(["-C", str(c2), "add", ".learnark/journal/events.jsonl"], case.root).returncode == 0,
        "c2 add 失败",
    )
    check(_git(["-C", str(c2), "commit", "-m", "c2 event"], case.root).returncode == 0, "c2 commit 失败")
    proc = case.run("sync", "--recover", cwd=c2)
    check(proc.returncode == 0, "sync --recover 失败", proc)
    check("recover=yes" in proc.stdout and "pushed=yes" in proc.stdout, "recover 未推送", proc)
    remote = _git(["-C", str(bare), "show", "HEAD:.learnark/journal/events.jsonl"], case.root)
    check(remote.returncode == 0, "远程 journal 读取失败", None)
    text = remote.stdout
    check("ev_c1_only" in text and "ev_c2_only" in text, "并集合并丢失事件", None)
    seqs = [json.loads(line)["seq"] for line in text.splitlines() if line.strip()]
    check(seqs == list(range(1, len(seqs) + 1)), f"合并后 seq 不连续: {seqs}")


def test_sync_snapshot_conflict(case: Case) -> None:
    """core 1.0.2：快照冲突不自动合并，sync 退出 3 并列出文件；本地不丢。"""
    case.init()
    case.run("start", "--project", "proj", "--offline")
    case.run("pause", "--project", "proj")
    bare, c1, c2 = _clone_pair(case)
    one = case.run("say", "我在 clone1 学习", cwd=c1)
    check(one.returncode == 0, "c1 say 失败", one)
    check(case.run("sync", cwd=c1).returncode == 0, "c1 sync 失败")
    two = case.run("say", "我在 clone2 学习", cwd=c2)
    check(two.returncode == 0, "c2 say 失败", two)
    proc = case.run("sync", cwd=c2)
    check(proc.returncode == 3, f"快照冲突应退出 3，实际 {proc.returncode}", proc)
    combined = proc.stdout + proc.stderr
    check("conflict" in proc.stdout.lower(), "未报告冲突", proc)
    check("state" in combined or "session.json" in combined, "未列出冲突文件", proc)
    check("冲突文件" in combined or "Conflicting paths" in combined, "冲突输出未给出可执行的冲突文件列表", proc)
    session_text = "".join(
        path.read_text(encoding="utf-8") for path in sorted((c2 / "sessions").glob("*.md"))
    )
    check("我在 clone2 学习" in session_text, "冲突后本地记录被覆盖")
    status = case.run("status", "--json", cwd=c2)
    payload = json.loads(status.stdout)
    check(payload["sync"]["diverged"] is True, "status 未标记 diverged")
    human = case.run("status", cwd=c2)
    check("分叉" in human.stdout, "人读 status 未提示分叉", human)
    doctor = case.run("doctor", cwd=c2)
    check(doctor.returncode == 3, "doctor 未因 diverged 失败", doctor)
    recover = case.run("sync", "--recover", cwd=c2)
    check(recover.returncode == 3, "快照冲突时 --recover 应退出 3", recover)
    check("session.json" in (recover.stdout + recover.stderr), "recover 未列出快照冲突文件", recover)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gap_learn_advances(case: Case) -> None:
    """round-03 #1：微课之后 next 前进；重复微课被抑制且带上次讲解。"""
    _review_then_gap(case)
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] != "gap_learn", f"gap learn 后 next 仍是 {nxt['action']}")
    check(nxt["action"] == "do_task", f"gap learn 后应去改作品，实际 {nxt['action']}")
    # 重复 gap learn：不重复讲，记录 gap_repeat_suppressed，并带上次讲解
    before_turns = len(case.events("mentor_turn"))
    repeat = case.run(
        "gap", "learn", "g-M1-contract", "--project", "proj", script=case.script([("", _guide_reply(2))])
    )
    check(repeat.returncode == 0, "重复 gap learn 不应失败", repeat)
    check("已上过微课" in repeat.stdout, "未提示已上过微课", repeat)
    check("上次讲解摘要" in repeat.stdout, "未展示上次讲解", repeat)
    suppressed = case.events("gap_repeat_suppressed")
    check(suppressed, "没有 gap_repeat_suppressed 事件")
    payload = suppressed[-1]["payload"]
    check(payload.get("context_has_prior") is True, f"上下文未带上次讲解: {payload}")
    check("contract" in (payload.get("prior_explanation") or ""), "prior_explanation 为空")
    check(len(case.events("mentor_turn")) == before_turns, "重复微课不应再调用导师")
    # --force 可以重讲
    forced = case.run(
        "gap", "learn", "g-M1-contract", "--project", "proj", "--force",
        script=case.script([("gap learn", _guide_reply(3))]),
    )
    check(forced.returncode == 0 and "不重复讲" not in forced.stdout, "--force 未重讲", forced)
    check(len(case.events("mentor_turn")) == before_turns + 1, "--force 未产生导师回合")
    # 复评仍失败 -> 缺口重新打开，允许再学
    case.artifact("v3.py", "v3")
    review = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=review).returncode == 0, "复评失败")
    gap = next(g for g in case.read(".learnark/state/gaps.json")["items"] if g["gap_id"] == "g-M1-contract")
    check(gap["status"] == "open", f"复评失败后缺口未重开: {gap['status']}")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] == "gap_learn", f"复评失败后应回到 gap_learn，实际 {nxt['action']}")


def test_registered_set_and_denial(case: Case) -> None:
    """round-03 #1/#3：已登记集合进入导师上下文；否认已登记作品要记账；guide 正文异动作要记冲突。"""
    case.init()
    docs = case.root / "docs"
    docs.mkdir(exist_ok=True)
    code = case.root / "agent.py"
    code.write_text(artifact_text("code"), encoding="utf-8")
    design = docs / "m1-design.md"
    design.write_text("# 设计说明\n" + "工具切分与回填。\n" * 3, encoding="utf-8")
    proc = case.run("artifact", "add", code, design, "--project", "proj")
    check(proc.returncode == 0, "多文件登记失败", proc)
    coach = {
        "mentor": "coach", "help_level": 1, "attempt": {}, "misconception": None,
        "next": "先登记作品", "mastery_delta": 0,
    }
    script = case.script([("我先检查", update_block(coach, "我没有看到已登记的作品文件，请先 artifact add。"))])
    proc = case.run("say", "我先检查一下", "--project", "proj", script=script)
    check(proc.returncode == 0, "say 失败", proc)
    denial = [event for event in case.events("review_note_conflict") if event["payload"].get("denied")]
    check(denial, "导师否认已登记作品但没有记账")
    check(len(denial[-1]["payload"].get("registered_paths") or []) == 2, "否认事件未带完整已登记集合")
    check("但运行时已有 2 件" in proc.stdout, "未在输出中纠正", proc)
    # 评审失败 -> gap_learn，然后 guide 在 say 里给正文动作，必须记 conflict
    review = case.script([("", critic_update([("runnability", 3), ("contract", 2), ("robustness", 3), ("explainability", 3)]))])
    check(case.run("review", "--project", "proj", script=review).returncode == 0, "review 失败")
    check(case.run("switch", "guide", "--project", "proj").returncode == 0, "switch guide 失败")
    guide = {
        "mentor": "guide", "help_level": 2, "attempt": {}, "misconception": None,
        "next": "回到作品改一处", "mastery_delta": 0,
    }
    script = case.script(
        [("接下来做什么", update_block(guide, "回到作品改一处，重新 artifact add + review。"))]
    )
    proc = case.run("say", "接下来做什么", "--project", "proj", script=script)
    check(proc.returncode == 0, "guide say 失败", proc)
    check("▶ 唯一动作：gap_learn" in proc.stdout, "未打印唯一权威动作", proc)
    check(proc.stdout.count("▶ 唯一动作") == 1, f"一次回复出现多行权威动作: {proc.stdout}")
    conflicts = case.events("mentor_next_conflict")
    check(conflicts, "guide 正文的异动作未记 mentor_next_conflict")
    check(conflicts[-1]["payload"].get("runtime_action") == "gap_learn", "冲突未指向 gap_learn")


def test_claim_without_evidence(case: Case) -> None:
    """round-03 #4：评审 note 的数量断言无行号证据 -> claim_without_evidence。"""
    case.init()
    case.artifact()
    raw = [
        {"dim": "runnability", "score": 2, "note": "有 6 步上限，能跑"},
        {"dim": "contract", "score": 2, "note": "参数缺校验"},
        {"dim": "robustness", "score": 2, "note": "异常未回填"},
        {"dim": "explainability", "score": 1, "note": "无设计说明"},
    ]
    script = case.script([("", critic_update([], raw_rubric=raw))])
    check(case.run("review", "--project", "proj", script=script).returncode == 0, "review 失败")
    events = case.events("claim_without_evidence")
    check(events, "未记录 claim_without_evidence")
    check("6 步" in json.dumps(events[-1]["payload"], ensure_ascii=False), "事件未指出具体断言")
    review = case.read(".learnark/state/reviews.json")["items"][-1]
    runnability = next(dim for dim in review["rubric"] if dim["dim"] == "runnability")
    check("6 步" not in runnability["note"], f"可见 note 未省略无依据断言: {runnability['note']}")
    check("已省略" in runnability["note"], "note 未说明省略了什么")
    # 带 evidence_line 的同一断言不再记录
    case.artifact("v2.py", "v2")
    raw2 = [
        {"dim": "runnability", "score": 2, "note": "有 6 步上限，能跑", "evidence_line": 12},
        {"dim": "contract", "score": 2, "note": "参数缺校验"},
        {"dim": "robustness", "score": 2, "note": "异常未回填"},
        {"dim": "explainability", "score": 1, "note": "无设计说明"},
    ]
    script2 = case.script([("", critic_update([], raw_rubric=raw2))])
    check(case.run("review", "--project", "proj", script=script2).returncode == 0, "review2 失败")
    check(len(case.events("claim_without_evidence")) == 1, "带证据的断言不应再记事件")


def test_clone_hash_consistency(case: Case) -> None:
    """round-04 #3：克隆后作品 sha 一致；旧项目缺 .gitattributes 时 doctor 提示且 sync 补上。"""
    case.init()
    case.artifact()
    case.run("pause", "--project", "proj")
    bare, c1, _c2 = _clone_pair(case)
    original = case.proj / "artifacts/M1/agent.py"
    cloned = c1 / "artifacts/M1/agent.py"
    check(original.is_file() and cloned.is_file(), "克隆后缺少作品文件")
    check(_sha256(original) == _sha256(cloned), "克隆后作品 sha 不一致（CRLF 未固定）")
    doctor = case.run("doctor", cwd=c1)
    check(doctor.returncode == 0, "克隆后 doctor 失败", doctor)
    # 旧项目：删除 .gitattributes，doctor 提示，sync 自动补回
    attributes = c1 / ".gitattributes"
    attributes.unlink()
    doctor = case.run("doctor", cwd=c1)
    check("sync 或 init" in doctor.stdout, "doctor 未说明如何补 .gitattributes", doctor)
    sync = case.run("sync", cwd=c1)
    check(sync.returncode == 0, "sync 失败", sync)
    check((c1 / ".gitattributes").is_file(), "sync 未补回 .gitattributes")


def test_email_template(case: Case) -> None:
    proc = case.run("init", "--goal", "英文工作邮件", "--dir", "mail", "--template", "email")
    check(proc.returncode == 0, "email 模板 init 失败", proc)
    brief = json.loads((case.root / "mail/.learnark/state/brief.json").read_text(encoding="utf-8"))
    check([m["id"] for m in brief["milestones"]] == ["E1", "E2", "E3"], "email 里程碑 id 不对")
    dims = [d["dim"] for d in brief["milestones"][0]["rubric"]]
    check(dims == ["structure", "tone", "clarity", "scenario_fit"], f"email rubric 不对：{dims}")
    draft = case.root / "e1-apology.md"
    draft.write_text("Subject: Project timeline update\n\nDear Alex,\n\nWe need to move the delivery date.\n" * 3, encoding="utf-8")
    proc = case.run("artifact", "add", draft, "--project", "mail")
    check(proc.returncode == 0, "email 作品登记失败", proc)
    image = case.root / "shot.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    proc = case.run("artifact", "add", image, "--project", "mail")
    check(proc.returncode == 2, ".png 应被拒绝", proc)
    check(".png" in (proc.stdout + proc.stderr) or "后缀" in (proc.stdout + proc.stderr), "拒绝原因不明确", proc)


def test_deterministic_opening_task(case: Case) -> None:
    """round-05 #1：同样输入（模板+里程碑+切片+档案）必须得到同一个固定任务。"""
    tasks = {}
    for name in ("p1", "p2"):
        check(case.run("init", "--goal", "Agent 开发", "--dir", name).returncode == 0, f"{name} init 失败")
        proc = case.run(
            "start", "--project", name, "--offline", "--minutes", "20",
            "--answers", "不确定,没有,二十分钟见到东西",
        )
        check(proc.returncode == 0 and "本步任务" in proc.stdout, f"{name} start 未给固定任务", proc)
        tasks[name] = json.loads(case.run("task", "--project", name, "--json").stdout)["task"]
    check(tasks["p1"]["task_id"] == tasks["p2"]["task_id"], f"task_id 不确定: {tasks}")
    check(tasks["p1"]["text"] == tasks["p2"]["text"], "任务文本不确定")
    check("m1/agent.py" in tasks["p1"]["text"], "开场任务不是 M1 最小任务")
    bigger = json.loads(case.run("task", "--project", "p1", "--json", "--minutes", "60").stdout)["task"]
    check(bigger["task_id"] != tasks["p1"]["task_id"], "切片变化未改变固定任务")
    check(bigger["slice"] == 60, "60 分钟切片未生效")


def test_gap_unverified_not_open(case: Case) -> None:
    """round-05 #2：达标但缺证据的维度记 unverified，不算开放缺口，next 只数低分维度。"""
    case.init()
    case.artifact()
    raw = [
        {"dim": "runnability", "score": 3, "note": note_for("runnability", 3, 5), "evidence_line": 5},
        {"dim": "contract", "score": 3, "note": note_for("contract", 3, 8), "evidence_line": 8},
        {"dim": "robustness", "score": 3, "note": note_for("robustness", 3, 12), "evidence_line": 12},
        {"dim": "explainability", "score": 3, "note": "设计说明写了工具切分，但没有行号", "evidence_path": "docs/m1-design.md"},
    ]
    script = case.script([("", critic_update([], raw_rubric=raw))])
    proc = case.run("review", "--project", "proj", script=script)
    check(proc.returncode == 0, "review 失败", proc)
    check("达标但缺证据" in proc.stdout and "unverified" in proc.stdout, "未报告 unverified", proc)
    gaps = case.read(".learnark/state/gaps.json")["items"]
    card = next(g for g in gaps if g["gap_id"] == "g-M1-explainability")
    check(card["status"] == "unverified", f"缺口状态不是 unverified: {card['status']}")
    check(not [g for g in gaps if g.get("status") in ("open", "learning")], "unverified 被算成开放缺口")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] == "defend", f"next 不应回到缺口: {nxt['action']}")
    check("低于阈值" not in nxt.get("reason", ""), "next 把 unverified 算进低分维度")
    status = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    check(not status["gaps"]["open"], "status 的 open 含 unverified")
    check(any(g["gap_id"] == "g-M1-explainability" for g in status["gaps"]["unverified"]), "status 未列 unverified")


def test_defense_question_unsupported(case: Case) -> None:
    """round-05 #3：防御题引用未提供的数字 -> 替换并记录 defense_question_unsupported。"""
    case.init()
    plain = case.root / "plain.py"
    plain.write_text("\n".join(f'# token-{word}' for word in ("alpha", "beta", "gamma", "delta") * 15) + "\n", encoding="utf-8")
    check(case.run("artifact", "add", plain, "--project", "proj").returncode == 0, "artifact 失败")
    raw = [
        {"dim": "runnability", "score": 3, "note": note_for("runnability", 3, 5), "evidence_line": 5},
        {"dim": "contract", "score": 3, "note": note_for("contract", 3, 8), "evidence_line": 8},
        {"dim": "robustness", "score": 3, "note": note_for("robustness", 3, 12), "evidence_line": 12},
        {"dim": "explainability", "score": 3, "note": note_for("explainability", 3, 20), "evidence_line": 20},
    ]
    script = case.script([("", critic_update([], raw_rubric=raw))])
    check(case.run("review", "--project", "proj", script=script).returncode == 0, "review 失败")
    defense = case.read(".learnark/state/defense.json")["items"][-1]
    q3 = next(q for q in defense["questions"] if q["qid"] == "m1-q3")
    check("6" not in q3["question"], f"未提供的 6 仍在问题里: {q3['question']}")
    check(q3.get("original_question"), "没有保留原问题以便审计")
    events = case.events("defense_question_unsupported")
    check(events, "没有 defense_question_unsupported 事件")
    check("6" in json.dumps(events[-1]["payload"], ensure_ascii=False), "事件未记录缺失数字")
    # 作品里真的写了 6 -> 原题保留
    case2 = Case("defense-supported")
    case2.init()
    case2.artifact(extra="MAX_STEPS = 6")
    script2 = case2.script([("", critic_update([], raw_rubric=raw))])
    check(case2.run("review", "--project", "proj", script=script2).returncode == 0, "review2 失败")
    defense2 = case2.read(".learnark/state/defense.json")["items"][-1]
    q3b = next(q for q in defense2["questions"] if q["qid"] == "m1-q3")
    check("6" in q3b["question"], "作品含 6 时原问题不应被替换")


def _email_body(lines: int = 12) -> str:
    body = ["Subject: Apology for the delayed delivery", ""]
    body += [f"Line {i}: we are sorry about the delay." for i in range(3, lines + 1)]
    return "\n".join(body) + "\n"


def _email_review(case: Case, scores: dict[str, int], evidence: dict[str, int]) -> subprocess.CompletedProcess:
    raw = [
        {"dim": dim, "score": scores[dim], "note": f"{dim} 见第 {evidence[dim]} 行", "evidence_line": evidence[dim]}
        for dim in ("structure", "tone", "clarity", "scenario_fit")
    ]
    return case.run("review", "--project", "proj", script=case.script([("", critic_update([], raw_rubric=raw))]))


def test_email_template_consistency(case: Case) -> None:
    """round-06 #5/#6/#8/#9：写作模板不出现编程内容，切片/定位/任务/防御都是写作语言。"""
    proc = case.run("init", "--goal", "英文工作邮件写作", "--dir", "proj", "--template", "email")
    check(proc.returncode == 0, "email init 失败", proc)
    start = case.run("start", "--project", "proj", "--offline", "--ask", input_text="\n\n\n")
    check(start.returncode == 0, "email start 失败", start)
    profile = case.read(".learnark/state/brief.json")["start_profile"]
    check(all(value == "未回答" for value in profile["answers"].values()), f"空回车被记成能力: {profile['answers']}")
    check(profile["mapped_start"].startswith("E1"), f"起点不是 E1: {profile['mapped_start']}")
    task = json.loads(case.run("task", "--project", "proj", "--json").stdout)
    check(task["deliverable"]["allowed_ext"] == [".md", ".txt"], f"email 允许后缀不对: {task['deliverable']}")
    check("邮件" in task["task"]["text"], f"任务不是写作任务: {task['task']['text']}")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check("邮件" in nxt["slice_hint"] and "运行" not in nxt["slice_hint"], f"切片提示仍是编程: {nxt['slice_hint']}")
    # 登记一封邮件并复评到通过，检查 review/defend 文案
    path = case.root / "e1-apology.md"
    path.write_text(_email_body(), encoding="utf-8")
    check(case.run("artifact", "add", path, "--project", "proj").returncode == 0, "邮件登记失败")
    check(_email_review(case, {"structure": 3, "tone": 3, "clarity": 3, "scenario_fit": 3}, {"structure": 3, "tone": 5, "clarity": 7, "scenario_fit": 9}).returncode == 0, "review 失败")
    defend = case.run("defend", "--project", "proj")
    check(defend.returncode == 0, "defend 失败", defend)
    check("e1-q1" in defend.stdout and "m1-q1" not in defend.stdout, "防御示例没有用实际 qid", defend)
    status = case.run("status", "--project", "proj")
    check(status.returncode == 0, "status 失败", status)
    for label, text in (("task", json.dumps(task, ensure_ascii=False)), ("next", json.dumps(nxt, ensure_ascii=False)),
                        ("defend", defend.stdout), ("status", status.stdout),
                        ("README", (case.proj / "README.md").read_text(encoding="utf-8")),
                        ("AGENTS", (case.proj / "AGENTS.md").read_text(encoding="utf-8"))):
        tokens = ("def ", "print(", "import ", "agent", "API", "m1-", "m1/", "代码")
        if label in ("task", "next", "defend", "status"):
            tokens += (".py",)
        for token in tokens:
            check(token not in text, f"{label} 残留编程词 {token!r}")
    guidance = forge_mentor.template_guidance({"template": "email"})
    check("禁止 Python" in guidance and "示例可用 Python" not in guidance, "写作模板提示词未禁用代码")


def test_status_reviews_capability(case: Case) -> None:
    """round-06 #7：status 显示最近评审（跨里程碑）与强项/待补。"""
    case.init(template="email", goal="英文工作邮件写作")
    path = case.root / "e1.md"
    path.write_text(_email_body(), encoding="utf-8")
    case.run("artifact", "add", path, "--project", "proj")
    check(_email_review(case, {"structure": 3, "tone": 3, "clarity": 2, "scenario_fit": 2}, {"structure": 3, "tone": 5, "clarity": 7, "scenario_fit": 9}).returncode == 0, "review1 失败")
    path.write_text(_email_body() + "Best regards,\n", encoding="utf-8")
    case.run("artifact", "add", path, "--project", "proj")
    check(_email_review(case, {"structure": 3, "tone": 3, "clarity": 3, "scenario_fit": 3}, {"structure": 3, "tone": 5, "clarity": 7, "scenario_fit": 9}).returncode == 0, "review2 失败")
    case.run("defend", "--project", "proj")
    status = json.loads(case.run("status", "--project", "proj", "--json").stdout)
    latest = status["reviews"]["latest"]
    check(latest and latest["id"].startswith("r-E1-"), f"reviews.latest 丢失: {latest}")
    check(latest["milestone"] == "E1", "latest 的里程碑不对")
    check(status["capability"]["strengths"], "capability 没有强项")
    human = case.run("status", "--project", "proj").stdout
    check("最近评审：r-E1-" in human, "人读 status 仍显示最近评审：无", None)
    check("强项" in human and "待补" in human, "status 没有能力视图", None)


def test_review_target_visible(case: Case) -> None:
    """round-05 #4：next/review 指向同一件作品（优先代码），并把目标 id/件数打出来。"""
    case.init()
    doc = case.root / "design.md"
    doc.write_text("# design\n" + "工具切分。\n" * 3, encoding="utf-8")
    check(case.run("artifact", "add", doc, "--project", "proj").returncode == 0, "doc 登记失败")
    code = case.root / "agent.py"
    code.write_text(artifact_text("code"), encoding="utf-8")
    check(case.run("artifact", "add", code, "--project", "proj").returncode == 0, "code 登记失败")
    nxt = json.loads(case.run("next", "--project", "proj", "--json").stdout)
    check(nxt["action"] == "review", "next 应为 review")
    items = case.read(".learnark/state/artifacts.json")["items"]
    code_id = next(item["id"] for item in items if str(item["path"]).endswith("agent.py"))
    check(nxt["ref"] == code_id, f"review ref 未优先代码件: {nxt['ref']} != {code_id}")
    check(nxt["ref"] in (nxt.get("artifacts") or []), f"ref 不在本批作品: {nxt}")
    proc = case.run("review", "--project", "proj", script=case.script([("", critic_update([("runnability", 2), ("contract", 2), ("robustness", 2), ("explainability", 1)]))]))
    check(proc.returncode == 0, "review 失败", proc)
    check(f"评审对象：{nxt['ref']}" in proc.stdout, "review 未打印目标 id", proc)
    check("2 件" in proc.stdout, "review 未打印本批件数", proc)


def test_start_peek_keeps_session(case: Case) -> None:
    """round-05 #4：start --peek 只读，不改会话/事件/usage。"""
    case.init()
    case.run("start", "--project", "proj", "--offline")
    case.run("pause", "--project", "proj")
    sessions = sorted((case.proj / "sessions").glob("*.md"))
    turns = len(case.events("mentor_turn"))
    usage = (case.proj / ".learnark/usage.jsonl").stat().st_size if (case.proj / ".learnark/usage.jsonl").exists() else 0
    peek = case.run("start", "--project", "proj", "--offline", "--peek")
    check(peek.returncode == 0 and "只读预览" in peek.stdout, "peek 未走只读路径", peek)
    check(len(sorted((case.proj / "sessions").glob("*.md"))) == len(sessions), "peek 新建了会话")
    check(len(case.events("mentor_turn")) == turns, "peek 调用了导师")
    usage2 = (case.proj / ".learnark/usage.jsonl").stat().st_size if (case.proj / ".learnark/usage.jsonl").exists() else 0
    check(usage2 == usage, "peek 写了 usage")
    status = case.run("status", "--project", "proj")
    last = sessions[-1].stem
    check(last in status.stdout, "status 未保留上次会话", status)


def test_switch_handoff(case: Case) -> None:
    case.init()
    case.run("start", "--project", "proj", "--offline")
    proc = case.run("switch", "guide", "--project", "proj")
    check(proc.returncode == 0, "switch guide 失败", proc)
    handoff = (case.proj / ".learnark/handoff/latest.md").read_text(encoding="utf-8")
    for field in ("from:", "to:", "reason:", "open_items", "ref:"):
        check(field in handoff, f"handoff 缺字段 {field}")
    check("mentor_switch" in case.journal_kinds(), "没有 mentor_switch 事件")
    proc = case.run("switch", "nobody", "--project", "proj")
    check(proc.returncode == 2, "未知导师应返回 2", proc)
    check(all(name in proc.stderr for name in ("coach", "critic", "guide")), "未列出可选导师", proc)


def test_offline_fallback_honest(case: Case) -> None:
    case.init()
    proc = case.run("start", "--project", "proj", "--offline")
    check(proc.returncode == 0, "start 失败", proc)
    proc = case.run("say", "这是一句离线脚本没有覆盖的话", "--project", "proj", "--offline")
    check(proc.returncode == 0, "say 失败", proc)
    check("[离线脚本导师]" in proc.stdout, "未标注离线导师", proc)
    check("离线模式" in proc.stdout, "未说明离线限制", proc)


TESTS = [
    ("init", test_init_idempotent),
    ("profile_answers", test_profile_answers),
    ("offline_e2e", test_offline_e2e),
    ("claim_without_artifact", test_claim_without_artifact),
    ("review_drives_gap", test_review_drives_gap),
    ("duplicate_artifact_and_review", test_duplicate_artifact_and_review),
    ("clamp_and_reject", test_clamp_and_reject),
    ("unevidenced_lowers", test_unevidenced_lowers),
    ("runtime_next_authoritative", test_runtime_next_authoritative),
    ("help_level_inferred", test_help_level_inferred),
    ("authority_and_conflict", test_authority_and_conflict),
    ("slice_persisted", test_slice_persisted),
    ("multi_path_artifact", test_multi_path_artifact),
    ("say_stdin", test_say_stdin),
    ("defense_fake_rejected", test_defense_fake_rejected),
    ("defense_pass", test_defense_pass_and_milestone),
    ("guide_not_assisted", test_guide_not_assisted),
    ("coach_help_counts", test_coach_help_counts),
    ("gap_close_paths", test_gap_close_paths),
    ("gap_learn_advances", test_gap_learn_advances),
    ("registered_set_and_denial", test_registered_set_and_denial),
    ("claim_without_evidence", test_claim_without_evidence),
    ("gap_drop_stale", test_gap_drop_stale),
    ("gap_drop_guard", test_gap_drop_guard),
    ("recovery", test_recovery),
    ("artifact_tamper", test_artifact_tamper),
    ("assisted_level", test_assisted_level),
    ("git_sync_clone", test_git_sync_and_clone),
    ("git_second_sync", test_git_second_sync),
    ("sync_recover_journal", test_sync_recover_journal),
    ("sync_snapshot_conflict", test_sync_snapshot_conflict),
    ("clone_hash_consistency", test_clone_hash_consistency),
    ("email_template", test_email_template),
    ("deterministic_opening_task", test_deterministic_opening_task),
    ("gap_unverified_not_open", test_gap_unverified_not_open),
    ("defense_question_unsupported", test_defense_question_unsupported),
    ("email_template_consistency", test_email_template_consistency),
    ("status_reviews_capability", test_status_reviews_capability),
    ("review_target_visible", test_review_target_visible),
    ("start_peek_keeps_session", test_start_peek_keeps_session),
    ("switch_handoff", test_switch_handoff),
    ("offline_fallback", test_offline_fallback_honest),
]


def main(argv: list[str]) -> int:
    keep = "--keep" in argv
    filters = [arg.split("=", 1)[1] for arg in argv if arg.startswith("--filter=")]
    failures: list[str] = []
    ran = 0
    for name, function in TESTS:
        if filters and not any(item in name for item in filters):
            continue
        ran += 1
        case = Case(name)
        try:
            function(case)
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 - test harness reports everything
            failures.append(name)
            print(f"FAIL {name}: {exc}")
            if "--verbose" in argv:
                traceback.print_exc()
        finally:
            if keep:
                print(f"     kept: {case.root}")
            else:
                case.cleanup()
    print("")
    print(f"{ran - len(failures)}/{ran} 通过")
    if failures:
        print("失败：" + ", ".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
