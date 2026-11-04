# 体验报告 — SkillMap（direction-a）· round-01 · S1（P1 小林）

- **版本**：SkillMap 0.1.1（`START_HERE.md` 页脚；标题仍写 v0.1.0）/ runtime core 1.0.1 / schema 1
- **体验者**：独立子 Agent（DeepSeek Harness 会话，非研发者；按 P1 小林画像模拟）
- **场景**：S1 初次进入（P1：会一点 Python、跟教程跑过 `requests`、没写过 Agent；今天约 30 分钟；概念题敢猜、代码题易卡）
- **项目目录**：`C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r01-s1\proj`
- **入口**：`python runtime\learn.py ...`（工作目录 `variants\direction-a-skillmap`）
- **交互预算**：10 次，实际 **10 次**（10 条 `say`；另有 2 条 `start` 自动开场被会话文件记为 learner turn，不计入 `say` 预算）
- **时间/模式**：2026-11-04 02:32–02:35（Asia/Shanghai），真实 LLM（`offline: false`），未使用 `--offline`

> 下文 `.learnark/...`、`sessions/...`、`artifacts/...` 均相对项目目录。只读了任务允许的公开材料：round-01 任务书、`evaluation\harness\learner-brief.md`、本方向 `START_HERE.md`、产品生成的 `AGENTS.md`，以及任务书指定用于报告模板的 `shared\scenarios\personas.md` 末尾模板。未读源码/设计/mentors/curriculum/templates/tests/experiments/其他方向。

## 实际步骤（命令 + 关键输出摘要）

### 1. 准备与建项

```powershell
. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1
$env:PYTHONIOENCODING='utf-8'
cd C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-a-skillmap
python runtime\learn.py init --goal "能独立设计与实现最小可用 Agent" --template agent-dev --dir C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r01-s1\proj
```

退出码 0。输出：项目路径、目标、`模板：agent-dev（12 个节点，诊断 5 题）`、`状态：已创建`、生成 `.learnark/project.json`、`map.json`、`plan.json`、`memory.json`、`AGENTS.md`、`README.md`、`.gitignore`，`git init`；下一步提示 `start --project ...`。

### 2. 首次 start 与 5 题诊断

```powershell
python runtime\learn.py start --project "...\proj" --minutes 30
```

退出码 0。开场说明目标、12 节点、诊断 5 题约 6 分钟；随后一题一题问，共 5 次 `say`：

| 探针 | 锚点 | 我的回答（摘要） | 导师判词 | 记录 level_set |
| --- | --- | --- | --- | --- |
| Q1 tool call 往返 | B1 | 模型出 tool_call（名+参数）→ 程序执行 → 结果回传 → 模型继续；字段名不确定 | “比大概扎实，顺序对” | **L0** |
| Q2 终止条件 bug | C2 | `while step<5` 不会在无 tool_calls 时退出；应 `else: break`；顺带指出页脚 `i += 0` 是死循环 | “答得比要求多……那确实是我贴错的另一段”“记为答对” | L1 |
| Q3 RAG vs 会话记忆 | D2 | 数据来源（本次对话 vs 外部库）、问题（连贯 vs 私有知识）、“长上下文≠RAG” | “答得完整……记为答对” | **L0** |
| Q4 超时与异常 | A2 | `timeout=`；Timeout/URLError/HTTPError；5xx/429 可退避，401/403/404 不重试 | “相当到位”“记为答对” | L1 |
| Q5 最小评测 | E1 | 空/单/多函数、注释干扰、嵌套歧义；数字一致 + 真读文件；主动说难点 | “答得好……不是背模板” | L1 |

导师收尾原话（`sessions` 第 162–164 行）：“**五题……全部答对**……**不给你跳过基础概念，直接进动手节点**。下一轮从 **A2** 开始”。

但同一条 `say` 的运行时页脚“今日任务”写的是：

