"""Phase 5 Launch (Core steps: open the store; deliver automatically).

Step 1 drafts the store page and launch posts (founder posts under their own
name after approval). Step 2 runs the MOCKED sale-to-cash test.
"""
from __future__ import annotations

import html

import approval
from agents.base import Agent
from delivery import DeliveryService
from payments import FEE_FIXED, FEE_PERCENT, MockPaymentProvider
from reconcile import reconcile
from refunds import issue_refund
from webhooks import WebhookHandler


class Launcher(Agent):
    role = "launcher"

    def store_and_posts(self) -> tuple[str, str]:
        build = self.ctx.state.get("build") or {}
        tiers = (self.ctx.state.get("pricing") or {}).get("tiers", [])
        name = build.get("name", "the tool")
        stub_desc = f"{name}: {build.get('summary', '')}. Open source (MIT). Core features are free."
        res = self.ask("draft_store_page",
                       f"Write a 2-3 sentence factual product description for `{name}`: {build.get('summary')}. "
                       "No testimonials, no user counts, no urgency, no promises of results.",
                       stub_text=stub_desc)
        rows = "".join(f"<tr><td>{html.escape(str(t.get('name')))}</td><td>${html.escape(str(t.get('price_usd')))}"
                       f"{'/' + html.escape(str(t.get('per'))) if t.get('per') else ''}</td>"
                       f"<td>{html.escape(str(t.get('includes')))}</td></tr>" for t in tiers if isinstance(t, dict))
        stubbed_note = "<p><em>The core feature in this build is STUBBED.</em></p>" if build.get("core_stubbed") else ""
        store = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(name)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:680px;margin:3rem auto;padding:0 1rem}}
