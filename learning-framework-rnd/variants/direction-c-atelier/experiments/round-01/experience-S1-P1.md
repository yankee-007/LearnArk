# 体验报告 — direction-c-atelier round-01 S1（P1 小林）

- 版本: 0.2.0（`version-manifest.json`）／`START_HERE.md` 正文写 0.1.0（不一致，见 G-10）
- 体验者: 独立子 Agent（DeepSeek Harness / deepseek-flash，独立上下文，非研发者）
- 场景: S1 初次进入（P1 小林，30 分钟，最多 10 次往返）
- 项目目录: `C:\Users\YK\Desktop\LearnArk\_sandbox\projects\c\r01-s1\proj`
- 入口: `python C:\Users\YK\Desktop\LearnArk\learning-framework-rnd\variants\direction-c-atelier\runtime\learn.py <命令>`
- 交互预算: 10 次；实际 `say` 8 次（仅 3 次拿到导师回复）
- 体验时间: 2026-11-04 02:32:51 – 02:36:22（+08:00）
- 环境: Python 3.14.6；`env.ps1` 已注入 `DEEPSEEK_API_KEY`；**全程真实 API**（`offline: false`、`mode=api`、`model=deepseek-flash`），未使用 `--offline`
- 编码: 每次命令前设 `[Console]::OutputEncoding=[Text.Encoding]::UTF8`；产品输出中文正常，无乱码

> 说明：本报告使用公开入口 `START_HERE.md`、任务卡、`learner-brief.md`、报告模板 `personas.md`，以及产品自身生成的 `sessions/`、`.learnark/` 输出；版本号按报告模板要求取自 `version-manifest.json`（仅版本字段，未读设计/源码/导师提示词）。未读 `runtime/`、`design.md`、`mentors/`、`curriculum/`、`templates/`、`tests/`、其他报告。未修改产品文件，未手改 `.learnark/`。
>
> 证据根目录：`C:\Users\YK\Desktop\LearnArk`。其中 `sessions/…`、`.learnark/…` 相对项目目录 `_sandbox/projects/c/r01-s1/proj`；`evidence/…` 相对 `_sandbox/projects/c/r01-s1`；其余路径相对证据根目录。

---

## 实际步骤（命令 + 关键输出摘要）

所有命令均先 `. C:\Users\YK\Desktop\LearnArk\_sandbox\env.ps1` 并设 UTF-8 输出编码，工作目录为项目目录（`init` 除外）。