```text
节点：A1 Python 数据结构与异常（L0 → 目标 L3）
阶段：讲解 explain · 导师：概念导师 · 活动：A1-explain
预计：45 分钟（本次预算 30 分钟，只承诺推进一个阶段）
```

`status` 与 journal 的 `plan_selected` 也都是 A1。诊断的 B1、D2 在 map 里仍为 L0。

### 3. status（诊断后，退出码 0）

```text
当前：A1 Python 数据结构与异常 · explain（A1-explain） · 导师 concept
等级：L0 9 · L1 3 · L2 0 · L3 0
薄弱：
  - A1 仍是 L0（Python 数据结构与异常）
  - B1 仍是 L0（消息结构与角色）
下一步：继续 A1 的 讲解（A1-explain），约 45 分钟
同步：dirty（written=yes committed=no pushed=no）
```

### 4. A1 explain → drill → apply

```powershell
python runtime\learn.py start --project "...\proj"
```

退出码 0。讲解 `dict` 缺键行为与 `get` 默认值；微检查我答对（`get("b",99)` 返回 `None`；只有键缺失才用默认值），记录 `stage_passed: A1-explain`、`level_up: A1 L0 → L1`。

drill 两题（3 处 / 4 处异常点）均独立答对，记录连续 2 题通过、进入 apply。apply 要求在 `artifacts/` 写 `parse_record.py` + `data.json`：读 JSON、`get` 补默认值、捕获 `JSONDecodeError`/`FileNotFoundError`、失败打印第几条与异常类型。

我创建并真实运行：

```powershell
cd "...\proj\artifacts"
python parse_record.py
```

退出码 0，真实输出：

```text
第 4 条处理失败：AttributeError
总条数：4，成功：3
{'id': 1, 'name': 'a', 'tags': ['x']}
{'id': 2, 'name': 'unknown', 'tags': []}
{'id': 3, 'name': 'c', 'tags': []}
```

另把 `data.json` 临时改名验证 `FileNotFoundError`：输出 `找不到文件：data.json`，已改回。把 `name` 改成 `null` 的预测也实跑验证：输出 `{'id': 4, 'name': None, 'tags': []}`（`get` 默认值不生效），与预测一致。

第一次 `say` 提交产物后，运行时提示：

```text
! apply 不算通过：没有可核验的产物。请把可运行文件写进 `artifacts/`，并在下一轮把相对路径放进 `artifact` 字段
```

导师接着问 3 个定位问题。我第 10 次 `say` 回答后，运行时记录 `stage_passed: A1-apply (help_level=1)`、`level_up: A1 L1 → L2`（artifact `artifacts/parse_record.py` + sha256），进入 `A1-check`，并给出“变式”任务（用 `isinstance` 前置校验、删宽 `except`）。此时 10 次往返预算已用完，未做该变式。

### 5. pause 与最终状态

```powershell
python runtime\learn.py pause --project "...\proj" --note "10 次往返预算用完，停在 A1-check 开始前；A1 已到 L2，check 未开始"
```

退出码 0：

```text
已收工。交接已写入 .learnark/handoff/latest.md
- 停在：A1 · check（A1-check）
- 未决：A1 的 检查 阶段未收口
- 下一步：继续 A1 的 检查（A1-check），约 45 分钟
git state: no-remote (written=yes, committed=yes, pushed=no)
written: yes
committed: yes (sha ee2d460, files 14)
pushed: no
remote: （none：无远程，真实 GitHub 同步未验证）
```

之后 `status`（退出码 0）：当前 A1-check，`L0 8 · L1 3 · L2 1 · L3 0`，显示上次交接与“下一步”，`同步：clean（written=yes committed=yes pushed=no）`。

## 完成情况

