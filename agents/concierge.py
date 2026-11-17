"""Free-form requests from the founder ("ask the team"). Hard limits are checked in code first."""
from __future__ import annotations

import guardrails
from agents.base import Agent


class Concierge(Agent):
    role = "concierge"

    def answer(self, request: str) -> dict:
        refusal = guardrails.check_request(request)
        if refusal:
            self.log("refuse_request", model=None, outcome="refused", rule=refusal.rule)
            return {"refused": True, "rule": refusal.rule,
                    "text": f"I won't do that. {refusal.message} {refusal.alternative}"}
        res = self.ask("answer_request", request,
                       stub_text="STUBBED: no model is running, so I can't answer free-form questions right now. "
                                 "The pipeline steps still run with labelled stub text.")
        return {"refused": False, "text": res.text, "stubbed": res.stubbed}
