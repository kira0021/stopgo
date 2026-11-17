"""Shared agent plumbing: prompts, model calls, guardrail scan, logging, outputs."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import guardrails
from decision_log import DecisionLog
from llm import LLM, LLMResult, extract_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(ROOT, "prompts")


def load_prompt(role: str) -> str:
    with open(os.path.join(PROMPTS_DIR, "_shared_rules.md"), encoding="utf-8") as f:
        shared = f.read()
    with open(os.path.join(PROMPTS_DIR, f"{role}.md"), encoding="utf-8") as f:
        own = f.read()
    return own.strip() + "\n\n" + shared.strip()


@dataclass
class Context:
    state: dict
    llm: LLM
    log: DecisionLog
    run_dir: str
    stubbed_steps: set = field(default_factory=set)

    @property
    def brief(self) -> dict:
        return self.state["brief"]

    @property
    def outputs_dir(self) -> str:
        d = os.path.join(self.run_dir, "outputs")
        os.makedirs(d, exist_ok=True)
        return d

    def brief_text(self) -> str:
        b = self.brief
        skills = ", ".join(b.get("skills", [])) if isinstance(b.get("skills"), list) else b.get("skills", "")
        return (f"Idea: {b.get('idea')}\nFounder skills: {skills}\nBudget (USD): {b.get('budget_usd')}\n"
                f"Time: {b.get('hours_per_week')} hours/week\nTarget market: {b.get('target_market')}\n"
                f"Values: {b.get('values')}")

    def write_output(self, filename: str, content: str, *, stubbed: bool = False, mocked: bool = False) -> str:
        labels = []
        if stubbed:
            labels.append("STUBBED: model-written text in this file came from the deterministic stub, not a model.")
        if mocked:
            labels.append("MOCKED: no real payment, publication or delivery happened.")
        if self.state.get("brief", {}).get("demo_fixture"):
            labels.append("DEMO FIXTURE: founder-reported numbers in this run come from a demo brief, "
                          "not from real interviews or sign-ups.")
        header = ""
        if filename.endswith(".md") and labels:
            header = "".join(f"> **{l.split(':')[0]}**:{l.split(':', 1)[1]}\n" for l in labels) + "\n"
        elif filename.endswith(".html") and labels:
            header = "".join(f"<!-- {l} -->\n" for l in labels)
        path = os.path.join(self.outputs_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + content.rstrip() + "\n")
        self.state.setdefault("artifacts", [])
        if filename not in self.state["artifacts"]:
            self.state["artifacts"].append(filename)
        return path


def label_claims(text: str) -> str:
    """Every bullet that states something must cite a URL or say ASSUMPTION.

    Enforced in code: any bullet line without a URL and without the word
    ASSUMPTION gets the label prepended.
    """
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s[:2] in ("- ", "* ") and not any(t in s for t in ("http", "ASSUMPTION", "founder-reported",
                                                               "founder-cited", "Founder-cited", "unavailable")):
            indent = line[: len(line) - len(s)]
            line = f"{indent}{s[:2]}ASSUMPTION: {s[2:]}"
        out.append(line)
    return "\n".join(out)


class Agent:
    role = "agent"

    def __init__(self, ctx: Context):
        self.ctx = ctx
        self.system = load_prompt(self.role)

    def ask(self, action: str, user: str, *, stub_text: str, json_mode: bool = False,
            sources: list[str] | None = None, scan: bool = True) -> LLMResult:
        res = self.ctx.llm.complete(self.system, user, stub_text=stub_text, json_mode=json_mode)
        violations: list[str] = []
        if scan and not json_mode:
            sr = guardrails.scan_output(res.text)
            res.text, violations = sr.clean_text, sr.violations
        self.ctx.log.append(self.role, action, sources=sources or [], model=res.model, cost=res.cost,
                            approved_by=None, tokens=res.tokens or None,
                            prompt_tokens_est=res.prompt_tokens_est or None,
                            guardrail_removed=violations or None)
        return res

    def ask_json(self, action: str, user: str, *, stub_obj, sources: list[str] | None = None):
        import json

        res = self.ask(action, user, stub_text=json.dumps(stub_obj), json_mode=True, sources=sources, scan=False)
        data = extract_json(res.text)
        if data is None:
            self.ctx.log.append(self.role, f"{action}:unparseable_model_json_used_stub", model=None)
            res.stubbed = True  # the template, not the model, produced this content
            return stub_obj, res
        return data, res

    def log(self, action: str, **kw):
        return self.ctx.log.append(self.role, action, **kw)
