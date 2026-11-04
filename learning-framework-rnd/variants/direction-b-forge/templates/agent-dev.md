# 模板：Agent 开发（Forge）

本文件是 `learn.py init --template agent-dev` 的唯一内容来源。下方 `json template` 块为机器可读定义（权威）；其后的中文小节是同一份定义的说明，供人阅读，CLI 不解析。

```json template
{
  "template_id": "agent-dev",
  "schema_version": 1,
  "display_name": "Agent 开发",
  "goal_default": "能独立做出并解释一个可用的 Agent 作品",
  "minutes_per_week_default": 12,
  "session_minutes_default": 25,
  "mentors": {"default": "coach", "review": "critic", "gap": "guide"},
  "constraints": ["Python 3.10+ 标准库", "DeepSeek API（OpenAI 兼容）", "不使用第三方 Agent 框架"],
  "artifact_dir": "artifacts",
  "score_range": [1, 4],
  "help_levels": {
    "0": "独立完成",
    "1": "小提示",
    "2": "分步引导",
    "3": "基本代做：只记受助完成"
  },
  "milestones": [
    {
      "id": "M1",
      "title": "工具调用闭环",
      "deliverable": "m1/agent.py + docs/m1-design.md",
      "activity_id": "m1-artifact-review",
      "gate": {"requires_artifact": true, "requires_review": true, "requires_defense": true},
      "rubric": [
        {"dim": "runnability", "criteria": "干净目录一条命令跑通真实输入，有可观察输出", "weight": 30, "threshold": 3},
        {"dim": "contract", "criteria": "工具定义与解析一致，参数有类型校验，非法输入返回结构化错误", "weight": 30, "threshold": 3},
        {"dim": "robustness", "criteria": "缺文件、空文件、非数字不崩溃，至少改道或重试一次，步数有硬上限", "weight": 20, "threshold": 3},
        {"dim": "explainability", "criteria": "设计说明讲清工具为何这样切、结果如何回填、上限为何是 6", "weight": 20, "threshold": 2}
      ],
      "defense_questions": [
        {"qid": "m1-q1", "dim": "contract", "question": "如果模型不支持 tool_calls，你的循环怎么改？"},
        {"qid": "m1-q2", "dim": "runnability", "question": "把输入文件换成一个不存在的路径，现在这版会发生什么？"},
        {"qid": "m1-q3", "dim": "explainability", "question": "为什么步数上限是 6 而不是无限循环？"}
      ]
    },
    {
      "id": "M2",
      "title": "记忆与恢复",
      "deliverable": "m2/agent.py + m2/state/session.json + docs/m2-design.md",
      "activity_id": "m2-artifact-review",
      "gate": {"requires_artifact": true, "requires_review": true, "requires_defense": true},
      "rubric": [
        {"dim": "runnability", "criteria": "中断后 --resume 能继续原任务，摘要不丢关键约束", "weight": 25, "threshold": 3},
        {"dim": "contract", "criteria": "状态文件字段固定且带 version，读到旧版本能拒绝或迁移", "weight": 25, "threshold": 3},
        {"dim": "robustness", "criteria": "状态 JSON 损坏可回退，重试不重复写文件，并发写被拒绝", "weight": 30, "threshold": 3},
        {"dim": "explainability", "criteria": "说明摘要触发条件、状态切分理由与副作用幂等做法", "weight": 20, "threshold": 2}
      ],
      "defense_questions": [
        {"qid": "m2-q1", "dim": "robustness", "question": "两个进程同时写 state.json 会坏在哪里？"},
        {"qid": "m2-q2", "dim": "explainability", "question": "为什么用滚动摘要而不是全量历史？"},
        {"qid": "m2-q3", "dim": "contract", "question": "读到旧 version 的状态文件，你选择拒绝还是迁移，依据是什么？"}
      ]
    },
    {
      "id": "M3",
      "title": "可评测的 Agent 作品集",
      "deliverable": "m3/ + eval/tasks.jsonl + logs/trajectories.jsonl + REPORT.md + 讲解稿",
      "activity_id": "m3-artifact-review",
      "gate": {"requires_artifact": true, "requires_review": true, "requires_defense": true},
      "rubric": [
        {"dim": "runnability", "criteria": "评测一条命令重跑，结果与报告一致", "weight": 20, "threshold": 3},
        {"dim": "contract", "criteria": "用例格式统一，判定条件可程序化，轨迹字段完整", "weight": 20, "threshold": 3},
        {"dim": "robustness", "criteria": "含失败与边界样例，崩溃记录为失败而不是中断", "weight": 25, "threshold": 3},
        {"dim": "explainability", "criteria": "报告有失败分类与改进假设，能讲清一次真实取舍", "weight": 35, "threshold": 3}
      ],
      "defense_questions": [
        {"qid": "m3-q1", "dim": "explainability", "question": "评测集有没有偏向你会做的题？怎么证明？"},
        {"qid": "m3-q2", "dim": "contract", "question": "失败样例由谁判定通过或不通过，条件能不能程序化？"},
        {"qid": "m3-q3", "dim": "robustness", "question": "成功率提到九成但成本翻倍，你接受吗，依据是什么？"}
      ]
    }
  ],
  "pass_rule": "all_dims_at_or_above_threshold_and_defense_passed",
  "defense_rules": {
    "questions_per_milestone": 3,
    "min_ok": 2,
    "heaviest_dim_must_pass": true,
    "evidence": "answer 必须引用作品行号 evidence_line",
    "pending": "三问 answer 全为 null 视为待作答，不算失败也不落 passed",
    "decided_by": "runtime"
  },
  "gap_rules": {
    "created_by": ["critic"],
    "trigger": "dim.score < dim.threshold",
    "extra_trigger": "explainability 达标但 note 无行号证据",
    "id_format": "g-{milestone}-{dim}",
    "upsert_key": "dim",
    "max_open": 5,
    "overflow_keep": "weight_desc",
    "sort": ["weight_desc", "threshold_minus_score_desc", "milestone_asc"],
    "statuses": ["open", "learning", "closed", "stale"],
    "learn_transition": "gap learn 后 open -> learning",
    "stale_transition": "gap drop 后 open -> stale，不算解决，doctor 必列",
    "close_paths": {
      "resolved": "later_review_same_dim_meets_threshold",
      "unverified": "micro_practice_help_level_le_1",
      "dropped": "gap_drop_after_3_stale_attempts"
    },
    "decay": {"reopen_after_stale": 0.6},
    "close_rule": "later_review_same_dim_meets_threshold",
    "closed_by": "runtime"
  }
}
```