- **开始**：成功（`init`、`start` 均 exit 0，项目与 git 初始化正常）。
- **诊断/定位**：**完成但结论自相矛盾**——5/5 探针完成、导师判“全对”，但 B1/D2 仍 L0，导师建议 A2、运行时却排 A1（见问题 1、5）。
- **尝试与反馈**：成功。explain 1 次、drill 2 题、apply 产物 + 3 问，全部为真实回答/真实代码/真实运行；A1 从 L0 到 **L2**。反馈具体（能指出“先抛 KeyError 而非 TypeError”等），不是泛泛表扬。
- **保存/恢复**：保存成功（`pause` 写入 handoff、commit `ee2d460`、`status` clean）。**恢复未测试**（S1 未要求；只在新进程跑了 `status`，能看到交接；没有在新进程 `start`）。
- **切换导师**：**未测试**（S1 未要求，未执行 `switch`）。观察到阶段推进时导师自动从 navigator → concept → coach → examiner，但记录归属有异常（问题 7）。

## 预期 vs 实际

| 预期（普通用户会期待） | 实际 | 证据 |
| --- | --- | --- |
| 5 题诊断后按导师结论进入起点 | 导师说“全部答对、下一轮 A2”，运行时“今日任务”是 A1（`dict.get`） | `sessions/20261104-023255-navigator.md:162-164`；`.learnark/journal/events.jsonl` seq 21；`status` |
| 诊断“全对”的节点至少不会是 L0 | B1、D2 仍 L0；状态还提示“B1 仍是 L0” | `status --json` 的 map；`sessions` 第 162 行 vs 探针记录 |
| 30 分钟预算内能完成一个阶段 | 每个任务都标“约 45 分钟”，10 次往返只到 check 开始前 | start/status 输出；“今日任务”页脚 |
| 诊断题正文与“诊断探针 n/5”页脚是同一题 | Q2、Q5 两处正文与页脚题面不同；Q2 导师承认“贴错的另一段” | `sessions:42-67, 134-158`；控制台页脚（附录 B.2） |
| 带引号的答案原样进入记录与下一轮导师上下文 | PowerShell 传参丢掉双引号；记录变成 `get(model, unknown)`，导师据此提醒“没加引号” | `sessions:293, 332` vs 我实际提交；附录 B.4 原始 argv 测试 |
| `artifacts/` 里的真实文件就算可核验产物 | 第一次 apply 判“没有可核验的产物”，journal 记 `artifact_missing`，第二次才通过 | journal seq 36/39；`sessions:379, 442` |
| 导师每轮带机器块，一次调用完成 | 12 个导师回合中 9 个需要“补问一次”；共 21 次 API 调用 | journal 的 `repaired:true`；`.learnark/usage.jsonl` |
| 中文输出正常、结束后知道自己在哪 | 控制台中文正常；结束后 status 明示 A1-check、L2、交接与下一步 | `status` 输出；`sessions` UTF-8 正常 |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | **重要** | 诊断结论、等级与计划三者不一致：导师判“五题全对、下一轮 A2”，运行时却选 A1（Python 数据结构）并把 B1/D2 记为 L0；P1 的 10 次往返全花在 `dict.get`/异常上，没接触 LLM/HTTP/Agent 主线 | `init` → `start` → 按真实水平答完 5 题 → 对比导师收尾、“今日任务”、`status` | `sessions:162-164`；`events.jsonl` seq 21；`status --json` map |
| 2 | **重要** | 12 个导师回合中 9 个首轮缺 `learn-update` 机器块，运行时自动补问；控制台出现“导师首轮回复缺少机器块”的内部提示，实际 12 轮对话产生 21 次 API 调用（47.6 s、76,139 tokens） | 任意 `say` 观察提示；或统计 journal 中 `repaired:true` 与 `usage.jsonl` 行数 | `events.jsonl`（mentor_turn）；`.learnark/usage.jsonl`（21 行） |
| 3 | **重要** | Windows PowerShell 5.1 下按 `START_HERE` 示例用 `say "..."`，正文里的双引号被原生参数解析吞掉；记录和下一轮导师上下文变成 `get(model, unknown)`，导师两次提醒我“没加引号”（我实际加了） | `python -c "import sys;print(repr(sys.argv[1]))" 'a "b" c'` → `'a b c'`；再用 `say 'data.get("model","unknown")'` 提交，读 `sessions` | `sessions:293, 298, 332, 339`；附录 B.4 |
| 4 | **重要** | apply 产物误判：真实文件已在 `artifacts/parse_record.py`，第一次仍记 `artifact_missing`（artifact 写作 `parse_record.py`），提示“没有可核验的产物”；白白消耗一次往返，第二次才以 `artifacts/parse_record.py` 通过 | 在 `artifacts/` 建好 `parse_record.py`，提交时说明路径；观察第一次 apply 与 journal | `events.jsonl` seq 36（`artifact_missing`）、seq 39（通过 + sha256）；`sessions:379, 442` |
| 5 | **重要** | 诊断探针正文与页脚不是同一题：Q2 正文是 12 行 `while` 伪代码，页脚却是 `i += 0` 死循环；Q5 正文是“数函数定义”，页脚是“加法工具最小评测”。学习者要花精力分辨答哪题，且页脚不落盘 | 首次 `start`，逐题对比导师正文与“—— 诊断探针 n/5”页脚 | 正文：`sessions:42-67, 134-158`；页脚：附录 B.2（控制台，产品未写入 sessions） |
| 6 | 一般 | 时间估算与预算不符：30 分钟预算，但每个节点/阶段都写“约 45 分钟”；10 次往返里 5 次被诊断占掉，A1 一个节点都没走完（check 未开始） | `start --minutes 30` → 看“今日任务”与 `status` 的“约 45 分钟” | `status` 输出；`sessions:175`；start 页脚 |
| 7 | 一般 | 会话/日志归属不一致：诊断收尾被 session 标成“概念导师”；最后一次 apply 回合在 session 标“考核导师”，journal 却是 `mentor:"coach", activity_id:"A1-check"`；handoff 是 `examiner → examiner` | 对照 `sessions` 的导师标题、journal 的 mentor_turn、`handoff/latest.md` | `sessions:148, 491`；`events.jsonl` seq 42；`.learnark/handoff/latest.md` |
| 8 | 一般 | 版本文档不一致：`START_HERE.md` 标题写 “v0.1.0”，页脚写 “版本 0.1.1”；用户不知道以哪个为准 | 读 `START_HERE.md` 第 1 行与第 90 行 | `variants/direction-a-skillmap/START_HERE.md:1,90` |

