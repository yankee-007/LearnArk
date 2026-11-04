"""learncore v1.0.2 -- pinned shared runtime core for LearnArk research variants.

This package is copied verbatim into each variant (``variants/<id>/runtime/learncore``)
and pinned by ``CORE_VERSION``. Variants may extend behaviour in their own modules
but MUST NOT edit their vendored copy without re-vendoring, so that a version that
was tested stays the version that ships.

Public surface (see shared/spec-core.md):
    fsutil   -- atomic writes, json helpers, file locks, errors
    clock    -- real / simulated clock
    events   -- append-only journal with idempotent dedupe keys
    store    -- versioned documents with compare-and-swap writes
    llm      -- OpenAI-compatible chat client (+ deterministic mock)
    mentor   -- mentor turn assembly and machine-readable update extraction
    sync     -- allowlisted git sync with explicit written/committed/pushed states
    cli      -- stdio, error envelope, json output helpers
"""

CORE_VERSION = "1.0.5"

__all__ = [
    "CORE_VERSION",
    "fsutil",
    "clock",
    "events",
    "store",
    "llm",
    "mentor",
    "sync",
    "cli",
]
