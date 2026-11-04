"""Git synchronisation with explicit, honest states.

Guarantees:
* only project-owned paths are staged (allowlist + ``.gitignore``);
* the report distinguishes written / committed / pushed;
* no ``--force``, no history rewriting, no ``reset --hard``;
* on divergence or conflict we stop, keep local work, and print recovery steps;
* remote URLs are sanitised before they are printed or stored.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .fsutil import LearnError

SECRET_PATTERNS = (
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/)[^/]*credential[^/]*$", re.IGNORECASE),
    re.compile(r"(^|/)[^/]*secret[^/]*$", re.IGNORECASE),
    re.compile(r"\.(key|pem|p12|pfx)$", re.IGNORECASE),
    re.compile(r"(^|/)tokens?\.(json|txt|yaml|yml|csv|md)$", re.IGNORECASE),
    re.compile(r"(^|/)[^/]*[-_.]tokens?\.(json|txt|yaml|yml|csv|md)$", re.IGNORECASE),
    re.compile(r"(^|/)\.?(access|api|auth|bearer)[-_]?tokens?$", re.IGNORECASE),
    re.compile(r"\.log$", re.IGNORECASE),
    re.compile(r"(^|/)usage\.jsonl$"),
    re.compile(r"(^|/)sync-log\.jsonl$"),
    re.compile(r"(^|/)\.learnark/tmp(/|$)"),
    re.compile(r"__pycache__"),
    re.compile(r"\.pytest_cache"),
    re.compile(r"\.(bak|lock|tmp)$"),
)

DEFAULT_GITIGNORE = """# LearnArk project -- generated
.env
.env.*
*.key
*credentials*
*secret*
*.log
*.lock
*.bak
*.tmp
__pycache__/
*.pyc
.pytest_cache/
.learnark/tmp/
.learnark/**/*.lock
.learnark/**/usage.jsonl
.learnark/**/sync-log.jsonl
.learnark/**/*.tmp
"""

# Keep bytes exact across machines: no CRLF normalisation of learned artifacts,
# otherwise the same file has a different hash after a clean clone.
DEFAULT_GITATTRIBUTES = """# LearnArk project -- generated
* -text
"""

JOURNAL_SUFFIXES = ("journal/events.jsonl", "journal/dedupe.json")


@dataclass
class SyncReport:
    state: str  # written | clean | committed-local | pushed | push-failed | conflict | no-repository | no-remote
    written: bool = False
    committed: bool = False
    pushed: bool = False
    branch: str = ""
    sha: str = ""
    files: list[str] = field(default_factory=list)
    remote: str = ""
    message: str = ""
    recovery: str = ""
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "written": self.written,
            "committed": self.committed,
            "pushed": self.pushed,
            "branch": self.branch,
            "sha": self.sha,
            "files": self.files,
            "remote": self.remote,
            "message": self.message,
            "recovery": self.recovery,
        }

    def headline(self) -> str:
        bits = [
            f"written={'yes' if self.written else 'no'}",
            f"committed={'yes' if self.committed else 'no'}",
            f"pushed={'yes' if self.pushed else 'no'}",
        ]
        return f"git state: {self.state} ({', '.join(bits)})"


def sanitize_remote(url: str) -> str:
    if not url:
        return ""
    url = re.sub(r"//[^/@]+@", "//<redacted>@", url)
    return url.strip()


class GitSync:
    def __init__(self, root: str | Path, include: list[str] | None = None, exclude: list[str] | None = None):
        self.root = Path(root).resolve()
        self.include = include or []
        self.exclude = exclude or []

    # -- plumbing --------------------------------------------------------
    def _git(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def run(self, *args: str, timeout: int = 60) -> tuple[int, str, str]:
        proc = self._git(*args, timeout=timeout)
        # Only trim the trailing newline: porcelain output starts with a status
        # column that may be a space (" M path"), and stripping it would shift
        # every path by one character.
        return proc.returncode, (proc.stdout or "").rstrip("\r\n"), (proc.stderr or "").rstrip("\r\n")

    def git_version(self) -> str:
        try:
            return self.run("--version")[1]
        except (OSError, subprocess.SubprocessError):
            return ""

    def available(self) -> bool:
        return bool(self.git_version())

    def is_repo(self) -> bool:
        """True only when *this project* is the repository root.

        A learning project may live inside another repository (a monorepo, the
        user's notes repo, or the LearnArk workspace itself). Being "inside" a
        repo is not enough: syncing must never commit the learner's records into
        an unrelated parent repository.
        """
        code, out, _ = self.run("rev-parse", "--show-toplevel")
        if code != 0 or not out:
            return False
        try:
            return Path(out).resolve() == self.root.resolve()
        except OSError:
            return False

    def enclosing_repo(self) -> str:
        code, out, _ = self.run("rev-parse", "--show-toplevel")
        if code == 0 and out:
            return out
        return ""

    def repo_root(self) -> Path:
        code, out, _ = self.run("rev-parse", "--show-toplevel")
        if code != 0 or not out:
            raise LearnError(f"{self.root} is not inside a git repository")
        return Path(out)

    def branch(self) -> str:
        code, out, _ = self.run("rev-parse", "--abbrev-ref", "HEAD")
        return out if code == 0 else ""

    def head_sha(self) -> str:
        code, out, _ = self.run("rev-parse", "--short", "HEAD")
        return out if code == 0 else ""

    def remotes(self) -> list[str]:
        code, out, _ = self.run("remote")
        return out.splitlines() if code == 0 and out else []

    def remote_url(self, name: str = "origin") -> str:
        code, out, _ = self.run("remote", "get-url", name)
        return sanitize_remote(out) if code == 0 else ""

    def has_upstream(self) -> bool:
        code, _, _ = self.run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        return code == 0

    # -- status ----------------------------------------------------------
    def changed_paths(self) -> list[str]:
        code, out, _ = self.run("status", "--porcelain", "--untracked-files=all")
        if code != 0 or not out:
            return []
        paths = []
        for line in out.splitlines():
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            paths.append(path.strip('"'))
        return paths

    def blocked(self, path: str) -> bool:
        posix = path.replace("\\", "/")
        for pattern in SECRET_PATTERNS:
            if pattern.search(posix):
                return True
        for prefix in self.exclude:
            prefix = prefix.replace("\\", "/").strip("/")
            if prefix and (posix == prefix or posix.startswith(prefix + "/")):
                return True
        if self.include:
            for prefix in self.include:
                normalized = prefix.replace("\\", "/").strip("/")
                if normalized in ("", "."):
                    return False  # whole project is in scope
                if posix == normalized or posix.startswith(normalized + "/"):
                    return False
            return True
        return False

    def status(self) -> dict:
        if not self.is_repo():
            return {"is_repo": False}
        changed = [p for p in self.changed_paths() if not self.blocked(p)]
        ignored = [p for p in self.changed_paths() if self.blocked(p)]
        ahead, behind = self._ahead_behind()
        unmerged = self.unmerged_paths()
        return {
            "is_repo": True,
            "branch": self.branch(),
            "remote": self.remote_url() if self.remotes() else "",
            "changed": changed,
            "blocked": ignored,
            "unmerged": unmerged,
            "ahead": ahead,
            "behind": behind,
            "diverged": bool(ahead and behind) or bool(unmerged),
            "clean": not changed and not unmerged,
        }

    def unmerged_paths(self) -> list[str]:
        code, out, _ = self.run("diff", "--name-only", "--diff-filter=U")
        if code != 0 or not out:
            return []
        return [line for line in out.splitlines() if line.strip()]

    def rebase_in_progress(self) -> bool:
        code, out, _ = self.run("rev-parse", "--git-path", "rebase-merge")
        if code != 0 or not out:
            return False
        try:
            path = Path(out)
            if not path.is_absolute():
                path = self.repo_root() / path
            return path.exists()
        except LearnError:
            return False

    def _ahead_behind(self) -> tuple[int, int]:
        if not self.has_upstream():
            return (0, 0)
        code, out, _ = self.run("rev-list", "--left-right", "--count", "@{u}...HEAD")
        if code != 0 or not out:
            return (0, 0)
        try:
            behind, ahead = out.split()
            return int(ahead), int(behind)
        except ValueError:
            return (0, 0)

    # -- operations ------------------------------------------------------
    def ensure_repository(self) -> list[str]:
        """Initialise a repo at the project root, even inside an outer repository."""
        created = []
        if not self.is_repo():
            if not (self.root / ".git").exists():
                code, _, err = self.run("init", "-q")
                if code != 0:
                    raise LearnError(f"git init failed: {err}")
                created.append("git init")
        gitignore = self.repo_root() / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(DEFAULT_GITIGNORE, encoding="utf-8")
            created.append(".gitignore")
        else:
            text = gitignore.read_text(encoding="utf-8", errors="replace")
            missing = [
                line
                for line in DEFAULT_GITIGNORE.splitlines()
                if line.strip() and line.strip() not in text.splitlines()
            ]
            if missing:
                with gitignore.open("a", encoding="utf-8") as fh:
                    if not text.endswith("\n"):
                        fh.write("\n")
                    fh.write("# added by LearnArk\n" + "\n".join(missing) + "\n")
                created.append(".gitignore(updated)")
        attributes = self.repo_root() / ".gitattributes"
        if not attributes.exists():
            attributes.write_text(DEFAULT_GITATTRIBUTES, encoding="utf-8")
            created.append(".gitattributes")
        return created

    def stage_project_paths(self) -> list[str]:
        changed = [p for p in self.changed_paths() if not self.blocked(p)]
        if not changed:
            return []
        code, _, err = self.run("add", "--", *changed)
        if code != 0:
            raise LearnError(f"git add failed: {err}")
        return changed

    def commit(self, message: str, *, author: str | None = None) -> dict:
        staged = self.stage_project_paths()
        if not staged:
            return {"committed": False, "reason": "nothing-to-commit", "sha": self.head_sha()}
        args = ["commit", "-q", "-m", message]
        code, _, err = self.run(*args)
        if code != 0:
            if "Please tell me who you are" in err or "unable to auto-detect email" in err:
                self.run("config", "user.email", "learner@learnark.local")
                self.run("config", "user.name", "LearnArk Learner")
                code, _, err = self.run(*args)
            if code != 0:
                raise LearnError(f"git commit failed: {err}")
        return {"committed": True, "sha": self.head_sha(), "files": staged, "message": message}

    def pull_rebase(self, *, abort_on_failure: bool = True) -> dict:
        if not self.has_upstream():
            return {"ok": True, "detail": "no upstream configured"}
        code, out, err = self.run("pull", "--rebase", "--no-autostash", timeout=120)
        if code != 0:
            detail = (err or out)[:800]
            if abort_on_failure:
                self.run("rebase", "--abort")
            return {"ok": False, "detail": detail}
        return {"ok": True, "detail": out[:400]}

    # -- divergence recovery ---------------------------------------------
    def _blob(self, relpath: str, stage: int) -> str:
        code, out, _ = self.run("show", f":{stage}:{relpath}")
        return out if code == 0 else ""

    def _union_events(self, relpath: str) -> tuple[str, int]:
        events: dict[str, dict] = {}
        for stage in (2, 3):
            for line in self._blob(relpath, stage).splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = event.get("id") or f"seq{event.get('seq')}"
                events[key] = event
        ordered = sorted(events.values(), key=lambda e: (str(e.get("at", "")), str(e.get("id", ""))))
        for index, event in enumerate(ordered, start=1):
            event["seq"] = index
        text = "\n".join(json.dumps(event, ensure_ascii=False) for event in ordered)
        return (text + "\n" if text else ""), len(ordered)

    def _rebuild_dedupe(self, journal_dir: Path) -> int:
        index: dict[str, str] = {}
        events_path = journal_dir / "events.jsonl"
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
        (journal_dir / "dedupe.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return len(index)

    def recover_diverged(self) -> dict:
        """Resolve a rebase stopped by journal-only conflicts.

        Journals are append-only: the safe merge is a union by event id, then a
        rebuilt dedupe index. Snapshot conflicts are *not* auto-merged (they need
        a human decision); in that case we abort and hand back the file list.
        """
        if not self.rebase_in_progress():
            return {"ok": False, "reason": "no rebase in progress"}
        unmerged = self.unmerged_paths()
        journal_paths = [p for p in unmerged if p.replace("\\", "/").endswith(JOURNAL_SUFFIXES)]
        others = [p for p in unmerged if p not in journal_paths]
        if others:
            self.run("rebase", "--abort")
            return {"ok": False, "reason": "non-journal-conflicts", "unmerged": unmerged, "blocking": others}
        merged = 0
        for relpath in journal_paths:
            if relpath.endswith("events.jsonl"):
                text, count = self._union_events(relpath)
                target = self.repo_root() / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
                merged = max(merged, count)
            elif relpath.endswith("dedupe.json"):
                # Recomputed below from the union journal.
                target = self.repo_root() / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    target.write_text("{}\n", encoding="utf-8")
        journal_dirs = {str((self.repo_root() / p).parent) for p in journal_paths if p.endswith("events.jsonl")}
        for journal_dir in journal_dirs:
            self._rebuild_dedupe(Path(journal_dir))
        add_paths = set(journal_paths)
        for journal_dir in journal_dirs:
            candidate = Path(journal_dir) / "dedupe.json"
            if candidate.exists():
                add_paths.add(str(candidate.relative_to(self.repo_root())))
        code, _, err = self.run("add", "--", *sorted(add_paths))
        if code != 0:
            self.run("rebase", "--abort")
            return {"ok": False, "reason": "stage-failed", "detail": err[:400]}
        code, out, err = self.run("-c", "core.editor=true", "rebase", "--continue", timeout=120)
        if code != 0:
            self.run("rebase", "--abort")
            return {"ok": False, "reason": "continue-failed", "detail": (err or out)[:400]}
        return {"ok": True, "merged_events": merged, "paths": sorted(add_paths)}

    def push(self) -> dict:
        if not self.remotes():
            return {"ok": False, "reason": "no-remote"}
        if not self.has_upstream():
            code, out, err = self.run("push", "-u", "origin", "HEAD", timeout=120)
        else:
            code, out, err = self.run("push", timeout=120)
        if code != 0:
            text = (err or out)
            return {"ok": False, "detail": text[:800], "rejected": "rejected" in text or "non-fast-forward" in text}
        return {"ok": True, "detail": out[:400]}

    # -- one-call sync ---------------------------------------------------
    def recover(self, message: str = "learnark: recover diverged learning history") -> SyncReport:
        """Explicit recovery path for a diverged history (journal union merge)."""
        report = SyncReport(state="clean", written=True, message=message)
        if not self.is_repo():
            report.state = "no-repository"
            report.recovery = "Not a git repository; nothing to recover."
            return report
        if not self.remotes():
            report.state = "no-remote"
            report.recovery = "No remote; nothing to recover. Local data is intact."
            return report
        try:
            commit = self.commit(message)
            report.committed = bool(commit.get("committed"))
            report.sha = commit.get("sha", "")
        except LearnError as exc:
            report.state = "commit-failed"
            report.detail = str(exc)[:400]
            return report
        if self.rebase_in_progress():
            outcome = self.recover_diverged()
        else:
            pull = self.pull_rebase(abort_on_failure=False)
            outcome = {"ok": True} if pull["ok"] else self.recover_diverged()
        if not outcome.get("ok"):
            report.state = "conflict"
            report.detail = json.dumps(outcome, ensure_ascii=False)[:800]
            report.recovery = (
                "Automatic recovery only merges journals. Conflicting state files need a manual choice: "
                "inspect `git status`, keep one side's state/*.json, then run `sync`."
            )
            return report
        push = self.push()
        if not push["ok"]:
            report.state = "push-failed"
            report.detail = push.get("detail", "")
            report.recovery = "Recovered locally but could not push; retry `sync` when network is back."
            return report
        report.pushed = True
        report.state = "pushed"
        report.detail = f"recovered by union merge ({outcome.get('merged_events', 0)} events)"
        return report

    def sync(self, message: str = "learnark: save learning state") -> SyncReport:
        report = SyncReport(state="clean", written=True, message=message)
        if not self.available():
            report.state, report.written = "no-git", True
            report.recovery = "Install git, then run sync again; learning records are already on disk."
            return report
        if not self.is_repo():
            report.state = "no-repository"
            report.recovery = "Run `git init` in the project folder, then retry sync."
            return report
        report.branch = self.branch()
        report.remote = self.remote_url() if self.remotes() else ""
        try:
            commit = self.commit(message)
        except LearnError as exc:
            report.state = "commit-failed"
            report.detail = str(exc)[:400]
            report.recovery = "Files are saved locally but not committed. Fix the reported git error and retry."
            return report
        report.committed = bool(commit.get("committed"))
        report.sha = commit.get("sha", "")
        report.files = commit.get("files", [])
        if report.committed:
            report.state = "committed-local"
        if not self.remotes():
            report.state = "no-remote" if report.committed else "clean"
            report.recovery = (
                "No git remote is configured. Local commit is kept; add a remote "
                "(git remote add origin URL) to enable cross-device sync."
            )
            return report
        pull = self.pull_rebase(abort_on_failure=False)
        if not pull["ok"]:
            recovered = self.recover_diverged()
            if not recovered.get("ok"):
                self.run("rebase", "--abort")
                report.state = "conflict"
                report.detail = json.dumps(recovered, ensure_ascii=False)[:800]
                report.recovery = (
                    "Remote and local histories diverged. Nothing was force-pushed and the local commit is intact. "
                    f"Conflicting paths: {recovered.get('blocking') or self.unmerged_paths() or 'unknown'}. "
                    "Journal-only conflicts can be recovered automatically with `sync --recover`; "
                    "state/snapshot conflicts need a human choice (keep local or remote) before syncing again."
                )
                return report
            report.detail = f"divergence recovered: union-merged {recovered.get('merged_events', 0)} events"
        push = self.push()
        if push["ok"]:
            report.pushed = True
            report.state = "pushed"
            return report
        if push.get("rejected"):
            # Someone pushed between our pull and push: try one safe round-trip.
            retry = self.pull_rebase(abort_on_failure=False)
            if retry["ok"] or self.recover_diverged().get("ok"):
                pushed_again = self.push()
                if pushed_again["ok"]:
                    report.pushed = True
                    report.state = "pushed"
                    report.detail = "recovered after a concurrent push"
                    return report
            self.run("rebase", "--abort")
            report.state = "conflict"
            report.recovery = (
                "Another device pushed while syncing. Local commits are kept; "
                "run `sync` again after checking `git status`; no force push was used."
            )
            return report
        report.state = "push-failed"
        report.detail = push.get("detail", "")
        report.recovery = (
            "Learning state is committed locally but not pushed. Check network/credentials; "
            "then run sync again. Do not force-push."
        )
        return report


def ensure_git_identity(root: str | Path, name: str = "LearnArk Learner", email: str = "learner@learnark.local") -> None:
    """Set a repo-local identity when the machine has none (never touches global config)."""
    for key, value in (("user.name", name), ("user.email", email)):
        proc = subprocess.run(
            ["git", "config", "--get", key],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0 or not (proc.stdout or "").strip():
            subprocess.run(
                ["git", "config", key, value],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )


def git_available() -> bool:
    try:
        subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def repo_has_remote(root: str | Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "remote"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return bool((proc.stdout or "").strip())
    except (OSError, subprocess.SubprocessError):
        return False


def default_sync_message(project_slug: str, note: str = "") -> str:
    stamp = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M")
    note = note.strip()
    return f"learn({project_slug}): {stamp}" + (f" {note}" if note else "")
