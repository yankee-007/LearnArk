# 体验报告 — direction-a-skillmap round-06 S6 跨主题迁移
- 版本: v0.2.3（core 1.0.2，schema 1；`status --json` 报 `core_version: 1.0.2`、`offline: false`）
- 体验者: 独立子 Agent（DeepSeek Harness 模拟学习者，独立上下文，非研发者，未参与实现）
- 场景: S6 跨主题迁移（P4 Tina，运营，不学编程，目标是英文工作邮件；本次 20 分钟）
- 项目目录: `_sandbox\projects\a\r06b-s6\proj`　入口: `python runtime\learn.py`（variant 目录下）
- 交互预算: 场景卡 8 次（模板默认 12 次），实际使用 **8 次**
- 真实 LLM: 是（未用 `--offline`；`status` 中 `离线：no`）

## 实际步骤（命令 + 关键输出摘要）

均在 PowerShell 中先 `. _sandbox\env.ps1`、`$env:PYTHONIOENCODING='utf-8'`，再 `cd variants\direction-a-skillmap` 执行。

1. **建项目**（email 模板）：
   `python runtime\learn.py init --goal "能写出清楚、得体、简洁的英文工作邮件" --template email --dir ...\r06b-s6\proj --minutes-per-week 3`
   → `模板：email（6 个节点，诊断 3 题）`；`.learnark/*`、`AGENTS.md`、`README.md`、git 均生成。
2. **开始**：`start --project ...\proj --minutes 20`
   → 开场先说目标，再给「第一题（诊断，1/3）：把 “Please provide the data today.” 改写成对上级的请求：保留紧迫感，但不失礼。」
   ⚠ 同一段里出现 `整个学习地图有 12 个节点`（实际 6 节点）。
3. **诊断 Q1**（往返 1）：提交一封 3 句改写（含 `sorry to bother you`、`if possible`）。
   → 反馈精确引用这两处：`“sorry to bother you”…把你自己放得太低了`、`“if possible” 和 “today” 放在一起，等于给了一个可以推后的出口`；随后**追问**「删掉 if possible 紧迫感会变强还是变弱」，题号不变。
4. **追问**（往返 2）：答“变强，因为 if possible 给了推迟的出口”。
   → W2 判 L1（`诊断上限，最多 L1`）。
5. **诊断 Q2**（往返 3）：题目是「下面这封 6 句邮件把结论放在最后一句」，但**正文没有给出这封邮件**。
   我如实反馈“邮件没看到，请贴出来”。
   → 导师承认 `是我这边的问题` 并补发 6 句样例，题号不变。
6. **Q2 作答**（往返 4）：指出“结论与截止日期压在最后一句，前四句全是道歉铺垫”，改法为“请求+时点提到开头，理由紧跟，感谢收尾”。
   → W1 判 L1；另补一条精度建议（第一句只放请求本身）。
7. **Q3**（往返 5）：项目延期两周、需批准新排期，列 3 段大纲。
   → W4 判 L1；反馈认可“如果不同意，请告诉我哪天可以”这条退路，并建议第二段先给新交付日。
8. **诊断收束与定位**：`诊断结束：只按证据置 L0/L1`；`定位：W2 由探针 Q1 判定 L1，先修 W1 L1 已就绪 → 跳过讲解与操练，直接从 apply 开始`。今日任务卡：W2 应用 apply（W2-apply）。
   ⚠ 任务卡只给了节点/阶段/预计分钟，**没有给具体的写作题目**；我按场景卡自行把“应用”理解成“写这封延期邮件”。
9. **提交第 1 版邮件**（往返 6，3 句 + 称呼落款，延期两天）：
   → 反馈说“能发了”，只点一处：`“I hope this is not too much trouble for your team.”这句的位置和分量`，指出它把“为什么延/延到哪天”两件硬信息隔开，且“替对方先定义了这件事很麻烦”；要求删掉或后移。
   ⚠ 同时记录 `本轮没有作答，只记录对话，不产生能力证据`——即我交出的完整邮件未被算作 apply 尝试。
10. **按反馈改第 2 版**（往返 7）：删掉中间道歉句，新日期紧跟原因，结尾改轻量的 `thanks for bearing with us`。
    → 反馈 `这版结构对了…可以发`；给一句可选微调（`We'll need to push` 更软）；随即发来**三周延期变式**；并提示 `应用还没通过：没有找到可核验的产物。把可运行文件放进 artifacts/，下一轮说明文件路径即可（本轮不计入尝试，可以原样重试）`。
