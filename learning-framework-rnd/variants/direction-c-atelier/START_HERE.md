# Atelier · 五导师工作室（direction-c-atelier）入口

**这是什么**：把一次学习拆成 planner / concept / coach / examiner / reviewer 五个职责不重叠的席位；
每次换人、暂停、开考、复盘都写一份机器可校验的交接单，学习者可以随时点名需要的那种帮助。
**适合谁**：已有零散经验、单次常只有 20 分钟、最烦“换个窗口就从头讲一遍”的自学者。
**不是什么**：不是零基础保姆，不是作品集驱动，不是多个真人；“多导师”是角色与会话。
**版本**：0.2.4 · learncore 1.0.4 · schema 1（本目录内自包含，不依赖 `shared/`）。

## 1. 三步开始（Windows PowerShell）

```powershell
# 0) 已有 DeepSeek key 才需要这一步；没有 key 也能用 --offline 跑流程
$env:DEEPSEEK_API_KEY = "sk-..."

# 1) 建项目（把 $LA 换成本目录的实际路径）
$LA = "C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier"
python "$LA\runtime\learn.py" init --goal "Agent 开发" --dir C:\learn\agent-dev

# 2) 进入项目并开始（只读计划并打开会话，不写交接、不调模型）
cd C:\learn\agent-dev
python "$LA\runtime\learn.py" start

# 3) 说话（第一次先由 planner 做 ≤4 轮诊断，自述不算能力）
python "$LA\runtime\learn.py" say "我做过 RAG，但没写过工具调用"
```

想少打字：`& "$LA\learn.cmd" start`（`learn.cmd` 内部用 `%~dp0runtime\learn.py`，可在任意目录调用）。

## 2. 全部命令

| 命令 | 作用 | 常用可选项 |
| --- | --- | --- |
| `init --goal TEXT` | 建项目、写计划 v1、生成 AGENTS/README、初始化 git | `--dir PATH` `--template agent-dev\|email` `--minutes-per-week N`（分钟） `--name SLUG` |
| `start` | 一句话入口：上次停在哪、计划是什么、该找哪位导师 | `--minutes 20` |
| `say TEXT` | 学习者发言，得到导师回复并记录（`say -` 读 stdin）；交接失败也不会丢回合 | `--no-auto`（关闭导师提案的自动交接） |
| `status` | 目标 / 计划 / 能力 / 未决 / 下一步 / git | `--json` |
| `switch MENTOR` | 换导师；运行时从记录合成完整交接单，默认成功 | `--why TEXT` `--strict`（契约测试） `--fill-missing` |
| `studio` | 五席位视图：回合、最近活动、未决、当前/建议 | `--json` |
| `handoff` | 查看最新交接；校验全部历史交接 | `--last N` `--check` |
| `plan` | 计划、步骤、已生效/待批准变更 | `--json` `--check` `--approve PC-xxxx` `--reject PC-xxxx` |
| `examine` | 切 examiner 并开考（写交接 + 建 pending_exam） | `--activity ID` `--fill-missing` |
| `review` | **reviewer 复盘**（不是 review 队列）：复盘 + 遗忘检查 + 自交接 | `--why TEXT` `--fill-missing` |
| `pause` | 结束本次：写自交接、保存、本地提交 | `--note TEXT` `--fill-missing` |
| `sync` | git 同步，如实报告 written/committed/pushed；分叉时 journal 自动并集，state 冲突需显式选边 | `--recover --prefer local\|remote` `--message TEXT` `--note TEXT` |
| `doctor` | 自检：状态、日志、去重索引、锁、git、API、计划哈希、交接 | `--plan`（只看计划权威） |
| `export` | 导出 Markdown 学习档案 | `--out FILE` |

全局：`--project PATH`（默认从 cwd 向上找 `.learnark/`，也可用 `LEARNARK_PROJECT`）、
`--offline`（等价 `LEARNARK_LLM=mock`，输出标明离线）。退出码：0 成功 / 2 用法错误或导师名歧义 / 3 状态冲突或显式 `--strict` 交接被拒 / 4 环境或网络。

## 3. 五个席位

| 导师 | 负责 | 不负责 |
| --- | --- | --- |
| planner | 目标澄清、周目标、步骤排序、时间预算、批准计划变更 | 不讲课、不判分、不陪练 |
| concept | 最小模型、类比、反例、要求复述 | 不排计划、不评分 |
| coach | 分级提示、调试、拆步 | 不宣布掌握、不改计划 |
| examiner | 迁移题、判定、写 verified 证据 | 不给提示、不辅导、不复用原题 |
| reviewer | 复盘、遗忘检查、下周建议 | 不重讲、不改当前任务、不判分 |

## 4. 记录在哪里

| 路径 | 内容 |
| --- | --- |
| `.learnark/project.json` | 目标、模板、约束、学习者、schema |
| `.learnark/state/studio.json` | 计划（planner 权威）、当前导师、未决项、计划变更 |
| `.learnark/state/capability.json` | 能力节点 + 逐条证据（只能由运行时写） |
| `.learnark/state/mentors/<id>.json` | 五份私有笔记（≤8 行，只有本人读） |
| `.learnark/handoff/` | 每次换人/暂停的交接单 + `latest.md` |
| `.learnark/journal/events.jsonl` | 权威事件流（`context_manifest`、`handoff`、`plan_change_applied`…） |
| `sessions/` | 每次会话的师生原文、help_level、尝试、下一步 |
| `artifacts/` | 练习产物与导出的档案 |

