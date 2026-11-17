import json
import os

import approval
import orchestrator as orch
from decision_log import validate_entries

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def brief(name):
    with open(os.path.join(ROOT, "briefs", name), encoding="utf-8") as f:
        return json.load(f)


def drive(rid, override_note="Founder override for the smoke test"):
    """Act as the founder: approve actions and accept each gate (with a note when overriding)."""
    st = orch.advance(rid)
    for _ in range(30):
        pend = approval.pending(st)
        if not pend:
            break
        rec = pend[0]
        if rec["kind"] == "approval":
            orch.decide(rid, rec["id"], "approve")
        else:
            orch.decide(rid, rec["id"], "go", None if rec["recommended"] == "go" else override_note)
        st = orch.advance(rid)
    return st


def test_weak_idea_is_stopped_at_discover():
    rid = orch.start_run(brief("devtool_weak.json"))
    st = orch.advance(rid)
    rec = approval.pending(st)[0]
    assert rec["recommended"] == "stop"
    orch.decide(rid, rec["id"], "stop")
    st = orch.advance(rid)
    assert st["status"] == "stopped"
    assert "phase1_gate_decision.md" in st["artifacts"]
    assert "phase2_step1_lean_canvas.md" not in st["artifacts"]


def test_strong_idea_runs_all_six_phases():
    rid = orch.start_run(brief("devtool_strong.json"))
    st = drive(rid)
    assert st["status"] == "completed"
    for phase in range(1, 7):
        assert any(a.startswith(f"phase{phase}_") for a in st["artifacts"]), phase
        assert f"phase{phase}_gate_decision.md" in st["artifacts"]
    assert "payment_test_log.md" in st["artifacts"]
    assert all(st["sale_to_cash"]["checks"].values())


def test_decision_log_has_required_keys_and_founder_approvals():
    rid = orch.start_run(brief("devtool_strong.json"))
    st = drive(rid)
    with open(os.path.join(st["run_dir"], "decision_log.json"), encoding="utf-8") as f:
        log = json.load(f)
    assert validate_entries(log) == []
    published = [e for e in log if e["action"] in ("publish_landing_page", "publish_store_page", "post_launch_posts")]
    assert published and all(e["approved_by"] == "founder" for e in published)


def test_stubbed_outputs_are_labelled():
    rid = orch.start_run(brief("devtool_strong.json"))
    st = drive(rid)
    text = open(os.path.join(st["run_dir"], "outputs", "phase2_step1_lean_canvas.md"), encoding="utf-8").read()
    assert "STUBBED" in text and "DEMO FIXTURE" in text
    pay = open(os.path.join(st["run_dir"], "outputs", "payment_test_log.md"), encoding="utf-8").read()
    assert "MOCKED" in pay


def test_market_claims_are_sourced_or_assumptions():
    rid = orch.start_run(brief("devtool_strong.json"))
    st = drive(rid)
    for name in ("phase1_step2_market.md", "phase2_step1_lean_canvas.md", "phase4_step1_pricing.md"):
        for line in open(os.path.join(st["run_dir"], "outputs", name), encoding="utf-8"):
            s = line.strip()
            if s.startswith("- ") and "unavailable" not in s:
                assert "http" in s or "ASSUMPTION" in s or "founder-reported" in s, (name, s)


def test_committed_decision_log_is_valid():
    path = os.path.join(ROOT, "decision_log.json")
    with open(path, encoding="utf-8") as f:
        assert validate_entries(json.load(f)) == []


def test_builder_with_model_written_core_passes_tests_gate(tmp_path):
    """Simulate a model reply for the build step and check the generated MVP is actually tested."""
    import gates
    from agents.base import Context
    from agents.builder import Builder
    from decision_log import DecisionLog
    from llm import LLM, LLMResult

    core = ("def process(text: str) -> str:\n"
            "    keys = [l.split('=')[0].strip() for l in text.splitlines() if '=' in l]\n"
            "    return ','.join(sorted(keys))\n")

    class FakeModel(LLM):
        def complete(self, system, user, *, stub_text, json_mode=False, temperature=0.4):
            if json_mode:
                return LLMResult(json.dumps({"summary": "List env keys", "core_code": core, "examples": [
                    {"input": "B=1\nA=2", "expected_output": "A,B"}, {"input": "", "expected_output": ""}]}),
                    model="fake-model")
            return LLMResult("## Install\n\npip install .", model="fake-model")

    st = {"brief": {"idea": "env keys"}, "run_dir": str(tmp_path), "opportunities": [{"idea": "env keys",
          "keywords": "env keys"}], "product_name": "envkeys"}
    ctx = Context(st, FakeModel(provider="ollama"), DecisionLog(str(tmp_path / "log.json")), str(tmp_path))
    b = Builder(ctx).build()
    assert b["passed"] and not b["core_stubbed"] and b["n_examples"] == 2
    assert gates.build_gate(b["passed"], b["attempts"], b["core_stubbed"]).recommended == gates.GO


def test_committed_outputs_pass_claims_audit():
    import claims
    out = os.path.join(ROOT, "outputs")
    assert claims.audit_dir(out) == {}
    names = os.listdir(out)
    assert any(n.startswith("phase1_gate_") and "weak" in n for n in names)
    stop_file = next(n for n in names if n.startswith("phase1_gate_") and "weak" in n)
    text = open(os.path.join(out, stop_file), encoding="utf-8").read()
    assert "Recommendation: STOP" in text and "Decision: **STOP**" in text


def test_every_run_output_passes_claims_audit():
    import claims
    rid = orch.start_run(brief("devtool_strong.json"))
    st = drive(rid)
    assert claims.audit_dir(os.path.join(st["run_dir"], "outputs")) == {}


def _log(st):
    with open(os.path.join(st["run_dir"], "decision_log.json"), encoding="utf-8") as f:
        return json.load(f)


def test_weak_idea_stop_is_logged_with_reasons_and_founder_decision():
    rid = orch.start_run(brief("devtool_weak.json"))
    st = orch.advance(rid)
    orch.decide(rid, approval.pending(st)[0]["id"], "stop", "Agree with the evidence.")
    st = orch.advance(rid)
    log = _log(st)
    gate = next(e for e in log if e["agent"] == "gate" and e["action"] == "phase1_evidence_gate")
    assert gate["outcome"] == "stop" and gate["reasons"] and "problem_confirmed_rate" in gate["failed_checks"]
    assert "https://github.com/jqlang/jq" in gate["sources"]
    dec = next(e for e in log if e["action"] == "gate_decision:phase1_evidence_gate" and e["agent"] == "founder")
    assert dec["approved_by"] == "founder" and dec["outcome"] == "stop" and dec["override"] is False
    assert dec["note"] == "Agree with the evidence."


def test_founder_override_of_stop_is_recorded_everywhere():
    rid = orch.start_run(brief("devtool_weak.json"))
    st = orch.advance(rid)
    orch.decide(rid, approval.pending(st)[0]["id"], "go", "I have context the interviews missed.")
    st = orch.advance(rid)
    dec = next(e for e in _log(st) if e["action"] == "gate_decision:phase1_evidence_gate" and e["agent"] == "founder")
    assert dec["override"] is True and dec["recommended"] == "stop"
    gate_md = open(os.path.join(st["run_dir"], "outputs", "phase1_gate_decision.md"), encoding="utf-8").read()
    assert "overrides the recommendation" in gate_md and "I have context" in gate_md
