# round-06 修复记录 — Forge v0.2.4

- 输入：`experiments/round-06/experience-S6-P4.md`（S6/P4，email 模板，0.2.3 + core 1.0.2）
- 版本：`direction-b-forge 0.2.4`｜vendored `learncore 1.0.2`｜state `schema_version 1`
- 范围：修报告 #5–#9（重要）；#11 路径漂移见文末。
- 回归：`python tests\run_tests.py` → **42/42 通过**；`shared/check_variant.py` → **18/18 ok**；
  `shared/vendor_core.py --check` → **core 1.0.2: all vendored copies match**。

## 问题 → 修复 → 测试

| # | 问题（报告） | 修复 | 测试 |
| --- | --- | --- | --- |
| 5 | 写作缺口的 `gap learn` 用 `def explain(...): print(...)` 当“最小示例” | `forge_mentor.template_guidance(brief)` 追加模板硬规则：email 模板下所有示例必须是英文邮件句段/`before → after`，禁止 Python/代码块，不得出现 `def/print/import/API/agent`；微课结构改为“一句概念 + 邮件对照 + 常见坑 + 改一句”；并显式覆盖 `mentors/guide.md` 的代码块要求。guide/critic/coach 三种 system prompt 都带这段。 | `email_template_consistency`：断言 `template_guidance({"template":"email"})` 含“禁止 Python”且不含“示例可用 Python”；整个写作项目的 task/next/defend/status/README/AGENTS 扫描无 `def /print(/import /agent/API/.py/m1-/代码`。 |
| 6 | 每个写作界面都出现编程切片提示“只做能跑的最小版本……” | `logic.pick_slice()` 按 `brief.template` 分支：email 20 分钟 = “写一封 ≤120 词的邮件 + 一次结构化修改（删模糊词、补明确截止），不写长文”；60 分钟 = “一封完整邮件 + 一次自评/修改说明，再复评”。`start`/`next`/`task`/`status` 统一使用。 | `email_template_consistency`：`next.slice_hint` 含“邮件”、不含“运行”。 |
| 7 | `status` 在 E2 显示“最近评审：无”，实际 E1 有 2 次评审；无能力视图 | `_status_payload` 的 `reviews.latest` 改为**跨里程碑最后一条**（附 `milestone`），另给 `latest_for_current`；新增 `capability`：最近评审的强项（达阈值维度）/待补（低分维度 + unverified），人读 status 打印“最近评审：r-…（E1）…”与“强项/待补”。 | `status_reviews_capability`：E1 两次评审后当前是 E2 → `reviews.latest.milestone=E1`、人读含 `r-E1-`、强项、待补，不再出现“最近评审：无”。 |
| 8 | email 仍问“能否跑通 DeepSeek API/做过工具调用 Agent”；回车被记成 api=能/tools=做过 | 定位问题改为模板问卷：email 问“写英文工作邮件频率 / 最想练哪类 / 这次想要什么”；`collect_profile(opts, template, first_mid)` 动态取题，`--answers` 数量按模板校验；交互空回车/非法输入一律记“未回答”（不再默认第一项），非交互也全“未回答”；`mapped_start` 用第一个里程碑 id（email 为 `E1-first/second-half`），不再出现 `M1-first`。 | `email_template_consistency`：`start --ask` 输入三个空行 → answers 全“未回答”、`mapped_start` 以 E1 开头；task 允许后缀只剩 `.md/.txt`。 |
| 9 | 残留：email 的 task 后缀 `.py` 排第一；README 说帮助等级按“骨架/代码”推断；`defend` 示例写死 `m1-q1/第38行`；coach opening 说“把它现在能做什么告诉我” | ① `parse_deliverable`/`normalize_milestone` 接模板，email 的 `allowed_ext=[.md,.txt]`；② README/AGENTS 的帮助推断措辞按模板改为“多步示例/邮件片段”；③ `defend` 示例从实际 `defense.questions` 的 qid 生成（如 `e1-q1…第 1/3/5 行`），不再写死 `m1-q1`；④ 写作提示词要求教练问“这封邮件现在能让收件人做什么、还差什么”，禁止跑通/API。 | `email_template_consistency`：defend 输出含 `e1-q1` 且不含 `m1-q1`；README/AGENTS 无“骨架/代码”，无 `.py` 残留（入口命令除外）；后缀/切片/问卷同用例覆盖。 |

## 复现命令（离线）

```powershell
$V = "<variant>"
python "$V\runtime\learn.py" init --goal "英文工作邮件写作" --template email --dir p
python "$V\runtime\learn.py" start --project p --offline --ask     # 三个回车 -> 未回答 / E1-first
python "$V\runtime\learn.py" task --project p --json               # 后缀 .md/.txt，任务为写信
python "$V\runtime\learn.py" next --project p --json               # slice_hint 为邮件
```

## 改动文件

- `runtime/forge_state.py`：`TEMPLATE_ALLOWED_EXT`，deliverable 按模板设后缀。
- `runtime/forge_logic.py`：email 切片提示、固定任务表、review 目标、unverified、防御题材料校验。
- `runtime/forge_mentor.py`：`template_guidance`（email 禁代码、写作动作/教练开场/防御措辞），接入 `_system`。
- `runtime/learn.py`：模板问卷与默认“未回答”、E1 起点、task 固定任务/后缀/切片、status 跨里程碑评审 + 能力视图、defend 动态 qid、README/AGENTS 措辞、`start --peek`、实际 model。
- `tests/run_tests.py`：新增 `email_template_consistency`、`status_reviews_capability`、`deterministic_opening_task`、`gap_unverified_not_open`、`defense_question_unsupported`、`review_target_visible`、`start_peek_keeps_session`。
- `START_HERE.md`、`version-manifest.json`、`examples/demo.md`：0.2.4。

## 未修（round-06 报告 #11 等）

- `artifact add` 仍会把邮件复制到 `artifacts/email/E1/e1-apology.md`（多一层里程碑目录），与 `task` 里的 `artifacts/email/e1-apology.md` 不完全一致；本轮只修了内容/语言残留，没有改存储布局。
- 离线脚本导师的 guide 语料仍是编程示例；email 微课的无代码约束由模板提示词保证，离线无法证明真实 LLM 一定遵守（manifest 已列为限制）。
- coach 开场白是 LLM 文本，提示词已改为写作语言，但没有确定性兜底（固定任务仍是权威）。
