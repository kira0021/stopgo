"""Append-only decision log: one entry per agent action.

Every entry carries the five required keys (action, sources, model, cost,
approved_by) plus timestamp and agent. Extra keys (outcome, run_id, detail,
tokens) are allowed.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone

REQUIRED_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")
_lock = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DecisionLog:
    def __init__(self, path: str, run_id: str | None = None):
        self.path = path
        self.run_id = run_id
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def append(
        self,
        agent: str,
        action: str,
        *,
        sources: list[str] | None = None,
        model: str | None = None,
        cost: float = 0,
        approved_by: str | None = None,
        **extra,
    ) -> dict:
        if approved_by not in (None, "founder"):
            raise ValueError("approved_by must be 'founder' or None")
        entry = {
            "timestamp": utc_now(),
            "agent": agent,
            "action": action,
            "sources": list(sources or []),
            "model": model,
            "cost": float(cost),
            "approved_by": approved_by,
        }
        if self.run_id:
            entry["run_id"] = self.run_id
        entry.update({k: v for k, v in extra.items() if v is not None})
        with _lock:
            entries = self.read()
            entries.append(entry)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=1, ensure_ascii=False)
            os.replace(tmp, self.path)
        return entry

    def read(self) -> list[dict]:
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)


def validate_entries(entries: list[dict]) -> list[str]:
    """Return a list of problems; empty means the log is valid."""
    problems = []
    if not isinstance(entries, list):
        return ["log is not a JSON array"]
    for i, e in enumerate(entries):
        for k in REQUIRED_KEYS:
            if k not in e:
                problems.append(f"entry {i}: missing '{k}'")
        if not isinstance(e.get("action"), str):
            problems.append(f"entry {i}: action must be a string")
        if not isinstance(e.get("sources"), list):
            problems.append(f"entry {i}: sources must be a list")
        if e.get("model") is not None and not isinstance(e.get("model"), str):
            problems.append(f"entry {i}: model must be a string or null")
        if not isinstance(e.get("cost"), (int, float)):
            problems.append(f"entry {i}: cost must be a number")
        if e.get("approved_by") not in (None, "founder"):
            problems.append(f"entry {i}: approved_by must be 'founder' or null")
    return problems
