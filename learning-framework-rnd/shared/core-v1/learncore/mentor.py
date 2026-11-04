"""Mentor turn assembly shared by every variant.

Contract
--------
A mentor reply is human-readable text, optionally followed by exactly one fenced
machine block::

    ```learn-update
    {"help_level": 1, "attempt": {"activity_id": "...", "correct": true}, ...}
    ```

The runtime never trusts prose. It only applies what the block says after
validating it against the direction's own schema; malformed blocks are recorded
as incidents rather than silently ignored, so that a broken mentor protocol is
visible in evidence instead of hiding.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_BLOCK_RE = re.compile(
    r"```learn-update[ \t]*\r?\n(?P<body>.*?)```|"
    r"<learn-update>(?P<tagged>.*?)</learn-update>",
    re.DOTALL | re.IGNORECASE,
)

UPDATE_HELP = """At the very end of your reply, add exactly one machine block:
```learn-update
{"help_level": 0, "attempt": {"activity_id": "ID", "correct": false}, "misconception": "short label or null", "next": "what to do next session, one sentence", "mastery_delta": 0}
```
Rules for the block: valid JSON, no comments, no trailing text after the closing fence.
help_level: 0 = learner worked without help, 1 = small hint, 2 = step-by-step guidance, 3 = you effectively did it for them.
Never claim an attempt is correct unless the learner's own message contains the answer."""


@dataclass
class MentorTurn:
    text: str
    updates: dict | None = None
    update_error: str = ""
    raw: str = ""
    mode: str = "api"
    usage: dict = field(default_factory=dict)
    model: str = ""


def extract_update(raw: str) -> tuple[str, dict | None, str]:
    """Return ``(visible_text, updates, error)``."""
    match = _BLOCK_RE.search(raw or "")
    if not match:
        return (raw or "").strip(), None, ""
    body = (match.group("body") or match.group("tagged") or "").strip()
    body = body.strip("`").strip()
    visible = (raw[: match.start()] + "\n" + raw[match.end() :]).strip()
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        return visible, None, f"invalid learn-update JSON: {exc}"
    if not isinstance(parsed, dict):
        return visible, None, "learn-update must be a JSON object"
    return visible, parsed, ""


def build_messages(
    *,
    system: str,
    context: str,
    user: str,
    transcript: list[dict] | None = None,
    max_history: int = 6,
) -> list[dict]:
    """Assemble a compact prompt: stable system, compact context, recent turns."""
    messages = [{"role": "system", "content": system.strip()}]
    if context.strip():
        messages.append(
            {
                "role": "system",
                "content": "Project state (authoritative, condensed by the runtime):\n" + context.strip(),
            }
        )
    for turn in (transcript or [])[-max_history:]:
        role = "assistant" if turn.get("role") == "mentor" else "user"
        content = (turn.get("text") or "").strip()
        if content:
            messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": user.strip()})
    return messages


def run_turn(
    llm,
    *,
    system: str,
    context: str,
    user: str,
    transcript: list[dict] | None = None,
    max_tokens: int = 1400,
    temperature: float = 0.5,
) -> MentorTurn:
    messages = build_messages(system=system, context=context, user=user, transcript=transcript)
    result = llm.chat(messages, temperature=temperature, max_tokens=max_tokens)
    text, updates, error = extract_update(result.text)
    return MentorTurn(
        text=text,
        updates=updates,
        update_error=error,
        raw=result.text,
        mode=result.mode,
        usage=result.usage,
        model=result.model,
    )


def validate_updates(updates: dict | None, *, max_help_level: int = 3) -> list[str]:
    """Direction-agnostic sanity checks. Returns a list of problems (empty = ok)."""
    if updates is None:
        return []
    problems: list[str] = []
    help_level = updates.get("help_level")
    if help_level is not None:
        if not isinstance(help_level, int) or not 0 <= help_level <= max_help_level:
            problems.append(f"help_level must be an int in 0..{max_help_level}, got {help_level!r}")
    attempt = updates.get("attempt")
    if attempt is not None and not isinstance(attempt, dict):
        problems.append("attempt must be an object")
    return problems
