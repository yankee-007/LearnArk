# round-05 修复记录 — Forge v0.2.4

- 输入：`experiments/round-05/experience-S5-P3.md`（S5/P3，0.2.3 + core 1.0.2）
- 版本：`direction-b-forge 0.2.4`｜vendored `learncore 1.0.2`｜state `schema_version 1`
- 注意：S5 报告披露误读了 round-04 报告；本记录只按 S5 里的命令输出复现问题，未采信其对相邻议题的预期。
- 范围：修报告 #1–#4（重要 + 次要）；其余见文末“未修”。
- 回归：`python tests\run_tests.py` → **42/42 通过**；`shared/check_variant.py` → **18/18 ok**；
  `shared/vendor_core.py --check` → **core 1.0.2: all vendored copies match**。

## 问题 → 修复 → 测试

| # | 问题（报告） | 修复 | 测试 |
| --- | --- | --- | --- |
| 1 | 同目标 + 同 20 分钟切片，主项目得到“读一行算式”，探针得到“读文件循环 + 接真实模型”；开场任务不可复现 | 新增纯函数 `logic.opening_task()`：输入 = 模板 + 里程碑 + 切片 + 档案（`mapped_start/strictness`），输出稳定的 `task_id`（`task-<sha10>`）与任务文本（`M1/20`、`M1/60`、`E1/20`…有固定表，其余模板给确定性兜底）。`start` 把固定任务写进 `runtime_next` 并打印；`task` 打印同一段文本，`task --json`/`next --json` 也带 `task_id/task_text`。导师开场白只是叙事，不再是任务来源。 | `deterministic_opening_task`：两个新项目同输入 → `task_id`/文本完全相同；改成 60 分钟 → `task_id` 变化且 `slice=60`；`start` 输出含“本步任务”。 |
| 2 | 一次小活动开 3 张 open 卡，含 `explainability 2/2 达标`；`next` 说“2 维低于阈值”却有 3 张卡 | `needs_extra_gap` 触发的“达标但缺行/段证据”不再写 open：`upsert_gap(..., status="unverified")`，`next` 只把 `score<threshold` 的维度算低分，`open_gaps`/`task`/`pause`/`status.gaps.open` 都不含 unverified；`status` 单列 `gaps.unverified`，review 输出“达标但缺证据（unverified，不算开放缺口）”。带证据的复评会关闭该卡（`close_gaps_for_review` 支持 unverified + `skip_dims`）。 | `gap_unverified_not_open`：explainability 3 分/阈值 2 但只有 `evidence_path` 无行号 → 卡 `status=unverified`、open 为空、`next=defend` 且不含“低于阈值”；`status --json` 的 `gaps.unverified` 有该卡。 |
| 3 | 防御题问“上限为何是 6”，但切片把上限推迟、作品里没有 6 | 新增 `logic.validate_defense_questions(milestone, materials_text)`：问题里的数字必须在“固定任务 + 本里程碑全部已登记作品”文本中出现；缺失时替换为按维度写死、可结合作品回答的 fallback，保留 `original_question`/`unsupported_terms`，并写 `defense_question_unsupported` 事件（review 自动建 defense 与 `defend` 手动建 defense 都走同一路径）。 | `defense_question_unsupported`：作品无 6 → q3 被替换、事件含缺失数字；作品含 `MAX_STEPS = 6` → 原题保留。 |
| 4 | review 的目标件在 `▶` 里看不出来；模型横幅写配置值；“只读 start”会顶掉上次会话 | `compute_next` 的 review 分支复用 `pick_review_target`（未评审优先、代码后缀优先），`▶`/`next --json` 带目标 id 与 `artifacts` 列表；`review` 输出新增“评审对象：<id>（本里程碑 N 件：…）”。`start` 显示“配置 X / 实际 Y”（取本次响应 model 或 journal 最近 model；离线仍明说离线）。新增 `start --peek`：只读打印里程碑/固定任务/下一步/交接，不建会话、不调导师、不写 usage；`status` 在“当前会话刚打开（≤1 轮）”时显示上一段会话并标注“本次会话：…（刚打开）”。 | `review_target_visible`：先登记设计说明再登记代码 → `next.ref` 是代码 id、`▶`/review 输出标出目标与 2 件；`start_peek_keeps_session`：peek 后 sessions/mentor_turn/usage 均不变，status 仍显示上一段会话。 |

## 复现命令（离线）

```powershell
$V = "<variant>"
python "$V\runtime\learn.py" init --goal "Agent 开发" --dir p1
python "$V\runtime\learn.py" start --project p1 --offline --minutes 20 --answers "不确定,没有,二十分钟见到东西"
python "$V\runtime\learn.py" task --project p1 --json        # task.task_id / task.text
python "$V\runtime\learn.py" start --project p1 --offline --peek
```

## 改动文件

- `runtime/forge_logic.py`：`opening_task`、`pick_review_target`、unverified 缺口、防御题材料校验。
- `runtime/learn.py`：`start` 固定任务/`--peek`/实际 model；`task` 固定任务；review 目标与 unverified；defense 替换事件；status 跨里程碑最近评审 + 强项/待补 + 上一段会话。
- `runtime/forge_state.py` / `version-manifest.json`：0.2.4。
- `tests/run_tests.py`：新增 5 个用例（见上表）。
- `START_HERE.md`、`examples/demo.md`：版本与命令说明。

## 未修（round-05 报告其余项）

- 导师开场白/教学文本仍是 LLM 生成，只保证固定任务与上下文一致，不保证逐字复现。
- 20 分钟是切片预算，不是墙钟计时；运行时不追踪真实学习分钟数。
- 真实 API 的模型别名只做“配置/实际”展示，不在运行时纠正供应商路由。
- S5 探针差异中的“接真实模型”若出现在导师正文，仍靠提示词与 `mentor_next_conflict` 约束，不是硬门控。
