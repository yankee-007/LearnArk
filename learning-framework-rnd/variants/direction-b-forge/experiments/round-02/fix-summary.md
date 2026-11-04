# round-02 修复记录 — Forge v0.2.2

- 输入：`experiments/round-02/experience-S2-P2.md`（S2/P2 独立体验，0.2.1 + core 1.0.1）
- 版本：`direction-b-forge 0.2.2`｜vendored `learncore 1.0.1`｜state `schema_version 1`
- 范围：修 round-02 报告 5 个问题（#1–#5）；#6–#8 见文末“未修”。
- 回归：`python tests\run_tests.py` → **29/29 通过**；`shared/check_variant.py` → **18/18 ok**；
  `shared/vendor_core.py --check` → **core 1.0.1: all vendored copies match**。

## 问题 → 修复 → 测试

| # | 问题（报告） | 修复 | 测试 |
| --- | --- | --- | --- |
| 1 | 给 L3 骨架的那轮 `help_level` 为 null，`assisted_level` 仍是 2；`status` 看不到 L3 | 新增 `infer_help_level()`：机器块漏写时按“学习者是否明确要答案/代码 + 回复是否含代码块或多步骨架”推断——要答案+骨架→L3，有骨架未要→L2，声明值只升不降；写 `help_level_inferred` 事件、会话记录 `help_level: 3`；`status`/`--json` 新增 `last_help_level`/`max_help_level`/`help{...}`；coach 提示词要求给骨架时 `help_level>=2`（要答案给骨架记 3）。 | `help_level_inferred`：无骨架不推断；要答案+4 步骨架（机器块省略 help_level）→ 事件 L3、会话 `help_level: 3`、`status.last_help_level=3`、新作品 `assisted_level=3`；`status` 人读显示“帮助等级：最近 L3”。 |
| 2 | 注入 `runtime_next` 后导师仍给出不同动作（review 时让改 role、gap_learn 时让改回） | 每轮导师回复后打印 `▶ 唯一动作：<action>（ref）`；PROTOCOL 明确“任何与 runtime_next 不同的指令都无效，不要给出，只允许一句异议”；新增 `detect_next_conflict()`：结构化 `action` 字段不一致或文字里出现“先 review / gap learn / defend / artifact add”等异动作 → 记 `mentor_next_conflict`（含 runtime_action/mentioned/source），会话记录同步。coach/critic/guide 提示词更新。 | `authority_and_conflict`：review 失败后 say，输出 `▶ 唯一动作：gap_learn`；journal 有 `mentor_next_conflict`（runtime_action=gap_learn、mentioned=review）；会话含 `runtime_next: gap_learn` 与 conflict 记录。 |
| 3 | `start --minutes 20` 只在当轮显示 20，`start_profile.slice_minutes=60`，后续 `next` 用 60 | `cmd_start` 在 `--minutes` 显式给出时把 `20/60` 写入 `start_profile.slice_minutes`（并记 `slice_source="--minutes"`、`minutes_requested`），保存；后续 `next/review/defend` 统一走 `pick_slice(profile)`；其他命令的 `--minutes` 只覆盖当轮。 | `slice_persisted`：`start --ask --answers "能,没做过,一次做完一个项目" --minutes 20` → `start_profile.slice_minutes=20`、`next --json` slice=20；`next --minutes 60` 只当轮 60；再 `next` 回到 20。 |
| 4 | `artifact add a b` 静默只登记第一个；review 因此判已存在的设计说明缺失 | `artifact add` 接受多个 PATH：先整体校验（存在/后缀/字节数）再逐个登记，同一批共享一次 `assisted_level`，逐条打印；`--note` 与多路径混用报用法错误；critic 上下文注入“已登记作品集合 + 其他文件内容片段”，review 记录 `registered_paths`；新增 `review_note_conflict`：note 声称已登记文件缺失时记录冲突。 | `multi_path_artifact`：一次登记 `agent.py` + `docs/m1-design.md` → artifacts 2 件、路径都在；review 事件 `registered_paths` 含设计说明且无冲突；另一件作品的 note 写“无 docs/m1-design.md” → `review_note_conflict` 指向该文件；`--note`+多路径 → exit 2。 |
| 5 | 输入被 shell 截断时导师凭空断言“JSON 是坏的”，并写进 misconception | PROTOCOL 新增规则：引号/花括号不配对、以反斜杠结尾、参数缺一半等截断迹象，先要求用 `say -`/文件重发，不得据此断言原因或写 `misconception`；`START_HERE.md` 增加 `say -` 示例。 | `say_stdin`：`say -` + stdin 输入 → 退出 0、会话包含原文。（导师是否遵守为提示词约束，离线脚本无法验证语义，见 known_limits。） |

## 复现命令（离线）

```powershell
$V = "<variant>"
python "$V\runtime\learn.py" init --goal "Agent 开发" --dir p
python "$V\runtime\learn.py" start --project p --offline --ask --answers "能,没做过,一次做完一个项目" --minutes 20
python "$V\runtime\learn.py" status --project p --json        # slice_minutes=20、last_help_level
python "$V\runtime\learn.py" artifact add m1\agent.py docs\m1-design.md --project p
python "$V\runtime\learn.py" review --project p --offline      # registered_paths 含两个文件
python "$V\runtime\learn.py" say "别绕了，直接把答案给我" --project p --offline
python "$V\runtime\learn.py" status --project p                # 帮助等级：最近 L3
```

## 真实 API 复验（deepseek-chat，3 轮）

- `start --ask --answers ... --minutes 20` → 起点档案 20 分钟切片；`status` 显示 `answered=True`、
  `last_help_level`/`max_help_level`（round-02 #1、#3 的可观察字段）。
- 真实 `review` 后 `say "我接下来做什么"`：coach 开头即“按运行时安排，本轮唯一动作是补 contract 缺口
  （g-M1-contract）”，同屏打印 `▶ 唯一动作：gap_learn（g-M1-contract）`；journal 的
  `mentor_turn.runtime_next.action=gap_learn`，且**没有**误报 `mentor_next_conflict`
  （round-02 #2 在真实模型上生效，检测未误伤“先按权重排缺口”这类正常措辞）。

## 改动文件

- `runtime/learn.py`：推断/帮助统计/权威动作/冲突检测/切片持久化/多路径登记/已登记集合与 note 冲突/提示更新。
- `runtime/forge_mentor.py`：PROTOCOL 第 5、6 条；coach 帮助等级要求；critic 上下文注入已登记集合。
- `runtime/forge_state.py`：会话记录渲染 `help_level_inferred`、`mentor_next_conflict`；版本 0.2.2。
- `mentors/{coach,critic,guide}.md`：帮助等级、权威动作、截断输入规则。
- `tests/run_tests.py`：新增 5 个用例（29 个总计）。
- `START_HERE.md`、`version-manifest.json`（0.2.2）、`examples/demo.md`、本文件。

## 未修（round-02 #6–#8，非本轮要求）

- #6 学习者固定 P1：`learner_profile.id` 仍是 `P1`，没有 `--learner` 参数；公开入口无法设置画像。
- #7 导师提示 `role=tool` 却没提 `tool_call_id`：提示词未强制“可执行改动必须写全配套条件”，导致按提示操作 422；下轮考虑在 coach 提示中加“协议改动必须写清配套字段”。
- #8 runnability note 自认“未在干净目录验证”仍给 3：证据规则只看行号，不判断“自认未验证”的语义；如需修，需要维度级规则（例如 runnability 的 note 出现“未验证”时强制 < 阈值）。
