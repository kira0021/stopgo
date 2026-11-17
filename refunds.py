"""Refunds: never automatic. A refund runs only with a founder approval for that exact refund.

In this prototype the provider is MOCKED, so no money moves.
"""
from __future__ import annotations

from approval import gated
from payments import MockPaymentProvider


@gated("issue_refund")
def issue_refund(state: dict, approval_id: str, payload: dict, provider: MockPaymentProvider) -> dict:
    """payload = {"order_id", "amount", "mocked": True}; returns the provider's refund event."""
    if not payload.get("mocked"):
        raise PermissionError("StopGo only issues MOCKED refunds; real refunds are done by the founder directly")
    charge = next((c for c in provider.charges.values() if c["order_id"] == payload["order_id"]), None)
    if charge is None or abs(charge["amount"] - payload["amount"]) > 0.001:
        raise ValueError("refund does not match a charge for that order and amount")
    return provider.refund(charge["id"])
