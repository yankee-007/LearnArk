# 模板：英文工作邮件（Forge）

本文件是 `learn.py init --template email` 的唯一内容来源。下方 `json template` 块为机器可读定义（权威）；其后的中文小节是同一份定义的说明，供人阅读，CLI 不解析。

```json template
{
  "template_id": "email",
  "schema_version": 1,
  "display_name": "英文工作邮件",
  "goal_default": "能为不同工作场景写出清楚、得体、对方愿意回的英文邮件，并说清自己的修改理由",
  "minutes_per_week_default": 6,
  "session_minutes_default": 25,
  "mentors": {"default": "coach", "review": "critic", "gap": "guide"},
  "constraints": ["英文正稿 120–200 词", "修改说明用中文", "不排课程，作品驱动"],
  "artifact_dir": "artifacts/email",
  "score_range": [1, 4],
  "help_levels": {
    "0": "独立完成",
    "1": "小提示",
    "2": "分步引导",
    "3": "基本代做：只记受助完成"
  },
  "milestones": [
    {
      "id": "E1",
      "title": "道歉与补救",
      "deliverable": "artifacts/email/e1-apology.md",
      "activity_id": "e1-artifact-review",
      "gate": {"requires_artifact": true, "requires_review": true, "requires_defense": true},
      "rubric": [
        {"dim": "structure", "criteria": "主题句在前，一段一件事，明确的行动请求与新的截止时间", "weight": 25, "threshold": 3},
        {"dim": "tone", "criteria": "承认责任不辩解，不过度自责，语气与客户关系匹配", "weight": 25, "threshold": 3},
        {"dim": "clarity", "criteria": "句子短、指代明确、无「ASAP/尽快」这类无法执行的表述", "weight": 20, "threshold": 3},
        {"dim": "scenario_fit", "criteria": "延期原因、补救措施、新时间与该客户场景一致", "weight": 30, "threshold": 3}
      ],
      "defense_questions": [
        {"qid": "e1-q1", "dim": "scenario_fit", "question": "如果延期是你们自己的排期失误，第一句你会怎么改？"},
        {"qid": "e1-q2", "dim": "tone", "question": "客户回复「不能接受」时，这封信留了什么余地？"},
        {"qid": "e1-q3", "dim": "structure", "question": "新时间放在哪一段，为什么不放开头？"}
      ]
    },
    {
      "id": "E2",
      "title": "跨部门请求",
      "deliverable": "artifacts/email/e2-request.md",
      "activity_id": "e2-artifact-review",
      "gate": {"requires_artifact": true, "requires_review": true, "requires_defense": true},
      "rubric": [
        {"dim": "structure", "criteria": "目的、范围、截止时间、下一步四件事齐全", "weight": 25, "threshold": 3},
        {"dim": "tone", "criteria": "请求而非命令，尊重对方排期，不过度道歉", "weight": 25, "threshold": 3},
        {"dim": "clarity", "criteria": "字段或选项可直接勾选，对方无需追问", "weight": 20, "threshold": 3},
        {"dim": "scenario_fit", "criteria": "称谓、术语、时区与内部协作惯例正确", "weight": 30, "threshold": 3}
      ],
      "defense_questions": [
        {"qid": "e2-q1", "dim": "scenario_fit", "question": "对方比你高两级，哪一句要改？"},
        {"qid": "e2-q2", "dim": "tone", "question": "为什么要给「先给前五列也可以」这个退让选项？"},
        {"qid": "e2-q3", "dim": "clarity", "question": "如果对方只回一个「好」，你能不能据此开工？"}
      ]
    },
    {
      "id": "E3",
      "title": "拒绝并保住关系 + 作品集收尾",
      "deliverable": "artifacts/email/e3-refusal.md + artifacts/email/portfolio.md",
      "activity_id": "e3-artifact-review",
      "gate": {"requires_artifact": true, "requires_review": true, "requires_defense": true},
      "rubric": [
        {"dim": "structure", "criteria": "理解、边界、替代方案三段清楚，结尾给出可执行下一步", "weight": 25, "threshold": 3},
        {"dim": "tone", "criteria": "坚定但不攻击，保留未来合作空间", "weight": 25, "threshold": 3},
        {"dim": "clarity", "criteria": "拒绝的理由具体，不含模糊承诺", "weight": 20, "threshold": 3},
        {"dim": "scenario_fit", "criteria": "三封齐全，修改说明讲清第一稿问题与改动依据", "weight": 30, "threshold": 3}
      ],
      "defense_questions": [
        {"qid": "e3-q1", "dim": "scenario_fit", "question": "供应商说「不涨价就停止供货」，这封信还成立吗？"},
        {"qid": "e3-q2", "dim": "tone", "question": "把「我们不能接受」改成「我们很难接受」，效果差在哪？"},
        {"qid": "e3-q3", "dim": "structure", "question": "三封里你最没把握的是哪封，为什么？"}
      ]
    }
  ],
  "pass_rule": "all_dims_at_or_above_threshold_and_defense_passed",
  "defense_rules": {
    "questions_per_milestone": 3,
    "min_ok": 2,
    "heaviest_dim_must_pass": true,
    "evidence": "answer 必须引用作品段落或行号 evidence_line",
    "pending": "三问 answer 全为 null 视为待作答，不算失败也不落 passed",
    "decided_by": "runtime"
  },
  "gap_rules": {
    "created_by": ["critic"],
    "trigger": "dim.score < dim.threshold",
    "id_format": "g-{milestone}-{dim}",
    "upsert_key": "dim",
    "max_open": 4,
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

`init --template email` 未给 `--goal` 时写 `goal_default`，每周时长默认 6 小时（写作任务比编程短）。这两个默认值写入 `project.json` 后不再被模板覆盖，学习者用 `init --goal` 覆盖时以显式参数为准。

## 里程碑与 Rubric

三个里程碑 id 为 `E1`/`E2`/`E3`，对应三封邮件；`E3` 同时要求 `portfolio.md`（三封合集 + 300 字修改说明），因此 E3 的 `scenario_fit` 覆盖作品集完整性。dim 名固定为 `structure`/`tone`/`clarity`/`scenario_fit`，与 `agent-dev` 模板完全隔离，不共用缺口卡命名空间（`g-E1-*` 与 `g-M1-*` 不会冲突）。

## 缺口卡规则

- 规则与编程模板一致：仅 critic 评审且 `score < threshold` 时建卡，id 为 `g-{milestone}-{dim}`，同 dim 只更新 note。
- `max_open` 为 4；超出时保留权重高的卡。
- 写作类缺口允许一张卡覆盖多封邮件（同 dim 跨 E1–E3 聚合），合并时 note 用分号列出具体邮件与段落。
- 关闭只能由运行时在后续评审确认同 dim 达阈值时执行（唯一算「已解决」）；微课 + `help_level <= 1` 的微练习只标「未在作品复验」，不算解决；guide 只推进到 `learning`。
- 三条关闭路径与编程模板一致：复评达标 / 微练习标记未复验 / 连续三次重开才允许 drop 记 `stale`（该 dim 后续权重乘 0.6 衰减，`doctor` 必须列出）。
- `gap drop` 只记 `stale`，不算解决，`doctor` 必须列出；`scenario_fit` 若 note 只写「场景不合适」而没指出具体邮件与段落，同样视为证据不足。

## 通过判定

运行时判定，导师不写：作品已登记且 sha256 未重复计分；四维全部 `score >= threshold`；`defense` 三问至少两问 `ok`，且权重最大的 `scenario_fit` 那一问必须 `ok`（学习者能说清改哪一句、为什么）。三封邮件未齐时 E3 不能候选通过；导师只提交问答与证据行，不写 passed。
