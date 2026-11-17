"""StopGo web UI (standard library only). Open http://localhost:8000

The founder starts a run from a brief, watches each phase, reads every output,
and approves or rejects every gated action. Agents cannot click these buttons:
decisions only arrive through the POST handlers below, which call
orchestrator.decide(..., by founder).
"""
from __future__ import annotations

import argparse
import html
import json
import os
import threading
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import approval
import orchestrator as orch
from llm import LLM

ROOT = os.path.dirname(os.path.abspath(__file__))
BRIEFS = os.path.join(ROOT, "briefs")
_workers: dict[str, threading.Thread] = {}

CSS = """
*{box-sizing:border-box}body{font-family:ui-sans-serif,system-ui,sans-serif;margin:0;color:#16181d;background:#f6f6f3}
header{background:#16181d;color:#fff;padding:.8rem 1.4rem;display:flex;gap:1rem;align-items:center}
header a{color:#fff;text-decoration:none;font-weight:700;letter-spacing:.02em}
main{max-width:1080px;margin:1.2rem auto;padding:0 1rem}
.card{background:#fff;border:1px solid #deded8;border-radius:10px;padding:1rem 1.2rem;margin-bottom:1rem}
.banner{padding:.55rem 1rem;font-weight:600}.stub{background:#ffd9d9;color:#7a0000}.live{background:#dff5e3;color:#0b5a1f}
.pill{display:inline-block;padding:.1rem .55rem;border-radius:99px;font-size:.78rem;font-weight:700;background:#eee}
.go{background:#d7f5dd;color:#0b5a1f}.stop{background:#ffd6d6;color:#8a0000}.repeat{background:#fff1c7;color:#6b5000}
.pivot{background:#e1e6ff;color:#1d2f8a}.pending{background:#fff1c7}.approved,.decided{background:#d7f5dd}.rejected{background:#ffd6d6}
table{border-collapse:collapse;width:100%;font-size:.88rem}td,th{border-bottom:1px solid #eee;padding:.35rem .4rem;text-align:left;vertical-align:top}
textarea,input,select{font:inherit;padding:.45rem;border:1px solid #ccc;border-radius:6px;width:100%}
button{font:inherit;padding:.45rem .9rem;border-radius:6px;border:1px solid #16181d;background:#16181d;color:#fff;cursor:pointer}
button.alt{background:#fff;color:#16181d}.row{display:flex;gap:.6rem;flex-wrap:wrap;align-items:center}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.6rem}
pre{white-space:pre-wrap;background:#fafaf7;border:1px solid #eee;padding:.8rem;border-radius:8px;font-size:.85rem}
.phase{border-left:4px solid #ccc;padding:.2rem .7rem;margin:.3rem 0}.phase.done{border-color:#2a9d4b}.phase.now{border-color:#e0a800}
small{color:#666}
"""


def esc(x) -> str:
    return html.escape(str(x if x is not None else ""))


def page(title: str, body: str, refresh: bool = False, llm_label: str | None = None, stubbed: bool | None = None) -> bytes:
    if stubbed is None:
        llm = LLM()
        llm.check()
        stubbed, llm_label = llm.stubbed, llm.label
    banner = (f'<div class="banner stub">LLM: STUBBED. Model-written text is deterministic template text, not a model. '
              f'{esc(llm_label)}</div>' if stubbed else f'<div class="banner live">LLM: {esc(llm_label)} &middot; $0.00</div>')
    meta = '<meta http-equiv="refresh" content="2">' if refresh else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">{meta}<title>{esc(title)} · StopGo</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body>
<header><a href="/">StopGo</a><span>open-source venture builder · the founder decides</span></header>{banner}
<main>{body}</main></body></html>""".encode()


def start_worker(run_id: str) -> None:
    t = _workers.get(run_id)
    if t and t.is_alive():
        return

    def work():
        try:
            orch.advance(run_id)
        except Exception:  # noqa: BLE001 - recorded in state by advance()
            traceback.print_exc()

    t = threading.Thread(target=work, daemon=True)
    _workers[run_id] = t
    t.start()


def is_working(run_id: str) -> bool:
    t = _workers.get(run_id)
    return bool(t and t.is_alive())


# ------------------------------------------------------------------ views
def view_index() -> bytes:
    samples = sorted(f for f in os.listdir(BRIEFS) if f.endswith(".json"))
    opts = "".join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in samples)
    runs = orch.list_runs()
    rows = "".join(f'<tr><td><a href="/run/{esc(r["run_id"])}">{esc(r["run_id"])}</a></td><td>{esc(r["idea"])}</td>'
                   f'<td><span class="pill {esc(r["status"])}">{esc(r["status"])}</span></td></tr>' for r in runs)
    body = f"""
