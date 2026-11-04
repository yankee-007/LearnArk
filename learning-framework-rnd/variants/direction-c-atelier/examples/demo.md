# Atelier 离线运行记录（demo）

> **这是离线 / 合成记录。** 全部导师回复来自 `LEARNARK_LLM=mock` + `tests/fixtures/mentor_script.jsonl`
> 的脚本导师，输出前缀 `[离线脚本导师]`，事件里标 `synthetic: true`。
> 它只证明“五导师 + 交接契约 + 计划权威 + 证据规则”这条流程能跑通，**不证明真实教学质量，也不构成学习效果证据**。
> 本次运行使用模拟时钟 `LEARNARK_NOW=2026-11-04T20:10:00+08:00`（仅用于可复现的时间戳）。
>
> **历史记录**：本记录采集于 0.1.0 / core 1.0.0，早于 round-01 修复。0.2.1 起
> `say` 不再因交接失败丢回合，交接内容由运行时从记录合成（`switch` 默认成功）；
> 命令序列与产物结构仍可复现，但输出措辞与交接字段以 `START_HERE.md` / 当前版本为准。

## 1. 环境与命令序列

- 版本：`direction-c-atelier` 0.1.0 · `learncore` 1.0.0（demo 运行时的 core；交付版本已升到 1.0.1，仅修 git 同步） · schema 1
- 平台：Windows / Python 3.14 / 无远程 git 仓库
- 目录：`<sandbox>/proj`（一次性演示项目）

```powershell
python runtime/learn.py init --goal "Agent 开发" --dir proj --minutes-per-week 12
cd proj
python runtime/learn.py start --offline
python runtime/learn.py say "帮我定这周计划" --offline
python runtime/learn.py say "今天只有二十分钟" --offline
python runtime/learn.py status --json
python runtime/learn.py switch concept
python runtime/learn.py say "RAG 和 Agent 记忆有什么区别" --offline
python runtime/learn.py studio
python runtime/learn.py plan
python runtime/learn.py pause --note "20 分钟到点"
python runtime/learn.py sync
python runtime/learn.py doctor
python runtime/learn.py handoff --check
python runtime/learn.py export --out ../demo-export.md
```

全部命令返回 `0`（`handoff --check` 也是 0）。

## 2. 关键输出（节选，逐字来自本次运行）

`start`（不调用模型，只读项目文件）：

```text
计划：plan-v1 v1（权威：planner） · 进度 0/10 步
  · 当前目标：w1-agent-loop 说清 Agent 与单次问答的差别
上次停在哪：尚无学习记录（首次进入）
这一轮该找谁：策划导师 planner
  · 为什么：首次进入：planner 用 ≤4 轮诊断确认目标与周时长，再按计划移交
```

第一轮 planner（`help_level=0`，提出并被应用一条 `replan_week`）：

```text
[离线脚本导师] 好。先按每周 12 小时、零基础起步排：第 1 周只做三步……
记录：help_level=0 ｜ next=确认周可用小时后进入 w1-agent-loop-ex1
计划：PC-0001 已由 planner 生效。
上下文：581 字符（manifest 已入 journal）
```

第二轮 planner（20 分钟约束，`defer_step`）：

```text
[离线脚本导师] 先别打开教程。那把今天砍到一步：只做「循环什么时候停」……
计划：PC-0002 已由 planner 生效。
上下文：784 字符（manifest 已入 journal）
```

`switch concept`（严格校验上一手 handoff 提案，通过后才换人）：

```text
已交接：planner → concept（H-0001，.learnark\handoff\20261104T201000-planner-to-concept.md）
```

概念导师（讲解属于 `help_level=2`，因此不产生能力提升）：

```text
[离线脚本导师] 给一个最小模型：检索是「现查现用」，记忆是「写下来下次还在」……
记录：help_level=2 ｜ next=请学习者回答：重启后哪些信息必须还在
上下文：1011 字符（manifest 已入 journal）
```

`studio`（五席位、当前/建议、最近交接、计划变更计数）：

```text
planner/策划导师   目标澄清 / 周目标 / 排序 / 时间预算  2  just now  0
concept/概念导师   最小模型 / 类比 / 反例 / 复述        1  just now  0   ← 当前
coach/练习导师     分级提示 / 调试 / 拆步               0  未使用     1
examiner/考核导师  迁移题 / 判定 / verified 证据        0  未使用     0
reviewer/复盘导师  复盘 / 遗忘检查 / 下周建议           0  未使用     0
最新交接：H-0001 planner→concept（just now）
计划变更：applied 2 条，proposed 0 条
```

`pause` / `sync`（三态如实报告：本地无远程）：

```text
已保存：.learnark\handoff\20261104T201000-concept-to-concept.md
交接：H-0002 concept → concept
git：git state: no-remote (written=yes, committed=yes, pushed=no)；remote=（无）

git state: no-remote
written=yes  committed=yes  pushed=no
branch=master sha=f650f5f remote=（无）
```

`doctor`（19 项检查全部 ok）：

```text
[ok ] journal_integrity：18 events
[ok ] plan_authority：plan v3 hash 一致
[ok ] handoffs：2 份，问题 0 份
[ok ] notes_planner：2/8 行
[ok ] evidence_honesty：synthetic turns=3
未发现问题。
```

`handoff --check`：

```text
检查 2 份交接：全部通过
  [ok ] …-concept-to-concept.md H-0002 concept→concept
  [ok ] …-planner-to-concept.md H-0001 planner→concept
```

## 3. 本次产生的证据（journal 对账）

- 事件 19 条，种类：`project_created`、`plan_created`、`mentor_turn`、`context_manifest`、
  `plan_change`、`plan_change_applied`、`handoff`、`mentor_switch`、`session_end`、`sync`、`export`。
- 3 个导师回合全部 `mode=mock`、`synthetic=true`、`invalid=false`（机器块均被正确解析）。
- 2 份交接：`H-0001 planner→concept`、`H-0002 concept→concept`，`handoff --check` 全部字段合法。
- 2 条计划变更（均为 planner `status:"apply"`）：`PC-0001 replan_week`、`PC-0002 defer_step`，
  各自带 before/after hash，`plan.version` 1→3。
- `context_manifest` 三回合字符数：581 → 784 → 1011，均 ≤6000；概念导师那回合 `handoff_id=H-0001`，
  `sources` 含 `handoff/latest` 与 `handoff/do_not_redo`，不含其他导师私有笔记。
- 能力节点本次全部保持 `0 未验证`：planner 与 concept 的回合都不满足“独立正确尝试”，
  这是预期行为，不是失败。

## 4. 这份记录不能证明什么

- 不能证明真实模型会稳定输出合法 `learn-update`（真实 API 回合见另一份 self-check 记录；
  该回合 `mode=api`、`invalid=false`）。
- 不能证明真人学习收益、长期保持率或 6000 字符预算在 30 回合下的曲线（轮 5 才验证）。
- 不能证明远程 GitHub 同步：本机没有配置 remote，`pushed=no` 是如实结果。
