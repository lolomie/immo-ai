"""
Structured pipeline logger.
Every automation step is written as a JSON-Lines record to
logs/pipeline/YYYY-MM-DD.jsonl for full auditability.
"""

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from .config import PIPELINE_LOGS_DIR

_std = logging.getLogger(__name__)


class PipelineLogger:
    """
    Attach one instance per automation run (one per expose_id).
    All entries share the same expose_id and run_id for correlation.
    """

    def __init__(self, expose_id: str, run_id: str):
        self.expose_id = expose_id
        self.run_id = run_id
        os.makedirs(PIPELINE_LOGS_DIR, exist_ok=True)

    def _log_path(self) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return os.path.join(PIPELINE_LOGS_DIR, f"{date_str}.jsonl")

    def _write(self, record: dict) -> None:
        record["expose_id"] = self.expose_id
        record["run_id"] = self.run_id
        record["timestamp"] = datetime.now(timezone.utc).isoformat()
        line = json.dumps(record, ensure_ascii=False)
        try:
            with open(self._log_path(), "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            _std.error("Failed to write pipeline log: %s", e)
        # also emit to standard logger
        level = logging.ERROR if record.get("status") == "error" else logging.INFO
        _std.log(level, "[pipeline] %s", line)

    def start(self, input_data: dict) -> None:
        self._write({
            "action": "pipeline_start",
            "status": "ok",
            "input": input_data,
        })

    def step(
        self,
        action: str,
        status: str,
        detail: Optional[Any] = None,
        error: Optional[str] = None,
    ) -> None:
        record: dict = {"action": action, "status": status}
        if detail is not None:
            record["detail"] = detail
        if error:
            record["error"] = error
        self._write(record)

    def error(self, action: str, exc: Exception) -> None:
        self._write({
            "action": action,
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })

    def finish(self, final_status: str, doc_url: Optional[str] = None) -> None:
        record: dict = {"action": "pipeline_finish", "status": final_status}
        if doc_url:
            record["doc_url"] = doc_url
        self._write(record)


def get_recent_logs(n_days: int = 7) -> list[dict]:
    """Return all log entries from the last n_days for the dashboard."""
    entries: list[dict] = []
    if not os.path.isdir(PIPELINE_LOGS_DIR):
        return entries
    for fname in sorted(os.listdir(PIPELINE_LOGS_DIR), reverse=True)[:n_days]:
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(PIPELINE_LOGS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        except OSError:
            pass
    return entries
