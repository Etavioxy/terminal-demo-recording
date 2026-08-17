"""Observability helpers for the 1.0 protocol core."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any


@dataclass(frozen=True)
class Event:
    kind: str
    state: str
    session_id: str
    command_kind: str
    timeout_ms: int | None = None
    pid: int | None = None
    snapshot_hash: str | None = None
    details: dict[str, Any] | None = None

    def to_json(self) -> str:
        payload = asdict(self)
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(payload, ensure_ascii=False)


def snapshot_hash(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def emit(event: Event) -> None:
    print(f"[event] {event.to_json()}")