| # | 时间 | 命令 | 退出码 | 关键输出 / 结果 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 1 | 02:32:51 | `init --goal "Agent 开发" --dir <项目>` | 0 | 已创建项目；模板 `agent-dev`；plan-v1（10 步）；git 初始提交 `71eb535` | `.learnark/journal/events.jsonl` seq 1-2 |
| 2 | 02:32:5x | `start` | 0 | 显示 plan v1、当前导师 planner、首次诊断 3 题（probe-d1/d2/d3），**并且直接写出了每题“期望”答案** | 下文“首次 start 原文”（当时未 tee；可用新目录 `init`+`start` 复现） |
| 3 | 02:33:11 | `say "你好，我第一次用这个……"` | **3** | 交接被拒：缺 `what_tried, open_loops, next`；**消息与回复均未保存**，`sessions/` 仍为空 | journal seq 3 `handoff_invalid` |
| 4 | 02:33:26 | `status` | 0 | “尚无学习记录（首次进入）”；planner；0/10；`dirty=True` | `_sandbox/projects/c/r01-s1/evidence/status-01.txt` |
| 5 | 02:33:31 | `say`（同样内容重发） | **3** | 同一错误；journal **无新事件**（被去重） | `evidence/turn02-say-retry.txt` |
| 6 | 02:33:42 | `say --auto "我第一次用，会一点 Python……"` | 0 | planner 首次回复（581 字符，help_level=0）；`PC-0001` 自动生效（plan v2） | `sessions/20261104-023339-planner.md`；seq 4-7 |
| 7 | 02:33:56 | `plan` | 0 | plan v2；第 1 周被压缩；步骤 1 `todo` | `evidence/plan-01.txt` |
| 8 | 02:34:04 | `say --auto "时间我打算两三个晚上各 40 分钟……四要素我猜是……"` | 0 | “你的四要素基本对……今天到此收工”；help_level=0；`PC-0002` 生效（plan v3） | session 第 2 轮；seq 8-11 |
| 9 | 02:34:16 | `status` / `plan` | 0 | 进度 0/10；“下一步：`switch concept`”；第 1 周备注写“①四要素（今天 30 分钟已完成）”但步骤 1 仍 `todo` | `evidence/status-02.txt`、`plan-02.txt` |
| 10 | 02:34:28 | `say --auto "我其实还有二十多分钟，不太想今天就收工……"` | 0 | 给出 6–10 行伪代码练习（含停止条件/状态位置/工具失败分支）；help_level=1；`PC-0003` 记为 proposed（`op=none`、reason 为空） | session 第 3 轮；seq 12-14 |
| 11 | 02:34:36 | `say --auto -`（stdin 提交 6 行伪代码） | **3** | 同一交接拒绝；**伪代码尝试、导师回复都没落盘**，journal 无事件 | `evidence/turn06-say-pseudocode.txt` |
| 12 | 02:35:01 | `pause --note "……伪代码尝试提交时被交接拒绝丢失。"` | 0 | 保存 `H-0001`（planner→planner，**degraded**，补齐 why/open_loops/next）；本地提交 `6b1c394`；无 remote | `.learnark/handoff/20261104T023501-planner-to-planner.md` |
| 13 | 02:35:0x | `handoff --check` | 0 | “检查 1 份交接：全部通过” | `evidence/handoff-check-01.txt` |
| 14 | 02:35:1x | `status` / `start`（新进程） | 0 | 恢复到 `H-0001`；下一步指向 concept；`start` 明确写“当前会话导师是 planner；切换会先写一份交接：`learn.cmd switch concept`” | `evidence/status-03-post-pause.txt`、`start-02-resume.txt` |
| 15 | 02:35:31 | `switch concept` | **3** | 缺 `why, what_tried, open_loops, next`；未换导师、未写文件 | `evidence/switch-concept-01.txt`；seq 19 |
| 16 | 02:35:36 | `switch concept --fill-missing` | 0 | `H-0002` planner→concept，**degraded**（4 个字段全部运行时补齐） | `.learnark/handoff/20261104T023536-planner-to-concept.md` |
| 17 | 02:35:4x | `plan` / `status` | 0 | 待批准 `PC-0003 op=none step=w1-agent-loop-ex1：（）`；提示“批准：`plan --approve PC-0001`”（**ID 错误**，PC-0001 已生效） | `evidence/plan-03-final.txt`、`status-04-final.txt` |
| 18 | 02:36:02 | `say "start 让我来找你。上次我跟 planner 说四要素是……"` | **0** | 被误判拦截：“你一句话里同时提到了 策划导师 planner、练习导师 coach……请用 switch 明确指定”；**无导师回复、无会话记录** | `evidence/turn07-say-concept.txt`；seq 23 |
| 19 | 02:36:13 | `say "我上次已经用自己的话说过四要素……"` | **3** | 同一交接拒绝；concept 回复丢失；journal 仅记 `handoff_invalid` | `evidence/turn08-say-concept2.txt`；seq 24 |
| 20 | 02:36:21 | `pause --note "切到 concept 后：一次被误判点名拦截，一次交接被拒……"` | 0 | `H-0003` concept→concept，**degraded**；本地提交 `c953bfc` | `.learnark/handoff/20261104T023621-concept-to-concept.md` |
| 21 | 02:36:22 | `status` | 0 | 当前 concept；上次停在 H-0003；0/10；待批 1 条；`dirty=True` | `evidence/status-05-final2.txt` |

### 首次 start 原文（说明：当时未 tee，以下为会话记录原文；可用全新目录 `init`+`start` 复现）

```
这一轮该找谁：策划导师 planner
  · 为什么：首次进入：planner 用 ≤4 轮诊断确认目标与周时长，再按计划移交
  · 首次诊断（每条 ≤1 分钟，答不出具体动作一律记 self_report）：
    - probe-d1：工具调用失败，第一步看什么（期望：原始返回与日志）
    - probe-d2：检索与记忆差在哪（期望：临时注入 vs 跨会话保留）
    - probe-d3：凭什么说改好了（期望：固定用例/回放）
```

### 首次卡住的确切位置

**第一次 `say`（02:33:11）就卡住**，在拿到任何学习内容之前：

