# Forge 离线演示记录（离线 / 合成数据，不是真实学习证据）

- 版本：`direction-b-forge 0.2.4`｜vendored `learncore 1.0.2`｜state `schema_version 1`
- 环境：Windows 11 + Python 3.14，`LEARNARK_LLM=mock`，导师回复来自
  `tests/fixtures/mentor_script.jsonl`（每条输出前标注 `[离线脚本导师]`）
- 作品：`examples/demo-artifact-v1.py`、`examples/demo-artifact-v2.py`（人工编写的合成 Agent 代码）
  与 demo 项目内的 `docs/m1-design.md`
- 学习者：无真人；本文只证明流程、门控、幂等与恢复，不证明教学质量或学习效果
- 本版修复（round-02）：`experiments/round-02/fix-summary.md`（L3 帮助落账、`▶ 唯一动作`、
  20 分钟切片持久化、多文件登记、截断输入规则）

工作目录与入口（`$V` 指本方向目录）：

```powershell
$V = "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-b-forge"
cd C:\temp\forge-demo
$env:LEARNARK_LLM = "mock"
```

## 1. 建项目并开始（三问可补答，20 分钟切片落档）

```powershell
python "$V\runtime\learn.py" init --goal "Agent 开发" --dir demo-project
python "$V\runtime\learn.py" start --project demo-project --offline --ask --answers "不确定,没有,二十分钟见到东西" --minutes 20
```

```text
起点档案（已记录）：{"api": "不确定", "tools": "没有", "mode": "二十分钟见到东西"}
  → M1-first（standard，20 分钟切片；只定起点，不作能力证据）

status：
起点档案：{...} → M1-first（standard，20 分钟切片；answered=True）
```

`start --minutes 20` 现在会写入 `start_profile.slice_minutes=20`，随后 `next`/`review`/`defend`
都用 20 分钟；只有 `next --minutes 60` 这种单次参数才临时覆盖。

## 2. 一次登记两个交付物 → 评分

```powershell
python "$V\runtime\learn.py" artifact add "$V\examples\demo-artifact-v1.py" demo-project\docs\m1-design.md --project demo-project --offline
python "$V\runtime\learn.py" review --project demo-project --offline
```

```text
已登记 2 件（同一批共享 assisted_level=0）：
  - a-M1-4af7c614 path=artifacts/M1/demo-artifact-v1.py sha256=4af7c6145fa8 size=2384
  - a-M1-5fb4cd33 path=artifacts/M1/m1-design.md sha256=5fb4cd33d125 size=104

▶ 唯一动作：gap_learn（g-M1-contract）
dim             weight  threshold  score  state  note
--------------  ------  ---------  -----  -----  --------------------------------
runnability     30      3          3      达标     对 in.txt 求和一次跑通，有可观察输出（第 24 行）
contract        30      3          2      未达标    TOOLS 缺 parameters 类型，模型传字符串时未校验
robustness      20      3          2      未达标    路径不存在时抛未捕获异常，无改道
explainability  20      2          1      未达标    docs/m1-design.md 缺失

证据不足降分：explainability 2→1（缺 evidence_line/evidence_path，threshold=2）
[运行时] 评审 note 声称已登记文件缺失，已记 review_note_conflict：explainability → artifacts/M1/m1-design.md
缺口卡：g-M1-contract(created)；g-M1-robustness(created)；g-M1-explainability(created)
```

多文件登记后 critic 的上下文包含“已登记作品集合 + 其他文件内容片段”；即使离线脚本仍在 note 里
说设计说明缺失，运行时也会记录 `review_note_conflict`，不会静默接受。

## 3. 缺口微课 → 改作品 → 复评

```powershell
python "$V\runtime\learn.py" gap learn g-M1-contract --project demo-project --offline
python "$V\runtime\learn.py" next --project demo-project --json
python "$V\runtime\learn.py" gap learn g-M1-contract --project demo-project --offline   # 重复：被抑制
python "$V\runtime\learn.py" artifact add "$V\examples\demo-artifact-v2.py" --project demo-project --offline
python "$V\runtime\learn.py" review --project demo-project --offline
```