11. **补产物**（往返 8）：把第 2 版存为 `artifacts/launch-delay-email-v2.md`，回复文件路径并重贴全文，说明变式留到下次。
    → `阶段通过：应用（W2-apply）`、`等级：W2 L1 → L2（独立通过）`，下一步 W2 检查（check）。
12. **status / pause**：`等级：L0 3 · L1 2 · L2 1 · L3 0`，当前 W2 `check`，薄弱含我这条具体错因；`pause` 输出 `written: yes / committed: yes (sha 4baa98c) / pushed: no（无远程）`，交接写入 `.learnark/handoff/latest.md`。
13. **新进程恢复**：在项目目录内、仅用 `start --minutes 20`（无其它参数）→ `上次停在 W2 的 检查，第 1 次提交已通过；今天续做 W2-check`，并直接给出两道 check 写作题（邮件 ≤120 词、称呼/结构/道歉位置要求）。
    ⚠ 该句“第 1 次提交已通过”与实际不符：check 阶段一次都没提交过。

## 完成情况

| 项 | 结果 |
| --- | --- |
| 开始（email 模板建项目 + start） | 成功；6 节点、3 探针，均为写作主题 |
| 首次诊断/定位 | 成功；3 题全走完，W2/W1/W4 置 L1，按规则从 W2-apply 起步 |
| 尝试（真实邮件） | 成功提交两版（v1 有道歉句错位，v2 按反馈修正） |
| 反馈 | 成功；两轮都精确到句，v2 被判“可以发” |
| 应用通过（L2） | 成功；W2 L1 → L2（独立通过），产物 `artifacts/launch-delay-email-v2.md` |
| 保存（pause + git） | 成功；written/committed=yes，pushed=no（无远程，产品明确说明） |
| 新进程恢复 | 成功；节点/阶段/下一步都在，且下一步仍是写作（W2-check） |
| 检查（check） | **未做**：8 次往返用尽（诊断追问 + 产物重交占掉 3 次），20 分钟预算到 |
| 切换导师 | 未要求（S6 卡不要求）；`status` 正确列出当前 examiner 与可切换项 |

## 预期 vs 实际

| 预期（普通用户期待） | 实际 | 证据 |
| --- | --- | --- |
| 换模板后课程/评分标准变成写作 | 是：6 节点全是邮件写作（结构与请求/语气/清晰度/场景/修改/主题行），check 题也是“称呼、结论先行、主动语态、道歉只能放一处” | `status --json` 的 `map.nodes`；`start` 的 check 题 |
| 诊断适配零基础写作的人 | 是：没有编程前置；“不知道/跳过”合法；判断题只置 L0/L1 | 三次探针输出 |
| 反馈针对我那封邮件 | 是：逐句引用 `sorry to bother you`、`if possible`、`I hope this is not too much trouble…`，并解释“硬信息被隔开”“替对方定义麻烦” | `sessions\20261104-115924-navigator.md` |
| 能力记录与 Agent 开发分开 | 是：节点 id 只有 W1–W6，`template: email`，无 A1/A2 或代码节点混入 | `status --json` |
| 换主题后不该再有编程痕迹 | 部分：写作标准里无代码；但出现「可运行文件」「接口文档/认证/联调」「12 个节点」 | 见问题 2、4、3 |
| 交出去的东西会被当作“这次尝试” | 不符：v2 判对却被记“本轮没有作答”，要另交 `artifacts/` 文件才算 | 第 10、11 步输出 |
| 恢复时告诉我真实进度 | 部分：节点/阶段/下一步都对，但“第 1 次提交已通过”check 并未提交过 | 第 13 步输出 |

## 问题

