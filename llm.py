"""Model client. Free backends only.

Providers
---------
ollama         Local open-weight model (default qwen3:4b). Cost $0.
openai_compat  A FREE-tier OpenAI-compatible endpoint serving an open-weight
               model (for example GPT-OSS 20B). Cost recorded as $0; never
               configure a paid plan.
stub           Deterministic text supplied by each agent. Every stubbed
               response is labelled STUBBED in the UI, the outputs and the log.

If the configured provider is unreachable and LLM_FALLBACK=stub (default), the
client switches to the stub for the rest of the run and says so.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

STUB_MODEL = "stub (STUBBED)"


@dataclass
class LLMResult:
    text: str
    model: str
    tokens: int = 0
    cost: float = 0.0
    stubbed: bool = False
    prompt_tokens_est: int = 0     # measured prompt size (chars / 4), for every provider including the stub


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 600) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _get_json(url: str, timeout: int = 2) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def extract_json(text: str):
    """Best-effort JSON extraction from a model reply. Returns None on failure."""
    text = strip_thinking(text)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    candidates = [fence.group(1)] if fence else []
    candidates.append(text)
    for c in candidates:
        c = c.strip()
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = c.find(opener), c.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(c[start : end + 1])
                except json.JSONDecodeError:
                    continue
    return None


class LLM:
    def __init__(self, provider: str | None = None, fallback: str | None = None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "ollama")).lower()
        self.fallback = (fallback or os.getenv("LLM_FALLBACK", "stub")).lower()
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen3:4b")
        self.oc_base = os.getenv("OPENAI_COMPAT_BASE_URL", "").rstrip("/")
        self.oc_key = os.getenv("OPENAI_COMPAT_API_KEY", "")
        self.oc_model = os.getenv("OPENAI_COMPAT_MODEL", "")
        self.max_output_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1500"))
        self.fell_back_reason: str | None = None
        self.total_tokens = 0

    # ------------------------------------------------------------------ status
    @property
    def stubbed(self) -> bool:
        return self.provider == "stub"

    @property
    def label(self) -> str:
        if self.provider == "ollama":
            return f"{self.ollama_model} via Ollama (local, open-weight)"
        if self.provider == "openai_compat":
            return f"{self.oc_model} via free-tier endpoint"
        return "STUBBED (deterministic templates, no model)"

    def check(self) -> tuple[bool, str]:
        """Probe the backend. Falls back to the stub if allowed."""
        if self.provider == "stub":
            return True, "stub"
        try:
            if self.provider == "ollama":
                tags = _get_json(f"{self.ollama_host}/api/tags")
                names = [m.get("name", "") for m in tags.get("models", [])]
                want = self.ollama_model if ":" in self.ollama_model else self.ollama_model + ":latest"
                if want not in names:
                    raise RuntimeError(f"model {self.ollama_model} not pulled yet (have: {names or 'none'})")
            elif self.provider == "openai_compat":
                if not (self.oc_base and self.oc_model):
                    raise RuntimeError("OPENAI_COMPAT_BASE_URL / OPENAI_COMPAT_MODEL not set")
            else:
                raise RuntimeError(f"unknown LLM_PROVIDER {self.provider}")
            return True, self.label
        except Exception as exc:  # noqa: BLE001 - any failure means "not available"
            return self._fallback(str(exc))

    def _fallback(self, reason: str) -> tuple[bool, str]:
        if self.fallback == "stub":
            self.fell_back_reason = f"{self.provider} unavailable ({reason}); using STUBBED LLM"
            self.provider = "stub"
            return True, self.fell_back_reason
        return False, reason

    # -------------------------------------------------------------- completion
    def complete(self, system: str, user: str, *, stub_text: str, json_mode: bool = False,
                 temperature: float = 0.4) -> LLMResult:
        """Run one completion. `stub_text` is what the STUBBED backend returns."""
        est = (len(system) + len(user)) // 4
        res = self._complete(system, user, stub_text=stub_text, json_mode=json_mode, temperature=temperature)
        res.prompt_tokens_est = est
        return res

    def _complete(self, system: str, user: str, *, stub_text: str, json_mode: bool, temperature: float) -> LLMResult:
        if self.provider == "stub":
            return LLMResult(text=stub_text, model=STUB_MODEL, stubbed=True)
        try:
            if self.provider == "ollama":
                payload = {
                    "model": self.ollama_model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "stream": False,
                    "think": False,
                    "options": {"temperature": temperature, "num_predict": self.max_output_tokens},
                }
                if json_mode:
                    payload["format"] = "json"
                r = _post_json(f"{self.ollama_host}/api/chat", payload)
                text = strip_thinking(r.get("message", {}).get("content", ""))
                tokens = int(r.get("prompt_eval_count", 0)) + int(r.get("eval_count", 0))
                self.total_tokens += tokens
                return LLMResult(text=text, model=self.ollama_model, tokens=tokens, cost=0.0)
            if self.provider == "openai_compat":
                payload = {
                    "model": self.oc_model,
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                    "temperature": temperature,
                    "max_tokens": self.max_output_tokens,
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}
                r = _post_json(f"{self.oc_base}/chat/completions", payload,
                               headers={"Authorization": f"Bearer {self.oc_key}"})
                text = strip_thinking(r["choices"][0]["message"]["content"])
                tokens = int(r.get("usage", {}).get("total_tokens", 0))
                self.total_tokens += tokens
                return LLMResult(text=text, model=self.oc_model, tokens=tokens, cost=0.0)
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError) as exc:
            ok, _ = self._fallback(str(exc))
            if ok:
                return LLMResult(text=stub_text, model=STUB_MODEL, stubbed=True)
            raise
        raise RuntimeError(f"unknown LLM_PROVIDER {self.provider}")