```
交接被拒：缺 what_tried, open_loops, next。未换导师、未写文件、计划不变。
补齐方式：导师在机器块里给 handoff 提案；或显式降级：learn.cmd switch coach --fill-missing（会记 handoff_degraded）。
```

对一个第一次使用的初学者，“交接被拒”“机器块”“handoff_degraded”都无法理解；终端也没说“你的消息是否已保存”。

---

## 完成情况

| 环节 | 结果 | 说明 |
| --- | --- | --- |
| 开始（init → start） | **成功** | 两条命令都 exit 0；计划、当前导师、首轮动作都看得懂 |
| 诊断或定位 | **部分** | planner 只问了“每周时间怎么分”，没有执行 start 列出的 3 条 probe；四要素复述被一句“基本对”接受，**没有证据、没有追问**；能力节点仍 0 条证据 |
| 尝试与反馈 | **失败（概念题有 1 次弱反馈）** | 概念题得到 1 句反馈；真正写的 6 行伪代码在提交时被 exit 3 丢弃，**没有任何反馈**；产品事后在 `H-0002` 里写“本次会话没有新的动手尝试”，与事实不符 |
| 结束保存 | **成功但降级** | `pause` 两次都 exit 0，写 `H-0001`/`H-0003` 并本地提交；两次都是 degraded，自交接（planner→planner、concept→concept） |
| 恢复 | **成功（只读）** | 新进程 `start` 能读出 `H-0001`/`H-0003` 与下一步；未在恢复后继续学习（见“未测试”） |
| 切换导师 | **默认失败，降级成功** | `switch concept` exit 3；`switch concept --fill-missing` exit 0，但 4 个交接字段全部由运行时编造 |

**结论：S1 场景目标未完成。** 进入成功、保存成功，但“至少 1 次真实尝试 → 得到反馈”的闭环没有成立：唯一一次动手尝试被系统拒绝并丢失。

---

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 第一次 `say` 能得到导师回复，并留下会话记录 | 8 次 `say` 只有 3 次有回复；4 次 `say` exit 3，消息/回复/回合全部丢失 | `sessions/20261104-023339-planner.md`；`evidence/turn01-say.txt`、`turn06-say-pseudocode.txt` |
| 出错时知道“我的内容保存了吗、下一步做什么” | exit 3 只给交接字段名与 `switch … --fill-missing`，不提消息已丢失 | 同上 |
| `start`/`status` 打印的“下一步”照着做就能继续 | 打印的 `switch concept` 直接 exit 3，必须再加 `--fill-missing` | `evidence/start-02-resume.txt`、`switch-concept-01.txt` |
| 换了导师会接着我的进度讲 | 交接单写“本次会话没有新的动手尝试”，且 `do_not_redo` 里有我从未说过的话（“RAG 就是长期记忆”“框架三行代码搞定”） | `H-0002`、`H-0001`、`H-0003` |
| 30 分钟会被用在练习上 | 第二次回复（02:34:04，距 init 约 73 秒）就说“今天到此收工”；我要求继续后，练习刚给出就因交接失败而丢失 | session 第 2、3 轮；seq 24 |
| 导师能判断我的水平 | 只凭自述与一次概念复述，未验证；能力 0 证据，却把“已完成”写进周目标 | `plan-02.txt`、`status-05-final2.txt` |
| 记录可审计 | 被去重的失败、exit 0 的拦截都不出现在 `sessions/`；concept 会话文件 209 字节、0 轮对话 | `sessions/20261104-023536-concept.md`；journal 共 28 条，无 02:34:36 提交的对应事件 |
| 暂停/恢复后知道“上次停在哪” | 能读出 `H-0001`/`H-0003`，但 `to: planner` 与 `next_step.mentor: concept` 不一致；当前已是 concept 还提示“建议下一轮找 concept” | `H-0001` 机器块；`status-05-final2.txt` |

