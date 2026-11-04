# 模板：agent-dev

供 `python learn.py init --goal "…" --template agent-dev` 使用。下方 json 代码块是唯一权威载荷（CLI 取文件中第一个 json 代码块）；其余文字只是说明，不参与解析。技能等级 0–3，卡片 id 由模板固定，运行时据此建 `state/skills.json` 与 `state/cards.json`。

```json
{
  "template_id": "agent-dev",
  "schema_version": 1,
  "goal_default": "能独立设计、实现并评测一个可用的 Agent 应用",
  "minutes_default": 20,
  "minutes_per_week": 600,
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
    {"type": "concept", "aliases": ["concept_block"], "mentor": "coach", "minutes": [10, 12]},
    {"type": "kata", "aliases": ["code_kata"], "mentor": "trainer", "minutes": [12, 18]},
    {"type": "explain-back", "aliases": ["explain_back"], "mentor": "coach", "minutes": [8, 10], "rubric": "explain-back"},
    {"type": "quiz", "aliases": [], "mentor": "examiner", "minutes": [6, 8], "max_items": 3},
    {"type": "project-slice", "aliases": ["transfer_task"], "mentor": "coach", "judge_mentor": "examiner", "minutes": [15, 20]}
  ],
  "skills": [
    {"id": "agent-loop", "title": "Agent 循环与停止条件", "level": 0, "tags": ["core", "loop"]},
    {"id": "tool-contract", "title": "工具契约与参数校验", "level": 0, "tags": ["tool", "schema"]},
    {"id": "tool-calling", "title": "工具调用与容错", "level": 0, "tags": ["tool", "retry"]},
    {"id": "state-memory", "title": "状态与记忆分层", "level": 0, "tags": ["memory"]},
    {"id": "rag-retrieval", "title": "检索与重排", "level": 0, "tags": ["rag", "retrieval"]},
    {"id": "grounding", "title": "依据与引用", "level": 0, "tags": ["grounding"]},
    {"id": "eval-harness", "title": "评测与回归", "level": 0, "tags": ["eval"]},
    {"id": "guardrails", "title": "安全边界与注入防护", "level": 0, "tags": ["security"]},
    {"id": "observability", "title": "可观测性与成本", "level": 0, "tags": ["trace", "cost"]},
    {"id": "deploy-ops", "title": "配置、密钥与交付", "level": 0, "tags": ["ops", "secret"]}
  ],
  "cards": [
    {"id": "card-0001", "skill": "agent-loop", "kind": "recall", "front": "Agent 循环的四个阶段是什么？", "back": "想（计划）→ 做（调用工具）→ 看（观察结果）→ 停（判定是否结束）。", "tags": ["loop", "basics"], "step": 0, "ease": 1.0},
    {"id": "card-0002", "skill": "agent-loop", "kind": "recall", "front": "循环的三种停止条件是什么？", "back": "达成目标、达到轮次上限、连续两次没有新信息。", "tags": ["loop", "stop"], "step": 0, "ease": 1.0},
    {"id": "card-0003", "skill": "tool-contract", "kind": "recall", "front": "工具 schema 至少要写清哪三类信息？", "back": "必填与类型、取值边界、错误返回约定。", "tags": ["tool", "schema"], "step": 0, "ease": 1.0},
    {"id": "card-0004", "skill": "tool-contract", "kind": "misconception", "front": "模型把 top_k 传成字符串「10」，工具该怎么办？", "back": "先校验，返回结构化参数错误；不静默转换，也不执行。", "tags": ["tool", "validation"], "step": 0, "ease": 1.0},
    {"id": "card-0005", "skill": "tool-calling", "kind": "recall", "front": "工具调用超时后，第一步先做什么？", "back": "区分超时与参数错误，再设超时与重试上限，并留一条失败样本。", "tags": ["tool", "retry"], "step": 0, "ease": 1.0},
    {"id": "card-0006", "skill": "state-memory", "kind": "recall", "front": "上下文窗口与长期记忆的区别？", "back": "上下文易失、按 token 计费；长期记忆要持久化、可检索、可更新与删除。", "tags": ["memory"], "step": 0, "ease": 1.0},
    {"id": "card-0007", "skill": "state-memory", "kind": "misconception", "front": "为什么 RAG 不等同于长期记忆？", "back": "RAG 只做单次检索注入；记忆还要求写入、更新、遗忘与跨会话恢复。", "tags": ["memory", "rag"], "step": 0, "ease": 1.0},
    {"id": "card-0008", "skill": "rag-retrieval", "kind": "recall", "front": "检索效果差，先查哪三处？", "back": "切块大小、查询与文档的用词错位、TopK 与重排设置。", "tags": ["rag", "retrieval"], "step": 0, "ease": 1.0},
    {"id": "card-0009", "skill": "grounding", "kind": "recall", "front": "答案没有依据时应该怎么答？", "back": "明确说不知道，并说明缺哪份资料；不得编造引用。", "tags": ["grounding"], "step": 0, "ease": 1.0},
    {"id": "card-0010", "skill": "eval-harness", "kind": "recall", "front": "最小评测集要有哪三样？", "back": "固定用例、可计算指标、可比较基线。", "tags": ["eval"], "step": 0, "ease": 1.0},
    {"id": "card-0011", "skill": "eval-harness", "kind": "misconception", "front": "通过率 100% 可能说明什么？", "back": "用例太简单、答案泄漏，或指标定义过宽。", "tags": ["eval", "pitfall"], "step": 0, "ease": 1.0},
    {"id": "card-0012", "skill": "guardrails", "kind": "recall", "front": "提示注入的第一道防线是什么？", "back": "输入隔离与来源标记；随后是工具白名单与敏感动作人工确认。", "tags": ["security"], "step": 0, "ease": 1.0}
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
    "explain-back": {"items": ["准确", "完整", "因果", "边界"], "pass_min": 3}
  },
  "assessments": [
    {"id": "assess-loop-transfer", "skills": ["agent-loop", "tool-calling"], "activity_type": "project-slice", "minutes": 15, "pass": ["分层排查：参数→权限→数据→网络", "每步有验证方式", "给出停止条件"]},
    {"id": "assess-rag-grounding", "skills": ["rag-retrieval", "grounding"], "activity_type": "project-slice", "minutes": 20, "pass": ["召回 ≥80%", "引用可核", "无依据时明确说不知道"]},
    {"id": "assess-eval-design", "skills": ["eval-harness"], "activity_type": "quiz", "minutes": 10, "pass": ["覆盖正常/边界/失败", "指标可计算", "有基线"]}
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

- `activity_types` 的 `aliases` 兼容 `design.md` 的早期命名（`recall_card` 等）；`project-slice` 含 `transfer_task`，由 examiner 以只判不教模式执行。
- `init` 时卡片 `due_at` 由运行时按 `step 0` 与当天日期写入；`source_event` 置为 `init:template`，不在这里硬编码日期。
- `minutes` 为闭区间；预算不足最小值的活动应被调度器硬过滤，而不是压缩时长。