**恢复**：新进程 / 新目录 / 干净克隆里 `start` 只读上述文件，不依赖聊天历史；`--project` 指向克隆目录即可。
**同步**：`sync` 只提交项目允许路径，区分 written / committed / pushed，绝不 force push；
没有 remote 时本地提交成功，并明确写“真实 GitHub 同步未验证”。分叉时 journal 按事件 id 并集合并，
state 冲突默认拒绝并要求 `--prefer local|remote`（会打印保留/覆盖了哪些文件），完成后推送；冲突退出码 3。
`status` 显示 `diverged/unmerged`，`doctor` 在分叉时失败。新项目自动生成 `.gitattributes`（`* -text`），并忽略 lock/usage/sync-log。

## 5. 交接契约（运行时强制）

- 触发：`switch`、`pause`、`examine`、`review`、导师提案的自动交接。
- 文件：`.learnark/handoff/YYYYMMDDTHHMMSS-<from>-to-<to>.md` + `latest.md`；末尾 ```handoff 机器块权威。
- 必填 9+2：`from/to/why/known/what_tried/do_not_redo/open_loops/next/created_at` + `handoff_id/schema_version`。
- `known` / `what_tried` / `open_loops` / `next` / `do_not_redo` 全部由运行时从 journal、会话与计划合成；
  导师只提供 `why`（缺省为“用户点名”）。`do_not_redo` 只收明确说过的条目，空是正常的。
- `say` 先落学习者消息、导师回复与会话，再处理交接；交接失败只记 `handoff_rejected` 并留在当前导师，退出码仍为 0。
- `switch` 默认就成功；`--strict` 才要求导师提案含 why/what_tried/open_loops/next（契约测试用），失败退出码 3、不写文件、不换导师。
- 换导师后新上下文只注入 `latest.md`，不注入完整历史；每回合写 `context_manifest`（字符数/来源/交接 id）。

## 6. 证据、下一步与恢复（0.2.4）

- **只有 examiner 能判对**：`correct=true` / `verified` 仅来自 examiner 会话；coach/concept/planner 的尝试记
  `practice_attempt`（`correct=null`，只作观察），**永不升级能力**。导师一边夸奖一边纠正会被记 `mentor_verdict_conflict`，按未通过处理。
- **时间会落盘**：学习者说“每周 1–2 小时 / 今天 20 分钟”后，project/plan/session 立即更新；start/plan 显示真实区间与剩余分钟，导师正文不能把 16 秒说成 20 分钟。
- **下一步可执行**：运行时 `next` 带动作、活动与预计分钟；导师承诺的下一活动会记成 blocking open_loop，不会被一句“过掉了”覆盖。
- **诊断要真的问**：planner 至少覆盖 2 道 probe（或给出计划/交接）才结束首次诊断；start 会列出还没问的题。
- **薄弱只来自学习者相关文本**：只有学习者原话被点名纠正（`你把…` / `你说…`）或 planner 明确诊断“误解/需要先讲清”时才写
  `misconception_observed`；解释句、夸奖句不会给未开始的技能造弱点。
- **多题考核可恢复**：`pending_exam` 保存 3 题队列与 remaining，答一题减一题，`next=examine` 直到全答完；examiner 自动写
  `artifacts/<题号>.md`，pass 关闭里程碑 open_loop，不再出现 verified 与空 artifact 并存。
- **next 只来自运行时**：导师正文说“过掉了”不会改计划或 step 状态；换人只认 `switch` 或“让 coach 来/找 planner”这类直接请求，
  叙述里提到导师只记 `mentor_mentioned`。
- **start 不造历史**：只读计划并打开会话（`session_opened`），不写 handoff/studio，不再凭“超过 7 天”补交接或生造未决项。
- **空会话不交接**：没有任何导师回合时 pause 只记 `pause_no_handoff`，不造空的 concept→concept 交接。
- **回合不因格式丢**：机器块缺失/非法时静默重试一次；仍失败只提示“本轮没有形成可记录的证据”，`status` 把该回合帮助等级显示为「未标注」，
  原文保留。帮助等级 0 显示为「独立作答（无提示）」，不再读成“完成”。
- 交接 `what_tried` 只在标点边界截断并保留 `…`，只收 journal/session 里的事实；提示词明确禁止虚构上一轮的尝试/报错。

## 7. 离线模式与已知限制

- `--offline` 用脚本导师（`tests/fixtures/mentor_script.jsonl`），每个回复以 `[离线脚本导师]` 开头，
  事件标 `synthetic: true`；**不能当作真实教学质量或学习效果证据**。
- `examine` 的题目是否真属迁移题，仍取决于模型质量；运行时只能查重与核对评分标准。
- 6000 字符上下文预算与 30 回合增长曲线尚未做真实长跑；单回合 token 成本预计高于单导师方向。
- `--minutes` 目前只影响提示与展示，尚未真正裁剪本回合活动大小。
- 未验证真人长期学习收益；模拟学习者数据只证明系统行为。email 模板只有流程与评分口径，没有真人写作数据。
- 已知问题清单以 `version-manifest.json` 的 `known_limits` 为准。

