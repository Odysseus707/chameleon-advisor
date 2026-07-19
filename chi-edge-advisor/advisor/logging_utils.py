"""Structured JSONL logging of every pipeline stage.

Each pipeline run appends one JSON object per stage to a JSONL file so runs can
be replayed and graded against a benchmark later. Stages: read, retrieve,
reason, validate, emit (plus arbitrary ad-hoc events like `probe`).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings


def _json_default(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, tuple)):
        return list(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


class RunLogger:
    """Append-only JSONL logger scoped to a single pipeline run."""

    def __init__(self, run_id: str | None = None, log_path: Path | None = None):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.log_path = Path(log_path or settings.log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, stage: str, **payload: Any) -> None:
        record = {
            "run_id": self.run_id,
            "stage": stage,
            "ts": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=_json_default) + "\n")

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"RunLogger(run_id={self.run_id!r}, log_path={self.log_path!s})"