| # | 严重度 | 描述 | 复现步骤 | 证据路径 |
| --- | --- | --- | --- | --- |
| 1 | 重要 | 诊断探针 2/3 只说“下面这封 6 句邮件”，**邮件正文没随题发出**，学习者无法作答；必须自己投诉才补发（多花 1 次往返） | 新建 email 项目 → `start` → 连答 Q1 及追问 → 收到 Q2，检查是否有邮件正文 | `proj\sessions\20261104-115924-navigator.md` |
| 2 | 重要 | apply 需要 `artifacts/` 里“**可运行文件**”才算通过，但事前任何地方没说要存文件、也没说路径；已判 `correct` 的一轮被记“本轮不计入尝试”，必须重贴同一封才通过（多花 1 次往返，且“可运行”是编程语汇） | 写完 v2 邮件 → `say` 提交 → 看“阶段通过/等级”是否变化 → 提示要求补产物 | `proj\sessions\20261104-115924-navigator.md`；`artifacts\launch-delay-email-v2.md` |
| 3 | 一般 | 节点数与题数与实际不符：开场两次说“整个学习地图有 12 个节点”（实际 6），一次说“5 题”（实际 3 题）；生成的 `README.md` 也写“12 节点能力地图” | `start` 看开场段；`map` 看“共 6 节点”；读 `README.md` 命令表 | `proj\README.md`；`python runtime\learn.py map` 输出 |
| 4 | 一般 | check 第 1 题场景是“合作方接口文档**认证**写错导致**联调**卡两天”，属软件工程语境，与运营岗/英文邮件写作的目标场景不贴合 | 用尽 apply 后新进程 `start` → 读 check 第 1 题 | `proj\sessions\20261104-120130-examiner.md` |
| 5 | 一般 | 恢复时输出“上次停在 W2 的 检查，**第 1 次提交已通过**”，但 check 从未提交过，容易被理解成“check 已通过” | `pause` → 新进程 `start` → 读第一行恢复语 | 同问题 2 会话尾部；`proj\.learnark\handoff\latest.md` |
| 6 | 一般 | 任务卡“理由 2”在 check 阶段仍复述诊断定位理由（“探针 Q1 把 W2 置为 L1…直接从 apply 开始”），是过期理由 | 新进程 `start` → 看“理由”三条 | 同上 |
| 7 | 一般 | 任务卡只有“节点/阶段/活动 id/预计分钟”，**没有当轮要做什么**；apply 的写作题目是我自己按场景卡补的，普通用户会卡在“应用什么？” | `start` 后读“今日任务”段 | 第 8 步输出 |
| 8 | 一般（负担） | 诊断追问不推进题号（“诊断进度不变”），20 分钟预算里一次追问就吃掉 1 次往返；本次 3 次往返（追问 1 + 投诉缺题 1 + 重交产物 1）没换来新进度 | 按诊断逐题作答即可复现 | 同上 |

## 使用负担

- 师生往返: **8 次**（上限 8）；其中真正产生写作证据的 5 次（Q1、Q2、Q3、v1、v2），另 3 次用于追问/缺题投诉/重交产物
- 命令数: **16 次** `python runtime\learn.py`（init、start×2、say×8、status×2、map、next、pause）；另加 1 次 `Get-Content` 读 README
- 需要阅读的文档: 4 处公开材料（`round-06.md`、`START_HERE.md`、`learner-brief.md`、`personas.md`）+ 产品生成的 `README.md`/`AGENTS.md`
- 不清楚的地方:
  1. “应用”阶段到底要我写什么——任务卡没给题目；
  2. 邮件该存到哪、存成什么格式才算“产物”，为什么叫“可运行文件”；
  3. 生成 `README.md` 用 `Get-Content` 直接读会乱码，要加 `-Encoding UTF8`（用户侧操作，不算产品缺陷，但会吓到非技术用户）；
  4. “第 1 次提交已通过”指哪一次提交。
- 中文控制台: 通过 `python ... | Out-String` 输出正常，未出现乱码。

## 结论

- **是否完成场景目标: 是**（20 分钟内：email 模板建项目 → 3 题诊断 → 定位 W2-apply → 交真实邮件 → 按反馈改出可发的 v2 → apply 通过并升到 L2 → pause 提交 → 新进程只凭项目恢复，下一步仍是写作 check）。未完成的是 check 阶段，原因是 8 次往返用尽，不是产品阻塞。
- **跨主题是否真的换掉了编程课**: 是。节点、任务、评分标准都是写作（结构/语气/场景/修改），反馈能逐句指出语气问题，能力记录独立（W1–W6，无 Agent 节点）。
- **是否有编程残留**: 轻度有，3 处——`artifacts/` 要求“可运行文件”、check 题的「接口文档/认证/联调」场景、四处“12 个节点”话术；**没有**代码块、API 调用、Agent 术语进入写作标准或反馈。
- **最需要修的一件事**: 让 apply 的“产物”对写作任务说人话并前置说明——写作产物就是邮件文本本身，应在任务卡里就写明“把邮件存成 `artifacts/<名字>.md`，然后回一句文件路径”，不要等到判对之后才用“可运行文件”把一轮已通过的作答作废。

