"""OpenAI-compatible chat client plus a deterministic mock for tests.

Credentials are never written to project state. The API key is read from the
environment (``DEEPSEEK_API_KEY`` / ``LEARNARK_API_KEY``); the variants only ever
record the model name and token counts.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from .fsutil import LearnError, append_jsonl, sha256_text

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


@dataclass
class LLMResult:
    text: str
    model: str
    mode: str
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    raw_finish_reason: str | None = None


class LLMUnavailable(LearnError):
    pass


class LLM:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 2,
        usage_file: str | Path | None = None,
    ):
        self.api_key = api_key or os.environ.get("LEARNARK_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("LEARNARK_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or os.environ.get("LEARNARK_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        self.max_retries = max_retries
        self.usage_file = Path(usage_file) if usage_file else None
        self.calls: list[dict] = []

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def describe(self) -> dict:
        return {"mode": "api" if self.available else "unavailable", "model": self.model, "base_url": self.base_url}

    # -- core call -------------------------------------------------------
    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.5,
        max_tokens: int = 1600,
        json_object: bool = False,
    ) -> LLMResult:
        if not self.available:
            raise LLMUnavailable(
                "no API key configured: set DEEPSEEK_API_KEY (or LEARNARK_API_KEY), "
                "or use --offline / LEARNARK_LLM=mock for the scripted mentor."
            )
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if json_object:
            payload["response_format"] = {"type": "json_object"}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        started = time.time()
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                choice = (data.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content") or ""
                usage = data.get("usage") or {}
                result = LLMResult(
                    text=text.strip(),
                    model=data.get("model", self.model),
                    mode="api",
                    usage=usage,
                    latency_ms=int((time.time() - started) * 1000),
                    raw_finish_reason=choice.get("finish_reason"),
                )
                self._record(result, messages)
                return result
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "replace")[:400]
                except Exception:  # pragma: no cover - best effort
                    pass
                last_error = LLMError(f"HTTP {exc.code} from {self.base_url}: {detail}")
                if exc.code in (401, 403):
                    raise LLMError(
                        "the configured API key was rejected (HTTP %s). "
                        "Check DEEPSEEK_API_KEY before retrying." % exc.code
                    ) from exc
                if exc.code not in (409, 429, 500, 502, 503, 504):
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                last_error = LLMError(f"network error talking to {self.base_url}: {exc}")
            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))
        raise last_error or LLMError("unknown LLM failure")

    def _record(self, result: LLMResult, messages: list[dict]) -> None:
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "model": result.model,
            "mode": result.mode,
            "latency_ms": result.latency_ms,
            "prompt_sha256": sha256_text(json.dumps(messages, ensure_ascii=False))[:16],
            "usage": result.usage,
        }
        self.calls.append(entry)
        if self.usage_file:
            try:
                append_jsonl(self.usage_file, entry, fsync=False)
            except OSError:
                pass


class LLMError(LearnError):
    pass


class MockLLM:
    """Deterministic stand-in. Replies come from a JSONL script.

    Each line: ``{"match": "optional substring", "reply": "text"}``.
    Unmatched calls consume the next reply in order, then fall back to a
    clearly-labelled canned answer so that tests never silently look real.
    """

    mode = "mock"

    def __init__(self, script_path: str | Path | None = None, fallback: str | None = None):
        self.script_path = Path(script_path) if script_path else None
        self.script: list[dict] = []
        self.index = 0
        self.calls: list[dict] = []
        self.fallback = fallback or (
            "[MOCK MENTOR] This reply comes from the offline scripted mentor, not a language model.\n"
            "In offline mode the flow still records attempts, clues and next steps, but teaching text is canned."
        )
        if self.script_path and self.script_path.exists():
            for line in self.script_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    self.script.append(json.loads(line))

    @property
    def available(self) -> bool:
        return True

    def describe(self) -> dict:
        return {"mode": "mock", "model": "mock", "base_url": "", "script": str(self.script_path or "")}

    def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.5,
        max_tokens: int = 1600,
        json_object: bool = False,
    ) -> LLMResult:
        user_text = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_text = message.get("content", "")
                break
        reply = None
        for entry in self.script[self.index :]:
            match = entry.get("match")
            if not match or match in user_text:
                reply = entry.get("reply", "")
                self.index = self.script.index(entry) + 1
                break
        if reply is None:
            reply = self.fallback
        self.calls.append({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "mode": "mock", "chars": len(reply)})
        return LLMResult(text=reply, model="mock", mode="mock", usage={}, latency_ms=0)


def from_env(usage_file: str | Path | None = None):
    """Pick the mentor backend: explicit env override, else API when keyed, else mock."""
    mode = (os.environ.get("LEARNARK_LLM") or "auto").strip().lower()
    script = os.environ.get("LEARNARK_MOCK_SCRIPT")
    if mode == "mock":
        return MockLLM(script)
    api = LLM(usage_file=usage_file)
    if mode == "api":
        return api
    if api.available:
        return api
    return MockLLM(script)
