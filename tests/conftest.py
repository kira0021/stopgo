import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def offline_stub(tmp_path, monkeypatch):
    """Every test runs offline with the STUBBED model and its own runs dir."""
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    monkeypatch.setenv("EVIDENCE_OFFLINE", "1")
    import orchestrator
    monkeypatch.setattr(orchestrator, "RUNS_DIR", str(tmp_path / "runs"))
    yield