### 重点问题说明

**1（诊断→计划断链）**：这不是“导师说错一句话”，而是定位结果没有进入计划。导师明确说“不给你跳过基础概念，直接进动手节点……从 A2 开始”，运行时却在同一条 `say` 的页脚排了 A1，`status` 也显示 A1；地图里 B1/D2 仍是 L0，与“全部答对”直接冲突。对 P1 的实际后果：30 分钟里做的是 `dict.get`、异常类型、`isinstance` 前置校验——这些概念题我已答对，真正想学的“用 Python 调 LLM/工具”一行没碰。产品承诺的“5 个探针定位、只在未掌握节点推进”在这条路径上没有兑现。

**2（机器块补问）**：控制台在 12 个导师回合中出现 9 次 `! 导师首轮回复缺少机器块，运行时补问一次后取得（教学正文保持原样）`。补问机制本身有效（没有卡死），但代价是每轮多一次调用，且把内部修复提示直接显示给学习者。`usage.jsonl` 21 条、总延迟 47.6 s、76,139 tokens，正好对应“12 轮 + 9 次补问”。

**3（PowerShell 引号丢失）**：我实际提交的是 `data["model"]`、`data.get("model", "unknown")`、`rec.get("owner", {}).get("name")`，但 `sessions` 第 293/332 行记录成不带引号的版本；导师因此在第 298/339 行提醒“记得加引号”。根因在我的调用方式与 Windows PowerShell 5.1 的原生参数解析（已用最小 `python -c` 复现），不是 SkillMap 的 Python 逻辑；但 `START_HERE` 的首选示例就是 `say "..."`，Windows 用户贴代码/带引号答案时极易踩到，且会污染记录与导师判断。第 9 次提交改用 `say -`（stdin）后，代码引号在 `sessions:379-452` 中完整保留——这是可行的规避方式，但文档没有针对“带引号代码”提示。