<div class="card"><h2>New run from a founder brief</h2>
<form method="post" action="/start">
<div class="grid">
<label>Idea (required)<textarea name="idea" rows="3" placeholder="e.g. a CLI that ..."></textarea></label>
<label>Skills (comma-separated)<input name="skills" placeholder="Python, DevOps"></label>
<label>Budget (USD)<input name="budget_usd" placeholder="50"></label>
<label>Hours per week<input name="hours_per_week" placeholder="10"></label>
<label>Target market<input name="target_market" placeholder="backend developers"></label>
<label>Values<input name="values" placeholder="open source, privacy"></label>
</div>
<p><small>Evidence you already have (interviews, waitlist) can be added later from the run page.
Excluded: physical goods; financial, investment or crypto; health or legal advice products.</small></p>
<button>Start run</button></form>
<form method="post" action="/start-sample" class="row" style="margin-top:.8rem">
<select name="sample" style="max-width:320px">{opts}</select><button class="alt">Start a demo brief</button></form></div>
<div class="card"><h2>Ask the team</h2><form method="post" action="/ask" class="row">
<input name="q" placeholder="Ask anything. Hard limits are enforced in code." style="flex:1"><button>Ask</button></form></div>
<div class="card"><h2>Runs</h2><table><tr><th>Run</th><th>Idea</th><th>Status</th></tr>{rows or '<tr><td colspan=3>None yet</td></tr>'}</table></div>
"""
    return page("Home", body)


def view_run(run_id: str) -> bytes:
    st = orch.load(run_id)
    working = is_working(run_id) or st["status"] == "running"
    phases = []
    cur = st["cursor"]
    for ph, name in orch.PHASES.items():
        nodes = [n for n in orch.NODES if n.phase == ph]
        idx = [orch.NODES.index(n) for n in nodes]
        cls = "done" if cur > max(idx) else ("now" if min(idx) <= cur <= max(idx) else "")
        steps = " · ".join(esc(n.title) for n in nodes)
        phases.append(f'<div class="phase {cls}"><b>{ph}. {esc(name)}</b><br><small>{steps}</small></div>')
    pend = approval.pending(st)
    pend_html = ""
    for rec in pend:
        if rec["kind"] == "gate":
            btns = "".join(f'<button name="decision" value="{o}" class="{"" if o == rec["recommended"] else "alt"}">'
                           f'{o.upper()}{" (recommended)" if o == rec["recommended"] else ""}</button>' for o in rec["options"])
        else:
            btns = '<button name="decision" value="approve">Approve</button><button name="decision" value="reject" class="alt">Reject</button>'
        node = orch.NODES[min(cur, len(orch.NODES) - 1)]
        gate_file = f"phase{node.phase}_gate_decision.md"
        preview = ""
        if rec["kind"] == "gate" and gate_file in st["artifacts"]:
            with open(os.path.join(st["run_dir"], "outputs", gate_file), encoding="utf-8") as f:
                preview = f"<pre>{esc(f.read())}</pre>"
        elif rec["kind"] == "approval":
            related = {"publish_landing_page": "phase2_step2_landing_page.html", "publish_store_page":
                       "phase5_step1_store_page.html", "post_launch_posts": "phase5_step1_launch_posts.md"}.get(rec["action"])
            if related:
                preview = f'<p>Review first: <a href="/run/{esc(run_id)}/file/{related}" target="_blank">{related}</a></p>'
        pend_html += f"""<div class="card" style="border:2px solid #e0a800"><h3>Founder decision needed</h3>
<p><b>{esc(rec['summary'])}</b> <small>({esc(rec['action'])})</small></p>{preview}
<form method="post" action="/run/{esc(run_id)}/decide"><input type="hidden" name="approval_id" value="{esc(rec['id'])}">
<label>Note (required to override a STOP)<input name="note"></label><div class="row" style="margin-top:.5rem">{btns}</div></form></div>"""
    ev = st.get("evidence") or {}
    iv, wl = ev.get("interviews") or {}, ev.get("waitlist") or {}
    evidence_form = f"""<div class="card"><h3>Report evidence (founder-reported)</h3>
