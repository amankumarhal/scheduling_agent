from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings


def _safe_session_id(session_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", session_id.strip())
    return safe[:80] or "default"


class SessionLogger:
    """Append-only JSONL session logger for demo auditing and debugging."""

    def __init__(self, log_dir: str | None = None):
        settings = get_settings()
        self.log_dir = Path(log_dir or settings.session_log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
        }
        path = self.log_dir / f"{_safe_session_id(session_id)}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

