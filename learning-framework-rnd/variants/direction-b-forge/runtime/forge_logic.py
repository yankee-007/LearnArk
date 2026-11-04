"""Forge 纯逻辑：rubric 判定、缺口排序、防御校验、下一步调度。

这里没有 IO，也没有导师调用：同样的状态一定算出同样的 ``next``（design §7），
LLM 的提议只有在 :mod:`forge_mentor` 校验通过后才会变成这里的输入。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from forge_state import NARRATIVE_DIMS, now_iso

MIN_ANSWER_CHARS = 10
GENERIC_ANSWER = re.compile(
    r"^(我(已经|都)?(理解|明白|懂|知道|会)了?(这个|整个|全部)?(设计|代码|整体)?[。.!！~～]*"
    r"|同上|就是那样|没问题|不知道|不会)$"
)


# --------------------------------------------------------------------------- #
# 里程碑 / 作品 / 评审 / 防御
# --------------------------------------------------------------------------- #
def milestone_index(brief: dict, mid: str | None) -> int:
    for index, item in enumerate(brief.get("milestones", [])):
        if item.get("id") == mid:
            return index
    return -1


def get_milestone(brief: dict, mid: str | None = None) -> dict | None:
    target = mid or brief.get("current_milestone")
    for item in brief.get("milestones", []):
        if item.get("id") == target:
            return item
    return None


def next_milestone(brief: dict, mid: str | None = None) -> dict | None:
    index = milestone_index(brief, mid or brief.get("current_milestone"))
    items = brief.get("milestones", [])
    if 0 <= index < len(items) - 1:
        return items[index + 1]
    return None


def rubric_by_dim(milestone: dict | None) -> dict[str, dict]:
    return {d["dim"]: d for d in (milestone or {}).get("rubric", [])}


def heaviest_dims(milestone: dict) -> list[str]:
    rubric = milestone.get("rubric", [])
    if not rubric:
        return []
    top = max(int(d["weight"]) for d in rubric)
    return [d["dim"] for d in rubric if int(d["weight"]) == top]


def artifacts_for(artifacts: dict, mid: str) -> list[dict]:
    return [a for a in artifacts.get("items", []) if a.get("milestone") == mid]


def latest_artifact(artifacts: dict, mid: str) -> dict | None:
    items = artifacts_for(artifacts, mid)
    return items[-1] if items else None


def review_for_artifact(reviews: dict, artifact_id: str) -> dict | None:
    """Latest review that covers this artifact (a review may cover several files)."""
    for item in reversed(reviews.get("items", [])):
        if item.get("artifact_id") == artifact_id:
            return item
        if artifact_id in (item.get("artifact_ids") or []):
            return item
    return None


def latest_review_for_milestone(reviews: dict, mid: str) -> dict | None:
    items = [r for r in reviews.get("items", []) if r.get("milestone") == mid]
    return items[-1] if items else None


def defense_for_artifact(defense: dict, artifact_id: str) -> dict | None:
    items = [d for d in defense.get("items", []) if d.get("artifact_id") == artifact_id]
    return items[-1] if items else None


def defense_for_milestone(defense: dict, mid: str) -> dict | None:
    items = [d for d in defense.get("items", []) if d.get("milestone") == mid]
    return items[-1] if items else None


def gap_items(gaps: dict) -> list[dict]:
    return gaps.get("items", [])


def gap_by_id(gaps: dict, gap_id: str) -> dict | None:
    for item in gap_items(gaps):
        if item.get("gap_id") == gap_id:
            return item
    return None


def open_gaps(gaps: dict, mid: str | None = None) -> list[dict]:
    return [
        g
        for g in gap_items(gaps)
        if g.get("status") in ("open", "learning") and (mid is None or g.get("milestone") == mid)
    ]


def effective_weight(gap: dict) -> float:
    """stale 过的维度后续排序权重乘 0.6（每次累积）。"""
    return round(float(gap.get("weight", 0)) * (0.6 ** int(gap.get("stale_drops", 0) or 0)), 2)


def gap_sort_key(gap: dict, order: dict[str, int]) -> tuple:
    # weight 降序 -> (threshold - score) 降序 -> 里程碑升序 -> 未复验靠后 -> dim
    return (
        -effective_weight(gap),
        -(int(gap.get("threshold", 0)) - int(gap.get("score", 0))),
        order.get(str(gap.get("milestone")), 99),
        1 if gap.get("unverified") else 0,
        str(gap.get("dim")),
    )


def order_gaps(gaps: dict, brief: dict, *, mid: str | None = None, include_closed: bool = False) -> list[dict]:
    order = {m["id"]: i for i, m in enumerate(brief.get("milestones", []))}
    items = list(gap_items(gaps))
    if mid is not None:
        items = [g for g in items if g.get("milestone") == mid]
    if not include_closed:
        items = [g for g in items if g.get("status") in ("open", "learning")]
    status_rank = {"open": 0, "learning": 0, "unverified": 1, "stale": 2, "closed": 3}
    items.sort(key=lambda g: (status_rank.get(str(g.get("status")), 9), *gap_sort_key(g, order)))
    return items


# --------------------------------------------------------------------------- #
# 切片 / 固定开场任务（round-05 #1）
# --------------------------------------------------------------------------- #
CODE_SUFFIXES = {".py", ".js", ".ts", ".go", ".java", ".sh", ".rb", ".rs", ".sql"}

EMAIL_OPENING = {
    ("E1", 20): (
        "写第一封英文道歉邮件的初稿：≤120 词；第一句说清为什么道歉，中间给补救措施和新的具体日期/时间，"
        "最后一句写你请对方做什么。今天只写这一封，不写修改说明。"
    ),
    ("E1", 60): (
        "写一封 ≤120 词的英文道歉邮件（原因、补救、新时间、明确请求），再写 3 句中文修改说明："
        "第一稿的问题、改了哪几处、凭什么判断对方更愿意回。"
    ),
    ("E2", 20): (
        "写一封 ≤120 词的英文跨部门请求邮件：目的、需要的字段/范围、截止时间、下一步各一处；"
        "给对方一个更小的退让选项。"
    ),
    ("E3", 20): (
        "写一封 ≤120 词的英文拒绝邮件：先理解对方处境，再给边界和理由，最后给一个可接受的替代方案。"
    ),
}

CODING_OPENING = {
    ("M1", 20): (
        "新建 m1/agent.py：读 m1/in.txt 里的一行算式（如 3+4），用你自己定义的一个本地工具函数算出结果并打印。"
        "今天先不接真实模型，也不做失败场景。"
    ),
    ("M1", 60): (
        "新建 m1/agent.py：读 in.txt 的算式，走一次「工具定义→解析→执行→回填」的最小闭环并打印；"
        "再补一个非法输入的可读错误。先不接真实模型。"
    ),
    ("M2", 20): (
        "在 m2/agent.py 先做最小状态文件：一次工具调用后原子写 m2/state/session.json，再用 --resume 读回继续。"
    ),
}


def pick_slice(brief: dict, minutes: int | None = None) -> tuple[int, str]:
    profile = brief.get("start_profile") or {}
    default = int(profile.get("slice_minutes") or brief.get("session_minutes_default") or 25)
    chosen = int(minutes) if minutes is not None else default
    if brief.get("template") == "email":
        if chosen <= 30:
            return (
                20,
                "20 分钟切片：写一封 ≤120 词的邮件 + 一次结构化修改（删模糊词、补明确截止），不写长文",
            )
        return (
            60,
            "60 分钟切片：一封完整邮件 + 一次自评/修改说明，然后再复评一次",
        )
    if chosen <= 30:
        return (
            20,
            "20 分钟切片：只做能跑的最小版本——一条真实输入 + 一次运行 + 打印结果；失败场景留到下次",
        )
    return (
        60,
        "60 分钟切片：最小可运行版本 + 一个失败场景 + 一页设计说明；结束前登记并评审一次",
    )


def opening_task(brief: dict, milestone: dict | None, minutes: int | None = None) -> dict:
    """Deterministic opening task: template + milestone + slice (+ profile) -> same id/text."""
    milestone = milestone or get_milestone(brief)
    mid = (milestone or {}).get("id", "?")
    slice_minutes, slice_hint = pick_slice(brief, minutes)
    template = brief.get("template", "agent-dev")
    profile = brief.get("start_profile") or {}
    profile_key = f"{profile.get('mapped_start', '')}|{profile.get('strictness', '')}"
    table = EMAIL_OPENING if template == "email" else CODING_OPENING
    text = table.get((mid, slice_minutes))
    if not text:
        deliverable = ((milestone or {}).get("deliverable") or {}).get("text") or "作品"
        if template == "email":
            text = f"完成「{(milestone or {}).get('title', mid)}」的最小写作任务：{deliverable}；只改一件事，写完复评一次。"
        else:
            text = f"完成「{(milestone or {}).get('title', mid)}」的最小可运行版本：{deliverable}；只做一条真实输入 + 一次运行。"
    digest = hashlib.sha256(f"{template}|{mid}|{slice_minutes}|{profile_key}|{text}".encode("utf-8")).hexdigest()
    return {
        "task_id": f"task-{digest[:10]}",
        "text": text,
        "milestone": mid,
        "slice": slice_minutes,
        "slice_hint": slice_hint,
        "template": template,
    }


# --------------------------------------------------------------------------- #
# 下一步：纯函数（design §7）
# --------------------------------------------------------------------------- #
def uncovered_artifacts(artifacts: dict, reviews: dict, mid: str) -> list[dict]:
    return [item for item in artifacts_for(artifacts, mid) if review_for_artifact(reviews, item["id"]) is None]


def pick_review_target(artifacts: dict, reviews: dict, mid: str) -> dict | None:
    """Same target for `next` and `review`: newest uncovered, code file preferred."""
    candidates = artifacts_for(artifacts, mid)
    uncovered = [item for item in candidates if review_for_artifact(reviews, item["id"]) is None]
    pool = uncovered or candidates
    if not pool:
        return None
    code = [item for item in pool if str(Path(str(item.get("path") or "")).suffix).lower() in CODE_SUFFIXES]
    return (code or pool)[-1]


def compute_next(
    brief: dict,
    artifacts: dict,
    reviews: dict,
    defense: dict,
    gaps: dict | None = None,
    *,
    minutes: int | None = None,
    claim_open: bool = False,
) -> dict:
    slice_minutes, slice_hint = pick_slice(brief, minutes)
    items = brief.get("milestones", [])
    mid = brief.get("current_milestone")
    m = get_milestone(brief, mid)
    base = {
        "milestone": mid,
        "milestone_title": (m or {}).get("title", ""),
        "minutes": slice_minutes,
        "slice": slice_minutes,
        "slice_hint": slice_hint,
    }

    if m is None or not items:
        return {"action": "done", "reason": "没有可执行的里程碑", "ref": None, **base}
    if all(x.get("status") in ("passed", "passed_assisted") for x in items):
        return {
            "action": "done",
            "reason": "全部里程碑已通过：运行 export --out 导出学习档案",
            "ref": mid,
            **base,
        }
    if m.get("status") in ("passed", "passed_assisted"):
        nxt = next_milestone(brief, mid)
        return {
            "action": "do_task",
            "reason": f"{mid} 已通过，当前应推进 {nxt['id']}；运行 milestones 查看全景" if nxt else "里程碑已通过",
            "ref": (nxt or {}).get("id"),
            **base,
        }

    art = latest_artifact(artifacts, mid)
    # ① 有完成声明但无作品 -> artifact_required（绝不因自述通过）
    if claim_open and art is None:
        task = opening_task(brief, m, minutes)
        return {
            "action": "artifact_required",
            "reason": f"{mid} 没有登记作品：learner 说完成不算证据，先 artifact add 把文件登记进来",
            "ref": None,
            "task_id": task["task_id"],
            "task_text": task["text"],
            **base,
        }
    # ② 无作品 -> do_task（按 minutes 切片，任务文本固定）
    task = opening_task(brief, m, minutes)
    if art is None:
        deliverable = (m.get("deliverable") or {}).get("text", "")
        return {
            "action": "do_task",
            "reason": f"{mid}「{m.get('title', '')}」还没有作品；交付物：{deliverable}",
            "ref": None,
            "task_id": task["task_id"],
            "task_text": task["text"],
            **base,
        }
    # ③ 有作品无评审 -> review（一次评审覆盖当时登记的一批作品；新增文件要再评）
    candidates = artifacts_for(artifacts, mid)
    uncovered = [item for item in candidates if review_for_artifact(reviews, item["id"]) is None]
    if uncovered:
        target = pick_review_target(artifacts, reviews, mid) or uncovered[-1]
        return {
            "action": "review",
            "reason": (
                f"作品 {target['id']}（{target.get('path')}）已登记但未评审；"
                f"本次将评审 {len(candidates)} 件：{', '.join(a['id'] for a in candidates)}"
            ),
            "ref": target["id"],
            "artifacts": [a["id"] for a in candidates],
            "task_id": task["task_id"],
            **base,
        }
    review = review_for_artifact(reviews, art["id"])
    # ④ 任一维低于阈值 -> gap_learn（排序最高者）
    rubric = rubric_by_dim(m)
    low = [d for d in review.get("rubric", []) if int(d["score"]) < int(rubric.get(d["dim"], {}).get("threshold", 0))]
    if low:
        # 一次评审周期只上一节微课：已有 learning 卡时先改作品，避免连着上多节课
        learning_gaps = [
            gap
            for gap in (gaps or {}).get("items", [])
            if gap.get("milestone") == mid and gap.get("status") == "learning"
        ]
        if learning_gaps:
            return {
                "action": "do_task",
                "reason": (
                    f"{m['id']} 的 {learning_gaps[-1]['gap_id']} 已上过微课；"
                    "先按微课改作品，再 artifact add + review 复评（缺口只能由复评达标关闭）"
                ),
                "ref": art["id"],
                "missing": "artifact_fix",
                **base,
            }
        gap = _pick_gap_for_dims(brief, gaps=gaps, mid=mid, dims=[d["dim"] for d in low])
        if gap is not None:
            return {
                "action": "gap_learn",
                "reason": (
                    f"{m['id']} 有 {len(low)} 维低于阈值；按 weight×缺口排序先补 "
                    f"{gap['dim']}（{gap.get('score')}/{gap.get('threshold')}，weight {effective_weight(gap)}）"
                ),
                "ref": gap["gap_id"],
                "dim": gap["dim"],
                "score": gap.get("score"),
                "threshold": gap.get("threshold"),
                "weight": effective_weight(gap),
                **base,
            }
        # 所有低于阈值的缺口都已上过微课（learning/covered）：先改作品再复评
        return {
            "action": "do_task",
            "reason": (
                f"{m['id']} 的缺口已上过微课（{', '.join(d['dim'] for d in low)}）；"
                "先按微课改作品，再 artifact add + review 复评（缺口只能由复评达标关闭）"
            ),
            "ref": art["id"],
            "missing": "artifact_fix",
            **base,
        }
    # ⑤ rubric 达标但 defense 未过 -> defend
    dfn = defense_for_artifact(defense, art["id"])
    if dfn is None:
        return {
            "action": "defend",
            "reason": f"{art['id']} 四维均达阈值，但还没有防御性解释记录；运行 defend 开始三问",
            "ref": art["id"],
            **base,
        }
    if not dfn.get("passed"):
        status = dfn.get("status", "pending")
        detail = {
            "pending": "三问待作答",
            "failed": f"三问仅 {dfn.get('ok_count', 0)} 问通过（至少 2 问，且最重维度必须通过）",
        }.get(status, status)
        return {
            "action": "defend",
            "reason": f"{art['id']} rubric 已达标，但 defense {detail}；继续回答防御问题",
            "ref": dfn.get("id"),
            "missing": "defense",
            **base,
        }
    # ⑥ 三者齐 -> 通过（由 reconcile 落库），⑦ 全过 -> done
    nxt = next_milestone(brief, mid)
    if nxt is None:
        return {
            "action": "done",
            "reason": f"{mid} 的 pass_evidence 已齐备，运行 status 完成收尾并 export",
            "ref": mid,
            **base,
        }
    return {
        "action": "milestone_passed",
        "reason": f"{mid} 作品 + rubric + defense 齐备；通过后推进 {nxt['id']}",
        "ref": mid,
        **base,
    }


def _pick_gap_for_dims(brief: dict, *, gaps: dict | None, mid: str, dims: list[str]) -> dict | None:
    """Choose the highest-priority existing open gap among the low dims."""
    if not gaps:
        return None
    candidates = [
        g
        for g in gaps.get("items", [])
        if g.get("milestone") == mid
        and g.get("dim") in dims
        and g.get("status") == "open"
    ]
    if not candidates:
        return None
    order = {m["id"]: i for i, m in enumerate(brief.get("milestones", []))}
    candidates.sort(key=lambda g: gap_sort_key(g, order))
    return candidates[0]


# --------------------------------------------------------------------------- #
# 评分
# --------------------------------------------------------------------------- #
def score_review(milestone: dict, dims: list[dict]) -> dict:
    rubric = rubric_by_dim(milestone)
    weighted = 0.0
    total_weight = 0
    low = []
    for d in dims:
        rule = rubric.get(d["dim"])
        if not rule:
            continue
        score = int(d["score"])
        threshold = int(rule["threshold"])
        weight = int(rule["weight"])
        weighted += weight * score
        total_weight += weight
        if score < threshold:
            low.append({"dim": d["dim"], "score": score, "threshold": threshold, "weight": weight, "gap": threshold - score})
    weighted_avg = round(weighted / total_weight, 2) if total_weight else 0.0
    return {
        "weighted": weighted_avg,
        "weights_total": total_weight,
        "threshold_pass": not low,
        "low_dims": low,
    }


def low_dim_names(milestone: dict, review: dict | None) -> list[str]:
    if not review:
        return []
    rubric = rubric_by_dim(milestone)
    return [
        d["dim"]
        for d in review.get("rubric", [])
        if int(d.get("score", 0)) < int(rubric.get(d.get("dim"), {}).get("threshold", 0))
    ]


_LINE_EVIDENCE = re.compile(
    r"(第\s*\d+\s*[行段]|line\s*\d+|L\d{1,4}\b|:\d{1,4}\b|行号|段落|第[一二三四五六七八九十]+段)",
    re.IGNORECASE,
)


def needs_extra_gap(milestone: dict, dim: dict) -> bool:
    """explainability 类维度：达标但 note 没有行号/段落级证据，仍开卡。"""
    if dim.get("dim") not in NARRATIVE_DIMS:
        return False
    return not has_line_evidence(dim.get("note") or "")


_POSITIVE_EVIDENCE = re.compile(r"(第\s*\d+\s*[行段]|line\s*\d+)", re.IGNORECASE)
_NEGATIVE_EVIDENCE = re.compile(
    r"(无|没有|缺|缺少|未|拿不到|未能|没给|尚未)[^。；;，,]{0,16}(行号|证据|段落)",
    re.IGNORECASE,
)


def has_line_evidence(text: str) -> bool:
    """True when a note/evidence string points at a concrete line or paragraph.

    A note like “无行号级证据” is an admission of missing evidence, not evidence:
    explicit negative wording wins unless a positive ``第 N 行/段`` reference exists.
    """
    value = str(text or "")
    if _NEGATIVE_EVIDENCE.search(value) and not _POSITIVE_EVIDENCE.search(value):
        return False
    return bool(_LINE_EVIDENCE.search(value))


# --------------------------------------------------------------------------- #
# 缺口卡
# --------------------------------------------------------------------------- #
def gap_card_id(mid: str, dim: str) -> str:
    return f"g-{mid}-{dim}"


def upsert_gap(
    gaps: dict,
    milestone: dict,
    dim: str,
    *,
    score: int,
    threshold: int,
    weight: int,
    note: str,
    review_id: str,
    artifact_sha: str,
    extra: bool = False,
    status: str = "open",
) -> dict:
    items = gaps.setdefault("items", [])
    gid = gap_card_id(milestone["id"], dim)
    existing = next((g for g in items if g.get("gap_id") == gid), None)
    at = now_iso()
    if existing is None:
        card = {
            "gap_id": gid,
            "milestone": milestone["id"],
            "dim": dim,
            "score": int(score),
            "threshold": int(threshold),
            "weight": int(weight),
            "note": str(note or "")[:200],
            "evidence": {"artifact_sha": artifact_sha, "review_id": review_id, "lines": ""},
            "source_review": review_id,
            "status": status,
            "closed_by": None,
            "closed_by_review": None,
            "closed_at": None,
            "attempts": 1,
            "stale_drops": 0,
            "unverified": status == "unverified",
            "extra_trigger": bool(extra),
            "source_artifact_sha": artifact_sha,
            "created_at": at,
            "updated_at": at,
        }
        items.append(card)
        return {"card": card, "change": "created"}
    old_status = existing.get("status")
    existing.update(
        {
            "score": int(score),
            "threshold": int(threshold),
            "weight": int(weight),
            "note": str(note or "")[:200],
            "source_review": review_id,
            "evidence": {"artifact_sha": artifact_sha, "review_id": review_id, "lines": ""},
            "updated_at": at,
            "extra_trigger": bool(extra) or bool(existing.get("extra_trigger")),
        }
    )
    if status == "unverified":
        # 达标但缺证据：不是开放缺口，只登记为 unverified，等下一次带证据的评审
        existing["status"] = "unverified"
        existing["unverified"] = True
        existing["closed_by"] = None
        existing["closed_by_review"] = None
        existing["closed_at"] = None
        return {"card": existing, "change": "updated" if old_status == "unverified" else "reopened"}
    if old_status == "open":
        existing["attempts"] = int(existing.get("attempts", 1)) + 1
        return {"card": existing, "change": "updated"}
    if old_status == "learning":
        # 复评仍未达标：重新打开这张卡，允许再上一次微课（attempts 递增）
        existing["status"] = "open"
        existing["attempts"] = int(existing.get("attempts", 1)) + 1
        existing["reopened_at"] = now_iso()
        existing["unverified"] = False
        return {"card": existing, "change": "reopened"}
    existing["status"] = "open"
    existing["attempts"] = int(existing.get("attempts", 1)) + 1
    existing["closed_by"] = None
    existing["closed_by_review"] = None
    existing["closed_at"] = None
    existing["unverified"] = False
    return {"card": existing, "change": "reopened"}


def close_gaps_for_review(
    gaps: dict,
    milestone: dict,
    dims: list[dict],
    *,
    review_id: str,
    artifact_sha: str,
    skip_dims: tuple[str, ...] = (),
) -> list[dict]:
    rubric = rubric_by_dim(milestone)
    closed = []
    for dim in dims:
        rule = rubric.get(dim["dim"])
        if not rule or int(dim["score"]) < int(rule["threshold"]):
            continue
        if dim["dim"] in skip_dims:
            continue
        for gap in gaps.get("items", []):
            if gap.get("milestone") != milestone["id"] or gap.get("dim") != dim["dim"]:
                continue
            if gap.get("status") not in ("open", "learning", "unverified"):
                continue
            if gap.get("source_review") == review_id:
                # 本次评审刚开的卡（explainability 证据不足例外）不能由同一次评审关闭
                continue
            gap.update(
                {
                    "status": "closed",
                    "closed_by": "review",
                    "closed_by_review": review_id,
                    "closed_at": now_iso(),
                    "closed_artifact_sha": artifact_sha,
                    "unverified": False,
                }
            )
            closed.append(gap)
    return closed


def mark_unverified_micro_practice(gaps: dict, mid: str) -> list[dict]:
    """路径 (b)：微课 + 微练习 help_level<=1 —— 标「未在作品复验」，不算解决。"""
    touched = []
    for gap in gaps.get("items", []):
        if gap.get("milestone") != mid or gap.get("status") not in ("open", "learning"):
            continue
        gap["unverified"] = True
        gap["micro_practice_at"] = now_iso()
        gap["note"] = (gap.get("note", "") + "｜微课+微练习独立完成，未在作品复验").strip("｜")[:200]
        gap["updated_at"] = now_iso()
        touched.append(gap)
    return touched


def drop_gap(gaps: dict, gap: dict, *, min_attempts: int = 3) -> dict:
    """路径 (c)：连续三次重开仍不过，才允许 drop -> stale（不算解决）。"""
    attempts = int(gap.get("attempts", 1))
    if gap.get("status") == "stale":
        return {"ok": False, "reason": "already_stale", "card": gap}
    if attempts < min_attempts:
        return {
            "ok": False,
            "reason": "attempts_below_min",
            "card": gap,
            "attempts": attempts,
            "min_attempts": min_attempts,
        }
    gap["status"] = "stale"
    gap["stale_drops"] = int(gap.get("stale_drops", 0)) + 1
    gap["closed_by"] = None
    gap["closed_by_review"] = None
    gap["stale_at"] = now_iso()
    gap["updated_at"] = now_iso()
    gap["note"] = (str(gap.get("note", "")) + "｜已 drop（stale，不算解决，doctor 会列出）")[:200]
    return {"ok": True, "card": gap, "effective_weight": effective_weight(gap)}


# --------------------------------------------------------------------------- #
# 防御
# --------------------------------------------------------------------------- #
FALLBACK_DEFENSE_QUESTIONS = {
    "runnability": "把输入换成另一个真实样例，现在这版还能跑通吗？指到具体行。",
    "contract": "输入不符合工具约定时，现在这版会返回什么？在哪一行处理？",
    "robustness": "把输入换成缺失或非法的情况，现在这版会发生什么？在哪一行？",
    "explainability": "为什么这样切分实现？举一处取舍并给出行号。",
    "structure": "如果收件人只读第一段，他能知道你要什么吗？为什么？",
    "tone": "如果对方比你高两级，你会改哪一句？为什么？",
    "clarity": "哪一句最容易被误读？你会怎么改？",
    "scenario_fit": "换一个更紧急或更正式的场景，这封邮件哪一段要改？为什么？",
}


def validate_defense_questions(milestone: dict, materials_text: str) -> tuple[list[dict], list[dict]]:
    """Drop/replace template questions that reference facts the learner never received."""
    questions: list[dict] = []
    unsupported: list[dict] = []
    for q in milestone.get("defense_questions", []):
        numbers = re.findall(r"\d+", q.get("question", ""))
        missing = [number for number in numbers if number not in (materials_text or "")]
        item = {
            "qid": q["qid"],
            "dim": q["dim"],
            "question": q["question"],
            "answer": None,
            "evidence_line": None,
            "ok": False,
            "mentor_ok": False,
            "check": "unanswered",
        }
        if missing:
            replacement = FALLBACK_DEFENSE_QUESTIONS.get(
                q["dim"], "请结合本次任务与作品的具体行，解释这一维的一个取舍。"
            )
            item["original_question"] = q["question"]
            item["question"] = replacement
            item["unsupported_terms"] = missing
            unsupported.append(
                {
                    "qid": q["qid"],
                    "dim": q["dim"],
                    "original": q["question"],
                    "replacement": replacement,
                    "missing": missing,
                }
            )
        questions.append(item)
    return questions, unsupported


def build_defense(
    milestone: dict,
    artifact: dict,
    review: dict,
    rules: dict | None = None,
    *,
    materials_text: str = "",
) -> dict:
    questions, unsupported = validate_defense_questions(milestone, materials_text)
    return {
        "id": f"d-{milestone['id']}-{artifact['sha256'][:8]}",
        "milestone": milestone["id"],
        "artifact_id": artifact["id"],
        "artifact_sha256": artifact["sha256"],
        "review_id": review["id"],
        "questions": questions,
        "unsupported_questions": unsupported,
        "ok_count": 0,
        "min_ok": int((rules or {}).get("min_ok", 2) or 2),
        "heaviest_dims": heaviest_dims(milestone),
        "heaviest_ok": False,
        "status": "pending",
        "passed": False,
        "attempts": 0,
        "decided_by": "runtime",
        "source": "runtime_template",
        "at": now_iso(),
    }


def _is_generic(answer: str) -> bool:
    text = (answer or "").strip().strip("。.!！~～ ")
    if not text:
        return True
    if GENERIC_ANSWER.match(text):
        return True
    # 只复述"我理解了设计"这类短语，且没有任何具体词
    if len(text) <= 12 and re.search(r"(理解了|明白了|懂了|没问题|差不多|还行)", text):
        return True
    return False


def verify_defense_questions(milestone: dict, proposed: list[dict], artifact_text: str) -> list[dict]:
    """Merge the mentor's answers with the fixed questions, then let the runtime decide ``ok``.

    运行时只做结构性证据校验：行号必须存在、该行非空、答案不是空话/复述题面。
    语义正确性仍由导师判断，但导师的 ``ok`` 不能绕过这里的检查。
    """
    lines = artifact_text.splitlines()
    used = set()
    merged = []
    for template in milestone.get("defense_questions", []):
        candidate = None
        for item in proposed:
            if item.get("qid") == template["qid"] and id(item) not in used:
                candidate = item
                break
        if candidate is None:
            for item in proposed:
                if item.get("dim") == template["dim"] and id(item) not in used:
                    candidate = item
                    break
        if candidate is not None:
            used.add(id(candidate))
        answer = (candidate or {}).get("answer")
        answer = str(answer).strip() if isinstance(answer, str) and answer.strip() else None
        raw_line = (candidate or {}).get("evidence_line")
        evidence_line = None
        if isinstance(raw_line, int) and not isinstance(raw_line, bool):
            evidence_line = raw_line
        elif isinstance(raw_line, str) and raw_line.strip().isdigit():
            evidence_line = int(raw_line.strip())
        mentor_ok = bool((candidate or {}).get("ok"))
        check = "ok"
        ok = False
        if answer is None:
            check = "unanswered"
        elif evidence_line is None:
            check = "evidence_line_missing"
        elif not 1 <= evidence_line <= len(lines):
            check = "evidence_line_out_of_range"
        elif not lines[evidence_line - 1].strip():
            check = "evidence_line_blank"
        elif len(answer) < MIN_ANSWER_CHARS:
            check = "answer_too_short"
        elif _is_generic(answer):
            check = "generic_answer"
        elif not mentor_ok:
            check = "mentor_marked_false"
        else:
            ok = True
        merged.append(
            {
                "qid": template["qid"],
                "dim": template["dim"],
                "question": template["question"],
                "answer": answer,
                "evidence_line": evidence_line,
                "mentor_ok": mentor_ok,
                "ok": ok,
                "check": check,
            }
        )
    return merged


def evaluate_defense(milestone: dict, rules: dict, questions: list[dict]) -> dict:
    heaviest = heaviest_dims(milestone)
    ok_count = sum(1 for q in questions if q.get("ok"))
    min_ok = int(rules.get("min_ok", 2) or 2)
    heaviest_required = bool(rules.get("heaviest_dim_must_pass", True))
    heaviest_ok = True
    if heaviest_required:
        heaviest_ok = bool(heaviest) and all(
            any(q.get("ok") and q.get("dim") == dim for q in questions) for dim in heaviest
        )
    pending = bool(questions) and all((q.get("answer") or "") == "" for q in questions)
    passed = bool(questions) and not pending and ok_count >= min_ok and (heaviest_ok or not heaviest_required)
    status = "pending" if pending else ("passed" if passed else "failed")
    return {
        "ok_count": ok_count,
        "min_ok": min_ok,
        "heaviest_dims": heaviest,
        "heaviest_ok": heaviest_ok,
        "pending": pending,
        "passed": passed,
        "status": status,
    }


def pending_defense_for_milestone(defense: dict, mid: str) -> dict | None:
    items = [d for d in defense.get("items", []) if d.get("milestone") == mid]
    if not items:
        return None
    latest = items[-1]
    if latest.get("status") in ("pending", "failed"):
        return latest
    return None


# --------------------------------------------------------------------------- #
# 里程碑通过
# --------------------------------------------------------------------------- #
def evidence_complete(milestone: dict, artifacts: dict, reviews: dict, defense: dict) -> dict:
    """Return ``{ok, artifact, review, defense, missing}`` without mutating anything."""
    mid = milestone["id"]
    art = latest_artifact(artifacts, mid)
    result = {"ok": False, "artifact": art, "review": None, "defense": None, "missing": []}
    if art is None:
        result["missing"].append("artifact")
        return result
    review = review_for_artifact(reviews, art["id"])
    if review is None or not review.get("threshold_pass"):
        result["missing"].append("review")
        return result
    result["review"] = review
    dfn = defense_for_artifact(defense, art["id"])
    if dfn is None or not dfn.get("passed"):
        result["missing"].append("defense")
        result["defense"] = dfn
        return result
    result["ok"] = True
    result["defense"] = dfn
    return result


def pass_status(artifact: dict) -> str:
    """verified = 达标 + assisted_level<=1 + defense；observed = 达标但 assisted_level>=2。"""
    return "passed" if int(artifact.get("assisted_level", 0)) <= 1 else "passed_assisted"