## 目标默认值

`init` 未给 `--goal` 时写 `goal_default`；`--minutes-per-week` 未给时写 `minutes_per_week_default`。两者写入 `project.json` 后不再被模板覆盖。

## 里程碑与 Rubric

三个里程碑 id 固定为 `M1`/`M2`/`M3`，顺序即状态机顺序。每个里程碑四维，dim 名跨里程碑稳定（`runnability`/`contract`/`robustness`/`explainability`），便于缺口卡跨轮聚合；`weight` 之和为 100，`threshold` 为 1–4 分的整数下限。`init` 时把 `milestones` 原样写入 `.learnark/state/brief.json`，`status` 置 `pending`，`current_milestone` 置 `M1`。

## 缺口卡规则

- 只有 critic 的评审能创建缺口：某维 `score < threshold` 时生成对应卡；同 dim 已存在 open/learning 卡时更新 note，不新建。
- id 由 `g-{milestone}-{dim}` 确定性生成，重复评审同一维度不产生新 id。
- 排序：`weight` 降序，同权重按 `score` 升序；`max_open` 超出时保留权重高的卡，其余挂起而非删除。
- 关闭只能由运行时在后续评审中确认同 dim 达到阈值时执行；guide 的 `gap learn` 只把状态推进到 `learning`，导师不得自行关闭。
- 例外：`explainability` 即使 `score >= threshold`，若 note 拿不到行号级证据，也开一张卡（证据不足不等于通过）。`gap drop` 只把状态记为 `stale`，不算解决，`doctor` 必须列出。
- 三条关闭路径：(a) 后续复评同 dim ≥ 阈值 → `closed`，唯一算「已解决」；(b) 微课 + 微练习且 `help_level <= 1` → 标「未在作品复验」，只降优先级；(c) 连续三次重开仍不过才允许 `gap drop` → `stale`，该 dim 后续排序权重乘 0.6（每次累积）。

## 通过判定

运行时判定，导师不写。三条件同时满足才是候选通过：作品已登记（同 sha256 不重复计分）；四维全部 `score >= threshold`；`defense` 三问中至少两问 `ok`，且权重最大维度那一问必须 `ok`。缺任一条，`next` 由缺口排序或防御性提问决定。导师的 `defense` 只提交问答与 `evidence_line`，通过与否由运行时计算。
