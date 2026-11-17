import pytest

import approval
import orchestrator as orch
import publisher


def make_state(tmp_path):
    return {"approvals": [], "run_dir": str(tmp_path)}


def test_publish_without_approval_is_blocked(tmp_path):
    st = make_state(tmp_path)
    with pytest.raises(approval.ApprovalRequired):
        publisher.publish_landing_page(st, None, "<html></html>")
    rec = approval.request(st, "publish_landing_page", "<html></html>", "test")
    with pytest.raises(approval.ApprovalRequired):  # still pending
        publisher.publish_landing_page(st, rec["id"], "<html></html>")
    assert not (tmp_path / "published").exists()


def test_rejected_is_blocked(tmp_path):
    st = make_state(tmp_path)
    rec = approval.request(st, "publish_store_page", "x", "test")
    approval.decide(st, rec["id"], "reject", by="founder")
    with pytest.raises(approval.ApprovalRejected):
        publisher.publish_store_page(st, rec["id"], "x")


def test_content_changed_after_approval_is_blocked(tmp_path):
    st = make_state(tmp_path)
    rec = approval.request(st, "post_launch_posts", "original", "test")
    approval.decide(st, rec["id"], "approve", by="founder")
    with pytest.raises(approval.ApprovalRequired):
        publisher.post_launch_posts(st, rec["id"], "edited after approval")
    assert publisher.post_launch_posts(st, rec["id"], "original")["mocked"] is True


def test_approval_for_other_action_cannot_be_reused(tmp_path):
    st = make_state(tmp_path)
    rec = approval.request(st, "publish_landing_page", "x", "test")
    approval.decide(st, rec["id"], "approve", by="founder")
    with pytest.raises(approval.ApprovalRequired):
        publisher.publish_store_page(st, rec["id"], "x")


def test_only_founder_can_decide(tmp_path):
    st = make_state(tmp_path)
    rec = approval.request(st, "spend", {"usd": 10}, "test")
    with pytest.raises(PermissionError):
        approval.decide(st, rec["id"], "approve", by="researcher")


def test_pipeline_pauses_for_founder_and_never_publishes_alone():
    rid = orch.start_run({"idea": "A CLI that checks .env files against .env.example", "skills": ["Python"],
                          "hours_per_week": 10, "budget_usd": 0, "target_market": "backend developers",
                          "evidence": {"interviews": {"completed": 8, "problem_confirmed": 6}}})
    st = orch.advance(rid)
    assert st["status"] == "awaiting_founder"
    # Approve the phase 1 gate only; the pipeline must then stop at the publish approval.
    orch.decide(rid, approval.pending(st)[0]["id"], "go")
    st = orch.advance(rid)
    pending = approval.pending(st)
    assert st["status"] == "awaiting_founder" and pending[0]["action"] == "publish_landing_page"
    import os
    assert not os.path.exists(os.path.join(st["run_dir"], "published"))


def test_overriding_stop_needs_a_reason():
    rid = orch.start_run({"idea": "A CLI that pretty-prints JSON", "skills": ["JavaScript"],
                          "evidence": {"interviews": {"completed": 6, "problem_confirmed": 1}}})
    st = orch.advance(rid)
    rec = approval.pending(st)[0]
    assert rec["recommended"] == "stop"
    with pytest.raises(ValueError):
        orch.decide(rid, rec["id"], "go")
