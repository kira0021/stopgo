import pytest

import approval
from delivery import DeliveryService
from payments import MockPaymentProvider
from reconcile import reconcile
from refunds import issue_refund
from webhooks import WebhookHandler


def setup():
    provider, delivery = MockPaymentProvider(), DeliveryService()
    hooks = WebhookHandler(delivery)
    ev = provider.simulate_payment(provider.create_checkout("ord_1", 9.0))
    return provider, delivery, hooks, ev


def test_payment_triggers_delivery_once():
    provider, delivery, hooks, ev = setup()
    assert hooks.handle(ev) == "access_granted"
    assert hooks.handle(ev) == "duplicate_ignored"
    assert delivery.has_access("ord_1") and len(delivery.deliveries) == 1


def test_refund_needs_founder_and_revokes_access():
    provider, delivery, hooks, ev = setup()
    hooks.handle(ev)
    st = {"approvals": []}
    payload = {"order_id": "ord_1", "amount": 9.0, "mocked": True}
    with pytest.raises(approval.ApprovalRequired):
        issue_refund(st, None, payload, provider)
    rec = approval.request(st, "issue_refund", payload, "test")
    approval.decide(st, rec["id"], "approve", by="founder")
    assert hooks.handle(issue_refund(st, rec["id"], payload, provider)) == "access_revoked"
    assert not delivery.has_access("ord_1")


def test_real_refunds_are_refused():
    provider, delivery, hooks, ev = setup()
    st = {"approvals": []}
    payload = {"order_id": "ord_1", "amount": 9.0, "mocked": False}
    rec = approval.request(st, "issue_refund", payload, "test")
    approval.decide(st, rec["id"], "approve", by="founder")
    with pytest.raises(PermissionError):
        issue_refund(st, rec["id"], payload, provider)


def test_reconciliation_balances():
    provider, delivery, hooks, ev = setup()
    hooks.handle(ev)
    r = reconcile([{"id": "ord_1", "amount": 9.0}], provider, delivery)
    assert r["balanced"] and r["payout_total"] == round(9.0 - r["fees"], 2)
