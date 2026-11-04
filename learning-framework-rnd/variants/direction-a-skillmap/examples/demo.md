# 示例：一次完整的离线运行（离线 / 合成）

> **离线 / 合成，不证明教学质量。** 本文件由 2026-11-04 在 Windows + Python 3.14.6 上的真实运行整理
> （v0.2.3 / core 1.0.2 复跑；可用门槛 L1、诊断定位、`probe` 机器块与产物路径归一化之后的输出）：
> `LEARNARK_LLM=mock`，导师回复来自 `tests/fixtures/mentor_script.jsonl` 的脚本，不是语言模型。
> 它证明的是**流程与状态**（诊断、四段推进、证据门槛、复习排期、交接、同步、自检），
> 不是教学效果，也不是真人学习收益。所有输出都带 `[离线脚本导师]` 前缀。

```powershell
$env:LEARNARK_LLM = "mock"
$v = "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-a-skillmap"
```

## 1. 建项目并开始（首次进入 = 诊断）

```powershell
python $v\runtime\learn.py init --goal "能独立设计与实现最小可用 Agent" --dir C:\learn\agent-dev --template agent-dev
python $v\runtime\learn.py start --project C:\learn\agent-dev --minutes 20
```

`init` 输出（摘要）：项目路径、目标、`模板：agent-dev（12 个节点，诊断 5 题）`、生成文件清单、`git init`。

`start` 输出（摘要）：

```
[离线脚本导师]
先不急着讲概念，我们用六分钟定位你在哪一层。五题可以只答思路……答完我按证据定起点，不自述定级。

—— 诊断探针 1/5 · 锚点 B1 ——
用自己的话讲一次 tool call 的一来一回：模型输出什么？你的代码做什么？结果怎么回到模型那里？
回答「不知道」或「跳过」也是合法答案；诊断只会把节点置为 L0/L1，不会给 L2 以上。
```

每答一题（`say "..."`）只推进一个探针，答完 5 题才写 `diagnosis_done` 并给出 `next`。答题记录示例：

```
—— 记录 ——
- diagnosis: Q1 → done（无机器块，按无证据记 L0）

—— 诊断探针 2/5 · 锚点 C2 ——
读出这段伪代码里终止条件的 bug……
```

> 说明：默认脚本导师只在命中关键词时返回带 `learn-update` 的回复；未命中时回退到英文占位文本，
> 运行时记 `mentor_update_invalid` 并按「无证据」处理（探针仍消费，只能记 L0）。这是有意保守的行为。

## 2. 状态 / 地图 / 下一步

```powershell
python $v\runtime\learn.py status --project C:\learn\agent-dev --json
python $v\runtime\learn.py map --project C:\learn\agent-dev
python $v\runtime\learn.py next --project C:\learn\agent-dev
```

`status --json` 关键字段（摘要）：

```json
{
  "goal": "能独立设计与实现最小可用 Agent",
  "learner": {"diagnosis": {"status": "done", "round": 1, "probes": [
      {"id": "Q1", "node": "B1", "status": "done", "level_set": 0}, {"id": "Q2", "node": "C2", "status": "done", "level_set": 0},
      {"id": "Q3", "node": "D2", "status": "done", "level_set": 0}, {"id": "Q4", "node": "A2", "status": "done", "level_set": 0},
      {"id": "Q5", "node": "E1", "status": "done", "level_set": 0}]}},
  "map": {"levels": {"L0": 12, "L1": 0, "L2": 0, "L3": 0},
          "status_counts": {"in_progress": 1, "locked": 11}},
  "current": {"node": "A1", "stage": "explain", "activity_id": "A1-explain", "mentor": "concept"},
  "next_action": "继续 A1 的 讲解（A1-explain），约 20 分钟",
  "sync": {"state": "dirty", "written": true, "committed": false, "pushed": false},
  "offline": true
}
```

`map`（真实输出，CJK 对齐后）：

```
能力地图 · agent-dev（可用门槛 L1：先修 ≥L1 即可开始；掌握仍要 apply/check 的 L2/L3 证据，共 12 节点）
id  节点                      簇          等级  状态         先修    复习到期
--  ------------------------  ----------  ----  -----------  ------  --------
A1  Python 数据结构与异常     foundation  L0    in_progress  —       —
A2  HTTP/API 与 JSON 边界     foundation  L0    locked       A1      —
B1  消息结构与角色            llm         L0    locked       A2      —
C2  调用往返                  tools       L0    locked       C1、B2  —
C3  Agent 循环与终止          tools       L0    locked       C2、B3  —
E1  评测集与回归              evaluation  L0    locked       C3、C4  —
（共 12 行，这里省略 B2/B3/C1/C4/D1/D2）
```

`next` 的三条理由与被排除节点（真实输出）：

```
下一个：A1 Python 数据结构与异常 · 讲解（A1-explain）
导师：概念导师 · 预计 20 分钟 · 当前 L0 → 目标 L3
理由：
  1. 无到期复习：队列里没有 due ≤ 2026-11-04 的节点（尚无复习安排）
  2. 阶段续做：上次停在 A1 的 讲解（A1-explain），先收口再换节点
  3. 等级最低 + 簇顺序：A1 当前 L0（目标 L3），先修 无先修 均已 ≥L1；……
被排除的节点（11）：
  - A2：先修 A1 为 L0，低于门槛 L1
  - C2：先修 C1 为 L0、B2 为 L0，低于门槛 L1
  - C3：先修 C2 为 L0、B3 为 L0，低于门槛 L1
```