**4（apply 产物误判）**：第 9 次往返我已在 `artifacts/` 放好两个真实文件并跑了脚本，仍然收到“没有可核验的产物”；journal 的 `artifact_missing` 明确写 `artifact: "parse_record.py"`。第 10 次往返后同一文件以 `artifacts/parse_record.py` 通过并写入 sha256。学习者无法控制 `artifact` 字段，只能重说一遍路径，因此这是产品/导师侧的一次假阴性；在更紧的预算下会直接卡住。

**5（探针题面不一致）**：Q2 正文问 12 行 `while step < 5` 的终止条件，页脚却让我读 `i += 0` 的死循环；我两个都答了，导师承认“那确实是我贴错的另一段”。Q5 正文问“读文件数函数定义”，页脚问“只做加法的小工具”，我按正文答。探针页脚没有写进 `sessions`，事后只能从控制台回溯——这本身也让诊断证据不可审计。

## 使用负担

- **师生往返**：10 / 10（`say` 10 次；另有 2 次 `start` 开场，会话共 12 个 learner turn）。
- **命令数**：18 条产品 CLI（`init` 1、`start` 2、`say` 10、`status` 3 次文本 + 1 次 `--json`、`pause` 1）+ 5 次本地 Python 运行/测试 + 2 次写文件。
- **API 负担**：21 次调用（12 导师回合 + 9 次补问），47.6 s 延迟，76,139 tokens（来自 `.learnark/usage.jsonl`；token 为 API 返回值，非估算）。
- **需要读的文档**：3 份指定材料 + 产品生成的 `AGENTS.md` + 报告模板 = 5 处；`START_HERE` 90 行、brief 49 行、任务书 74 行。
- **时间**：真实墙钟约 2 分 50 秒（02:32:35–02:35:25），不是完整的 30 分钟学习；10 次往返本身很快，说明“45 分钟/阶段”是内容预算而非实际交互耗时。
- **不清楚的地方**：
  1. 诊断后到底听导师（A2）还是听 `status`/“今日任务”（A1）？产品没有解释为什么导师结论没生效。
  2. “诊断探针 n/5”页脚和导师正文哪个才是题目？
  3. `apply` 的产物路径应写 `artifacts/parse_record.py` 还是 `parse_record.py`？文档说 `artifacts/`，导师第一次记的是 basename。
  4. `start` 自动开场算不算“师生往返”？我按 `say` 计为 10 次；如果算开场就是 12 次，会超过任务书的 10 次上限。
  5. 为什么“全部答对”的 B1/D2 还是 L0？状态里的“薄弱”因此不可信。
- **编码备注**：产品控制台中文正常；`sessions/*.md` 用 read 工具读取正常。用 Windows PowerShell 5.1 的 `Get-Content` 默认编码读 `.learnark/journal/events.jsonl` 会显示乱码，加 `-Encoding UTF8` 正常——这是查看方式问题，不计为产品缺陷。`shared/scenarios/personas.md` 模板本身显示为乱码（双重编码），我只按可见结构复刻了报告小节。

## 首次卡点与感知