```text
缺口卡 g-M1-contract：contract 2/3 → status=learning（关闭只能靠后续复评达标）
▶ 唯一动作：do_task（a-M1-5fb4cd33） — M1 的 g-M1-contract 已上过微课；先按微课改作品，再 artifact add + review 复评

next --json：
{"action": "do_task", "ref": "a-M1-5fb4cd33",
 "reason": "M1 的 g-M1-contract 已上过微课；先按微课改作品，再 artifact add + review 复评"}

重复 gap learn：
g-M1-contract 已上过微课（learn_count=1），不重复讲。
上次讲解摘要：[离线脚本导师] 这张卡是 contract：工具定义不是注释，是给模型看的契约……
先按上次微课改一处，再 artifact add + review；确实需要重讲请用 gap learn --force。
（同时写入 gap_repeat_suppressed 事件，不再调用导师）

已登记：a-M1-cfb4fa52
  path=artifacts/M1/demo-artifact-v2.py sha256=cfb4fa52a64b size=2650 assisted_level=1
  取代：a-M1-4af7c614（新 sha 需要重新评审）

runnability 3 / contract 3 / robustness 3 / explainability 3，加权 3.0，达阈值
本次关闭缺口：g-M1-contract, g-M1-robustness, g-M1-explainability（复评达标）
```

`assisted_level=1` 只来自这轮 coach 的 L1 提示；`gap learn` 的 guide 微课（help=3）不计入作品帮助。
若这一轮导师只给了 4 步骨架而机器块漏写 `help_level`，运行时会推断 L3 并写 `help_level_inferred`，
`status` 的“帮助等级”能看到最近/最高等级。

## 4. 防御性解释 → 里程碑通过

```powershell
python "$V\runtime\learn.py" say "我解释完了" --project demo-project --offline
```

```text
▶ 唯一动作：do_task — M2「记忆与恢复」还没有作品；交付物：m2/agent.py + m2/state/session.json + docs/m2-design.md
[运行时] defense 3/3 问通过；最重维度 通过；判定：passed
[运行时] 里程碑 M1 通过（passed），已激活 M2
导师：coach｜M1 status=passed｜help_level=0
```

## 5. 状态 / 暂停 / 同步 / 自检 / 导出

```powershell
python "$V\runtime\learn.py" status --project demo-project
python "$V\runtime\learn.py" pause --project demo-project --note "v0.2.3 离线闭环"
python "$V\runtime\learn.py" sync --project demo-project
python "$V\runtime\learn.py" doctor --project demo-project
python "$V\runtime\learn.py" export --out demo-archive.md --project demo-project
```

```text
起点档案：{...} → M1-first（standard，20 分钟切片；answered=True）
帮助等级：最近 L0（critic）｜最高 L2（guide）
作品：3 件｜最新 a-M1-cfb4fa52 artifacts/M1/demo-artifact-v2.py sha=cfb4fa52a64b assisted_level=1

已暂停。交接写入 .learnark/handoff/latest.md
git state: no-remote (written=yes, committed=yes, pushed=no)
  remote=无远程（本地提交已保留，真实 GitHub 同步未验证）
自检通过：0 个错误，1 个提示。下一步：do_task
已导出：...\demo-archive.md（5152 字节）
```

## 6. 这次演示没有证明什么

- 没有真人学习，也没有真实 LLM 教学：导师文本来自离线脚本，只能证明流程与门控。
- 没有验证远程 GitHub：同步只到本地提交，无远程时明确标注“真实 GitHub 同步未验证”。
- 帮助等级推断与动作冲突检测都是启发式：`help_level_inferred` 可能高估/低估，
  `mentor_next_conflict` 只识别少量动作词；以界面上的 `▶ 唯一动作` 为准。
- 离线脚本的固定台词仍可能提到 `agent_v2.py` 之类文件；真实导师是否服从 `runtime_next`
  需要真实 API 轮次验证（round-02 报告中仍有冲突，本版已加可见权威动作与冲突记录）。