> 这套默认脚本 5 题都落到 L0（脚本没有匹配到关键词），所以没有触发诊断定位；全对档案会从 B1-apply 起步，
> 见 `tests/run_tests.py::test_placement_all_correct_profile` 与 `START_HERE.md` 第 6 节。

## 3. 收工、同步、自检、导出

```powershell
python $v\runtime\learn.py pause --project C:\learn\agent-dev
python $v\runtime\learn.py sync  --project C:\learn\agent-dev
python $v\runtime\learn.py doctor --project C:\learn\agent-dev
python $v\runtime\learn.py export --out C:\learn\learning-archive.md --project C:\learn\agent-dev
```

`pause` 写入 `.learnark/handoff/latest.md` 并提交：

```
已收工。交接已写入 .learnark/handoff/latest.md
- 停在：A1 · explain（A1-explain）
- 未决：A1 的 讲解 阶段未收口
- 下一步：继续 A1 的 讲解（A1-explain），约 20 分钟
git state: no-remote (written=yes, committed=yes, pushed=no)
```

交接文件字段（真实内容，节选）：`from / to / at / node / stage / reason` + `## what_tried`、`## unresolved`、`## next`、`## context_digest`。

`sync`：`written: yes / committed: yes (sha …, files 2) / pushed: no / remote: （none…）`，退出码 0。

`doctor`：13 项检查全部 `ok`（项目可读、schema、12/12 节点、计划引用、journal 完整、去重索引、锁、git、LLM 配置、证据可追溯、产物存在、vendored core），`全部检查通过`。

`export`：写出 Markdown 档案（目标、等级分布、能力地图表、错因、交接、会话列表、下一步）。

## 4. 确定性证据链：四段推进与等级（脚本导师 `stage_flow.jsonl`）

默认脚本覆盖不到 A1 的完整路径，所以用仓库内的确定性脚本演示证据规则：

```powershell
$env:LEARNARK_MOCK_SCRIPT = "$v\tests\fixtures\stage_flow.jsonl"
python $v\runtime\learn.py init --goal "能独立设计与实现最小可用 Agent" --dir C:\learn\stage-demo
python $v\runtime\learn.py diagnose --skip --project C:\learn\stage-demo
# 先放一个真实产物，apply 只认存在的文件
Set-Content C:\learn\stage-demo\artifacts\parse_record.py "print('rows=3')"
foreach ($t in "EXPLAIN_OK","DRILL_ONE","DRILL_TWO","APPLY_OK","CHECK_OK") {
  python $v\runtime\learn.py say $t --project C:\learn\stage-demo
}
```

逐轮记录（真实输出，节选）：

| 轮次 | 记录 | 结果 |
| --- | --- | --- |
| EXPLAIN_OK | `stage_passed: A1-explain（help_level=1）`、`level_up: A1 L0 → L1` | 进入 drill |
| DRILL_ONE | `drill 进度：连续正确 1/2` | 仍 drill |
| DRILL_TWO | `stage_passed: A1-drill（help_level=0）` | 进入 apply |
| APPLY_OK | `stage_passed: A1-apply`、`level_up: A1 L1 → L2`（产物 sha256 可核验） | 进入 check |
| CHECK_OK | `stage_passed: A1-check`、`level_up: A1 L2 → L3` | 节点完成，A2 解锁 |

随后：

```
能力地图：A1 L3 mastered，复习到期 2026-11-11（7 天后）；A2 L0 in_progress；其余 locked
review  ：0 个到期复习（今天 2026-11-04）。最近到期：A1 · 2026-11-11。
今日任务：A2 HTTP/API 与 JSON 边界 · 讲解（A2-explain）· 概念导师
```

负向行为（同一套命令也验证过）：`help_level=2` 的正确尝试只记 `assisted_completion` 不升级；
explain 阶段提交 `A1-apply` → 退出码 2、不写 attempt；examiner 返回 `help_level≥1` →
`examiner_help_violation` 并作废该轮。

## 5. 这次运行证明了什么

- 证明：init/start/say/status/map/next/review/pause/switch/sync/doctor/export 全部退出码 0；
  诊断一题一轮并只置 L0/L1；先修 **L1 可用门槛**让先修未达标的节点不进入 `next`（A1 仍是 L0 时 A2/C2/C3 都被排除）；
  强档案（Q1→B1、Q4→A2 答对）诊断后写 `placement_applied`，直接从 `B1-apply` 起步，弱档案仍从 `A1-explain` 起步；
  证据规则按 help_level 分档；复习间隔按 `[1,3,7,16,35]` 前进；pause/switch 写交接；无远程时三态诚实报告；`doctor` 全绿。
- 没证明：教学效果、诊断精度、真实遗忘曲线、真实 GitHub 同步、真人学习收益。
  离线脚本导师的文本是罐头内容；换成真实 API 才有教学价值（见 `START_HERE.md` 第 5 节）。
