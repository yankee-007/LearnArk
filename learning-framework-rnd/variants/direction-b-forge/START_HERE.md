# Forge 作品驱动 · 入口（direction-b-forge 0.2.4）

一句话：**不排课程，只给里程碑与 rubric；先交作品，按 rubric 打分，低分维度就是下一节微课。**

适合谁：自述有 Python/API 经验、想做出能跑的 Agent、接受作品被公开标准打分的自学者；
每周 10–20 小时，单次可以只有 20 分钟。

不是什么：不教编程基础（不懂语法/调试会卡住），不排课表，不代写，不做账号、云端、后台唤醒、移动端。
本目录是研究用实现，离线模式的导师输出是脚本，不代表真实教学质量。

## 3 步开始（Windows PowerShell，原文照抄）

```powershell
$env:DEEPSEEK_API_KEY = "sk-..."           # 只放环境变量，不写进项目文件
cd C:\Users\你\学习目录
python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\runtime\learn.py" init --goal "Agent 开发" --dir forge-m1
python "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge\runtime\learn.py" start --project forge-m1 --ask
```

`--ask` 会问三个选择题；也可以非交互补答：`start --ask --answers "能,做过,一次做完一个项目"`。
三问只用于定起点/严苛档/切片，答案会写进 `start_profile`（`status` 可见 `answered`），**不作能力证据**。
`project.json` 的 `learner_profile.self_report` 默认为空，只记录你明说的内容：
`init --self-report "python=会一点,api=调用过"`。

想先离线试跑：每条命令加 `--offline`（= `LEARNARK_LLM=mock`，输出标注 `[离线脚本导师]`）。
Windows 也可以直接用 `learn.cmd`（同目录）代替 `python ...\runtime\learn.py`。

## 全部命令

| 命令 | 作用 |
| --- | --- |
| `init --goal TEXT [--template agent-dev\|email] [--minutes-per-week N] [--dir PATH] [--name SLUG] [--self-report "python=…,api=…"]` | 建项目、写状态、生成 README/AGENTS、`git init`；可重复执行 |
| `start [--minutes N] [--ask] [--answers "…"] [--peek]` | 恢复或开始；定位问题按模板（email 问写作），回车=未回答；`--peek` 只读不建会话 |
| `say TEXT`（`say -` 从 stdin 读） | 学习者发言 → 导师回复 → 写会话/事件/help_level；长文本或含引号时用 `say -` |
| `status [--json]` | 目标、里程碑、作品/评审（跨里程碑最近一次 + 强项/待补）、缺口、交接、下一步、git |
| `next [--json] [--minutes N]` | 纯函数计算的下一步（LLM 不能覆盖）；切片 20/60 分钟；含固定任务 id/text |
| `task [--json]` | 当前里程碑的**固定任务**（id+文本）+ 交付物 + rubric + 已有分数 |
| `artifact add PATH [PATH...]` / `artifact add --note TEXT` | 复制进 `artifacts/<里程碑>/`、记 sha256/size/assisted_level；一次可登记多个交付物（如代码 + 设计说明） |
| `artifact list [--json]` | 已登记作品 |
| `review [ARTIFACT_ID]` | 强制切到 critic，按 rubric 打分；`▶` 与输出都标出评审目标 id 与本批件数 |
| `defend` | 防御三问（用 `say` 作答，答案要给行号）；问题引用了作品/任务里没有的事实会被替换并记为 `defense_question_unsupported` |
| `gap [--all] [--json]` / `gap learn ID` / `gap drop ID` | 缺口列表 / guide 微课 / 连续三次未过后记 stale；达标但缺证据记 `unverified`，不算开放缺口 |
| `milestones [--json]` | 三个里程碑全景与通过证据 |
| `pause [--note TEXT]` | 写交接、保存、git 同步 |
| `switch coach\|critic\|guide` | 手动切换导师（写 from/to/reason/open_items/ref） |
| `sync [--message TEXT] [--recover]` | 真实报告 written / committed / pushed 三态；`--recover` 并集合并 journal，绝不 force push |
| `doctor [--json] [--rebuild]` | 状态、journal、去重索引、锁、git、LLM、作品 sha、证据链自检 |
| `export --out FILE` | 导出 Markdown 学习档案（含已解决缺口的五元组） |

全局：`--project PATH`（默认从 cwd 向上找 `.learnark/`）、`--offline`（= `LEARNARK_LLM=mock`）。
退出码：0 成功；2 用法错误；3 状态/冲突（含 `review_invalid`、doctor 发现问题）；4 环境/网络。

## 一次完整闭环

```powershell
python runtime\learn.py start --project forge-m1 --minutes 20   # 20 分钟切片会写入档案
python runtime\learn.py task --project forge-m1           # rubric 与交付物
python runtime\learn.py artifact add m1\agent.py docs\m1-design.md --project forge-m1
python runtime\learn.py review --project forge-m1         # 低分维度 → 缺口卡
python runtime\learn.py gap --project forge-m1
python runtime\learn.py gap learn g-M1-contract --project forge-m1
# 长文本/含引号时从 stdin 输入，避免 PowerShell 吞引号：
'我按第 3 步改了 role，但报 422：{"error":"missing tool_call_id"}' | python runtime\learn.py say - --project forge-m1
# 改完作品再登记一次（新 sha），再 review；四维达标后：
python runtime\learn.py defend --project forge-m1
python runtime\learn.py say "m1-q1：……（第 38 行）；m1-q2：……（第 27 行）；m1-q3：……（第 41 行）" --project forge-m1
python runtime\learn.py status --json --project forge-m1
```