- **第一次卡住的地方**：不是代码，而是诊断结束后的方向冲突——导师说“下一轮 A2”，同一条回复的运行时页脚却排“A1 explain 45 分钟”，`status` 也是 A1。我按运行时继续了，但不知道哪个才算数。第二次卡点是第 9 次往返：文件已在 `artifacts/` 且脚本真实跑通，apply 仍被判“没有可核验的产物”；第三次是导师提醒我“记得加引号”，而我提交时明明加了（实际是 PowerShell 把引号吞了）。
- **是否知道下一步做什么**：诊断前知道（`init` → `start`）；诊断后不完全知道（A2 vs A1）；进入 A1 后每一步都知道（导师给的动作具体：微检查、drill 两题、apply 写脚本并跑）；结束时知道——`status`/handoff 明确“A1-check，约 45 分钟”。10 次预算用完后我按停止条件没有再答变式。
- **导师是否理解我的水平**：**大体准确，但被计划和记录拖累**。导师能说出“概念层扎实、短板在真跑通”，并跳过异常基础直接问终止条件/最小评测；drill 和 apply 的反馈能指出具体判断（先抛 KeyError 而非 TypeError、`get` 默认值不生效）。但运行时仍把我放进 A1 的 `dict.get`；另外因引号丢失，导师两次基于失真文本提醒我“没加引号”，这让我怀疑它是否真的看到了我的答案。

## 结论

- **是否完成场景目标：是（有保留）**。S1 要求的“首次进入 → 5 题诊断 → 至少 1 次真实尝试 → 保存”全部完成：`init`/`start` 成功，5 个探针有真实回答，explain/drill/apply 均有真实文本与真实产物，`pause` 提交了 `ee2d460` 且 `status` clean。未完成的是“按定位进入 Agent 主线”：10 次往返只走到 A1 的 check 前，`A1-check` 未开始，L3 未验证；`A1` 内容是 P1 已会的 Python 基础，不是目标中的 Agent。
- **最需要修的一件事**：**让诊断结论、等级与下一步计划对齐**。既然导师判“全对、去 A2”，运行时就不该把 B1/D2 留在 L0 并排 A1；至少要向学习者解释“导师建议未生效”的原因，或让 `status`/“今日任务”成为唯一权威并在导师文本里同步。否则 SkillMap 最核心的“5 探针定位”在首次进入就会把用户送回已知内容，30 分钟预算被消耗掉却看不到 Agent。
- **次优先**：修机器块稳定性（9/12 补问）与 `say` 在 Windows PowerShell 下的引号/多行输入问题（引导用 `say -` 或文件），以及 apply 产物路径的假阴性。

## 附录 A：命令与退出码（按执行顺序）

工作目录除注明外均为 `variants\direction-a-skillmap`；`P` = `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\a\r01-s1\proj`。

| # | 命令（截断） | 退出码 | 关键输出摘要 |
| --- | --- | --- | --- |
| 1 | `. env.ps1; $env:PYTHONIOENCODING='utf-8'` | 0 | 密钥 present（长度 35）；Python 3.14.6 |
| 2 | `python runtime\learn.py init --goal "..." --template agent-dev --dir P` | 0 | 项目已创建；12 节点、诊断 5 题；git init |
| 3 | `python runtime\learn.py start --project P --minutes 30` | 0 | 开场；第 1 题/5（锚点 B1） |
| 4 | `say '<Q1 回答>' --project P` | 0 | B1 → L0；第 2 题/5（页脚为 `i += 0`） |
| 5 | `say '<Q2 回答>' --project P` | 0 | C2 → L1；第 3 题/5 |
| 6 | `say '<Q3 回答>' --project P` | 0 | D2 → **L0**（导师判“完整”）；第 4 题/5 |
| 7 | `say '<Q4 回答>' --project P` | 0 | A2 → L1；第 5 题/5（页脚为加法工具） |
| 8 | `say '<Q5 回答>' --project P` | 0 | E1 → L1；诊断结束；“今日任务 A1 · 45 分钟” |
| 9 | `python runtime\learn.py status --project P` | 0 | A1 explain；L0 9 / L1 3；下一步 45 分钟 |
| 10 | `python runtime\learn.py start --project P` | 0 | A1 explain 正文 + 微检查 |
| 11 | `say '<微检查回答>' --project P` | 0 | explain 通过；A1 L0→L1；进 drill |
| 12 | `say '<drill 第1题>' --project P` | 0 | 3 处全对；drill 1/2 |
| 13 | `say '<drill 第2题>' --project P` | 0 | 4 处全对；drill 通过；进 apply |
| 14 | `cd P\artifacts; python parse_record.py` | 0 | 失败 1 条 + 成功 3 条；另测 FileNotFound（改名后 exit 0） |
| 15 | `say -`（stdin，提交 `parse_record.py` 与真实输出） | 0 | 运行时提示 apply 不算通过（artifact_missing）；导师问 3 问 |
| 16 | `say -`（stdin，回答 3 问，含 null 预测/实跑） | 0 | apply 通过；A1 L1→L2；进 check；请求做变式 |
| 17 | `python runtime\learn.py status --project P` | 0 | A1 check；L0 8 / L1 3 / L2 1 |
| 18 | `python runtime\learn.py status --json --project P` | 0 | plan.turn_index=12；journal 42 事件；`offline:false` |
| 19 | `python runtime\learn.py pause --project P --note "10 次往返预算用完..."` | 0 | handoff 写入；commit `ee2d460`（14 files）；pushed: no |
| 20 | `python runtime\learn.py status --project P` | 0 | A1-check；交接；`同步：clean` |

