"""Reconciliation: match orders, payments, fees, refunds and payouts (on MOCKED data)."""
from __future__ import annotations


def reconcile(orders: list[dict], provider, delivery) -> dict:
    charges_by_order = {c["order_id"]: c for c in provider.charges.values()}
    refunded_orders = {r["order_id"] for r in provider.refunds.values()}
    rows, problems = [], []
    for o in orders:
        ch = charges_by_order.get(o["id"])
        paid = ch is not None
        refunded = o["id"] in refunded_orders
        access = delivery.has_access(o["id"])
        expected_access = paid and not refunded
        if paid and abs(ch["amount"] - o["amount"]) > 0.001:
            problems.append(f"{o['id']}: charged {ch['amount']} but order says {o['amount']}")
        if access != expected_access:
            problems.append(f"{o['id']}: access={access} but expected {expected_access}")
        rows.append({"order": o["id"], "amount": o["amount"], "paid": paid, "fee": ch["fee"] if ch else 0.0,
                     "refunded": refunded, "access": access})
    gross = round(sum(r["amount"] for r in rows if r["paid"]), 2)
    fees = round(sum(r["fee"] for r in rows), 2)
    refunds = round(sum(r["amount"] for r in rows if r["refunded"]), 2)
    expected_net = round(gross - fees - refunds, 2)
    payout_total = round(sum(p["amount"] for p in provider.payouts()), 2)
    if abs(payout_total - expected_net) > 0.001:
        problems.append(f"payout {payout_total} != gross - fees - refunds {expected_net}")
    deliveries = {}
    for d in delivery.deliveries:
        deliveries[d["order_id"]] = deliveries.get(d["order_id"], 0) + 1
    for oid, n in deliveries.items():
        if n > 1:
            problems.append(f"{oid}: delivered {n} times")
    return {"rows": rows, "gross": gross, "fees": fees, "refunds": refunds, "expected_net": expected_net,
            "payout_total": payout_total, "problems": problems, "balanced": not problems}
