"""Idempotent webhook handler: the only path from a payment event to delivery.

Each provider event id is processed at most once, so a retried or duplicated
webhook can never deliver twice or revoke twice.
"""
from __future__ import annotations

from delivery import DeliveryService


class WebhookHandler:
    def __init__(self, delivery: DeliveryService):
        self.delivery = delivery
        self.processed: set[str] = set()
        self.journal: list[dict] = []

    def handle(self, event: dict) -> str:
        if event["id"] in self.processed:
            self.journal.append({"event": event["id"], "type": event["type"], "result": "duplicate_ignored"})
            return "duplicate_ignored"
        self.processed.add(event["id"])
        data = event["data"]
        if event["type"] == "payment.succeeded":
            self.delivery.grant(data["order_id"], data["id"])
            result = "access_granted"
        elif event["type"] == "refund.succeeded":
            self.delivery.revoke(data["order_id"])
            result = "access_revoked"
        else:
            result = "ignored_unknown_type"
        self.journal.append({"event": event["id"], "type": event["type"], "order": data.get("order_id"),
                             "result": result})
        return result
