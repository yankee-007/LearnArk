"""Product-level divergence recovery with an explicit side preference.

Core 1.0.2 can union-merge journals automatically, but state snapshots
(``studio.json`` / ``session.json`` / capability) need a human decision.  This
module implements that decision as ``sync --recover --prefer local|remote``:

* journal conflicts are ALWAYS union-merged by event id (both sides kept);
* state/session conflicts take the chosen side (local = commit being rebased,
  i.e. git's ``--theirs`` during a rebase; remote = upstream, ``--ours``);
* the rebase is continued and the result pushed without force;
* every choice/loss is returned for logging and printing.
"""

from __future__ import annotations

import json
from pathlib import Path

from learncore.sync import GitSync, SyncReport


def _read_stage(git: GitSync, relpath: str, stage: int) -> str:
    code, out, _ = git.run("show", f":{stage}:{relpath}")
    return out if code == 0 else ""


def _union_events(git: GitSync, relpath: str) -> tuple[str, int]:
    events: dict[str, dict] = {}
    for stage in (2, 3):
        for line in _read_stage(git, relpath, stage).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = event.get("id") or f"seq{event.get('seq')}"
            events[key] = event
    ordered = sorted(events.values(), key=lambda item: (str(item.get("at", "")), str(item.get("id", ""))))
    for index, event in enumerate(ordered, start=1):
        event["seq"] = index
    text = "\n".join(json.dumps(event, ensure_ascii=False) for event in ordered)
    return (text + "\n" if text else ""), len(ordered)


