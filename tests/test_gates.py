import gates


def iv(done, confirmed):
    return {"interviews": {"completed": done, "problem_confirmed": confirmed}}


def test_weak_evidence_recommends_stop():
    g = gates.discover_gate(iv(6, 1), founder_fit=0.8, excluded=[])
    assert g.recommended == gates.STOP


def test_strong_evidence_goes():
    assert gates.discover_gate(iv(8, 6), founder_fit=0.8, excluded=[]).recommended == gates.GO


def test_missing_evidence_repeats_not_go():
    g = gates.discover_gate({}, founder_fit=1.0, excluded=[])
    assert g.recommended == gates.REPEAT and g.missing


def test_middling_evidence_pivots():
    assert gates.discover_gate(iv(10, 4), founder_fit=0.8, excluded=[]).recommended == gates.PIVOT


def test_excluded_category_stops():
    assert gates.discover_gate(iv(10, 9), 1.0, excluded=["health advice"]).recommended == gates.STOP


def test_waitlist_example_from_problem_statement_stops():
    # Target 100 sign-ups in 14 days, got 12 -> the gate fails and recommends stop, not spin.
    g = gates.validate_gate({"waitlist": {"target": 100, "window_days": 14, "signups": 12}})
    assert g.recommended == gates.STOP


def test_waitlist_bands():
    def r(n):
        return gates.validate_gate({"waitlist": {"target": 100, "signups": n}}).recommended
    assert (r(120), r(60), r(30), r(10)) == (gates.GO, gates.REPEAT, gates.PIVOT, gates.STOP)


def test_waitlist_without_data_repeats():
    assert gates.validate_gate({}).recommended == gates.REPEAT


def test_build_gate_needs_real_core():
    assert gates.build_gate(True, 1, core_stubbed=True).recommended == gates.REPEAT
    assert gates.build_gate(True, 1, core_stubbed=False).recommended == gates.GO


def test_weak_interviews_stop_even_with_strong_public_signals():
    ev = {**iv(6, 1), "public": {"stackoverflow": {"count": 5000, "url": "https://stackoverflow.com/search?q=x"},
                                  "github": {"top_stars": 50, "url": "https://github.com/search?q=x"}}}
    assert gates.discover_gate(ev, founder_fit=1.0, excluded=[]).recommended == gates.STOP


def test_stop_reasons_name_cited_alternatives():
    alts = [{"name": "jq", "url": "https://github.com/jqlang/jq"}]
    g = gates.discover_gate(iv(6, 1), founder_fit=0.55, excluded=[], known_alternatives=alts)
    text = " ".join(g.reasons)
    assert g.recommended == gates.STOP and "https://github.com/jqlang/jq" in text and "17%" in text