---

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| B-1 | **阻塞** | 导师提出交接到 coach 时，默认 `say` 以 exit 3 整体失败；学习者消息、导师回复、回合记录全部丢弃。planner 上复现 3 次（含伪代码尝试），concept 上 1 次。`--auto` 不是可靠绕过：交接机器块为空时（`raw_sha256=44136fa3…`，与空对象 `{}` 的 SHA-256 相同，推断）仍被拒 | `say "…"` → exit 3；重发仍 exit 3；`say --auto` 有时成功、有时仍 exit 3 | journal seq 3、19、24；`sessions/` 仅 3 轮对话；`evidence/turn06-say-pseudocode.txt` |
| B-2 | **阻塞** | `start`/`status` 明确提示的 `switch concept` 本身 exit 3（缺 4 个字段），只有 `--fill-missing` 才能换人；默认路径与产品自己的指引相反 | `start` → 按提示 `switch concept` → exit 3；加 `--fill-missing` → exit 0（degraded） | `evidence/start-02-resume.txt`、`switch-concept-01.txt`、`switch-concept-02-fillmissing.txt`；seq 19 |
| B-3 | **阻塞** | 丢失的回合在审计里不可见：5 次 exit 3 中 2 次（02:33:31 与 02:34:36 的 `say`）因 `handoff_invalid` 与首次同键被去重，完全没有事件；误判拦截以 exit 0 返回且不写 `sessions/`；concept 会话文件只有“会话结束” | 失败后查 `sessions/` 与 `events.jsonl`；对比 5 次 exit 3 只有 3 条 `handoff_invalid` | `sessions/20261104-023536-concept.md`（209 字节，0 轮）；journal 28 条事件中没有 02:34:36 那次提交的任何记录 |
| I-4 | **重要** | 交接单内容失真：`H-0002` 的 `what_tried` 写“本次会话没有新的动手尝试（运行时补齐）”，而学习者刚提交过伪代码；三份交接都带 `do_not_redo`“不要用「RAG 就是长期记忆」类比开场”“不要用「框架三行代码搞定」制造虚假完成感”——本次会话从未出现 RAG 或“三行代码”话题。下一导师会据此建立错误前提 | 提交尝试被拒后 `pause`；读任意一份交接单的 `what_tried` 与 `do_not_redo` | `.learnark/handoff/20261104T023501-planner-to-planner.md`、`.learnark/handoff/20261104T023536-planner-to-concept.md`、`.learnark/handoff/20261104T023621-concept-to-concept.md` |
| I-5 | **重要** | 导师名提拦截误判：消息里只有“planner”，被判定同时提到 planner 和 coach，exit 0 拒绝回答；提示让用户“用 switch 明确指定”，但学习者并没有要换导师 | 以 concept 为当前导师，`say "…上次我跟 planner 说…"` → 拒绝 | `evidence/turn07-say-concept.txt`；journal seq 23 `mentor_named_ambiguous` |
| I-6 | **重要** | 计划/进度自相矛盾：周目标写“①四要素（今天 30 分钟已完成）”，但步骤 1 仍 `todo`、进度 0/10、能力 0 证据；项目按 12 小时/周，学习者说约 10 小时，planner 还复述成“你说…每周约 12 小时”；待批 `PC-0003` 是 `op=none`、reason 为空的空变更；批准提示却让批 `PC-0001`（已生效） | `plan`、`status` 对照阅读 | `evidence/plan-02.txt`、`plan-03-final.txt`、`status-05-final2.txt`；seq 10-11、14 |
| I-7 | **重要** | 内部术语直接泄漏给初学者：导师回复里出现“交接信息缺失（没有上一份 handoff 的 `known` / `do_not_redo` / `open_loops`）”；终端打印“help_level=0”“上下文：581 字符（manifest 已入 journal）”“PC-0001 已由 planner 生效”，不解释是什么、对我有什么影响 | 任意成功 `say` 的终端输出 | `evidence/turn03-say-auto.txt`、`turn04-say-attempt.txt` |
| G-8 | 一般 | 首次 `start` 就把 3 条诊断题的“期望答案”印出来（如“期望：原始返回与日志”），诊断可被直接抄答案，无法测真实水平 | `start` 首屏 | 本报告“首次 start 原文”；复现：新目录 `init`+`start` |
| G-9 | 一般 | git 多次在 `pause` 成功后仍 `dirty=True`；新出现的 `.learnark/usage.jsonl` 未被跟踪/忽略，真实 API 调用后必然弄脏工作区 | `pause` 后立刻 `status` / `git status` | `evidence/status-03-post-pause.txt`、`evidence/status-05-final2.txt`；`git status` 输出 |
| G-10 | 一般 | 版本文档不一致：`START_HERE.md` 写“版本：0.1.0”，`version-manifest.json` 写 0.2.0；`status` 已停在 concept 仍建议“下一轮找 concept”；`pause` 的自交接仍以 `planner→planner` / `concept→concept` 的“换人”格式记录 | 读入口文档与 manifest；`pause` 后 `status` | `START_HERE.md` §版本；`version-manifest.json`；`status-05-final2.txt` |

