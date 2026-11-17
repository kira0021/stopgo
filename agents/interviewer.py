"""Phase 1 Discover, step 3: Mom Test interview kit + summary of founder-reported results.

StopGo never contacts anyone. It drafts the script and an outreach note; the
founder sends it from their own account, after reading it.
"""
from __future__ import annotations

from agents.base import Agent

MOM_TEST_RULES = (
    "Talk about their life, not your idea. Ask about specifics in the past, not opinions about the future. "
    "Talk less, listen more. Compliments and 'I would buy that' are not evidence; past behaviour and money/time "
    "already spent are."
)


class Interviewer(Agent):
    role = "interviewer"

    def interview_kit(self) -> None:
        opp = self.ctx.state["opportunities"][0]
        stub = (
            "## Questions\n"
            "1. Tell me about the last time you ran into this problem. What happened?\n"
            "2. How did you deal with it? What did you try?\n"
            "3. How much time did that take you? How often does it happen?\n"
            "4. Have you looked for or paid for anything to fix it? Why / why not?\n"
            "5. What is the hardest part about it?\n"
            "6. Who else on your team deals with this?\n"
            "7. Is there anyone else you think I should talk to?\n\n"
            "## Outreach note (draft for the founder to send personally)\n"
            "Hi <name>, I'm researching how developers handle <problem>. Could I ask you about the last time it "
            "came up? 15 minutes, no pitch. Thanks, <founder name>"
        )
        res = self.ask(
            "draft_mom_test_script",
            f"{self.ctx.brief_text()}\nProblem to explore: {opp['idea']}\n\nWrite markdown with: '## Questions' "
            "(7 Mom Test questions about past behaviour; no hypotheticals, no pitching) and '## Outreach note (draft for "
            "the founder to send personally)' with placeholders <name> and <founder name>. Never write in a "
            "customer's voice.",
            stub_text=stub,
        )
        iv = (self.ctx.state.get("evidence", {}) or {}).get("interviews") or {}
        lines = [
            "# Phase 1 / Step 3: Customer interviews (Mom Test)",
            "",
            f"**Rules:** {MOM_TEST_RULES}",
            "",
            "StopGo does not contact anyone. The founder sends the outreach note personally and records results.",
            "",
            res.text,
            "",
            "## What to record per interview",
            "",
            "| Field | Meaning |",
            "|---|---|",
            "| problem_confirmed | They described the problem from a specific, recent experience (yes/no) |",
            "| workaround | What they do today |",
            "| spent | Time or money already spent on it |",
            "| referral | They offered another person to talk to |",
            "",
            "## Results so far (founder-reported)",
            "",
        ]
        if iv.get("completed") is not None:
            lines += [f"- founder-reported: {iv['completed']} interviews completed, "
                      f"{iv.get('problem_confirmed', 0)} described the problem from recent experience."]
            for n in iv.get("notes", [])[:8]:
                lines.append(f"- founder-reported note: {n}")
        else:
            lines.append("- No interviews reported yet. The Discover gate will recommend REPEAT until they are.")
        self.ctx.write_output("phase1_step3_interviews.md", "\n".join(lines), stubbed=res.stubbed)
