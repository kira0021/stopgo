"""Founder approval, enforced in code.

Anything that would be published, sent, spent or signed goes through
`require()`, which raises unless the founder approved *exactly this payload*
(matched by SHA-256). Editing the content after approval voids the approval.

Approvals are only created by the orchestrator and only decided through the
founder-facing UI or CLI (`decide`). No agent can decide an approval.
"""
from __future__ import annotations

import functools
import hashlib
import json
import uuid

from decision_log import utc_now

FOUNDER = "founder"


class ApprovalRequired(PermissionError):
    """Raised when a gated action has no matching founder approval."""


class ApprovalRejected(PermissionError):
    """Raised when the founder rejected the action."""


def payload_hash(payload) -> str:
    if not isinstance(payload, (str, bytes)):
        payload = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    if isinstance(payload, str):
        payload = payload.encode()
    return hashlib.sha256(payload).hexdigest()


def request(state: dict, action: str, payload, summary: str, *, kind: str = "approval",
            options: list[str] | None = None, recommended: str | None = None) -> dict:
    """Create a pending approval request on the run state and return it."""
    rec = {
        "id": f"apr_{uuid.uuid4().hex[:10]}",
        "kind": kind,
        "action": action,
        "summary": summary,
        "payload_hash": payload_hash(payload),
        "options": options or ["approve", "reject"],
        "recommended": recommended,
        "status": "pending",
        "requested_at": utc_now(),
        "decided_at": None,
        "decided_by": None,
        "decision": None,
        "note": None,
    }
    state.setdefault("approvals", []).append(rec)
    return rec


def get(state: dict, approval_id: str) -> dict:
    for rec in state.get("approvals", []):
        if rec["id"] == approval_id:
            return rec
    raise KeyError(approval_id)


def pending(state: dict) -> list[dict]:
    return [r for r in state.get("approvals", []) if r["status"] == "pending"]


def decide(state: dict, approval_id: str, decision: str, *, by: str, note: str | None = None) -> dict:
    """Record the founder's decision. Only the founder may decide."""
    if by != FOUNDER:
        raise PermissionError("only the founder can decide approvals")
    rec = get(state, approval_id)
    if rec["status"] != "pending":
        raise ValueError(f"approval {approval_id} already decided ({rec['status']})")
    if decision not in rec["options"]:
        raise ValueError(f"decision must be one of {rec['options']}")
    rec["decision"] = decision
    if rec["kind"] == "approval":
        rec["status"] = "approved" if decision == "approve" else "rejected"
    else:  # gate decisions: go / repeat / pivot / stop
        rec["status"] = "decided"
    rec["decided_by"] = FOUNDER
    rec["decided_at"] = utc_now()
    rec["note"] = note
    return rec


def require(state: dict, approval_id: str | None, payload) -> dict:
    """Raise unless the founder approved this exact payload."""
    if not approval_id:
        raise ApprovalRequired("no approval id given; founder approval is required")
    try:
        rec = get(state, approval_id)
    except KeyError:
        raise ApprovalRequired(f"unknown approval {approval_id}") from None
    if rec["status"] == "rejected":
        raise ApprovalRejected(f"founder rejected {rec['action']}")
    if rec["status"] != "approved" or rec["decided_by"] != FOUNDER:
        raise ApprovalRequired(f"{rec['action']} is not approved by the founder (status: {rec['status']})")
    if rec["payload_hash"] != payload_hash(payload):
        raise ApprovalRequired(f"content changed after approval of {rec['action']}; approve again")
    return rec


def gated(action: str):
    """Decorator for side-effect functions: f(state, approval_id, payload, ...)."""

    def wrap(fn):
        @functools.wraps(fn)
        def inner(state, approval_id, payload, *args, **kwargs):
            rec = require(state, approval_id, payload)
            if rec["action"] != action:
                raise ApprovalRequired(f"approval {approval_id} is for {rec['action']}, not {action}")
            return fn(state, approval_id, payload, *args, **kwargs)

        inner.gated_action = action
        return inner

    return wrap
