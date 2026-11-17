"""Phase 6 Operate and learn: support FAQ, metrics, persevere-or-pivot memo."""
from __future__ import annotations

import gates
from agents.base import Agent


class Operator(Agent):
    role = "operator"

    def support_and_metrics(self) -> dict:
        build = self.ctx.state.get("build") or {}
        stub = ("## Support FAQ (draft)\n\n**How do I install it?** `pip install .` from the repository.\n\n"
                "**Is my data sent anywhere?** No. The CLI runs locally.\n\n"
                "**How do I get a refund?** Email the founder within 14 days; the founder reviews and issues it.\n\n"
                "**Where do I report a bug?** Open an issue in the project's repository.")
        res = self.ask("draft_support_faq",
                       f"Write a short support FAQ (4-6 Q&As, markdown, heading '## Support FAQ (draft)') for "
                       f"`{build.get('name')}`: {build.get('summary')}. Refunds are reviewed and issued by the founder. "
                       "No promises.", stub_text=stub)
        s2c = self.ctx.state.get("sale_to_cash") or {}
        rec = s2c.get("reconciliation") or {}
        real = (self.ctx.state.get("evidence") or {}).get("real_buyers")
        metrics = ["# Phase 6 / Step 1: Support and metrics", "", res.text, "",
                   "## Metrics", "",
                   "| Metric | Value | Source |", "|---|---|---|",
                   f"| Real buyers | {real if real is not None else 'none reported'} | founder-reported |",
                   f"| Mock orders in sale-to-cash test | 3 | MOCKED simulation |",
                   f"| Mock gross / fees / refunds | {rec.get('gross', 0):.2f} / {rec.get('fees', 0):.2f} / "
                   f"{rec.get('refunds', 0):.2f} | MOCKED simulation |",
                   "", "Mocked numbers are test fixtures, not traction."]
        self.ctx.write_output("phase6_step1_support_and_metrics.md", "\n".join(metrics), stubbed=res.stubbed)
        return {"real_buyers": real}

    def memo(self, gate: gates.GateResult) -> None:
        stub = ("## What we learned\n- Evidence so far comes from interviews and the waitlist test.\n"
                "## What we do not know\n- Whether people will pay: no real sales yet.\n"
                "## Next experiment\n- Open the store for real (founder approval required) and track the first 10 buyers.")
        res = self.ask("draft_persevere_or_pivot_memo",
                       f"Gate history: {self.ctx.state.get('gate_history')}\nGate now: {gate.recommended}: {gate.reasons}\n\n"
                       "Write a short memo in markdown with sections '## What we learned', '## What we do not know', "
                       "'## Next experiment'. Be honest about missing data; no promises.", stub_text=stub)
        body = ["# Phase 6 / Step 2: Persevere-or-pivot memo", "",
                f"**Recommendation:** {gate.recommended.upper()}", ""] + [f"- {r}" for r in gate.reasons] + ["", res.text]
        self.ctx.write_output("phase6_step2_memo.md", "\n".join(body), stubbed=res.stubbed)
