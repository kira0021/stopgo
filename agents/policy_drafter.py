"""Phase 4 Commercial setup, step 2: draft terms, privacy and refund policies (Core step).

These are drafts for the founder to review, ideally with a qualified person,
before anything is published. StopGo does not give legal advice.
"""
from __future__ import annotations

from agents.base import Agent

DISCLAIMER = ("DRAFT for founder review. Not legal advice. Have a qualified person review it for your "
              "jurisdiction before publishing. Nothing is published without founder approval.")


class PolicyDrafter(Agent):
    role = "policy_drafter"

    def policies(self) -> None:
        build = self.ctx.state.get("build") or {}
        name = build.get("name", "the product")
        stub = (
            f"## Terms of use\n\n{name} is provided under the MIT licence, \"as is\", without warranty. The paid tier, "
            "if offered, covers hosted convenience and support only.\n\n"
            "## Privacy\n\nThe CLI runs locally and sends no data. The waitlist stores only the email address you "
            "give, used to tell you when the product is available. You can ask for it to be deleted at any time.\n\n"
            "## Refunds\n\nIf the paid tier does not work for you, ask for a refund within 14 days of purchase. "
            "Refunds are reviewed and issued by the founder; access to paid features ends when the refund is issued."
        )
        res = self.ask(
            "draft_policies",
            f"Product: {name}. Pricing: {self.ctx.state.get('pricing')}.\n\nDraft three short plain-language "
            "sections in markdown: '## Terms of use', '## Privacy', '## Refunds'. The refund policy must say refunds "
            "are issued by the founder (never automatically) and that a refund ends paid access. No guarantees of "
            "results. Keep it under 300 words.",
            stub_text=stub,
        )
        body = f"# Phase 4 / Step 2: Policies\n\n> {DISCLAIMER}\n\n{res.text}"
        self.ctx.write_output("phase4_step2_policies.md", body, stubbed=res.stubbed)
