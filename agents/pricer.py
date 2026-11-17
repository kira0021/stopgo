"""Phase 4 Commercial setup, step 1: set the price (Core step). No payments of any kind."""
from __future__ import annotations

from agents.base import Agent, label_claims


class Pricer(Agent):
    role = "pricer"

    def pricing(self) -> dict:
        opp = self.ctx.state["opportunities"][0]
        pub = (self.ctx.state.get("evidence") or {}).get("public") or {}
        gh = pub.get("github") or {}
        comps = gh.get("top", [])[:3] if gh.get("status") == "ok" else []
        budget = self.ctx.brief.get("budget_usd")
        stub = {
            "model": "open core: the CLI is free and open source; a paid tier sells convenience, not the core",
            "tiers": [
                {"name": "Community", "price_usd": 0, "includes": "Full CLI, all core features, MIT licence"},
                {"name": "Team", "price_usd": 9, "per": "month", "includes": "Hosted CI check and email support"},
            ],
            "rationale": [
                "Free open-source alternatives exist, so the core must stay free.",
                "A low monthly price for convenience is a hypothesis to test with the waitlist.",
            ],
        }
        data, res = self.ask_json(
            "set_price",
            f"Idea: {opp['idea']}\nFree alternatives found: {[c['name'] for c in comps]}\nFounder budget: {budget}\n\n"
            "Propose pricing as JSON: model (one line), tiers (2-3 items: name, price_usd, per, includes), rationale "
            "(list). Rules: the core feature must stay free (no paywalling core features); prices are hypotheses; "
            "no income projections.",
            stub_obj=stub,
            sources=[c["url"] for c in comps],
        )
        tiers = data.get("tiers") or stub["tiers"]
        if not any((t.get("price_usd") in (0, "0", None)) for t in tiers if isinstance(t, dict)):
            tiers = [stub["tiers"][0]] + tiers  # enforce: core stays free
        lines = ["# Phase 4 / Step 1: Pricing", "",
                 "No payment provider is connected. Nothing is charged (payments are MOCKED in Phase 5).", "",
                 f"**Model:** {data.get('model', stub['model'])}", "",
                 "| Tier | Price (USD, ASSUMPTION: hypothesis to test) | Includes |", "|---|---|---|"]
        for t in tiers:
            if isinstance(t, dict):
                per = f"/{t.get('per')}" if t.get("per") else ""
                lines.append(f"| {t.get('name')} | {t.get('price_usd')}{per} | {t.get('includes')} |")
        lines += ["", "## Rationale", ""] + [f"- {r}" for r in (data.get("rationale") or stub["rationale"])]
        lines += ["", "## Comparable free tools (sourced)", ""]
        lines += [f"- {c['name']} ({c['stars']} stars, free): {c['url']}" for c in comps] or \
                 ["- Comparable tools unavailable for this run (GitHub not reachable)."]
        lines += ["", "No revenue is projected or promised. Prices are hypotheses to test."]
        self.ctx.state["pricing"] = {"tiers": tiers}
        self.ctx.write_output("phase4_step1_pricing.md", label_claims("\n".join(lines)), stubbed=res.stubbed)
        return {"tiers": tiers}
