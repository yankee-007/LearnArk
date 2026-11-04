# SkillMap 能力地图 · v0.2.4

**一句话**：把「学 Agent 开发」做成一张 12 节点、带先修关系的能力地图——首次进入用 5 个诊断探针定位，之后每次只在「先修就绪 + 未掌握 + 复习到期」的节点上按 **讲解 → 操练 → 应用 → 检查** 四段推进；等级只由运行时证据规则决定，不由导师话术决定。

- **适合谁**：接触过 Python 与 HTTP API、用 AI 攒过 RAG，但说不清自己哪会哪不会的人；怕漏基础、中断后想立刻定位的人；每周 10–20 小时、单次可能只有 20 分钟。
- **不是什么**：不是零基础 Python 系统课（A1 只做诊断与缺口提示），不是自由聊天（每条导师输出都挂在某节点某阶段），不做账号/云/移动端/后台唤醒，一个项目只有一个主题。
- **入口**：`runtime/learn.py`（或根目录 `learn.cmd`）。依赖 Python 3.10+ 标准库与 git，内置 `runtime/learncore`（core 1.0.2，禁止手改）。

## 1. 三步开始（Windows PowerShell 原文）

```powershell
# ① 设置密钥（只从环境变量读，不落盘、不打印）
$env:DEEPSEEK_API_KEY = "sk-你的key"

# ② 建项目（可重复执行，不覆盖已有状态）
cd C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-a-skillmap
python runtime\learn.py init --goal "能独立设计与实现最小可用 Agent" --template agent-dev --dir C:\learn\agent-dev

# ③ 一句话开始（首次进入自动做 5 题诊断，约 6 分钟）
python runtime\learn.py start --project C:\learn\agent-dev --minutes 20
```

也可以 `.\learn.cmd start --project C:\learn\agent-dev`。回答导师用 `say "..."`；20 分钟只承诺推进**一个阶段**，不承诺一个节点。

> **答案里有双引号或代码时**（Windows PowerShell 5.1 会吞掉双引号，这不是你的错）：把答案写进 UTF-8 文件再用 stdin，引号与多行会原样保留。
>
> ```powershell
> Get-Content .\answer.txt -Raw -Encoding UTF8 | python runtime\learn.py say - --project C:\learn\agent-dev
> ```
>
> 也可以直接 `python runtime\learn.py say - --project ...`，粘贴后按 Ctrl+Z 回车（Windows）。产品不会因为记录里少了引号而改判对错。

## 2. 全部命令

| 命令 | 作用 | 备注 |
| --- | --- | --- |
| `init --goal TEXT [--template agent-dev\|email] [--dir PATH] [--name NAME] [--minutes-per-week N]` | 建项目、生成 map/plan/memory、AGENTS.md、README.md、git | 可重复执行 |
| `start [--minutes N] [--node ID]` | 开始/继续；首次含诊断 | 预算是整场（诊断 + 活动 + 收尾）：诊断约 3 分钟（<30 分钟只做 2 题）、活动 = 剩余减 2 分钟收尾；任务卡显示算式；`--node` 越过先修门槛（等级上限锁 L1） |
| `say TEXT` | 回答导师 / 交产物；`say -` 读 stdin | 自动写会话、事件、证据；email 模板的 apply 会把本轮邮件正文自动存成 `artifacts/*.md` |
| `status [--json]` | 目标、当前节点/阶段、等级、薄弱、帮助等级、可切换导师、上次交接、下一步、同步状态 | JSON 为纯 JSON |
| `map [--json]` | 能力地图：等级、状态、先修、复习到期（节点数随模板） | 状态读时重算 |
| `next [--json]` | 下一个节点 + 3 条理由 + 被排除节点 + 预计分钟（整场预算内） | 同状态两次输出字节一致 |
| `review` | 到期复习队列（进入 check，零提示） | 每会话 ≤2 个，20 分钟会话 1 个 |
| `diagnose [--skip]` | 重新诊断 / 跳过诊断 | 诊断只置 L0/L1；跳过时已答对的等级与定位保留；对话里说“诊断到此结束”也会生效 |
| `pause [--note TEXT]` | 收工：写交接、提交 git | 恢复时 `start` 读交接 |
| `switch MENTOR` | 切换导师（navigator/concept/coach/examiner） | 当前阶段可切换的导师会列在 `status`/任务卡里；concept 随时可按需切换（记 `on_demand_switch`）；不允许时退出码 2 并列出可选项 |
| `sync [--message TEXT] [--recover]` | git 同步；`--recover` 在本地与远程都提交过时合并事件流 | 报告 written/committed/pushed；分叉时 `status`/`doctor` 会报 `diverged`，不会 force push |
| `doctor` | 自检：状态、日志、去重索引、锁、git、LLM、产物 | 有问题返回非 0 |
| `export --out FILE` | 导出 Markdown 学习档案 | 不含密钥 |

全局参数（可放任意位置）：`--project PATH`（从任意子目录向上找 `.learnark/`，或 `LEARNARK_PROJECT`）、`--offline`（= `LEARNARK_LLM=mock`，输出带 `[离线脚本导师]`）。退出码：`0` 成功 / `2` 用法或阶段门控 / `3` 状态冲突 / `4` 环境（无密钥、网络、意外）。

## 3. 学习记录在哪

