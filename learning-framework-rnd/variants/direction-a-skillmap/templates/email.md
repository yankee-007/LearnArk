---
template: email
schema_version: 1
title: "英文工作邮件写作"
default_goal: "能在常见工作场景写出结构清楚、语气得体、可直接发送的英文邮件"
default_minutes_per_week: 180
level_scale: 3
prereq_gate: 1
mastery_gate: 2
stages: [explain, drill, apply, check]
mentors: [navigator, concept, coach, examiner]
review_intervals: [1, 3, 7, 16, 35]
---

# 模板 · email

跨主题迁移验证用：沿用同一套节点/阶段/证据规则，但**任务与评价标准全部换成写作**，不含任何代码产物。

## 1. 目标默认值
- `goal`（可被 `--goal` 覆盖）：`能在常见工作场景写出结构清楚、语气得体、可直接发送的英文邮件`
- `minutes_per_week`：180（小主题，3 小时/周；单次 20 分钟只做一个微任务）。
- 学习者画像：能写英文但易堆长句、请求不明确；自述“我英文还行”只作为待验证假设。
- 非目标：不做语法系统课、不做考试写作、不教商务谈判策略。

## 2. 节点清单（6 节点 / 3 簇）

| id | title | cluster | prereqs | target_level |
| --- | --- | --- | --- | --- |
| W1 | 结构与请求 | drafting | （无） | 3 |
| W6 | 主题行与首句 | drafting | W1 | 2 |
| W2 | 语气与关系 | voice | W1 | 3 |
| W3 | 清晰度与简洁 | voice | W2 | 3 |
| W4 | 场景适配 | fit | W3 | 3 |
| W5 | 修改与自查 | fit | W4 | 2 |

- `prereq_gate=1`（可用门槛）：W1 达 L1 即解锁 W2/W6；`mastery_gate=2`：要声明 W1 已掌握仍需 apply 证据。
- 写作节点**不产生代码**：`artifact` 指向 `artifacts/<name>.md` 的邮件稿；`source=verified` 需文件存在且 sha256 一致。

## 3. 阶段说明

| stage | 进入条件 | 导师 | 学习者产出 | 退出（通过） | 不通过 / 超时 |
| --- | --- | --- | --- | --- | --- |
| explain | 先修全 ≥L1（可用门槛）且本节点 ≤L1 | concept | 用自己的话说出该节点的 2 条规则 + 指出 1 个反例的问题 | 复述通过且 help_level≤1 | ≤4 轮 / 8 分钟；不行写 `prereq_gap` 退回先修 |
| drill | explain 通过 | coach | 2 个微任务（改写 1 句请求、改写 1 段语气） | 连续 2 题在 help_level≤1 下达标 | 降难度（只改一句），最多 2 次；10 分钟超时写 `stage_timeout` |
| apply | drill 通过 | coach | 1 封完整邮件写入 `artifacts/` | rubric ≥7/10 且无 0 分项、help_level≤1 | `help_level≥2` 记 `assisted_completion` 并回 drill |
| check | apply 通过 | examiner | 新场景邮件 + 迁移改写 | 两题都过 rubric 且 help_level=0 | 写 `misconception`（如“结论埋在中段”）；同错因 2 次 → `decayed` |

## 4. 首次诊断

3 题约 5 分钟，可跳过；**只允许置 L0 或 L1**。

| 探针 | 问题要点 | 锚点节点 |
| --- | --- | --- |
| Q1 | 把“Please provide the data today.”改成对上级的请求，保留紧迫感 | W2 |
| Q2 | 给一段 6 句、结论在末句的邮件，指出结构问题并给改法 | W1 |
| Q3 | 项目延期两周，列一封邮件的大纲（3 段以内） | W4 |

- **诊断定位**：若某锚点被探针置 L1、且其全部先修也 ≥L1，直接以 `apply` 起步并写 `placement_applied`；有先修仍为 L0 的节点不参与定位。

## 5. 评价标准（rubric）

| 维度 | 0 分 | 1 分 | 2 分 |
| --- | --- | --- | --- |
| 目的可见 | 读完不知要做什么 | 需要读两遍 | 首段一句说清 |
| 结构 | 无段落逻辑 | 有段落但请求分散 | 结论先行、一段一事 |
| 语气适配 | 冒犯或过度卑微 | 基本得体但生硬 | 与关系和场景匹配 |
| 清晰度 | 长句歧义 | 有 1–2 处模糊指代 | 具体、可执行、有日期 |
| 语言准确性 | 影响理解的错误 | 少量错误不碍理解 | 无明显错误 |

- 通过：总分 ≥7 且无 0 分项；`check` 通过额外要求两题都过且 `help_level=0`。
- 评分必须给证据句：引用原文片段说明扣分原因，禁止只给分数。

## 6. 等级与证据

- L1：能复述规则 + ≥1 次受助完成；L2：独立写出 rubric 达标邮件且有文件；L3：换场景（对内→对外、常规→坏消息）仍达标且 ≥7 天后复测通过。
- 只有 `help_level≤1` 的通过计入升级；单轮最多 +1；重复提交同一稿用幂等键 `sha256(session_id|activity_id|answer)`。
- 导师不得说“写得好／已掌握”，只给证据与下一步。

## 7. 复习

- 间隔 `[1, 3, 7, 16, 35]` 天；20 分钟会话只做 1 个到期节点。
- 复习形式：给 1 个新场景写 80 词以内，或改一段有 3 处问题的旧稿。

## 8. 导师与切换

- explain→concept；drill/apply→coach；check→examiner；诊断/交接/复习→navigator。
- 切换写 `handoff`（from、to、reason、unresolved、context_digest）；examiner 返回 `help_level≥1` 视为违规，本轮作废。

## 9. 运行约束

- 纯文本产出，UTF-8；邮件稿写入 `artifacts/*.md`，会话写入 `sessions/`。
- 不引入编程任务、不要求运行代码；离线模式（`LEARNARK_LLM=mock`）必须标注“离线脚本导师”。

## 10. 内容文件索引

- 导师系统提示：`mentors/navigator.md`、`mentors/concept.md`、`mentors/coach.md`、`mentors/examiner.md`
- 节点种子：`curriculum/email.md`
- 离线脚本：`tests/fixtures/mentor_script.jsonl`
