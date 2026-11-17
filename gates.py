"""Gates and the STOP recommendation engine.

Every phase ends with a gate. A gate is one of:
  * an evidence threshold set *before* the evidence comes in,
  * tests passing, or
  * founder approval.
Outcomes: go | repeat | pivot | stop. The system recommends; the founder
decides, and the decision is logged. Thresholds are fixed constants here so the
system cannot move the goalposts after seeing the data.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

GO, REPEAT, PIVOT, STOP = "go", "repeat", "pivot", "stop"
OUTCOMES = (GO, REPEAT, PIVOT, STOP)

# Pre-set thresholds. Changing these is a code change, visible in git history.
THRESHOLDS = {
    "discover": {
        "min_interviews": 5,              # Mom Test conversations completed
        "go_problem_rate": 0.5,           # share who described the problem from recent experience
        "stop_problem_rate": 0.3,         # below this, recommend STOP
        "min_public_pain_hits": 20,       # Stack Overflow questions matching the problem
        "min_founder_fit": 0.5,           # 0..1 from the fit rubric
        "max_free_alternatives_stars": 5000,  # a free tool this popular is a strong incumbent
    },
    "validate": {
        "default_waitlist_target": 100,
        "default_window_days": 14,
        "go_ratio": 1.0,                  # >= 100% of target -> go
        "repeat_ratio": 0.5,              # 50-99% -> repeat (iterate message, extend once)
        "pivot_ratio": 0.25,              # 25-49% -> pivot; below 25% -> stop
    },
    "build": {"max_test_attempts": 3},
    "operate": {"min_real_buyers_for_decision": 10},
}


@dataclass
class Check:
    name: str
    passed: bool | None          # None = no data
    value: object
    threshold: object
    source: str                  # URL, "founder-reported", or "ASSUMPTION"


@dataclass
class GateResult:
    gate: str
    recommended: str
    reasons: list[str]
    checks: list[Check] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["checks"] = [asdict(c) for c in self.checks]
        return d


# ------------------------------------------------------------------ phase 1
def discover_gate(evidence: dict, founder_fit: float, excluded: list[str],
                  known_alternatives: list[dict] | None = None) -> GateResult:
    t = THRESHOLDS["discover"]
    checks: list[Check] = []
    reasons: list[str] = []

    if excluded:
        return GateResult("phase1_evidence_gate", STOP,
                          [f"Idea falls in an excluded category: {', '.join(excluded)}."])

    iv = evidence.get("interviews") or {}
    done = iv.get("completed")
    confirmed = iv.get("problem_confirmed")
    rate = (confirmed / done) if done else None
    checks.append(Check("interviews_completed", None if done is None else done >= t["min_interviews"],
                        done, f">= {t['min_interviews']}", "founder-reported"))
    checks.append(Check("problem_confirmed_rate", None if rate is None else rate >= t["go_problem_rate"],
                        None if rate is None else round(rate, 2), f">= {t['go_problem_rate']}", "founder-reported"))

    pub = evidence.get("public") or {}
    so = pub.get("stackoverflow") or {}
    so_hits = so.get("count")
    checks.append(Check("public_pain_signal (Stack Overflow questions)",
                        None if so_hits is None else so_hits >= t["min_public_pain_hits"],
                        so_hits, f">= {t['min_public_pain_hits']}", so.get("url") or "unavailable"))
    gh = pub.get("github") or {}
    top_stars = gh.get("top_stars")
    checks.append(Check("strongest_free_alternative_stars",
                        None if top_stars is None else top_stars <= t["max_free_alternatives_stars"],
                        top_stars, f"<= {t['max_free_alternatives_stars']}", gh.get("url") or "unavailable"))
    checks.append(Check("founder_fit", founder_fit >= t["min_founder_fit"], round(founder_fit, 2),
                        f">= {t['min_founder_fit']}", "rubric over the founder brief"))
    alts = [a for a in (known_alternatives or []) if isinstance(a, dict) and a.get("url")]
    if alts:
        checks.append(Check("founder_cited_alternatives (context, not scored)", None,
                            ", ".join(a.get("name", "?") for a in alts), "context only",
                            " ".join(a["url"] for a in alts)))

    missing = []
    if done is None or confirmed is None:
        missing.append("interviews.completed and interviews.problem_confirmed (run the Mom Test script first)")

    # Decision
    if done is None:
        reasons.append("No customer interview evidence yet. Run the interview script, then report results.")
        return GateResult("phase1_evidence_gate", REPEAT, reasons, checks, missing)
    if done < t["min_interviews"]:
        reasons.append(f"Only {done} interviews; the pre-set minimum is {t['min_interviews']}.")
        if rate is not None and rate < t["stop_problem_rate"] and done >= 3:
            reasons.append(f"Early signal is weak ({rate:.0%} confirmed the problem).")
        return GateResult("phase1_evidence_gate", REPEAT, reasons, checks, missing)

    strong_incumbent = top_stars is not None and top_stars > t["max_free_alternatives_stars"]
    weak_public = so_hits is not None and so_hits < t["min_public_pain_hits"]

    if rate < t["stop_problem_rate"]:
        reasons.append(f"Only {confirmed}/{done} interviewees ({rate:.0%}) described the problem from recent "
                       f"experience; the pre-set stop line is {t['stop_problem_rate']:.0%}.")
        if strong_incumbent:
            reasons.append(f"A free alternative already has {top_stars} GitHub stars.")
        if weak_public:
            reasons.append(f"Public pain signal is low ({so_hits} matching Stack Overflow questions).")
        if alts:
            reasons.append("Free alternatives the founder already cited cover this job: "
                           + "; ".join(f"{a.get('name')} ({a['url']})" for a in alts) + ".")
        if founder_fit < 0.6:
            reasons.append(f"Founder fit is marginal ({founder_fit:.2f}): see the rubric in phase1_step1_opportunities.")
        reasons.append("Recommendation: STOP. Do not build this. The evidence does not support demand, and "
                       "spending more time here would cost the founder more than it is likely to teach.")
        return GateResult("phase1_evidence_gate", STOP, reasons, checks, missing)
    if rate < t["go_problem_rate"]:
        reasons.append(f"{rate:.0%} confirmed the problem: some pain, but below the {t['go_problem_rate']:.0%} go line. "
                       "Recommendation: PIVOT to the segment or job where pain was strongest.")
        return GateResult("phase1_evidence_gate", PIVOT, reasons, checks, missing)
    if founder_fit < t["min_founder_fit"]:
        reasons.append("Demand looks real, but the founder's skills/time/budget fit is weak. Recommendation: PIVOT "
                       "to a version the founder can build and support.")
        return GateResult("phase1_evidence_gate", PIVOT, reasons, checks, missing)
    if strong_incumbent and weak_public:
        reasons.append("Interviews are positive but a popular free tool exists and public pain is low. "
                       "Recommendation: PIVOT to a clear differentiator, or STOP.")
        return GateResult("phase1_evidence_gate", PIVOT, reasons, checks, missing)

    reasons.append(f"{confirmed}/{done} interviewees ({rate:.0%}) described the problem from recent experience "
                   f"(go line {t['go_problem_rate']:.0%}). Recommendation: GO to Validate.")
    if strong_incumbent:
        reasons.append(f"Note: a free alternative has {top_stars} stars; positioning must say why this is different.")
    return GateResult("phase1_evidence_gate", GO, reasons, checks, missing)


# ------------------------------------------------------------------ phase 2
def validate_gate(evidence: dict) -> GateResult:
    t = THRESHOLDS["validate"]
    wl = evidence.get("waitlist") or {}
    target = wl.get("target") or t["default_waitlist_target"]
    days = wl.get("window_days") or t["default_window_days"]
    signups = wl.get("signups")
    if signups is None:
        return GateResult(
            "phase2_waitlist_gate", REPEAT,
            [f"Target set before launch: {target} waitlist sign-ups in {days} days. No results reported yet. "
             "Publish the landing page (after approval), wait for the window to close, then report real sign-ups."],
            [Check("waitlist_signups", None, None, f">= {target} in {days} days", "founder-reported")],
            ["waitlist.signups (real count from your form provider)"],
        )
    ratio = signups / target
    chk = [Check("waitlist_signups", ratio >= t["go_ratio"], signups, f">= {target} in {days} days", "founder-reported"),
           Check("ratio_to_target", None, round(ratio, 2), "go >= 1.0, repeat >= 0.5, pivot >= 0.25", "computed")]
    if ratio >= t["go_ratio"]:
        return GateResult("phase2_waitlist_gate", GO, [f"{signups}/{target} sign-ups ({ratio:.0%}). Target met. GO to Build."], chk)
    if ratio >= t["repeat_ratio"]:
        return GateResult("phase2_waitlist_gate", REPEAT, [f"{signups}/{target} ({ratio:.0%}): close. REPEAT once with a "
                          "sharper message to the same segment; do not lower the target."], chk)
    if ratio >= t["pivot_ratio"]:
        return GateResult("phase2_waitlist_gate", PIVOT, [f"{signups}/{target} ({ratio:.0%}): weak. PIVOT back to Discover "
                          "and re-test the problem or the segment."], chk)
    return GateResult("phase2_waitlist_gate", STOP, [f"{signups}/{target} ({ratio:.0%}) against a target set in advance. "
                      "Recommendation: STOP. Do not spin this result."], chk)


# ------------------------------------------------------------------ phase 3
def build_gate(test_passed: bool, attempts: int, core_stubbed: bool) -> GateResult:
    t = THRESHOLDS["build"]
    chk = [Check("mvp_tests_pass", test_passed, test_passed, "all pass", "pytest run"),
           Check("core_logic_generated", not core_stubbed, not core_stubbed, "model-written core", "builder")]
    if test_passed and not core_stubbed:
        return GateResult("phase3_tests_gate", GO, ["MVP tests pass. GO to Commercial setup."], chk)
    if test_passed and core_stubbed:
        return GateResult("phase3_tests_gate", REPEAT, ["Scaffold tests pass, but the core feature is STUBBED. "
                          "REPEAT the build with a model, or have the founder implement the core."], chk)
    if attempts < t["max_test_attempts"]:
        return GateResult("phase3_tests_gate", REPEAT, [f"Tests failed (attempt {attempts}). REPEAT build."], chk)
    return GateResult("phase3_tests_gate", PIVOT, ["Tests still fail after the maximum attempts. PIVOT to a smaller scope."], chk)


# ------------------------------------------------------------------ phase 5
def launch_gate(sim_checks: dict[str, bool]) -> GateResult:
    chk = [Check(k, v, v, True, "mocked sale-to-cash simulation") for k, v in sim_checks.items()]
    if all(sim_checks.values()):
        return GateResult("phase5_launch_gate", GO, ["All sale-to-cash checks pass on the MOCKED flow. "
                          "GO, pending founder approval to open the (mocked) store."], chk)
    failed = [k for k, v in sim_checks.items() if not v]
    return GateResult("phase5_launch_gate", REPEAT, [f"Failed checks: {', '.join(failed)}. REPEAT before launch."], chk)


# ------------------------------------------------------------------ phase 6
def operate_gate(real_buyers: int | None, refund_rate: float | None) -> GateResult:
    t = THRESHOLDS["operate"]
    chk = [Check("real_buyers", None if real_buyers is None else real_buyers >= t["min_real_buyers_for_decision"],
                 real_buyers, f">= {t['min_real_buyers_for_decision']}", "founder-reported")]
    if not real_buyers or real_buyers < t["min_real_buyers_for_decision"]:
        return GateResult("phase6_persevere_or_pivot", REPEAT,
                          ["Not enough real buyers to decide persevere vs pivot. Metrics in this run are MOCKED. "
                           "REPEAT: run the launch for real (with approval) and collect data."], chk,
                          ["real buyer count"])
    if refund_rate is not None and refund_rate > 0.2:
        return GateResult("phase6_persevere_or_pivot", PIVOT, [f"Refund rate {refund_rate:.0%} is high. PIVOT."], chk)
    return GateResult("phase6_persevere_or_pivot", GO, ["Enough real buyers and low refunds. PERSEVERE."], chk)


# --------------------------------------------------------------- founder fit
def founder_fit(brief: dict) -> tuple[float, list[str]]:
    """Simple transparent rubric (0..1). Each line explains a point."""
    notes, score = [], 0.0
    skills = " ".join(brief.get("skills") or []).lower() if isinstance(brief.get("skills"), list) else str(brief.get("skills", "")).lower()
    if any(k in skills for k in ("python", "javascript", "typescript", "go", "rust", "developer", "engineer", "programming", "code", "software")):
        score += 0.4; notes.append("+0.4 founder can write software (needed for a developer tool)")
    else:
        notes.append("+0.0 no programming skill listed; a developer tool will be hard to build and support")
    hours = brief.get("hours_per_week")
    if isinstance(hours, (int, float)) and hours >= 10:
        score += 0.3; notes.append(f"+0.3 {hours} h/week is enough for a small MVP")
    elif isinstance(hours, (int, float)) and hours >= 5:
        score += 0.15; notes.append(f"+0.15 {hours} h/week is tight")
    else:
        notes.append("+0.0 time per week unknown or under 5 h")
    budget = brief.get("budget_usd")
    if isinstance(budget, (int, float)) and budget >= 0:
        score += 0.15; notes.append(f"+0.15 budget ${budget} is enough: StopGo itself costs $0 to run")
    market = str(brief.get("target_market", "")).lower()
    if any(k in market for k in ("developer", "engineer", "devops", "programmer", "maintainer", "data scien", "sre")):
        score += 0.15; notes.append("+0.15 target market is technical users the founder can reach")
    else:
        notes.append("+0.0 target market is not clearly technical users")
    return round(min(score, 1.0), 2), notes