---

## 附 A：两版邮件（原文）

**第 1 版（v1，提交后被指出道歉句错位）**

> Hi Mark,
>
> Sorry for the late update - unfortunately we have to push the launch by two days, because the design files came in later than planned. I hope this is not too much trouble for your team. The new date is November 12. Let me know if that works for you.
>
> Thanks,
> Tina

**第 2 版（v2，按反馈修改，被判“可以发”，已存 `artifacts\launch-delay-email-v2.md`）**

> Hi Mark,
>
> We need to push the launch by two days because the design files came in later than planned. The new date is November 12. Please let me know if that works for you - thanks for bearing with us.
>
> Best,
> Tina

改动：删掉 `Sorry for the late update` 与中间那句 `I hope this is not too much trouble for your team.`；新日期紧跟原因；结尾换成一句轻的 `thanks for bearing with us`。

## 附 B：导师反馈摘要

| 轮次 | 反馈要点（原文摘句） |
| --- | --- |
| 诊断 Q1 | `“sorry to bother you” 在平级之间没问题，但对上级、且事情确实紧急时，它把你自己放得太低了`；`“if possible” 和 “today” 放在一起，等于给了一个可以推后的出口，紧迫感被自己拆掉了` |
| Q1 追问 | `正是对上级保留紧迫感又不失礼的核心机制：不是靠加礼貌词，而是靠把请求写成一个明确的、可回应的动作` |
| 诊断 Q2 | `你抓的正是“结论压在最后”这个结构病`；补充 `第一句最好只放请求本身…理由更适合单独成句` |
| 诊断 Q3 | 认可“如果不同意，请告诉我哪天可以”这条退路；建议 `先给新交付日，再列受影响的节点` |
| apply v1 | `只点一个最关键的问题：“I hope this is not too much trouble for your team.”这句的位置和分量`；`它夹在原因和新日期之间，把两件硬信息…隔开了`；`把“麻烦”这个词主动递给了对方` |
| apply v2 | `这版结构对了：原因和新日期连在一起…道歉换成了结尾一句轻的“thanks for bearing with us”，分量刚好…可以发`；可选微调 `“We'll need to push”` 更软 |
| 产物补交后 | `阶段通过：应用（W2-apply）`；`等级：W2 L1 → L2（独立通过）` |

评价：反馈是**针对我的句子**的（逐句引用 + 说明机制 + 给可选改法），不是“写得好/继续努力”式泛评；两轮都只点 1 个主问题，符合 20 分钟节奏。

## 附 C：status 摘要（pause 前 / 恢复后）

```
SkillMap · 能写出清楚、得体、简洁的英文工作邮件
项目：proj（template email）  离线：no
当前：W2 语气与关系 · check（W2-check） · 导师 examiner
等级：L0 3 · L1 2 · L2 1 · L3 0
帮助：上次提示等级 1 · 独立通过 1 次 · 受助完成 0 次
最近等级变化：W2 L1 → L2（独立通过）
薄弱：
  - W6 仍是 L0（主题行与首句）
  - W2：道歉句插在原因与新日期之间，隔断硬信息并放大对方的麻烦感
  - W3 仍是 L0（清晰度与简洁）
  - W5 仍是 L0（修改与自查）
下一步：继续 W2 的 检查（W2-check），约 20 分钟
同步：dirty（written=yes committed=no pushed=no）
```

`map`（6 节点，全部写作，无编程节点）：W1 结构与请求 L1 · W6 主题行与首句 L0 · W2 语气与关系 L2（in_progress）· W3 清晰度与简洁 L0 · W4 场景适配 L1（locked）· W5 修改与自查 L0。

交接（`.learnark\handoff\latest.md`）：停在 W2 · check；未决两条（W2 错因未澄清、check 未收口）；下一步“继续 W2 的 检查”。
