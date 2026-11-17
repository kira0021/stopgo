"""Delivery and access control. MOCKED delivery (no email is sent; a local licence record is created).

Payment triggers delivery; a refund revokes access. Licence keys are random
tokens for the product, never passwords or card data.
"""
from __future__ import annotations

import secrets

MOCKED = True


class DeliveryService:
    def __init__(self):
        self.licences: dict[str, dict] = {}   # order_id -> licence
        self.deliveries: list[dict] = []      # every delivery actually performed

    def grant(self, order_id: str, charge_id: str) -> dict:
        if order_id in self.licences and self.licences[order_id]["active"]:
            return self.licences[order_id]   # already delivered: never deliver twice
        lic = {"order_id": order_id, "charge_id": charge_id, "key": "lic_" + secrets.token_hex(8),
               "active": True, "download": f"/downloads/{order_id}.zip (MOCKED)", "mocked": True}
        self.licences[order_id] = lic
        self.deliveries.append({"order_id": order_id, "mocked": True})
        return lic

    def revoke(self, order_id: str) -> None:
        if order_id in self.licences:
            self.licences[order_id]["active"] = False

    def has_access(self, order_id: str) -> bool:
        return bool(self.licences.get(order_id, {}).get("active"))