<form method="post" action="/run/{esc(run_id)}/evidence" class="grid">
<label>Interviews completed<input name="iv_completed" value="{esc(iv.get('completed', ''))}"></label>
<label>Described the problem from recent experience<input name="iv_confirmed" value="{esc(iv.get('problem_confirmed', ''))}"></label>
<label>Waitlist target (set in advance)<input name="wl_target" value="{esc(wl.get('target', ''))}"></label>
<label>Waitlist sign-ups (real)<input name="wl_signups" value="{esc(wl.get('signups', ''))}"></label>
<label>Real buyers<input name="real_buyers" value="{esc(ev.get('real_buyers', ''))}"></label>
<div><button>Submit evidence</button></div></form></div>"""
    arts = "".join(f'<li><a href="/run/{esc(run_id)}/file/{esc(a)}">{esc(a)}</a></li>' for a in st["artifacts"])
    log = []
    try:
        with open(os.path.join(st["run_dir"], "decision_log.json"), encoding="utf-8") as f:
            log = json.load(f)
    except (OSError, ValueError):
        pass
    log_rows = "".join(
        f"<tr><td>{esc(e['timestamp'][11:19])}</td><td>{esc(e['agent'])}</td><td>{esc(e['action'])}</td>"
        f"<td>{esc(e.get('outcome', ''))}</td><td>{esc(e['model'])}</td><td>{esc(e['approved_by'])}</td>"
        f"<td>{len(e['sources'])}</td></tr>" for e in log[-40:][::-1])
    try:
        m = orch.run_metrics(st)
        metrics = (f"<p><small>{m['model_calls']} model calls ({m['stubbed_calls']} STUBBED) · "
                   f"{m['tokens_measured']} tokens measured · ~{m['prompt_tokens_est']} prompt tokens · "
                   f"<b>${m['cost_usd']:.2f}</b> · {m['founder_decisions']} founder decisions · "
                   f"{m['sources_cited']} source URLs</small></p>")
    except (OSError, ValueError):
        metrics = ""
    status = st["status"] + (" (working…)" if working and st["status"] != "awaiting_founder" else "")
    extra = ""
    if st.get("stopped_reason"):
        extra += f'<p><span class="pill stop">STOPPED</span> {esc(st["stopped_reason"])}</p>'
    if st.get("error"):
        extra += f'<p><span class="pill stop">ERROR</span> {esc(st["error"])}</p>'
    for r in st.get("refused_requests", []):
        extra += f'<p><span class="pill stop">REFUSED</span> {esc(r["request"])}: {esc(r["why"])}</p>'
    body = f"""<div class="card"><h2>{esc(st['brief'].get('idea'))}</h2>
