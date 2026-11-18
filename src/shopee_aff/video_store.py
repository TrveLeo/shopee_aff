"""Atomic JSON state with one writer per queue, including local CLI invocations."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
import pathlib
import tempfile


def read(path: pathlib.Path, collection: str) -> dict:
    empty = [] if collection == "jobs" else {}
    if not path.exists():
        return {"version": 1, collection: empty}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get(collection), type(empty)):
        raise ValueError(f"Unsupported or invalid {collection} file: {path}")
    return data


def write(path: pathlib.Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another process is already updating this queue.") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