里程碑通过 = **已登记作品（sha256）+ 四维全达阈值 + defense 至少 2/3 通过且最重维度通过**。
只有这三者齐备，运行时才写 `milestone_passed`；导师说“通过”不算。

## 运行时规则（导师不能改）

1. **next 是唯一权威动作**：导师上下文带 `runtime_next`，不得另排任务/另开文件；不同意只能一句话说明后仍按它继续。
2. **证据不足不能算达标**：`score >= threshold` 必须带 `evidence_line`/`evidence_path`，缺失降到 `threshold-1` 并记 `rubric_unevidenced`。
   note 里的数量断言（如“6 步上限”）没有行号证据也会从可见 note 中省略，并记 `claim_without_evidence`。
3. **微课不是代做**：`guide` 的 `gap learn` 只推进缺口卡，**不计入**下一次作品的 `assisted_level`；只有 coach/critic 的帮助才计入。
4. **自述不算证据**：起点三问只在你回答时写入 `start_profile`；`self_report` 只记录你明说的内容；`say "我做完了"` 只写 `claim_without_artifact`。
5. **帮助等级必须落账**：漏写时按“要答案 + 多步骨架/代码”推断并记 `help_level_inferred`（要答案+骨架→L3，有骨架→L2），`status` 显示最近/最高等级。
6. **每轮只有一行「▶ 唯一动作」**：导师正文若提别的动作会记 `mentor_next_conflict`；上下文里的已登记作品集合是权威，否认已登记作品会记 `review_note_conflict`。
7. **微课会推进 next**：`gap learn` 成功后该卡为 `learning`，`next` 转向改作品/复评；同一张卡没有新的失败评审时不重复讲（记 `gap_repeat_suppressed`），`gap learn --force` 可重讲。
8. **固定任务与模板**：`task_id` 由模板+里程碑+切片+档案确定，`start`/`task` 打印同一段任务文本；email 模板的定位问题、切片提示、示例与防御题都是写作语言（不出现代码/`.py`/API）。
9. **切片会持久化**：`start --minutes 20` 写入 `start_profile.slice_minutes`，之后 `next`/`review`/`defend` 都按 20；只想改一轮用 `next --minutes 60`。
10. **截断输入不猜原因**：消息被 shell 截断时，导师应先让你用 `say -` 或文件重发，不得据此断言错误。

## 学习记录在哪

- `.learnark/project.json` 与 `.learnark/state/{brief,artifacts,reviews,gaps,defense,session}.json`：目标/模板/档案与快照（各自带 `schema_version`，损坏自动从 `.bak` 恢复）；
- `.learnark/journal/events.jsonl`：**权威事件流**（截断的半行会被忽略）；
- `.learnark/handoff/latest.md` + `latest.json`：最近交接（from/to/reason/open_items/ref）；
- `sessions/YYYYMMDD-HHMMSS-<mentor>.md`：每次会话；
- `artifacts/<里程碑>/…`：登记过的作品副本（doctor 会校验 sha256）；
- `README.md`（1 分钟上手）、`AGENTS.md`（给任意 Agent 的规则）。

## 恢复、同步、没有远程时

- `start` 只读项目文件（project + 快照 + journal + handoff），不依赖旧聊天或进程缓存；`pause`/`switch` 写交接，下一导师上下文含当前里程碑、最近分数、open gap 前三、上次 handoff 的 next。
- `sync` 一定输出三态：`written`（已落盘）/ `committed`（本地提交）/ `pushed`（远程）；无远程时保留本地提交并明确“真实 GitHub 同步未验证”，不报错。
- 远程分叉：`sync` 先 `pull --rebase`，journal-only 冲突自动并集合并（按 id 去重、重建 dedupe）后推送；快照（`state/*.json`）冲突不自动合并，退出 **3** 并列出文件，本地提交保留。手动入口 `sync --recover`。
- `status` 的 `sync.diverged`/`unmerged` 标出分叉与未合并文件；`doctor` 在 diverged 时退出 3。
- `init` 生成 `.gitattributes`（`* -text`）防克隆换行导致 sha 变化；`.gitignore` 忽略 `*.lock`、`usage.jsonl`、`sync-log.jsonl`。

## 离线模式的限制

- `--offline` 用 `tests/fixtures/mentor_script.jsonl` 的脚本回复（`LEARNARK_MOCK_SCRIPT` 可换），每条输出前标 `[离线脚本导师]`；脚本没命中会明说“只记录状态，不产生教学证据”。
- 离线只证明流程、门控、幂等与恢复，不证明真实 LLM 的教学质量，也不能当作真实学习证据。

## 已知限制与版本

- 版本：`direction-b-forge 0.2.4`｜vendored `learncore 1.0.4`｜state `schema_version 1`｜Python 3.10+ 标准库。
- rubric 由 critic 提议，运行时只能 clamp（1–4）、按证据降分与整次拒绝（缺维/多维/改权重/非法 JSON），无法消除评委主观性；按证据降分是有意保守：critic 忘给 `evidence_line` 时达标分会降一级。
- 帮助等级推断（`help_level_inferred`）与动作冲突检测（`mentor_next_conflict`）都是启发式：前者可能高估/低估，后者只识别少量动作关键词，最终以 `▶ 唯一动作` 为准。
- 只覆盖 Agent 开发入门 3 个里程碑；email 模板只验证评价标准可替换，不证明写作能力提升；防御性解释只能降低、不能消除 AI 代做。
- 未验证真人长期学习收益；`sync --recover` 只合并 journal，快照冲突必须人工选择；真实 GitHub 未验证。