<p>Run <code>{esc(run_id)}</code> · <span class="pill {esc(st['status'])}">{esc(status)}</span>
{' · <span class="pill repeat">DEMO FIXTURE brief</span>' if st['brief'].get('demo_fixture') else ''}</p>{metrics}{extra}</div>
{pend_html}
<div class="grid"><div class="card">{''.join(phases)}</div><div class="card"><h3>Outputs</h3><ul>{arts or '<li>None yet</li>'}</ul></div></div>
{evidence_form if st['status'] not in ('completed', 'stopped') else ''}
<div class="card"><h3>Decision log (latest first)</h3><table><tr><th>Time</th><th>Agent</th><th>Action</th><th>Outcome</th>
<th>Model</th><th>Approved by</th><th>Sources</th></tr>{log_rows}</table></div>"""
    return page(run_id, body, refresh=working and not pend, llm_label=st["llm"]["label"], stubbed=st["llm"]["stubbed"])


def view_file(run_id: str, name: str) -> tuple[bytes, str]:
    st = orch.load(run_id)
    if name not in st["artifacts"]:
        raise FileNotFoundError(name)
    with open(os.path.join(st["run_dir"], "outputs", name), encoding="utf-8") as f:
        content = f.read()
    if name.endswith(".html"):
        body = (f'<p><a href="/run/{esc(run_id)}">&larr; back</a> · preview (sandboxed, scripts disabled)</p>'
                f'<iframe sandbox="" style="width:100%;height:75vh;border:1px solid #ccc;background:#fff" '
                f'srcdoc="{esc(content)}"></iframe>')
    else:
        body = f'<p><a href="/run/{esc(run_id)}">&larr; back</a></p><div class="card"><pre>{esc(content)}</pre></div>'
    return page(name, body, llm_label=st["llm"]["label"], stubbed=st["llm"]["stubbed"]), "text/html"


# ---------------------------------------------------------------- handler
class Handler(BaseHTTPRequestHandler):
    def _send(self, data: bytes, ctype="text/html; charset=utf-8", code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, to: str):
        self.send_response(303)
        self.send_header("Location", to)
        self.end_headers()

    def _form(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n).decode()
        return {k: v[0] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}

    def log_message(self, fmt, *args):  # quieter logs
        pass

    def do_GET(self):
        try:
            parts = [p for p in self.path.split("?")[0].split("/") if p]
            if not parts:
                return self._send(view_index())
            if parts[0] == "health":
                return self._send(b'{"ok": true}', "application/json")
            if parts[0] == "run" and len(parts) == 2:
                return self._send(view_run(parts[1]))
            if parts[0] == "run" and len(parts) == 4 and parts[2] == "file":
                data, ctype = view_file(parts[1], urllib.parse.unquote(parts[3]))
                return self._send(data, ctype + "; charset=utf-8")
            if parts[0] == "api" and parts[1:2] == ["runs"] and len(parts) == 3:
                return self._send(json.dumps(orch.load(parts[2]), default=str).encode(), "application/json")
            self._send(page("Not found", "<p>Not found</p>"), code=404)
        except FileNotFoundError:
            self._send(page("Not found", "<p>Not found</p>"), code=404)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send(page("Error", f"<pre>{esc(exc)}</pre>"), code=500)

    def do_POST(self):
        try:
            parts = [p for p in self.path.split("/") if p]
            f = self._form()
            if parts == ["start"]:
                brief = {k: f.get(k, "").strip() for k in
                         ("idea", "skills", "budget_usd", "hours_per_week", "target_market", "values")}
                if not brief["idea"]:
                    return self._send(page("Missing idea", '<p>An idea is required. <a href="/">Back</a></p>'), code=400)
                rid = orch.start_run(brief)
                start_worker(rid)
                return self._redirect(f"/run/{rid}")
            if parts == ["start-sample"]:
                name = os.path.basename(f.get("sample", ""))
                with open(os.path.join(BRIEFS, name), encoding="utf-8") as fh:
                    rid = orch.start_run(json.load(fh))
                start_worker(rid)
                return self._redirect(f"/run/{rid}")
            if parts == ["ask"]:
                ans = orch.ask(f.get("q", ""))
                pill = '<span class="pill stop">REFUSED</span>' if ans["refused"] else ""
                body = (f'<div class="card"><p><b>You asked:</b> {esc(f.get("q"))}</p>{pill}<pre>{esc(ans["text"])}</pre>'
                        f'<a href="/">&larr; back</a></div>')
                return self._send(page("Ask", body))
            if len(parts) == 3 and parts[0] == "run" and parts[2] == "decide":
                try:
                    orch.decide(parts[1], f["approval_id"], f["decision"], f.get("note") or None)
                except ValueError as exc:
                    return self._send(page("Not accepted", f'<div class="card"><p>{esc(exc)}</p>'
                                      f'<a href="/run/{esc(parts[1])}">&larr; back</a></div>'), code=400)
                start_worker(parts[1])
                return self._redirect(f"/run/{parts[1]}")
            if len(parts) == 3 and parts[0] == "run" and parts[2] == "evidence":
                data: dict = {}

                def num(key):
                    v = f.get(key, "").strip()
                    return int(float(v)) if v else None

                iv = {k: v for k, v in (("completed", num("iv_completed")), ("problem_confirmed", num("iv_confirmed")))
                      if v is not None}
                wl = {k: v for k, v in (("target", num("wl_target")), ("signups", num("wl_signups"))) if v is not None}
                if iv:
                    data["interviews"] = iv
                if wl:
                    data["waitlist"] = wl
                if num("real_buyers") is not None:
                    data["real_buyers"] = num("real_buyers")
                if data:
                    orch.submit_evidence(parts[1], data)
                    start_worker(parts[1])
                return self._redirect(f"/run/{parts[1]}")
            self._send(page("Not found", "<p>Not found</p>"), code=404)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._send(page("Error", f"<pre>{esc(exc)}</pre>"), code=500)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    a = p.parse_args()
    os.makedirs(orch.RUNS_DIR, exist_ok=True)
    print(f"StopGo UI on http://{a.host}:{a.port}  (open http://localhost:{a.port})")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
