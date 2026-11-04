# round-03 修复记录 — Forge v0.2.3

- 输入：`experiments/round-03/experience-S3-P3.md`（S3/P3，0.2.2 + core 1.0.1）
- 版本：`direction-b-forge 0.2.3`｜vendored `learncore 1.0.2`｜state `schema_version 1`
- 范围：修报告 #1–#4（重要）；#5–#10 见文末“未修”。
- 回归：`python tests\run_tests.py` → **35/35 通过**；`shared/check_variant.py` → **18/18 ok**；
  `shared/vendor_core.py --check` → **core 1.0.2: all vendored copies match**。

## 问题 → 修复 → 测试

| # | 问题（报告） | 修复 | 测试 |
| --- | --- | --- | --- |
| 1 | 已登记作品被 coach 两次说成“未登记”（实际两件都在） | 导师上下文对所有角色都注入「已登记作品集合」（id/path/sha256，critic 另附其他文件内容）；PROTOCOL 明确该集合是权威、不得说未登记/缺失；coach/guide 文本若仍声称没有作品，运行时记 `review_note_conflict`（`source=mentor_text`、`denied=true`、完整 `registered_paths`），并在输出中纠正“但运行时已有 N 件”。 | `registered_set_and_denial`：一次登记两件后 coach 说“没有看到已登记作品” → 事件带 2 条路径、输出有纠正；随后 review 失败、guide 在 `say` 中给正文动作 → `mentor_next_conflict`。 |
| 2 | `gap learn` 后 `next` 仍返回同一 `gap_learn`；guide 9 秒后几乎逐字重复上次讲解 | `compute_next` 只在缺口 `status=open` 时给 `gap_learn`；微课成功置 `learning`+`covered_at` 后 `next` 推进到 `do_task`（改作品→复评）。重复 `gap learn` 在无新失败评审时直接抑制：写 `gap_repeat_suppressed`（带 `prior_explanation`、`context_has_prior`），展示上次讲解摘要、不调用导师；`--force` 可重讲。复评再次失败时 `upsert_gap` 把 learning 重开为 open，允许再学。 | `gap_learn_advances`：微课后 `next=do_task`；重复命令 exit 0、有 `gap_repeat_suppressed`、`context_has_prior=true`、无新导师回合；`--force` 产生新回合；复评仍 2 分后缺口 status=open 且 `next=gap_learn`。 |
| 3 | 一条 guide 回复里正文“回到作品…artifact add + review”与页脚 `▶ 唯一动作：gap_learn` 并存，且未记录冲突 | 每个导师回复后只打印一行 `▶ 唯一动作：动作（ref）— 原因`（移除额外的“下一步/本轮权威动作”行）；`detect_next_conflict` 扩展 `重新 review`/`重新 artifact add`/`回到作品` 等正文指令，命中即记 `mentor_next_conflict`（含 runtime_action/mentioned/excerpt），会话同步记录；评委/coach/guide 提示词重申“只给 runtime_next 一个动作”。 | `registered_set_and_denial` 的 guide 正文用例；`authority_and_conflict`：输出仅一行 `▶ gap_learn`，journal 有冲突；`say` 的评审失败后正文“先 review”也触发。 |
| 4 | critic 虚构“步数上限为 6”，与自己 robustness note 矛盾，作品里没有 6 | `unsupported_numeric_claims()`：rubric note 出现数量断言（`上限/最多/不超过/cap/limit` + 数字，或 `N 步`）且该维没有 `evidence_line`/`evidence_path`/行号引用时，写 `claim_without_evidence` 事件；**从可见 note 中省略该断言**（保留 `raw_note`），表中不再展示未证实数字。critic 提示词要求数量断言必须带行号或省略。 | `claim_without_evidence`：note“有 6 步上限”无证据 → 事件含“6 步”，落库 note 不含“6 步”且有“已省略”；同一断言带 `evidence_line` 的复评不再记事件。 |

## 复现命令（离线）

```powershell
$V = "<variant>"
python "$V\runtime\learn.py" init --goal "Agent 开发" --dir p
python "$V\runtime\learn.py" artifact add a.py docs\design.md --project p
python "$V\runtime\learn.py" review --project p --offline        # 缺口 + 单一 ▶
python "$V\runtime\learn.py" gap learn g-M1-contract --project p --offline
python "$V\runtime\learn.py" next --project p --json              # 不再是 gap_learn
python "$V\runtime\learn.py" gap learn g-M1-contract --project p  # gap_repeat_suppressed
python "$V\runtime\learn.py" next --project p --json
python "$V\runtime\learn.py" say "我接下来做什么" --project p --offline
```

## 改动文件

- `runtime/forge_logic.py`：gap 只在 open 时可学；learning 复评失败重开；微课后 next 转 do_task。
- `runtime/forge_mentor.py`：所有导师上下文含已登记集合（critic 附内容）；PROTOCOL/ critic 提示词（数量断言、不得否认已登记）。
- `runtime/learn.py`：重复微课抑制与 `--force`、`prior_explanation` 注入；单一 `▶` 输出；guide 正文冲突；`claim_without_evidence` 与 note 省略；coach 否认已登记事件。
- `tests/run_tests.py`：新增 `gap_learn_advances`、`registered_set_and_denial`、`claim_without_evidence`。
- `START_HERE.md`、`version-manifest.json`（0.2.3）、`examples/demo.md`。

## 未修（round-03 #5–#10，非本轮要求）

- #5 切换只在 2 次交互后回 coach、会话文件仍按首次导师命名、`handoff/latest.md` 单槽覆盖。
- #6 对话里说“只有十分钟”不会自动改切片（仍以 `start --minutes`/`next --minutes` 为准）。
- #7 导师对预测题的反馈与示例代码相反（纯 LLM 语义问题，运行时无法判定）。
- #8 guide 说“受助完成”与 `assisted_level` 规则的措辞未统一（文档已说明 guide 不计入）。
- #9 项目外 `start --help` 仍先找项目、退出 1；#10 学习者 id 仍默认 P1。