（严重度口径：阻塞 = 主流程无法继续/成果丢失；重要 = 会误导学习者或下一导师、破坏信任；一般 = 体验糙点。）

---

## 使用负担

- **师生往返**: 8 次 `say`（3 次有回复、4 次 `say` exit 3、1 次 exit 0 但被拦截），另有 `switch` exit 3 一次；有效教学回合仅 **3 次**。按任务卡最多 10 次计，剩 2 次，但已无可继续的默认路径。
- **命令数**: 24 条产品命令（`init` 1、`start` 2、`say` 8、`status` 5、`plan` 3、`pause` 2、`handoff` 1、`switch` 2）+ 约 10 条只读检查命令（列目录、读 `sessions/`/journal/handoff、`git log`）。
- **需要阅读的文档**: 4 处（任务卡、`learner-brief.md`、`START_HERE.md`、报告模板 `personas.md`）。仅凭 `START_HERE.md` 能完成 init/start，这部分是清楚的。
- **真实 API 用量**: 3 次成功调用，合计 7,576 tokens（2,215 + 2,586 + 2,775），单次延迟约 2.1–2.6 s（`.learnark/usage.jsonl`）。
- **不清楚的地方**（作为 P1 的真实困惑）:
  1. 为什么第一次说话就“交接被拒”？我的消息到底发出去没有？
  2. 错误提示让我 `switch coach`，但我还没学任何东西，为什么要换导师？
  3. `--auto` 是不是必须加？文档只说“允许自动交接”，没说默认会失败。
  4. `PC-0001`/`PC-0002`/`PC-0003` 改了什么？`help_level` 是什么？与我有关吗？
  5. 周目标说“今天已完成”，为什么进度还是 0/10？我到底算不算学过？
  6. 我已经在 concept 了，为什么还建议“下一轮找 concept”？
- **第一次卡住的地方**: 第一次 `say`（02:33:11）即 exit 3，早于任何教学互动。
- **是否知道下一步**: `start` 之后知道（做四要素复述）；每次 exit 3 之后不知道（提示与学习无关）；第 2 轮回复（02:34:04 说“收工”）与 `status`（02:34:16 说“switch concept”）**两处指引互相矛盾**。
- **导师是否理解我的水平**: 没有证据表明理解。它接受了一句概念复述就判定“基本对”，没有验证工具调用调试能力（probe-d1 未执行），还把项目默认的 12 小时/周说成“你说的”。

---

## 未测试（不推测为通过）

- 降级换人后未能继续：`switch concept --fill-missing` 之后两次 `say` 都没有拿到 concept 回复（一次被误判拦截、一次 exit 3）。
- 新进程恢复后真正继续一轮学习、以及 `pause` 后跨天恢复：只验证了 `start` 只读恢复。
- `examiner` / `reviewer` / `examine` / `review` 流程：未进入。
- 真实 GitHub 远程同步与干净克隆（S4）：本项目无 remote，只验证了本地提交（`written=yes, committed=yes, pushed=no`）。
- 长会话（30 回合）上下文预算、断网/超时/无效 key 的错误处理：未测试。
- 离线脚本导师：按任务要求**未使用**。

---

## 结论

- **是否完成场景目标**: **否**。进入与保存成功，但“提交一次真实尝试并获得反馈”未完成——伪代码尝试被 `say` 的 exit 3 交接拒绝吞掉，且没有留下任何会话或事件记录；切换导师与继续学习都必须显式降级（`--fill-missing`）才可能进行。
- **最需要修的一件事**: **把“回合落盘”与“交接校验”解耦**——先把学习者消息、导师回复、`mentor_turn`/session 原子写入，再处理交接；交接字段不全时降级为“保留当前导师 + 提示”，绝不允许 exit 3 丢掉已经发生的教学回合（当前 5 次 exit 3（其中 2 次无任何审计痕迹）、1 次伪代码尝试丢失，都是这一条引起）。
- 补充判断：方向 C 的“五导师 + 交接单”概念对 P1 有吸引力（`start` 一屏能说清该找谁），但当前实现把**交接的严格性**放在了**学习记录的可靠性**之上，第一次使用就会让学习者失去自己写的东西——这比“讲得不够好”严重得多。