| 路径 | 内容 |
| --- | --- |
| `.learnark/project.json` | 目标、模板、约束、学习者档案、诊断状态 |
| `.learnark/state/map.json` | 能力地图：节点、先修、等级、证据、复习间隔 |
| `.learnark/state/plan.json` | 当前节点/阶段、会话、上次决策 |
| `.learnark/journal/events.jsonl` | **权威事件流**（诊断、尝试、升级、交接、同步） |
| `.learnark/journal/dedupe.json` | 幂等索引（损坏可重建） |
| `.learnark/handoff/latest.md` | 最近一次交接（from/to/reason/what_tried/unresolved/next） |
| `sessions/YYYYMMDD-HHMMSS-<mentor>.md` | 每次会话原文与记录 |
| `artifacts/` | 你的产物（apply 通过需要真实存在的文件） |

## 4. 恢复 · 同步 · 没有远程

- **恢复**：换进程、换目录、干净克隆后直接 `start`，只读项目文件；输出形如「上次停在 A1 的 讲解，第 1 次提交未通过；今天续做 A1-explain，约 20 分钟」。
- **同步**：`pause` 会自动 `sync`。`init` 已 `git init` 并写 `.gitignore`/`.gitattributes`（排除密钥、锁、usage 日志，固定行尾）。三态输出：`written`（已写盘）、`committed`（已本地提交）、`pushed`（已推远程）。
- **两台设备都提交过（分叉）**：`status` 会显示 `diverged`，`doctor` 会失败；运行 `sync --recover` 合并事件流（按事件 id 取并集、重建去重索引、保留本地状态），不会 force push。状态文件（`state/*.json`）或产物冲突时，命令会列出真实文件列表并退出 3，等人工决定保留哪边。
- **没有远程**：本地提交照常，明确输出 `pushed: no` 与「无远程，真实 GitHub 同步未验证」；不会 force push。

## 5. 离线模式（`--offline` / `LEARNARK_LLM=mock`）

用 `tests/fixtures/mentor_script.jsonl` 的**脚本导师**，每轮输出前标 `[离线脚本导师]`。它只用于无网络演示、确定性测试与断网降级：**回复是罐头文本，不代表真实教学质量**；脚本没匹配到的轮次会回退到英文占位文本并记 `mentor_update_invalid`（按“无证据”处理，不升级）。想看升级/复习全链路，可用 `tests/fixtures/stage_flow.jsonl`（见 `examples/demo.md`）。

## 6. 等级与证据（由运行时判定）

| 等级 | 含义 | 最低证据 |
| --- | --- | --- |
| L0 | 未接触 | 无事件，或只有自述 |
| L1 | 能复述 | explain 在 `help_level≤1` 下通过（诊断最多到 L1） |
| L2 | 独立应用 | apply 在 `help_level≤1` 下通过 + `artifacts/` 里有 sha256 可核验的产物 |
| L3 | 独立迁移 | check 两题都由 examiner 判对且 `help_level=0` |

只有 `correct=true 且 help_level≤1` 能升级，**单轮最多 +1**；`help_level≥2` 一律记 `assisted_completion`、上限 L1。check 阶段 examiner 返回 `help_level≥1` 会被作废并记 `examiner_help_violation`。

**先修与诊断定位**：可用门槛是 **L1**——先修全部 ≥L1 的节点才会出现在 `next`（`--node` 可强制进入被锁节点，但等级锁 L1）；要声明某个先修「已掌握」仍需 L2 证据。诊断的评级由导师写进机器块的 `probe` 字段（`{"node": 锚点, "level": 0|1, "reason": "依据"}`）才进入地图，只写在正文里不算；导师只是追问时，题号不变、同一题会再问一次。诊断结束后，若某个被探针置为 L1 的锚点、其先修也都 ≥L1，运行时直接把它设为当前节点并从 **apply** 起步（跳过讲解与操练），写 `placement_applied`，`next` 的第 2 条理由会写明定位依据；先修仍为 L0 的节点不参与定位。

**帮助等级是可见的**：`status` 会显示上次提示等级、独立通过次数、受助完成次数，以及最近一次等级变化是「独立通过」还是「受助后，不计为独立」。刚接受过完整提示（提示等级 ≥2）的下一轮，即使自己答对也只算受助后的确认，最多到 L1，不会当成独立掌握。

复习间隔 `[1,3,7,16,35]` 天：通过 +1 档，失败降 1 级、退 2 档并记 `lapses`。

## 7. 已知限制

- 地图是 12 个手写节点，覆盖 Agent 主线，不含训练/部署/多模态；跨主题只提供一个写作模板（email，6 节点）。
- 诊断 5 题、只置 L0/L1，精度未与人工基线比对；`correct` 最终由导师判断，同一答案不同措辞可能结论不同。
- L3 在 check 通过时授予，并把下次复习排在 7 天后；「≥7 天复测」记录为 `retest_confirmed` 事件，而不是阻止先到达 L3。
- 真实 LLM 偶尔漏 `learn-update` 机器块：API 模式会静默补问一次（只在 journal 记 `mentor_update_retried`，不打扰学习者），仍失败则记 `mentor_update_invalid` 并按无证据处理。
- 到期复习只在执行命令时计算，没有后台提醒；真实 GitHub/跨设备与真人学习效果未验证。
- 版本 0.2.4 · core 1.0.2 · schema 1。问题与复现步骤请写 `issues.md`。