补充本地操作（非产品命令）：写 `artifacts\parse_record.py`、`artifacts\data.json`；临时目录复跑 `name:null` 预测（首次 UTF-8 BOM 导致 JSONDecodeError，去掉 BOM 后输出与预测一致）；`$s='test "quoted" word'; python -c "...sys.argv[1]..." $s` 复现引号丢失。

## 附录 B：关键输出原文（节选自本次控制台）

### B.1 诊断收尾 vs 同一条 `say` 的“今日任务”

导师正文（`sessions:162-164`）：

```text
诊断结束。五题你的表现：Q1 tool call 一来一回、Q2 终止条件、Q3 RAG vs 记忆、Q4 超时与异常、Q5 最小评测——全部答对……
所以定位结论：不给你跳过基础概念，直接进动手节点。下一轮从 A2（LLM 调用：urllib.request + timeout= + HTTPError/URLError 分支）开始……
```

同一条回复末尾的运行时页脚（控制台）：

```text
—— 今日任务 ——
节点：A1 Python 数据结构与异常（L0 → 目标 L3）
阶段：讲解 explain · 导师：概念导师 · 活动：A1-explain
预计：45 分钟（本次预算 30 分钟，只承诺推进一个阶段）
```

### B.2 诊断探针页脚与导师正文不一致（Q2 / Q5）

Q2 导师正文是 12 行 `while step < 5` 伪代码；同一条回复页脚是：

```text
—— 诊断探针 2/5 · 锚点 C2 ——
读出这段伪代码里终止条件的 bug，并说明它为什么停不下来：
      i = 0
      while i < 5:
          call_tool()
          i += 0
回答「不知道」或「跳过」也是合法答案；诊断只会把节点置为 L0/L1，不会给 L2 以上。
```

Q5 导师正文是“读本地文件、数函数定义”；页脚是：

```text
—— 诊断探针 5/5 · 锚点 E1 ——
给一个只做加法的小工具任务设计最小评测：用例从哪来、怎么判定通过。
```

导师在 Q2 反馈中承认（`sessions:76`）：“还顺手抓到了我上一轮贴的片段里 `i += 0` 那个死循环——那确实是我贴错的另一段”。

### B.3 机器块补问与 API 用量

控制台在每个发生补问的回合显示：

```text
! 导师首轮回复缺少机器块，运行时补问一次后取得（教学正文保持原样）。
```

journal 统计：`mentor_turn` 12 条，其中 `repaired:true` 9 条（turn 2/3/4/5/8/9/10/11/12）。`.learnark/usage.jsonl` 21 条：总延迟 47,616 ms，总 tokens 76,139。

