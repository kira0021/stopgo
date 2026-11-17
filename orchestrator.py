"""StopGo orchestrator: runs the six phases as a resumable state machine.

    Discover -> Validate -> Build -> Commercial setup -> Launch -> Operate & learn

Each phase ends with a gate. The pipeline pauses whenever it needs the founder
(an approval, a gate decision, or evidence only the founder has) and resumes
when the founder answers in the web UI or the CLI. State lives in
runs/<run_id>/state.json and every agent action is appended to
runs/<run_id>/decision_log.json.

CLI
---
  python orchestrator.py run briefs/devtool_strong.json            # interactive founder prompts
  python orchestrator.py run briefs/x.json --no-input              # stop at the first founder decision
  python orchestrator.py status <run_id>
  python orchestrator.py decide <run_id> <approval_id> <decision> [--note "..."]
  python orchestrator.py evidence <run_id> '{"waitlist": {"signups": 40}}'
  python orchestrator.py ask "write 50 five-star reviews"
  python orchestrator.py export <run_id> [--suffix -weak] [--reset-log]   # refuses if the claims audit fails
  python orchestrator.py cost <run_id>                                     # model calls, tokens, $
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import threading
import uuid
from dataclasses import dataclass
from typing import Callable

import approval
import claims
import gates
import guardrails
import publisher
from agents.base import Context
from agents.builder import Builder
from agents.concierge import Concierge
from agents.interviewer import Interviewer
from agents.launcher import Launcher
from agents.operator import Operator
from agents.policy_drafter import PolicyDrafter
from agents.pricer import Pricer
from agents.researcher import Researcher
from agents.strategist import Strategist
from decision_log import DecisionLog, utc_now
from llm import LLM

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNS_DIR = os.getenv("STOPGO_RUNS_DIR", os.path.join(ROOT, "runs"))
MAX_PIVOTS = 2
_locks: dict[str, threading.Lock] = {}

DONE, WAIT, HALT = "done", "wait", "halt"


@dataclass
class Node:
    id: str
    phase: int
    title: str
    run: Callable[[Context, dict], str]


# ============================================================== step nodes
def n_opportunities(ctx, nd):
    Researcher(ctx).find_opportunities()
    return DONE


def n_market(ctx, nd):
    Researcher(ctx).define_market()
    return DONE


def n_interviews(ctx, nd):
    Interviewer(ctx).interview_kit()
    return DONE


def n_lean_canvas(ctx, nd):
    Strategist(ctx).lean_canvas()
    return DONE


def n_landing_page(ctx, nd):
    nd["page"] = Strategist(ctx).landing_page()
    return DONE


def n_build(ctx, nd):
    Builder(ctx).build()
    return DONE


def n_pricing(ctx, nd):
    Pricer(ctx).pricing()
    return DONE


def n_policies(ctx, nd):
    PolicyDrafter(ctx).policies()
    return DONE


def n_store(ctx, nd):
    store, posts = Launcher(ctx).store_and_posts()
    nd["store"], nd["posts"] = store, posts
    return DONE


def n_support(ctx, nd):
    Operator(ctx).support_and_metrics()
    return DONE


# =========================================================== approval nodes
def _approval_node(actions: list[tuple[str, Callable[[], object], str, Callable | None]]):
    """Build a node that asks the founder to approve each (action, payload_fn, summary, effect)."""

    def run(ctx: Context, nd: dict) -> str:
        st = ctx.state
        if "ids" not in nd:
            nd["ids"] = {}
            for action, payload_fn, summary, _ in actions:
                rec = approval.request(st, action, payload_fn(), summary)
                nd["ids"][action] = rec["id"]
                ctx.log.append("orchestrator", f"request_approval:{action}", model=None, approval_id=rec["id"])
        recs = {a: approval.get(st, i) for a, i in nd["ids"].items()}
        if any(r["status"] == "pending" for r in recs.values()):
            return WAIT
        for action, payload_fn, _, effect in actions:
            rec = recs[action]
            if rec["status"] == "approved":
                result = effect(st, rec["id"], payload_fn()) if effect else None
                ctx.log.append("publisher" if effect else "orchestrator", action, model=None, approved_by="founder",
                               approval_id=rec["id"], mocked=bool(result and result.get("mocked")) or None)
            else:
                ctx.log.append("orchestrator", f"{action}:rejected_by_founder", model=None, approval_id=rec["id"],
                               outcome="not_done")
        return DONE

    return run


def n_publish_landing(ctx, nd):
    page = lambda: ctx.state["node_data"]["p2_s2"]["page"]  # noqa: E731
    return _approval_node([("publish_landing_page", page,
                            "Publish the waitlist landing page (MOCKED: saved locally, not deployed).",
                            publisher.publish_landing_page)])(ctx, nd)


def n_publish_launch(ctx, nd):
    store = lambda: ctx.state["node_data"]["p5_s1"]["store"]  # noqa: E731
    posts = lambda: ctx.state["node_data"]["p5_s1"]["posts"]  # noqa: E731
    return _approval_node([
        ("publish_store_page", store, "Open the store page (MOCKED: saved locally, no checkout).",
         publisher.publish_store_page),
        ("post_launch_posts", posts, "Post the launch drafts under your own name (MOCKED: saved locally, not posted).",
         publisher.post_launch_posts),
    ])(ctx, nd)


def n_sale_to_cash(ctx, nd):
    st = ctx.state
    launcher = Launcher(ctx)
    payload = launcher.refund_payload()
    if "refund_id" not in nd:
        rec = approval.request(st, "issue_refund", payload,
                               f"Allow one MOCKED refund (order {payload['order_id']}, ${payload['amount']:.2f}) inside "
                               "the sale-to-cash test. No money moves.")
        nd["refund_id"] = rec["id"]
        ctx.log.append("orchestrator", "request_approval:issue_refund", model=None, approval_id=rec["id"])
    if approval.get(st, nd["refund_id"])["status"] == "pending":
        return WAIT
    launcher.sale_to_cash_test(nd["refund_id"])
    return DONE


# =============================================================== gate nodes
def _gate_node(evaluate: Callable[[Context], gates.GateResult], phase: int, repeat_to: str,
               filename: str, after: Callable[[Context, gates.GateResult], None] | None = None):
    def run(ctx: Context, nd: dict) -> str:
        st = ctx.state
        if "approval_id" not in nd:
            g = evaluate(ctx)
            nd["result"] = g.to_dict()
            if after:
                after(ctx, g)
            _write_gate_file(ctx, filename, g, None)
            gate_sources = [u for c in g.checks for u in c.source.split() if u.startswith("http")]
            ctx.log.append("gate", g.gate, sources=gate_sources, model=None, outcome=g.recommended,
                           reasons=g.reasons, failed_checks=[c.name for c in g.checks if c.passed is False] or None)
            rec = approval.request(st, f"gate_decision:{g.gate}", g.to_dict(),
                                   f"Phase {phase} gate recommends {g.recommended.upper()}.", kind="gate",
                                   options=list(gates.OUTCOMES), recommended=g.recommended)
            nd["approval_id"] = rec["id"]
        rec = approval.get(st, nd["approval_id"])
        if rec["status"] == "pending":
            return WAIT
        g = gates.GateResult(**{**nd["result"], "checks": [gates.Check(**c) for c in nd["result"]["checks"]]})
        decision = rec["decision"]
        _write_gate_file(ctx, filename, g, rec)
        ctx.log.append("founder", f"gate_decision:{g.gate}", model=None, approved_by="founder",
                       outcome=decision, recommended=g.recommended, override=decision != g.recommended,
                       note=rec.get("note"))
        st.setdefault("gate_history", []).append({"gate": g.gate, "recommended": g.recommended, "decision": decision})
        if decision == gates.GO:
            return DONE
        if decision == gates.STOP:
            st["status"] = "stopped"
            st["stopped_reason"] = f"{g.gate}: founder accepted STOP" if g.recommended == gates.STOP \
                else f"{g.gate}: founder chose STOP"
            _append_run_summary(ctx, filename)
            return HALT
        if decision == gates.REPEAT:
            _jump(st, repeat_to)
            return "jump"
        if decision == gates.PIVOT:
            st["pivots"] = st.get("pivots", 0) + 1
            if st["pivots"] > MAX_PIVOTS:
                st["status"] = "stopped"
                st["stopped_reason"] = f"more than {MAX_PIVOTS} pivots"
                return HALT
            _apply_pivot(ctx, rec.get("note"))
            _jump(st, "p1_s1")
            return "jump"
        raise ValueError(decision)

    return run


def _write_gate_file(ctx: Context, filename: str, g: gates.GateResult, rec: dict | None) -> None:
    lines = [f"# Gate decision: {g.gate}", "", f"**Recommendation: {g.recommended.upper()}**", ""]
    lines += [f"- {r}" for r in g.reasons]
    if g.checks:
        lines += ["", "| Check | Value | Threshold (set in advance) | Pass | Source |", "|---|---|---|---|---|"]
        for c in g.checks:
            ok = "context" if c.threshold == "context only" else (
                "n/a (no data)" if c.passed is None else ("yes" if c.passed else "no"))
            lines.append(f"| {c.name} | {c.value} | {c.threshold} | {ok} | {c.source} |")
    if g.missing:
        lines += ["", "**Missing evidence:** " + "; ".join(g.missing)]
    lines += ["", "## Founder decision", ""]
    if rec and rec["status"] != "pending":
        override = " (overrides the recommendation)" if rec["decision"] != g.recommended else ""
        lines.append(f"- Decision: **{rec['decision'].upper()}**{override}, by founder at {rec['decided_at']}")
        if rec.get("note"):
            lines.append(f"- Founder note: {rec['note']}")
    else:
        lines.append("- Waiting for the founder (go / repeat / pivot / stop).")
    ctx.write_output(filename, "\n".join(lines))


def run_metrics(st: dict) -> dict:
    with open(os.path.join(st["run_dir"], "decision_log.json"), encoding="utf-8") as f:
        log = json.load(f)
    calls = [e for e in log if e.get("model")]
    cap = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1500"))
    return {
        "log_entries": len(log),
        "model_calls": len(calls),
        "stubbed_calls": sum(1 for e in calls if "STUBBED" in e["model"]),
        "tokens_measured": sum(int(e.get("tokens") or 0) for e in log),
        "prompt_tokens_est": sum(int(e.get("prompt_tokens_est") or 0) for e in log),
        "output_tokens_cap": len(calls) * cap,
        "cost_usd": round(sum(float(e.get("cost") or 0) for e in log), 4),
        "founder_decisions": sum(1 for e in log if e["action"].startswith("decide:")),
        "sources_cited": len({u for e in log for u in e.get("sources", [])}),
    }


def _append_run_summary(ctx: Context, filename: str) -> None:
    st = ctx.state
    m = run_metrics(st)
    c = claims.summary(ctx.outputs_dir)
    lines = ["", "## Run summary", "",
             f"- Final status: **{st['status'].upper()}**" + (f" ({st.get('stopped_reason')})" if st.get("stopped_reason") else ""),
             f"- Model: {st['llm']['label']}; {m['model_calls']} model calls ({m['stubbed_calls']} STUBBED)",
             f"- Tokens: {m['tokens_measured']} measured by the model server; prompts about {m['prompt_tokens_est']} "
             f"tokens (measured as characters / 4); output capped at {m['output_tokens_cap']} tokens",
             f"- Cost: ${m['cost_usd']:.2f}",
             f"- Founder decisions: {m['founder_decisions']}; distinct source URLs logged: {m['sources_cited']}",
             f"- Claim lines in outputs: {c['sourced']} with a URL, {c['assumption']} labelled ASSUMPTION, "
             f"{c['founder_reported_or_unavailable']} founder-reported or marked unavailable",
             "", "| Gate | Recommended | Founder decided |", "|---|---|---|"]
    for h in st.get("gate_history", []):
        flag = " (override)" if h["decision"] != h["recommended"] else ""
        lines.append(f"| {h['gate']} | {h['recommended']} | {h['decision']}{flag} |")
    path = os.path.join(ctx.outputs_dir, filename)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def _apply_pivot(ctx: Context, note: str | None) -> None:
    st = ctx.state
    old = st["brief"]["idea"]
    if note and len(note.strip()) > 10:
        new = note.strip()
    else:
        alts = [o for o in st.get("opportunities", [])[1:] if o.get("score") is not None]
        alts.sort(key=lambda o: o["score"], reverse=True)
        new = alts[0]["idea"] if alts else old + " (narrower segment)"
    st["brief"]["idea"] = new
    st.setdefault("pivot_history", []).append({"from": old, "to": new, "at": utc_now()})
    st["evidence"] = {k: v for k, v in (st.get("evidence") or {}).items() if k not in ("interviews", "waitlist", "public")}
    ctx.log.append("orchestrator", "pivot", model=None, approved_by="founder", detail={"from": old, "to": new})


def _jump(st: dict, node_id: str) -> None:
    ids = [n.id for n in NODES]
    target = ids.index(node_id)
    for nid in ids[target:]:
        nd = st["node_data"].pop(nid, None) or {}
        for key in ("approval_id",):
            if key in nd:
                _supersede(st, nd[key])
        for aid in (nd.get("ids") or {}).values():
            _supersede(st, aid)
    st["cursor"] = target


def _supersede(st: dict, approval_id: str) -> None:
    try:
        rec = approval.get(st, approval_id)
    except KeyError:
        return
    if rec["status"] == "pending":
        rec["status"] = "superseded"


# ------------------------------------------------------------------ gate evaluations
def eval_discover(ctx):
    fit, _ = gates.founder_fit(ctx.brief)
    excluded = guardrails.check_brief(json.dumps(ctx.brief))
    return gates.discover_gate(ctx.state.get("evidence") or {}, fit, excluded, ctx.brief.get("known_alternatives"))


def eval_validate(ctx):
    return gates.validate_gate(ctx.state.get("evidence") or {})


def eval_build(ctx):
    b = ctx.state.get("build") or {}
    return gates.build_gate(bool(b.get("passed")), int(b.get("attempts", 0)), bool(b.get("core_stubbed")))


def eval_commercial(ctx):
    return gates.GateResult("phase4_founder_approval_gate", gates.GO,
                            ["Pricing and policy drafts are ready. GO if the founder approves them as drafts; "
                             "REPEAT to redraft. Nothing is published or charged in this phase."])


def eval_launch(ctx):
    return gates.launch_gate((ctx.state.get("sale_to_cash") or {}).get("checks") or {"simulation_ran": False})


def eval_operate(ctx):
    return gates.operate_gate((ctx.state.get("evidence") or {}).get("real_buyers"), None)


def memo_after(ctx, g):
    Operator(ctx).memo(g)


NODES: list[Node] = [
    Node("p1_s1", 1, "Find opportunities", n_opportunities),
    Node("p1_s2", 1, "Define the market", n_market),
    Node("p1_s3", 1, "Customer interviews (Mom Test)", n_interviews),
    Node("p1_gate", 1, "Evidence gate", _gate_node(eval_discover, 1, "p1_s3", "phase1_gate_decision.md")),
    Node("p2_s1", 2, "Lean Canvas", n_lean_canvas),
    Node("p2_s2", 2, "Landing page", n_landing_page),
    Node("p2_publish", 2, "Founder approval: publish landing page", n_publish_landing),
    Node("p2_gate", 2, "Waitlist gate", _gate_node(eval_validate, 2, "p2_s2", "phase2_gate_decision.md")),
    Node("p3_s1", 3, "Build MVP + user docs", n_build),
    Node("p3_gate", 3, "Tests gate", _gate_node(eval_build, 3, "p3_s1", "phase3_gate_decision.md")),
    Node("p4_s1", 4, "Pricing", n_pricing),
    Node("p4_s2", 4, "Policies", n_policies),
    Node("p4_gate", 4, "Founder approval gate", _gate_node(eval_commercial, 4, "p4_s1", "phase4_gate_decision.md")),
    Node("p5_s1", 5, "Store page + launch posts", n_store),
    Node("p5_publish", 5, "Founder approval: open store, post", n_publish_launch),
    Node("p5_s2", 5, "Sale-to-cash test (MOCKED)", n_sale_to_cash),
    Node("p5_gate", 5, "Launch gate", _gate_node(eval_launch, 5, "p5_s1", "phase5_gate_decision.md")),
    Node("p6_s1", 6, "Support + metrics", n_support),
    Node("p6_gate", 6, "Persevere-or-pivot", _gate_node(eval_operate, 6, "p6_s1", "phase6_gate_decision.md", memo_after)),
]
PHASES = {1: "Discover", 2: "Validate", 3: "Build", 4: "Commercial setup", 5: "Launch", 6: "Operate and learn"}


# =================================================================== runs
def run_dir(run_id: str) -> str:
    return os.path.join(RUNS_DIR, run_id)


def load(run_id: str) -> dict:
    with open(os.path.join(run_dir(run_id), "state.json"), encoding="utf-8") as f:
        return json.load(f)


def save(st: dict) -> None:
    path = os.path.join(st["run_dir"], "state.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1, ensure_ascii=False, default=str)
    os.replace(tmp, path)


def list_runs() -> list[dict]:
    if not os.path.isdir(RUNS_DIR):
        return []
    out = []
    for rid in sorted(os.listdir(RUNS_DIR), reverse=True):
        try:
            st = load(rid)
            out.append({"run_id": rid, "idea": st["brief"].get("idea"), "status": st["status"],
                        "created": st.get("created")})
        except (OSError, ValueError, KeyError):
            continue
    return out


def normalize_brief(brief: dict | str) -> dict:
    if isinstance(brief, str):
        brief = {"idea": brief.strip()}
    b = dict(brief)
    if not b.get("idea"):
        raise ValueError("brief needs an 'idea'")
    if isinstance(b.get("skills"), str):
        b["skills"] = [s.strip() for s in b["skills"].split(",") if s.strip()]
    for k in ("budget_usd", "hours_per_week"):
        if isinstance(b.get(k), str):
            try:
                b[k] = float(b[k])
            except ValueError:
                b[k] = None
    return b


def start_run(brief: dict | str, llm: LLM | None = None) -> str:
    b = normalize_brief(brief)
    run_id = utc_now().replace(":", "").replace("-", "") + "_" + uuid.uuid4().hex[:4]
    d = run_dir(run_id)
    os.makedirs(d, exist_ok=True)
    llm = llm or LLM()
    ok, llm_status = llm.check()
    st = {
        "run_id": run_id, "run_dir": d, "created": utc_now(), "status": "running", "cursor": 0,
        "brief": {k: v for k, v in b.items() if k != "evidence"},
        "evidence": b.get("evidence") or {},
        "node_data": {}, "approvals": [], "artifacts": [],
        "llm": {"provider": llm.provider, "label": llm.label, "status": llm_status, "stubbed": llm.stubbed},
    }
    log = DecisionLog(os.path.join(d, "decision_log.json"), run_id)
    log.append("orchestrator", "start_run", model=None, detail={"idea": b["idea"], "llm": llm.label})
    if st["evidence"]:
        log.append("founder", "provide_evidence_in_brief", model=None, approved_by="founder",
                   detail=sorted(st["evidence"].keys()))

    # Hard limits before any work: excluded categories and embedded trick requests.
    excluded = guardrails.check_brief(json.dumps(st["brief"]))
    for extra in b.get("requests", []) or []:
        ref = guardrails.check_request(extra)
        if ref:
            log.append("guardrail", "refuse_request_in_brief", model=None, outcome="refused", rule=ref.rule)
            st.setdefault("refused_requests", []).append({"request": extra, "rule": ref.rule, "why": ref.message})
    if excluded:
        ctx = Context(st, llm, log, d)
        g = gates.GateResult("phase1_scope_gate", gates.STOP,
                             [f"Out of scope: {', '.join(excluded)}. StopGo does not build these products."])
        _write_gate_file(ctx, "phase1_gate_decision.md", g, None)
        log.append("gate", "phase1_scope_gate", model=None, outcome="stop", excluded=excluded)
        st["status"], st["stopped_reason"] = "stopped", f"excluded category: {', '.join(excluded)}"
    if not ok:
        st["status"], st["stopped_reason"] = "error", llm_status
    save(st)
    return run_id


def advance(run_id: str, llm: LLM | None = None, on_step: Callable[[dict], None] | None = None) -> dict:
    """Run nodes until the pipeline needs the founder, stops, or completes."""
    lock = _locks.setdefault(run_id, threading.Lock())
    with lock:
        st = load(run_id)
        if st["status"] in ("stopped", "completed", "error"):
            return st
        llm = llm or LLM(provider=st["llm"]["provider"])
        if st["llm"]["provider"] != "stub":
            llm.check()
        log = DecisionLog(os.path.join(st["run_dir"], "decision_log.json"), run_id)
        ctx = Context(st, llm, log, st["run_dir"])
        st["status"] = "running"
        while st["cursor"] < len(NODES):
            node = NODES[st["cursor"]]
            st["current"] = node.id
            nd = st["node_data"].setdefault(node.id, {})
            try:
                res = node.run(ctx, nd)
            except Exception as exc:  # surface errors to the founder instead of crashing the server
                st["status"], st["error"] = "error", f"{node.id}: {type(exc).__name__}: {exc}"
                log.append("orchestrator", f"error:{node.id}", model=None, detail=str(exc)[:300])
                save(st)
                raise
            if llm.stubbed and not st["llm"]["stubbed"]:
                st["llm"].update({"stubbed": True, "provider": "stub", "label": llm.label,
                                  "status": llm.fell_back_reason})
            if res == DONE:
                st["cursor"] += 1
            elif res == WAIT:
                st["status"] = "awaiting_founder"
                save(st)
                return st
            elif res == HALT:
                save(st)
                return st
            save(st)
            if on_step:
                on_step(st)
        st["status"] = "completed"
        st["metrics"] = run_metrics(st)
        log.append("orchestrator", "complete_run", model=None, cost=0, metrics=st["metrics"])
        _append_run_summary(ctx, "phase6_gate_decision.md")
        save(st)
        return st


def decide(run_id: str, approval_id: str, decision: str, note: str | None = None) -> dict:
    """Founder-only entry point (called from the UI/CLI handlers)."""
    lock = _locks.setdefault(run_id, threading.Lock())
    with lock:
        st = load(run_id)
        rec = approval.get(st, approval_id)
        if rec["kind"] == "gate" and rec.get("recommended") == gates.STOP and decision == gates.GO \
                and not (note and note.strip()):
            raise ValueError("Overriding a STOP recommendation needs a written reason from the founder.")
        approval.decide(st, approval_id, decision, by=approval.FOUNDER, note=note)
        DecisionLog(os.path.join(st["run_dir"], "decision_log.json"), run_id).append(
            "founder", f"decide:{rec['action']}", model=None, approved_by="founder", outcome=decision,
            approval_id=approval_id, note=note)
        save(st)
        return st


def submit_evidence(run_id: str, data: dict) -> dict:
    """The founder reports evidence only they have (interviews, waitlist, buyers). Re-opens a waiting gate."""
    allowed = {"interviews", "waitlist", "real_buyers"}
    bad = set(data) - allowed
    if bad:
        raise ValueError(f"unknown evidence keys {bad}; allowed: {sorted(allowed)}")
    lock = _locks.setdefault(run_id, threading.Lock())
    with lock:
        st = load(run_id)
        ev = st.setdefault("evidence", {})
        for k, v in data.items():
            ev[k] = {**(ev.get(k) or {}), **v} if isinstance(v, dict) else v
        DecisionLog(os.path.join(st["run_dir"], "decision_log.json"), run_id).append(
            "founder", "submit_evidence", model=None, approved_by="founder", detail=data)
        node = NODES[min(st["cursor"], len(NODES) - 1)]
        if node.id.endswith("_gate") and st["status"] == "awaiting_founder":
            target = "p1_s3" if node.id == "p1_gate" else node.id
            _jump(st, target)
        save(st)
    return st


def ask(request: str, llm: LLM | None = None) -> dict:
    d = os.path.join(RUNS_DIR, "_concierge")
    os.makedirs(d, exist_ok=True)
    llm = llm or LLM()
    llm.check()
    st = {"brief": {}, "run_dir": d}
    ctx = Context(st, llm, DecisionLog(os.path.join(d, "decision_log.json")), d)
    return Concierge(ctx).answer(request)


def export(run_id: str, suffix: str = "", reset_log: bool = False, dest: str = ROOT) -> list[str]:
    """Copy a run's outputs to outputs/ and its log into decision_log.json (the committed demo run)."""
    st = load(run_id)
    problems = claims.audit_dir(os.path.join(st["run_dir"], "outputs"))
    if problems:
        raise ValueError(f"claims audit failed, not exporting: {problems}")
    out_dir = os.path.join(dest, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    written = []
    src_dir = os.path.join(st["run_dir"], "outputs")
    for name in sorted(os.listdir(src_dir)):
        base, ext = os.path.splitext(name)
        target = f"{base}{suffix}{ext}"
        shutil.copyfile(os.path.join(src_dir, name), os.path.join(out_dir, target))
        written.append(target)
    log_path = os.path.join(dest, "decision_log.json")
    existing = []
    if not reset_log and os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as f:
            existing = json.load(f)
    with open(os.path.join(st["run_dir"], "decision_log.json"), encoding="utf-8") as f:
        existing += json.load(f)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=1, ensure_ascii=False)
    return written


