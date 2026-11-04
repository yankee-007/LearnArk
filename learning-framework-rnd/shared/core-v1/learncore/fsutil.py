"""Filesystem primitives: durability, locks, tolerant JSON/JSONL access."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


class LearnError(Exception):
    """Base class for expected, user-facing failures (exit code 2)."""


class StateCorrupt(LearnError):
    """A state file exists but cannot be parsed and no usable backup exists."""


class StaleWrite(LearnError):
    """A writer tried to persist a document based on an outdated version."""


class LockTimeout(LearnError):
    """Another process held the project lock for longer than the caller allowed."""


_MISSING = object()


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":  # directory fsync is not supported on Windows
        return
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_text(path: str | os.PathLike, text: str, *, backup: bool = False) -> None:
    """Write ``text`` so that readers never observe a partially written file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if backup:
        # Keep the most recently *successful* content next to the document, so a
        # later corruption of the document itself recovers without losing a write.
        try:
            bak = path.with_name(path.name + ".bak")
            tmp_bak = tempfile.mkstemp(prefix=path.name + ".bak.", suffix=".tmp", dir=str(path.parent))
            with os.fdopen(tmp_bak[0], "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_bak[1], bak)
        except OSError:
            pass
    _fsync_dir(path.parent)


def read_text(path: str | os.PathLike, default=_MISSING) -> str:
    path = Path(path)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if default is _MISSING:
            raise
        return default
    except UnicodeDecodeError as exc:
        raise StateCorrupt(f"{path} is not valid UTF-8: {exc}") from exc


def write_json(path: str | os.PathLike, obj, *, backup: bool = False) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n", backup=backup)


def _read_json_file(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StateCorrupt(f"{path} is not valid JSON: {exc}") from exc


def read_json(path: str | os.PathLike, default=_MISSING):
    """Read JSON, transparently falling back to ``<name>.bak`` when corrupt.

    Returns a tuple-free value; use :func:`load_json_state` when you need to know
    whether a repair happened.
    """
    path = Path(path)
    try:
        return _read_json_file(path)
    except FileNotFoundError:
        if default is _MISSING:
            raise
        return default
    except StateCorrupt:
        bak = path.with_name(path.name + ".bak")
        if bak.exists():
            try:
                return _read_json_file(bak)
            except (FileNotFoundError, StateCorrupt):
                pass
        raise


def load_json_state(path: str | os.PathLike, default):
    """Return ``(value, repaired, note)``; repairs from ``.bak`` in place."""
    path = Path(path)
    try:
        return _read_json_file(path), False, ""
    except FileNotFoundError:
        return default, False, ""
    except StateCorrupt as exc:
        bak = path.with_name(path.name + ".bak")
        if bak.exists():
            try:
                value = _read_json_file(bak)
                atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")
                return value, True, f"recovered {path.name} from backup ({exc})"
            except (FileNotFoundError, StateCorrupt):
                pass
        raise


def append_jsonl(path: str | os.PathLike, record: dict, *, fsync: bool = True) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A crash can leave a partial last line. Appending directly would concatenate
    # the new record onto it, silently losing the new event and corrupting the
    # file for every later read. Drop only that incomplete tail first.
    if path.exists() and path.stat().st_size:
        with open(path, "rb+") as probe:
            probe.seek(-1, os.SEEK_END)
            trailing_newline = probe.read(1) == b"\n"
        if not trailing_newline:
            data = path.read_bytes()
            cutoff = data.rfind(b"\n")
            keep = data[: cutoff + 1] if cutoff >= 0 else b""
            with open(path, "wb") as repair:
                repair.write(keep)
                repair.flush()
                os.fsync(repair.fileno())
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
        fh.flush()
        if fsync:
            os.fsync(fh.fileno())


def read_jsonl(path: str | os.PathLike, *, tolerate_tail: bool = True) -> list:
    """Read JSONL, skipping a torn final line (harmless crash residue)."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    out = []
    lines = raw.splitlines()
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            if tolerate_tail and i >= len(lines) - 1:
                break
            raise StateCorrupt(f"{path} line {i + 1} is not valid JSON")
    return out


@contextmanager
def file_lock(path: str | os.PathLike, timeout: float = 20.0, poll: float = 0.03):
    """Advisory exclusive lock (cross-platform, no third-party dependency)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+b")
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK, errno.EPERM):
                fh.close()
                raise
            if time.monotonic() >= deadline:
                fh.close()
                raise LockTimeout(
                    f"another LearnArk process is writing this project (lock: {path}). "
                    "Wait a moment and retry."
                ) from exc
            time.sleep(poll)
    try:
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()} at={time.time():.3f}\n".encode("ascii"))
        fh.flush()
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def short_hash(text: str, n: int = 10) -> str:
    return sha256_text(text)[:n]


def find_project_root(start: str | os.PathLike | None = None, marker: str = ".learnark") -> Path:
    """Walk upwards until a directory containing ``marker`` is found."""
    here = Path(start or os.getcwd()).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / marker).is_dir():
            return candidate
    raise LearnError(
        f"not inside a LearnArk project (no {marker}/ found from {here}). "
        f"Run the variant's 'init' command first."
    )