table{{border-collapse:collapse}}td,th{{border:1px solid #ccc;padding:.4rem .7rem}}
.mock{{background:#ffe9e9;border:1px solid #d33;padding:.5rem;border-radius:6px}}</style></head><body>
<p class="mock">MOCKED store: checkout is simulated. No payment is taken and nothing is charged.</p>
<h1>{html.escape(name)}</h1>
<p>{html.escape(res.text)}</p>{stubbed_note}
<table><tr><th>Tier</th><th>Price</th><th>Includes</th></tr>{rows}</table>
<p><button disabled>Buy (MOCKED checkout)</button></p>
<p style="font-size:.85rem">Refunds: see the refund policy. Refunds are issued by the founder.</p>
</body></html>"""
        stub_posts = (f"## Show HN draft\n\nShow HN: {name}: {build.get('summary', '')}\n\nI built this because I kept "
                      "running into the problem myself. It's open source (MIT). Feedback welcome, especially on "
                      "what's missing.\n\n## Forum post draft\n\nI'm the author of "
                      f"{name}, a small open-source CLI. Would love to hear whether it fits how you work.")
        posts = self.ask("draft_launch_posts",
                         f"Draft two short launch posts for `{name}` ({build.get('summary')}), written for the founder "
                         "to post under their own name: '## Show HN draft' and '## Forum post draft'. First person as "
                         "the founder, factual, disclose they are the author. No fake users, testimonials, urgency or "
                         "promises.", stub_text=stub_posts)
        self.ctx.write_output("phase5_step1_store_page.html", store, stubbed=res.stubbed, mocked=True)
        self.ctx.write_output("phase5_step1_launch_posts.md",
                              "# Phase 5 / Step 1: Launch posts (drafts)\n\nDrafts for the founder to post personally "
                              "after approval. StopGo never posts as the founder.\n\n" + posts.text,
                              stubbed=posts.stubbed)
        return store, posts.text

    def test_price(self) -> float:
        tiers = [t for t in (self.ctx.state.get("pricing") or {}).get("tiers", []) if isinstance(t, dict)]
        paid = []
        for t in tiers:
            try:
                if float(t.get("price_usd")) > 0:
                    paid.append(float(t["price_usd"]))
            except (TypeError, ValueError):
                continue
        return paid[0] if paid else 9.0

    def refund_payload(self, refund_order: str = "ord_2") -> dict:
        return {"order_id": refund_order, "amount": self.test_price(), "mocked": True}

    def sale_to_cash_test(self, refund_approval_id: str) -> dict:
        """Run the MOCKED sale-to-cash flow and write outputs/payment_test_log.md."""
        state = self.ctx.state
        price = self.test_price()
        payload = self.refund_payload()
        refund_order = payload["order_id"]
        provider, delivery = MockPaymentProvider(), DeliveryService()
        hooks = WebhookHandler(delivery)
        orders = [{"id": f"ord_{i}", "amount": price} for i in (1, 2, 3)]
        log = ["# Payment and delivery test log", "",
               "**MOCKED.** No payment provider (real or sandbox) is called. Events are simulated in-process.",
               f"Price under test: ${price:.2f}. Fee model (ASSUMPTION): {FEE_PERCENT:.1%} + ${FEE_FIXED:.2f} per charge.",
               "", "## Events", "", "| # | Step | Result |", "|---|---|---|"]
        n = 0

        def step(desc, result):
            nonlocal n
            n += 1
            log.append(f"| {n} | {desc} | {result} |")

        events = {}
        for o in orders:
            sess = provider.create_checkout(o["id"], o["amount"])
            ev = provider.simulate_payment(sess)
            events[o["id"]] = ev
            step(f"payment.succeeded for {o['id']} ({ev['id']})", hooks.handle(ev))
        dup = hooks.handle(events["ord_1"])
        step("same payment webhook for ord_1 delivered again (provider retry)", dup)

        try:
            issue_refund(state, None, payload, provider)
            blocked = False
        except approval.ApprovalRequired:
            blocked = True
        step(f"refund {refund_order} without founder approval", "blocked (ApprovalRequired)" if blocked else "NOT BLOCKED")
        rec = approval.get(state, refund_approval_id)
        if rec["status"] == "approved":
            rf_ev = issue_refund(state, refund_approval_id, payload, provider)
            step(f"refund {refund_order} with founder approval {refund_approval_id} (MOCKED)", hooks.handle(rf_ev))
            step(f"same refund webhook delivered again", hooks.handle(rf_ev))
        else:
            step(f"refund {refund_order}: founder rejected the mocked refund test", "skipped")
        rec_ = reconcile(orders, provider, delivery)
        checks = {
            "payment_grants_access": delivery.has_access("ord_1") and delivery.has_access("ord_3"),
            "duplicate_webhook_no_double_delivery": dup == "duplicate_ignored" and len(delivery.deliveries) == 3,
            "refund_blocked_without_approval": blocked,
            "refund_revokes_access": (not delivery.has_access(refund_order)) if rec["status"] == "approved" else True,
            "reconciliation_balanced": rec_["balanced"],
        }
        log += ["", "## Reconciliation", "", "| Order | Amount | Paid | Fee | Refunded | Access |", "|---|---|---|---|---|---|"]
        log += [f"| {r['order']} | {r['amount']:.2f} | {r['paid']} | {r['fee']:.2f} | {r['refunded']} | {r['access']} |"
                for r in rec_["rows"]]
        log += ["", f"Gross {rec_['gross']:.2f} - fees {rec_['fees']:.2f} - refunds {rec_['refunds']:.2f} = "
                f"expected payout {rec_['expected_net']:.2f}; mocked payout {rec_['payout_total']:.2f}.",
                f"Problems: {', '.join(rec_['problems']) or 'none'}", "", "## Checks", ""]
        log += [f"- {'PASS' if v else 'FAIL'}: {k}" for k, v in checks.items()]
        self.ctx.write_output("payment_test_log.md", "\n".join(log), mocked=True)
        self.log("mock_sale_to_cash_test", model=None, outcome="pass" if all(checks.values()) else "fail")
        state["sale_to_cash"] = {"checks": checks, "reconciliation": {k: v for k, v in rec_.items() if k != "rows"}}
        return checks
