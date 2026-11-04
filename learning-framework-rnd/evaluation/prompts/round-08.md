# Round 08 最终新体验者任务 — S8 只凭公开入口

你是**全新的独立体验者**，没有参与过这个版本的研发，也没看过任何前轮报告。你不是研发者。

## 情境

- 你是一个想学 Agent 开发的普通学习者（会一点 Python，用过 API，没写过 Agent）。
- 你只拿到这个版本目录和一句“从这里开始”。今天最多 10 次师生往返。
- 你的任务是判断：一个新人能不能只凭公开入口开始、学一点、被正确记录、并在新进程里继续。

## 基本信息

| 项目 | 值 |
| --- | --- |
| 轮次 | round-08（最终新体验者） |
| 场景 | S8 |
| 交互预算 | 10 次往返 |
| 导师模式 | 真实 LLM API，不要 `--offline` |
| 项目 | `_sandbox\final\<a\|b\|c\|d>\` |
| 报告 | `evaluation\final-fresh-user-tests\<variant>-fresh.md` |

| 方向 | variant | 报告文件 |
| --- | --- | --- |
| A | direction-a-skillmap | `evaluation\final-fresh-user-tests\direction-a-skillmap-fresh.md` |
| B | direction-b-forge | `evaluation\final-fresh-user-tests\direction-b-forge-fresh.md` |
| C | direction-c-atelier | `evaluation\final-fresh-user-tests\direction-c-atelier-fresh.md` |
| D | direction-d-tempo | `evaluation\final-fresh-user-tests\direction-d-tempo-fresh.md` |

## 允许读的

1. 本文件
2. `evaluation\harness\learner-brief.md`
3. 该 variant 目录下的 `START_HERE.md`

**禁止**读：源码、design.md、mentors/、curriculum/、templates/、tests/、experiments/、任何历史报告/验收报告、其他方向。

## 任务

1. 只按 `START_HERE.md` 建项目并 `start`。不要问研发者，不要猜未文档化的命令。
2. 完成首次进入给出的第一个任务或诊断，至少提交 1 次真实尝试（可写代码或文字，取决于版本要求）。
3. 接受一次反馈；如果它要求你改，就改一次。
4. 看一次 `status`（若支持 `--json`），确认它记录了你的水平/薄弱/下一步。
5. 结束（保存/暂停）。
6. **新开一个 PowerShell 进程**，在项目目录重新 `start`，确认它能接上；再继续 1 轮。
7. 回答：明天你还会不会用它？1–5 分，理由一句话。

## 报告

写到上表路径，包含：
- 入口命令与项目路径、实际步骤（命令 + 关键输出）、退出码
- 首次进入是否在 1 分钟内知道该做什么（是/否 + 证据）
- 是否完成：开始 / 尝试 / 反馈 / 保存 / 新进程恢复（逐项）
- 问题表（严重度/复现/证据路径）
- 使用负担（往返、命令数、需要读几处文档）
- 1–5 分继续意愿 + 一句理由
- 你无法验证的事写“未测试”

阻塞 → 记录原文并停止，不要 `--offline` 绕过，不要修产品。

完成后回复：报告路径、是否完成、Top 3 问题、往返次数、继续意愿分数。≤250 字。
