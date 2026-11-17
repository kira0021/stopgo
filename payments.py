"""MOCKED payment provider. No real or sandbox payment API is called, ever.

It produces the same event shapes a real provider would (checkout session,
payment.succeeded, refund.succeeded, payout) so the sale-to-cash logic in
webhooks.py / delivery.py / refunds.py / reconcile.py can be tested end to end.
"""
from __future__ import annotations

import uuid

MOCKED = True
# ASSUMPTION: a typical card-processing fee of 2.9% + $0.30 per charge; used only for the mock.
FEE_PERCENT = 0.029
FEE_FIXED = 0.30


def _id(prefix: str) -> str:
    return f"{prefix}_mock_{uuid.uuid4().hex[:8]}"


def fee_for(amount: float) -> float:
    return round(amount * FEE_PERCENT + FEE_FIXED, 2)


class MockPaymentProvider:
    """Holds no money. Every object it returns has mocked=True."""

    def __init__(self):
        self.charges: dict[str, dict] = {}
        self.refunds: dict[str, dict] = {}

    def create_checkout(self, order_id: str, amount: float, currency: str = "usd") -> dict:
        return {"id": _id("cs"), "order_id": order_id, "amount": amount, "currency": currency,
                "status": "open", "mocked": True}

    def simulate_payment(self, session: dict) -> dict:
        """What a provider webhook would send after a buyer pays. MOCKED."""
        charge = {"id": _id("ch"), "order_id": session["order_id"], "amount": session["amount"],
                  "fee": fee_for(session["amount"]), "mocked": True}
        self.charges[charge["id"]] = charge
        return {"id": _id("evt"), "type": "payment.succeeded", "data": charge, "mocked": True}

    def refund(self, charge_id: str) -> dict:
        """Only refunds.py calls this, and only with a founder approval. MOCKED."""
        ch = self.charges[charge_id]
        rf = {"id": _id("re"), "charge_id": charge_id, "order_id": ch["order_id"], "amount": ch["amount"],
              "mocked": True}
        self.refunds[rf["id"]] = rf
        return {"id": _id("evt"), "type": "refund.succeeded", "data": rf, "mocked": True}

    def payouts(self) -> list[dict]:
        refunded = {r["charge_id"] for r in self.refunds.values()}
        gross = sum(c["amount"] for c in self.charges.values())
        fees = sum(c["fee"] for c in self.charges.values())
        refunds = sum(c["amount"] for cid, c in self.charges.items() if cid in refunded)
        return [{"id": _id("po"), "amount": round(gross - fees - refunds, 2), "mocked": True}]