### B.4 Windows PowerShell 引号丢失（最小复现）

```powershell
PS> $s = 'test "quoted" word'
PS> python -c "import sys; print(repr(sys.argv[1]))" $s
'test quoted word'
```

我提交的是 `data["model"]`、`data.get("model", "unknown")`、`rec.get("owner", {}).get("name")`；`sessions` 记录（第 293/332 行）分别为：

```text
data[model] ... 改成 data.get(model, unknown)
rec[tags][2] ... 改成 rec.get(owner, {}).get(name)
```

导师据此两次提醒（`sessions:298,339`）“记得加引号”。第 9 次提交改用 `say -` 后，代码里的双引号在 `sessions:379-452` 完整保留。

### B.5 apply 第一次判失败与 pause

第 9 次 `say` 后控制台：

```text
! apply 不算通过：没有可核验的产物。请把可运行文件写进 `artifacts/`，并在下一轮把相对路径放进 `artifact` 字段（本轮不写 attempt，可原样重试）。
```

journal 对应事件（seq 36）：

```json
{"kind":"artifact_missing","payload":{"node":"A1","activity_id":"A1-apply","artifact":"parse_record.py","error":"artifact missing"}}
```

第 10 次后（seq 39）通过：

```json
{"kind":"level_up","payload":{"node":"A1","from":1,"to":2,"reason":"apply_passed","source":"verified","artifact":"artifacts/parse_record.py","artifact_sha256":"3375fc76..."}}
```

pause 输出：

```text
已收工。交接已写入 .learnark/handoff/latest.md
- 停在：A1 · check（A1-check）
git state: no-remote (written=yes, committed=yes, pushed=no)
committed: yes (sha ee2d460, files 14)
```

## 附录 C：证据索引

| 证据 | 内容 | 证明了什么 |
| --- | --- | --- |
| `sessions/20261104-023255-navigator.md` | 513 行；12 个 learner turn（2 次 `start` 开场 + 10 次 `say`）、12 个导师回合 | 全流程原文；第 162-164 行诊断结论；第 293/332 行引号丢失；第 379/442 行 apply 提交 |
| `.learnark/journal/events.jsonl` | 42 条事件；`mentor_turn` 12、`repaired:true` 9、`level_up` 5、`artifact_missing` 1 | 计划选 A1（seq 21）、产物误判（seq 36）、apply 通过（seq 39）、等级证据 |
| `.learnark/usage.jsonl` | 21 条 API 调用；47,616 ms；76,139 tokens | 补问带来的双倍调用与延迟 |
| `.learnark/handoff/latest.md` | examiner → examiner；停在 A1-check；未决“A1 检查未收口” | pause 的交接内容与下次起点 |
| `artifacts/parse_record.py`、`artifacts/data.json` | 可运行代码与 fixture；sha256 已在 journal 记录 | apply 的 L2 产物真实存在 |
| `git log` | `ee2d460 learn(proj): pause 2026-11-04 02:35` | 保存已提交；无远程、未推送 |
| `status`（文本 + `--json`） | A1-check、L2、B1/D2 L0、同步 clean | 结束后定位与等级分布 |

## 未测试 / 边界

- **新进程 `start` 恢复**：未测试（S1 不要求；只在新进程跑 `status`，能读到 handoff）。
- **`switch` 切换导师**：未测试（S1 不要求）；只观察到阶段推进时导师自动切换。
- **A1-check / L3**：未开始；`check` 的两题 examiner 判定、`help_level=0`、复习排期均未验证。
- **`review` / `sync` 独立命令 / `doctor` / `export` / `map` / `next`**：未测试（不属本次 10 次预算内）。
- **真实 GitHub 同步**：未测试（项目无远程；`pause` 明确 `pushed: no`）。
- **30 分钟完整学习**：未模拟；实际墙钟约 2 分 50 秒，内容上只推进到 A1-check 前。