def _rebuild_dedupe(git: GitSync, journal_dir: Path) -> int:
    events_path = journal_dir / "events.jsonl"
    index: dict[str, str] = {}
    if events_path.exists():
        for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = event.get("dedupe_key")
            if key and key not in index:
                index[key] = event.get("id", "")
    journal_dir.mkdir(parents=True, exist_ok=True)
    (journal_dir / "dedupe.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(index)


def _resolve_rebase(git: GitSync, prefer: str) -> dict:
    """Resolve every conflict of the in-progress rebase according to ``prefer``."""
    root = git.repo_root()
    resolved: list[str] = []
    lost_local: list[str] = []
    lost_remote: list[str] = []
    merged_events = 0
    for _ in range(20):
        if not git.rebase_in_progress():
            return {
                "ok": True,
                "paths": resolved,
                "lost_local": lost_local,
                "lost_remote": lost_remote,
                "merged_events": merged_events,
            }
        unmerged = git.unmerged_paths()
        event_paths = [path for path in unmerged if path.replace("\\", "/").endswith("journal/events.jsonl")]
        dedupe_paths = [path for path in unmerged if path.replace("\\", "/").endswith("journal/dedupe.json")]
        for path in event_paths:
            text, count = _union_events(git, path)
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            code, _, _ = git.run("add", "--", path)
            if code != 0:
                return {"ok": False, "reason": "stage-events-failed", "unmerged": unmerged}
            merged_events = max(merged_events, count)
            resolved.append(path)
        journal_dirs = {str((root / path).parent) for path in event_paths + dedupe_paths}
        for journal_dir in journal_dirs:
            try:
                _rebuild_dedupe(git, Path(journal_dir))
                dedupe_rel = str((Path(journal_dir) / "dedupe.json").relative_to(root))
                git.run("add", "--", dedupe_rel)
                resolved.append(dedupe_rel)
            except OSError:
                pass
        side = "theirs" if prefer == "local" else "ours"
        lost = lost_local if prefer == "remote" else lost_remote
        for path in unmerged:
            if path in event_paths or path in dedupe_paths:
                continue
            code, _, _ = git.run("checkout", f"--{side}", "--", path)
            if code != 0:
                other = "ours" if side == "theirs" else "theirs"
                code, _, _ = git.run("checkout", f"--{other}", "--", path)
            if code != 0:
                return {"ok": False, "reason": "checkout-failed", "path": path, "unmerged": unmerged}
            git.run("add", "--", path)
            resolved.append(path)
            lost.append(path)
        code, out, err = git.run("-c", "core.editor=true", "rebase", "--continue", timeout=120)
        if code == 0:
            continue
        if git.unmerged_paths():
            continue
        return {"ok": False, "reason": "rebase-continue-failed", "detail": (err or out)[:400]}
    return {"ok": False, "reason": "too-many-rounds"}


def _likely_conflicts(git: GitSync) -> list[str]:
    """Files changed on both sides since the merge base (for refusal reports)."""
    code, base, _ = git.run("merge-base", "HEAD", "@{u}")
    if code != 0 or not base:
        return []
    _, local, _ = git.run("diff", "--name-only", base, "HEAD")
    _, remote, _ = git.run("diff", "--name-only", base, "@{u}")
    local_paths = {line.strip() for line in local.splitlines() if line.strip()}
    remote_paths = {line.strip() for line in remote.splitlines() if line.strip()}
    return sorted(local_paths & remote_paths)


def recover_with_preference(git: GitSync, prefer: str | None, message: str) -> tuple[SyncReport, dict]:
    """Perform the explicit recovery.  Missing preference refuses without writing."""
    report = SyncReport(state="conflict", written=False, message=message)
    report.branch = git.branch()
    report.remote = git.remote_url() if git.remotes() else ""
    info: dict = {"prefer": prefer, "chosen": prefer or "", "lost_local": [], "lost_remote": [], "merged_events": 0}
    if prefer not in ("local", "remote"):
        blocking: list[str] = []
        if git.is_repo() and git.remotes() and not git.rebase_in_progress():
            pull = git.pull_rebase(abort_on_failure=False)
            if not pull["ok"]:
                blocking = git.unmerged_paths() or _likely_conflicts(git)
                git.run("rebase", "--abort")
        report.detail = json.dumps({"reason": "preference-required", "blocking": blocking}, ensure_ascii=False)
        report.recovery = (
            "分叉需要显式选择：learn.cmd sync --recover --prefer local 或 --prefer remote。"
            "本次没有写入或提交任何文件。"
        )
        return report, info
    if not git.is_repo():
        report.state = "no-repository"
        report.recovery = "不是 git 仓库，无法恢复。"
        return report, info
    if not git.remotes():
        report.state = "no-remote"
        report.recovery = "没有远程，本地记录完好，无需恢复。"
        return report, info

    commit_info = {"committed": False, "files": [], "sha": git.head_sha()}
    if not git.rebase_in_progress():
        try:
            commit_info = git.commit(message)
        except Exception as exc:  # LearnError
            report.state = "commit-failed"
            report.detail = str(exc)[:400]
            report.recovery = "本地提交失败，未做恢复。"
            return report, info
        if commit_info.get("committed"):
            report.written = True
            report.committed = True
            report.files = list(commit_info.get("files") or [])
        report.sha = commit_info.get("sha") or git.head_sha()
        pull = git.pull_rebase(abort_on_failure=False)
        if pull["ok"]:
            push = git.push()
            report.pushed = bool(push.get("ok"))
            report.state = "pushed" if report.pushed else "push-failed"
            report.sha = git.head_sha()
            report.detail = "no divergence"
            if not report.pushed:
                report.detail = push.get("detail", "")
                report.recovery = "已恢复本地，但推送失败；网络恢复后重试 sync。"
            return report, info
        if not git.rebase_in_progress():
            report.state = "conflict"
            report.detail = json.dumps({"reason": "pull-failed", "detail": pull.get("detail", "")}, ensure_ascii=False)
            report.recovery = "拉取失败且没有进入 rebase；请检查网络/凭据后重试。"
            return report, info

    outcome = _resolve_rebase(git, prefer)
    if not outcome.get("ok"):
        git.run("rebase", "--abort")
        report.state = "conflict"
        report.detail = json.dumps(outcome, ensure_ascii=False)[:800]
        report.recovery = (
            "恢复未完成：快照冲突需要人工选择（--prefer local|remote），"
            "本次已中止 rebase，未 force push。"
        )
        report.sha = git.head_sha()
        return report, info
    info.update(
        {
            "chosen": prefer,
            "lost_local": outcome.get("lost_local", []),
            "lost_remote": outcome.get("lost_remote", []),
            "merged_events": outcome.get("merged_events", 0),
        }
    )
    report.written = True
    report.committed = True
    report.files = sorted(set(report.files) | set(outcome.get("paths") or []))
    report.sha = git.head_sha()
    push = git.push()
    report.pushed = bool(push.get("ok"))
    report.state = "pushed" if report.pushed else "push-failed"
    report.detail = json.dumps(
        {
            "prefer": prefer,
            "merged_events": outcome.get("merged_events", 0),
            "lost_local": info["lost_local"],
            "lost_remote": info["lost_remote"],
        },
        ensure_ascii=False,
    )
    if not report.pushed:
        report.recovery = "已按选择恢复并提交，但推送失败；网络恢复后重试 sync。"
    return report, info
