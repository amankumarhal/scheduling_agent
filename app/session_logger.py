from __future__ import annotations

import json
import queue
import re
import threading
import atexit
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings


def _safe_session_id(session_id: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", session_id.strip())
    return safe[:80] or "default"


class SessionLogger:
    """Append-only JSONL session logger for auditing and debugging."""

    def __init__(self, log_dir: str | None = None):
        settings = get_settings()
        self.log_dir = Path(log_dir or settings.session_log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._queue: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()
        self._closed = False
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        atexit.register(self.shutdown)

    def log(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        if self._closed:
            return
        record = {
            "timestamp": datetime.utcnow().isoformat(),
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
        }
        path = self.log_dir / f"{_safe_session_id(session_id)}.jsonl"
        self._queue.put((str(path), record))

    def _worker(self) -> None:
        handles: dict[str, Any] = {}
        while True:
            item = self._queue.get()
            if item is None:
                break
            path, record = item
            handle = handles.get(path)
            if handle is None:
                handle = Path(path).open("a", encoding="utf-8")
            handles[path] = handle
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            handle.flush()
        for handle in handles.values():
            handle.close()

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._thread.join(timeout=2)
