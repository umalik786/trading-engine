"""Append-only JSONL decision log. See docs/trading-engine-architecture.md §2.9.

One JSON object per line. `Decimal` serialises as a string, never a float.
Datetimes serialise as ISO-8601 with offset. Every write is flushed and
fsynced immediately -- a process killed mid-session must not lose the last
decisions it made.
"""

from __future__ import annotations

import dataclasses
import json
import os
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from engine.core.decisions import DecisionRecord

# Outside the repository, per docs/operator-context.md §3 -- `git clean -xdf`
# must not be able to destroy logged decisions.
DEFAULT_LOG_DIR = Path("C:/trading/runtime/logs")
DEFAULT_LOG_PATH = DEFAULT_LOG_DIR / "decisions.jsonl"


def _to_jsonable(value: Any) -> Any:
    """Recursively convert a value into JSON-safe primitives.

    `Decimal` -> str (never float, to keep precision exact). `datetime` ->
    ISO-8601 with offset. `Enum` -> its value. Dataclasses and mappings ->
    plain dict, recursively.
    """
    if value is None or isinstance(value, str | bool | int):
        result: Any = value
    elif isinstance(value, Decimal):
        result = str(value)
    elif isinstance(value, datetime):
        result = value.isoformat()
    elif isinstance(value, Enum):
        result = value.value
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        result = {f.name: _to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    elif isinstance(value, Mapping):
        result = {str(k): _to_jsonable(v) for k, v in value.items()}
    elif isinstance(value, list | tuple):
        result = [_to_jsonable(v) for v in value]
    else:
        raise TypeError(f"Cannot serialise {type(value).__name__} to JSON")
    return result


class DecisionLogWriter:
    """Append-only JSONL writer for `DecisionRecord`.

    Opens the log file in append mode; each `write` emits exactly one JSON
    object per line, then flushes and fsyncs before returning, so a killed
    process loses at most the write in flight, never one already returned.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else DEFAULT_LOG_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8")

    def write(self, record: DecisionRecord) -> None:
        line = json.dumps(_to_jsonable(record), separators=(",", ":"))
        self._file.write(line + "\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> DecisionLogWriter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