# =================================================================== CLI
def describe(st: dict) -> str:
    lines = [f"run {st['run_id']}  status={st['status']}  LLM={st['llm']['label']}"]
    if st.get("stopped_reason"):
        lines.append(f"  stopped: {st['stopped_reason']}")
    if st.get("error"):
        lines.append(f"  error: {st['error']}")
    for rec in approval.pending(st):
        rec_txt = f" (recommended: {rec['recommended']})" if rec.get("recommended") else ""
        lines.append(f"  PENDING {rec['id']}: {rec['summary']}{rec_txt} options={rec['options']}")
    return "\n".join(lines)


def _interactive(run_id: str) -> dict:
    """Terminal UI for the founder: every gated action waits for typed input."""
    st = advance(run_id)
    while st["status"] == "awaiting_founder":
        print("\n" + describe(st))
        node = NODES[st["cursor"]]
        rec = approval.pending(st)[0]
        if rec["kind"] == "gate":
            gfile = os.path.join(st["run_dir"], "outputs", f"phase{node.phase}_gate_decision.md")
            if os.path.exists(gfile):
                print("\n" + open(gfile, encoding="utf-8").read())
            if node.id in ("p1_gate", "p2_gate", "p6_gate"):
                raw = input("Founder: report new evidence as JSON, or press Enter to decide now > ").strip()
                if raw:
                    try:
                        submit_evidence(run_id, json.loads(raw))
                    except ValueError as exc:
                        print(f"  {exc}")
                    st = advance(run_id)
                    continue
        choice = input(f"[{rec['id']}] {rec['summary']} {rec['options']} > ").strip().lower()
        while choice not in rec["options"]:
            choice = input(f"  choose one of {rec['options']} > ").strip().lower()
        note = input("  note (optional; required to override STOP) > ").strip() or None
        try:
            decide(run_id, rec["id"], choice, note)
        except ValueError as exc:
            print(f"  {exc}")
        st = advance(run_id)
    print("\n" + describe(st))
    return st


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="stopgo", description="StopGo agentic venture builder")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("brief"); r.add_argument("--no-input", action="store_true")
    s = sub.add_parser("status"); s.add_argument("run_id")
    d = sub.add_parser("decide"); d.add_argument("run_id"); d.add_argument("approval_id"); d.add_argument("decision")
    d.add_argument("--note")
    e = sub.add_parser("evidence"); e.add_argument("run_id"); e.add_argument("json")
    a = sub.add_parser("ask"); a.add_argument("request")
    x = sub.add_parser("export"); x.add_argument("run_id"); x.add_argument("--suffix", default="")
    x.add_argument("--reset-log", action="store_true")
    sub.add_parser("list")
    c = sub.add_parser("cost"); c.add_argument("run_id")
    args = p.parse_args(argv)

    if args.cmd == "run":
        if os.path.exists(args.brief):
            with open(args.brief, encoding="utf-8") as f:
                raw = f.read()
            brief = json.loads(raw) if args.brief.endswith(".json") else raw
        else:
            brief = args.brief
        rid = start_run(brief)
        print(f"started {rid}")
        st = advance(rid) if args.no_input else _interactive(rid)
        if args.no_input:
            print(describe(st))
    elif args.cmd == "status":
        print(describe(load(args.run_id)))
    elif args.cmd == "decide":
        decide(args.run_id, args.approval_id, args.decision, args.note)
        print(describe(advance(args.run_id)))
    elif args.cmd == "evidence":
        submit_evidence(args.run_id, json.loads(args.json))
        print(describe(advance(args.run_id)))
    elif args.cmd == "ask":
        print(json.dumps(ask(args.request), indent=1))
    elif args.cmd == "export":
        for w in export(args.run_id, args.suffix, args.reset_log):
            print("outputs/" + w)
    elif args.cmd == "cost":
        print(json.dumps(run_metrics(load(args.run_id)), indent=1))
    elif args.cmd == "list":
        for rinfo in list_runs():
            print(f"{rinfo['run_id']}  {rinfo['status']:<17} {rinfo['idea']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
