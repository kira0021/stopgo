"""The Ollama client path, tested against a tiny fake Ollama server (no model needed)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from llm import LLM, extract_json


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._json({"models": [{"name": "qwen3:4b"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert body["model"] == "qwen3:4b" and body["stream"] is False
        content = '<think>hidden</think>{"ok": true}' if body.get("format") == "json" else "Hello"
        self._json({"message": {"content": content}, "prompt_eval_count": 10, "eval_count": 5})


@pytest.fixture
def fake_ollama(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("OLLAMA_HOST", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:4b")
    yield
    srv.shutdown()


def test_ollama_path(fake_ollama):
    llm = LLM(provider="ollama", fallback="fail")
    ok, _ = llm.check()
    assert ok and not llm.stubbed
    r = llm.complete("sys", "user", stub_text="STUB")
    assert r.text == "Hello" and r.tokens == 15 and r.cost == 0 and not r.stubbed
    rj = llm.complete("sys", "user", stub_text="{}", json_mode=True)
    assert extract_json(rj.text) == {"ok": True}


def test_unreachable_ollama_falls_back_to_labelled_stub(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    llm = LLM(provider="ollama", fallback="stub")
    ok, msg = llm.check()
    assert ok and llm.stubbed and "STUBBED" in msg
    assert llm.complete("s", "u", stub_text="T").model == "stub (STUBBED)"


def test_unreachable_ollama_without_fallback_fails(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9")
    ok, _ = LLM(provider="ollama", fallback="fail").check()
    assert not ok
