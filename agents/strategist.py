"""Phase 2 Validate: Lean Canvas and the honest landing page (Core step: design the business)."""
from __future__ import annotations

import html

import gates
from agents.base import Agent, label_claims

CANVAS_BOXES = ["problem", "customer_segments", "unique_value_proposition", "solution", "channels",
                "revenue_streams", "cost_structure", "key_metrics", "unfair_advantage"]


class Strategist(Agent):
    role = "strategist"

    def lean_canvas(self) -> dict:
        opp = self.ctx.state["opportunities"][0]
        b = self.ctx.brief
        stub = {
            "problem": [opp["idea"]],
            "customer_segments": [str(b.get("target_market"))],
            "unique_value_proposition": f"{opp['idea']}, open source, runs locally.",
            "solution": ["Small CLI that does one job well", "CI-friendly exit codes"],
            "channels": ["GitHub README", "Developer forums the founder already uses"],
            "revenue_streams": ["Paid convenience tier (support, hosted CI check); core stays free"],
            "cost_structure": ["Founder time", "Domain and hosting on free tiers"],
            "key_metrics": ["Waitlist sign-ups vs pre-set target", "Weekly active installs"],
            "unfair_advantage": ["None yet"],
        }
        data, res = self.ask_json(
            "lean_canvas",
            f"{self.ctx.brief_text()}\nIdea: {opp['idea']}\n\nReturn JSON with keys {CANVAS_BOXES}. Values are short "
            "strings or lists of short strings. No statistics, no income claims. 'unfair_advantage' may be 'None yet'.",
            stub_obj=stub,
        )
        canvas = {k: data.get(k, stub[k]) for k in CANVAS_BOXES}
        self.ctx.state["lean_canvas"] = canvas
        lines = ["# Phase 2 / Step 1: Lean Canvas", "",
                 "Everything here is a hypothesis to test. Unsourced lines are labelled ASSUMPTION.", ""]
        for k in CANVAS_BOXES:
            v = canvas[k]
            lines.append(f"## {k.replace('_', ' ').title()}")
            for item in (v if isinstance(v, list) else [v]):
                lines.append(f"- {item}")
            lines.append("")
        wl = (self.ctx.state.get("evidence") or {}).get("waitlist") or {}
        t = gates.THRESHOLDS["validate"]
        lines += ["## Demand test set before launch", "",
                  f"- Target: {wl.get('target') or t['default_waitlist_target']} waitlist sign-ups in "
                  f"{wl.get('window_days') or t['default_window_days']} days (founder-reported target, fixed in advance)."]
        self.ctx.write_output("phase2_step1_lean_canvas.md", label_claims("\n".join(lines)), stubbed=res.stubbed)
        return canvas

    def landing_page(self) -> str:
        c = self.ctx.state["lean_canvas"]
        opp = self.ctx.state["opportunities"][0]
        stub = {
            "headline": str(c["unique_value_proposition"])[:90],
            "subheadline": f"For {', '.join(c['customer_segments']) if isinstance(c['customer_segments'], list) else c['customer_segments']}.",
            "problem": "; ".join(c["problem"]) if isinstance(c["problem"], list) else str(c["problem"]),
            "how_it_works": c["solution"] if isinstance(c["solution"], list) else [c["solution"]],
        }
        data, res = self.ask_json(
            "draft_landing_page",
            f"Idea: {opp['idea']}\nLean canvas: {c}\n\nReturn JSON: headline (<= 90 chars), subheadline, problem "
            "(1-2 sentences), how_it_works (3 short bullets). No testimonials, no user counts, no urgency, no income claims.",
            stub_obj=stub,
        )
        import guardrails

        def clean(s) -> str:
            return html.escape(guardrails.scan_output(str(s)).clean_text)

        bullets = "".join(f"<li>{clean(x)}</li>" for x in (data.get("how_it_works") or stub["how_it_works"])[:4])
        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{clean(data.get('headline', stub['headline']))}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:640px;margin:3rem auto;padding:0 1rem;line-height:1.5;color:#1b1b1b}}
.note{{background:#fff6d6;border:1px solid #e6c200;padding:.6rem .8rem;border-radius:6px;font-size:.9rem}}
form{{display:flex;gap:.5rem;margin-top:1rem}}input{{flex:1;padding:.6rem}}button{{padding:.6rem 1rem}}</style></head>
<body>
<p class="note">Early-stage project: this tool is not built yet. Joining the waitlist only means we may email you once
when there is something to try. No payment is taken.</p>
<h1>{clean(data.get('headline', stub['headline']))}</h1>
<p><strong>{clean(data.get('subheadline', stub['subheadline']))}</strong></p>
<h2>The problem</h2><p>{clean(data.get('problem', stub['problem']))}</p>
<h2>How it would work</h2><ul>{bullets}</ul>
<h2>Join the waitlist</h2>
<form action="#" method="post" onsubmit="return false"><input type="email" placeholder="you@example.com" required>
<button type="submit">Join waitlist</button></form>
<p style="font-size:.8rem;color:#555">The form is not connected in this prototype (MOCKED). The founder connects it to
a form tool of their choice before publishing. Open source, MIT licensed.</p>
</body></html>"""
        self.ctx.write_output("phase2_step2_landing_page.html", page, stubbed=res.stubbed)
        return page
