# 模板：email

供 `python learn.py init --goal "…" --template email` 使用。下方 json 代码块是唯一权威载荷（CLI 取文件中第一个 json 代码块），其余为说明。本模板不含任何编程内容：活动是英文邮件写作的微技能操练，`kata` 在此表示短写作练习。

```json
{
  "template_id": "email",
  "schema_version": 1,
  "goal_default": "能写出清晰、得体、可执行的英文工作邮件",
  "minutes_default": 15,
  "minutes_per_week": 180,
  "mentors": ["coach", "trainer", "examiner"],
  "limits": {
    "min_activity_minutes": 5,
    "max_activity_minutes": 20,
    "close_out_reserve_minutes": 2,
    "max_items_per_session": 2,
    "due_cards_per_session": 3,
    "backlog_cap": 12
  },
  "activity_types": [
    {"type": "recall", "aliases": ["recall_card"], "mentor": "trainer", "minutes": [5, 6], "max_items": 3},
    {"type": "concept", "aliases": ["concept_block"], "mentor": "coach", "minutes": [8, 10]},
    {"type": "kata", "aliases": [], "label": "写作操练", "mentor": "trainer", "minutes": [12, 18]},
    {"type": "explain-back", "aliases": ["explain_back"], "mentor": "coach", "minutes": [8, 10], "rubric": "explain-back"},
    {"type": "quiz", "aliases": [], "mentor": "examiner", "minutes": [6, 8], "max_items": 3},
    {"type": "project-slice", "aliases": ["transfer_task"], "label": "整封邮件", "mentor": "coach", "judge_mentor": "examiner", "minutes": [15, 20], "rubric": "email"}
  ],
  "skills": [
    {"id": "subject-line", "title": "主题行", "level": 0, "tags": ["subject"]},
    {"id": "opening-purpose", "title": "首句与目的", "level": 0, "tags": ["opening"]},
    {"id": "ask-clarity", "title": "请求与行动项", "level": 0, "tags": ["request"]},
    {"id": "structure-clarity", "title": "结构与简洁", "level": 0, "tags": ["structure"]},
    {"id": "tone-register", "title": "语气与拒绝", "level": 0, "tags": ["tone"]},
    {"id": "language-accuracy", "title": "语言准确", "level": 0, "tags": ["language"]}
  ],
  "cards": [
    {"id": "card-e001", "skill": "subject-line", "kind": "recall", "front": "英文邮件主题行应包含哪些信息？", "back": "动作 + 对象 + 期限（如有），控制在 8 个词以内。", "tags": ["subject"], "step": 0, "ease": 1.0},
    {"id": "card-e002", "skill": "opening-purpose", "kind": "recall", "front": "邮件第一句应该写什么？", "back": "直接说明目的与需要的动作，不先寒暄。", "tags": ["opening"], "step": 0, "ease": 1.0},
    {"id": "card-e003", "skill": "ask-clarity", "kind": "recall", "front": "一封邮件最多放几个主请求？", "back": "一个；其余放列表，或拆到下一封。", "tags": ["request"], "step": 0, "ease": 1.0},
    {"id": "card-e004", "skill": "structure-clarity", "kind": "recall", "front": "长邮件如何压缩？", "back": "结论先行，一段一个意思，行动项单列。", "tags": ["structure"], "step": 0, "ease": 1.0},
    {"id": "card-e005", "skill": "tone-register", "kind": "misconception", "front": "拒绝请求时只写「I can't」为什么不好？", "back": "缺少理解与替代方案；应致谢、明确拒绝、给替代时间或人选。", "tags": ["tone"], "step": 0, "ease": 1.0},
    {"id": "card-e006", "skill": "language-accuracy", "kind": "misconception", "front": "为什么少用「Please kindly」？", "back": "冗余且中式；直接用 Could you 或 Please + 具体动作。", "tags": ["language"], "step": 0, "ease": 1.0}
  ],
  "review": {
    "grades": ["again", "hard", "good", "easy"],
    "ladder_days": [1, 2, 4, 8, 15, 30, 60],
    "ease_default": 1.0,
    "ease_range": [0.85, 1.6],
    "grade_policy": {
      "again": {"step_delta": -2, "ease_delta": -0.2, "due": "next_day"},
      "hard": {"step_delta": 0, "ease_delta": -0.05, "due": "half_interval"},
      "good": {"step_delta": 1, "ease_delta": 0.15, "due": "interval"},
      "easy": {"step_delta": 2, "ease_delta": 0.15, "due": "interval"}
    }
  },
  "rubrics": {
    "email": {
      "dimensions": [
        {"id": "purpose", "title": "目的与行动项", "levels": ["未说明目的", "目的模糊或行动项缺失", "目的清楚，行动项基本可执行", "目的与行动项清楚，含责任人与时间"]},
        {"id": "structure", "title": "结构与简洁", "levels": ["无结构或超长", "段落混乱", "结论先行，段落基本清楚", "结论先行，一段一意，行动项单列"]},
        {"id": "tone", "title": "语气与得体", "levels": ["生硬或过度卑微", "语气不稳", "礼貌且直接", "礼貌、直接，拒绝时给替代方案"]},
        {"id": "language", "title": "语言准确", "levels": ["多处错误影响理解", "有错误但可读", "少量错误", "准确自然，无中式表达"]}
      ],
      "max_score": 12,
      "pass_score": 9
    },
    "explain-back": {"items": ["准确", "完整", "因果", "边界"], "pass_min": 3}
  },
  "assessments": [
    {"id": "assess-email-request", "skills": ["subject-line", "ask-clarity"], "activity_type": "project-slice", "minutes": 15, "pass": ["主题含动作与期限", "首句说明目的", "只有一个主请求", "结尾行动项明确"]},
    {"id": "assess-email-refusal", "skills": ["tone-register", "language-accuracy"], "activity_type": "kata", "minutes": 15, "pass": ["致谢或理解对方处境", "明确拒绝", "给两个替代时间或人选", "语气不含糊"]}
  ],
  "mentor_update": {
    "required": ["help_level", "attempt", "next"],
    "extensions": ["card", "skill_signal"],
    "help_level_range": [0, 3],
    "card_max_per_turn": 3,
    "skill_signal_max_per_turn": 1
  }
}
```

说明：

- `kata` 在 email 模板里是 12–18 分钟的短写作练习（写一封 3–5 句邮件），不是编程任务。
- 评分只用 `rubrics.email` 的四个维度；单维 0–3 分，总分 9 分及以上通过，未过只补最低的一维。
- 卡片以句式与错误预防为主；不复用 agent-dev 的任何 id 或标签。
