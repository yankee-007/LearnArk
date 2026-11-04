"""Cross-variant smoke checker for the common CLI contract.

Runs the documented commands against a fresh temporary project in offline mode and
records what actually happened. It is deliberately tolerant about wording and
strict about exit codes, files, and state integrity.

Usage:
    python shared/check_variant.py --variant variants/direction-a-skillmap
    python shared/check_variant.py --all
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SANDBOX = ROOT.parent / "_sandbox" / "checks"


def _force_remove(func, path, exc_info=None):
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
        func(path)
    except OSError:
        pass


def run(entry: Path, args: list[str], cwd: Path, timeout: int = 180) -> dict:
    env = dict(os.environ)
    env.update({"LEARNARK_LLM": "mock", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    env.pop("LEARNARK_NOW", None)
    started = datetime.now()
    try:
        proc = subprocess.run(
            [sys.executable, str(entry), *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        return {
            "args": args,
            "cwd": str(cwd),
            "code": proc.returncode,
            "stdout": (proc.stdout or "")[-24000:],
            "stderr": (proc.stderr or "")[-4000:],
            "seconds": round((datetime.now() - started).total_seconds(), 2),
        }
    except subprocess.TimeoutExpired:
        return {"args": args, "cwd": str(cwd), "code": "TIMEOUT", "stdout": "", "stderr": "", "seconds": timeout}


def check(variant: Path, keep: bool = False) -> dict:
    variant = variant.resolve()
    entry = variant / "runtime" / "learn.py"
    manifest_path = variant / "version-manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {}
    name = manifest.get("id") or variant.name
    work = SANDBOX / name
    if work.exists():
        shutil.rmtree(work, onexc=_force_remove)
    work.mkdir(parents=True, exist_ok=True)
    proj = work / "proj"

    result: dict = {"variant": name, "variant_dir": str(variant), "entry": str(entry), "checks": {}, "runs": []}

    def record(key, args, cwd, expect=0):
        run_result = run(entry, args, cwd)
        result["runs"].append(run_result)
        ok = run_result["code"] == expect
        result["checks"][key] = {
            "ok": ok,
            "exit": run_result["code"],
            "seconds": run_result["seconds"],
            "note": "" if ok else (run_result["stderr"] or run_result["stdout"])[-500:],
        }
        return run_result

    if not entry.exists():
        result["checks"]["entry"] = {"ok": False, "note": f"missing {entry}"}
        return result

    record("init", ["init", "--goal", "能用 Python 独立做出带工具调用的小 Agent", "--dir", str(proj), "--template", "agent-dev"], work)

    def exists(rel: str) -> bool:
        return (proj / rel).exists()

    result["checks"]["project_state"] = {
        "ok": exists(".learnark/project.json") and exists(".gitignore") and exists("README.md"),
        "note": "missing one of .learnark/project.json / .gitignore / README.md",
    }
    start = record("start", ["start", "--minutes", "20"], proj)
    result["checks"]["start_output"] = {
        "ok": bool((start["stdout"] or "").strip()),
        "note": "start printed nothing",
    }
    record("say", ["say", "我学过 API 调用，但没写过工具调用（tool use），不太清楚 Agent 循环是什么"], proj)
    status = record("status_json", ["status", "--json"], proj)
    parsed = None
    if status["code"] == 0:
        text = status["stdout"].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            start_idx = text.find("{")
            if start_idx >= 0:
                try:
                    parsed = json.loads(text[start_idx:])
                except json.JSONDecodeError:
                    parsed = None
    result["checks"]["status_json_parses"] = {
        "ok": isinstance(parsed, dict),
        "note": "" if isinstance(parsed, dict) else "status --json did not return a JSON object",
    }
    result["status_keys"] = sorted(parsed.keys())[:20] if isinstance(parsed, dict) else []

    mentors = manifest.get("mentors") or []
    if mentors:
        switch = run(entry, ["switch", mentors[-1]], proj)
        result["switch"] = {"mentor": mentors[-1], "exit": switch["code"], "out": (switch["stdout"] or "")[-400:]}
        result["runs"].append(switch)
    record("pause", ["pause", "--note", "冒烟检查"], proj)
    result["checks"]["handoff"] = {
        "ok": any((proj / ".learnark" / "handoff").glob("*.md")) if (proj / ".learnark" / "handoff").exists() else False,
        "note": "no handoff markdown written by pause",
    }
    sync = record("sync", ["sync"], proj)
    result["checks"]["sync_reports_tristate"] = {
        "ok": all(word in ((sync["stdout"] or "") + (sync["stderr"] or "")).lower() for word in ("written", "committed", "pushed")),
        "note": "sync output does not state written/committed/pushed",
    }

    journal = proj / ".learnark" / "journal" / "events.jsonl"
    events = []
    if journal.exists():
        for line in journal.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    result["journal_events"] = len(events)
    kinds = sorted({e.get("kind", "?") for e in events})
    result["journal_kinds"] = kinds
    result["checks"]["journal_has_turns"] = {
        "ok": any("turn" in k or "say" in k or k in ("mentor_turn", "attempt", "session_turn") for k in kinds),
        "note": f"kinds={kinds}",
    }
    result["checks"]["journal_integrity"] = {"ok": bool(events), "note": "no events recorded"}

    sessions_dir = proj / "sessions"
    session_files = list(sessions_dir.rglob("*.md")) if sessions_dir.exists() else []
    result["sessions"] = [str(p.relative_to(proj)) for p in session_files][:20]
    result["checks"]["session_files"] = {
        "ok": len(session_files) >= 1,
        "note": "no session markdown written",
    }

    doctor = record("doctor", ["doctor"], proj, expect=None if False else 0)
    if doctor["code"] not in (0,):
        # doctor may legitimately report findings with a non-zero exit; keep the output
        result["checks"]["doctor"]["ok"] = False

    export = record("export", ["export", "--out", str(work / "export.md")], proj)
    result["checks"]["export_file"] = {
        "ok": (work / "export.md").exists() and (work / "export.md").stat().st_size > 100,
        "note": "export.md missing or too small",
    }
    result["checks"]["export_exit"] = {"ok": export["code"] == 0, "note": str(export["code"])}

    if not keep:
        pass  # keep artifacts for evidence; caller decides cleanup
    return result


def summary(result: dict) -> tuple[int, int]:
    ok = sum(1 for c in result.get("checks", {}).values() if c.get("ok"))
    total = len(result.get("checks", {}))
    return ok, total


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args(argv)
    variants = []
    if args.variant:
        variants.append(Path(args.variant))
    if args.all:
        variants += sorted((ROOT / "variants").glob("direction-*"))
    if not variants:
        parser.error("pass --variant or --all")
    SANDBOX.mkdir(parents=True, exist_ok=True)
    report = []
    exit_code = 0
    for variant in variants:
        result = check(variant, keep=args.keep)
        report.append(result)
        ok, total = summary(result)
        name = result["variant"]
        out = SANDBOX / name / "check-result.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n== {name}: {ok}/{total} checks ok")
        for key, value in result.get("checks", {}).items():
            mark = "ok " if value.get("ok") else "FAIL"
            extra = "" if value.get("ok") else f"  <- {value.get('note','')[:300]}"
            print(f"  [{mark}] {key}{extra}")
        if ok < total:
            exit_code = 1
    combined = SANDBOX / "check-all.json"
    combined.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nreport: {combined}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
