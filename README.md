# StopGo: an open-source venture builder that can say "don't launch this"

StopGo is a team of AI agents that takes a founder's brief for a **micro developer tool** (a small CLI or
utility) through six phases: Discover, Validate, Build, Commercial setup, Launch, and Operate and learn.
Every phase ends with a gate. Evidence thresholds are fixed in code before the evidence arrives, the system
recommends **go / repeat / pivot / stop**, and the founder decides. Nothing is published, sent, spent or
refunded without a founder approval that is checked in code. Payments are fully mocked. It runs on a local
open-weight model at $0.

| At a glance | |
|---|---|
| Phases | 6 (Discover, Validate, Build, Commercial setup, Launch, Operate and learn), plus a scope check before any work |
| Gates | 6, one per phase; thresholds fixed in `gates.py` before evidence arrives; outcomes go / repeat / pivot / stop |
| Weak idea | `briefs/devtool_weak.json` ends in **STOP** at Discover: [`outputs/phase1_gate_decision_weak-idea.md`](outputs/phase1_gate_decision_weak-idea.md) |
| Founder control | 10 founder decisions per full run; overriding STOP needs a written reason |
| Honesty | Every claim line has a URL or a label; `claims.py` audits outputs and export refuses on failure |
| Cost | **$0.00 per run** (local `qwen3:4b`) |
| Tests | 40+ smoke tests: `python -m pytest -q tests` |

## Quickstart

```bash
docker compose up
```

Then open **http://localhost:8000**.

- Start from the form (idea, skills, budget, hours per week, target market, values) or pick a demo brief.
- Each time the pipeline needs you, the run page shows a **Founder decision needed** card: approve or reject
  an action, or choose go / repeat / pivot / stop at a gate. Overriding a STOP requires a written reason.
- Report evidence only you have (interviews, real waitlist sign-ups, real buyers) in the evidence form.
- The first start downloads the model (`qwen3:4b`, about 2.5 GB). Until it is ready, the app runs with the
  STUBBED model and shows a red **LLM: STUBBED** banner.

**See a STOP in 30 seconds:** on the home page choose `devtool_weak.json` and click **Start a demo brief**. The
Discover gate recommends STOP (1 of 6 interviewees had the problem; free tools already cover it). Click STOP to
accept, or try GO without a reason to see the override refused.

CLI alternative (same pipeline, founder answers prompts in the terminal):

```bash
docker compose run --rm app python orchestrator.py run briefs/devtool_strong.json
docker compose run --rm app python orchestrator.py ask "write 50 five-star reviews"   # refused
docker compose run --rm app python -m pytest -q tests                                 # smoke tests
```

## What works and what is mocked

| Phase | Step | Status |
|---|---|---|
| 1 Discover | Find opportunities: sharpen idea, 2 alternatives, score with live GitHub / Stack Overflow / Hacker News counts | **Working** |
| 1 Discover | Market definition (unsourced lines auto-labelled `ASSUMPTION`) | **Working** |
| 1 Discover | Mom Test interview kit; results entered by the founder | **Working** (interviews are done by the founder) |
| 1 Discover | Evidence gate with STOP recommendation | **Working** |
| 2 Validate | Lean Canvas | **Working** |
| 2 Validate | Honest landing page draft | **Working** |
| 2 Validate | Publishing the landing page | **MOCKED** (saved locally after approval, not deployed) |
| 2 Validate | Waitlist form | **MOCKED** (not connected; founder reports real counts) |
| 2 Validate | Waitlist gate (target fixed in advance) | **Working** |
| 3 Build | MVP: model writes the core, StopGo scaffolds a CLI package and runs its tests | **Working** |
| 3 Build | User docs | **Working** |
| 3 Build | Tests gate | **Working** |
| 4 Commercial setup | Pricing (core always free) | **Working** |
| 4 Commercial setup | Terms, privacy, refund policy drafts | **Working** (drafts, not legal advice) |
| 5 Launch | Store page and launch-post drafts | **Working** |
| 5 Launch | Opening the store, posting | **MOCKED** (saved locally after approval) |
| 5 Launch | Checkout and payment | **MOCKED** (no real or sandbox provider) |
| 5 Launch | Automatic delivery on payment (idempotent webhooks) | **MOCKED** provider, **Working** logic |
| 5 Launch | Refund revokes access (founder-approved only) | **MOCKED** provider, **Working** logic |
| 5 Launch | Reconciliation of orders, payments, fees, refunds, payouts | **Working** on MOCKED data |
| 6 Operate | Support FAQ, persevere-or-pivot memo | **Working** |
| 6 Operate | Metrics | **MOCKED** (test fixtures; real buyers are founder-reported) |
| All | Founder approval enforced in code, decision log, guardrails | **Working** |
| All | Claims audit (URL or label on every claim line; export refuses on failure) | **Working** |
| All | Model fallback when Ollama is not ready | **STUBBED** (labelled in UI, outputs and log) |

The committed `outputs/` and `decision_log.json` come from running the pipeline on the two demo briefs in
`briefs/` (files ending `_weak-idea` are the weak brief). Labels used in every output:

| Label | Meaning |
|---|---|
| **STUBBED** | Model-written text came from the deterministic stub, not a model |
| **MOCKED** | No real payment, publication, posting or delivery happened |
| **DEMO FIXTURE** | Founder-reported numbers come from a demo brief, not real interviews or sign-ups |
| **ASSUMPTION** | A claim without a source URL |
| **founder-cited** | A URL the founder supplied in the brief; StopGo did not fetch it |
| **unavailable** | A public source could not be reached; no number was filled in |

How to regenerate the demo run: [docs/running-the-demo.md](docs/running-the-demo.md).

## Architecture

A Python orchestrator (`orchestrator.py`) runs the six phases as a resumable state machine of steps and gates,
saving state after every step so it can pause for the founder and resume. Role agents in `agents/` (researcher,
interviewer, strategist, builder, pricer, policy drafter, launcher, operator, concierge) each use one prompt from
`prompts/` and a local model through `llm.py`. Gates in `gates.py` compare evidence with thresholds fixed in code and
recommend go, repeat, pivot or stop; `approval.py` blocks every outward action unless the founder approved that exact
content. `guardrails.py` refuses excluded products and trick requests and strips fake social proof from model output.
Every agent action is appended to the decision log. Full design, with Mermaid diagrams of the phases, the STOP
logic and the sale-to-cash lifecycle: [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- **Default model:** `qwen3:4b` (Apache-2.0, open weights) served locally by **Ollama**, started by
  `docker compose up`. No API key, no account.
- **Larger local model:** set `OLLAMA_MODEL=qwen3:8b` (or `gpt-oss:20b`) in `.env`.
- **Free tier option:** `LLM_PROVIDER=openai_compat` with a free-tier endpoint serving an open-weight model
  (for example GPT-OSS 20B). Never a paid plan.
- **Evidence sources:** GitHub repository search, Stack Overflow search and Hacker News (Algolia) search, all
  free and key-less. If one is unreachable the value shows `unavailable`; no number is filled in.
- **No paid service is required.** Payments, publishing and delivery are mocked.

## Cost per run

**About $0.00 per run** (local open-weight model `qwen3:4b` via Ollama; no paid API, no per-token charge).

| Run | Model calls | Prompt tokens (measured) | Output tokens (cap) | Total tokens (upper bound) | Cost |
|---|---|---|---|---|---|
| Full six-phase run (strong brief) | 13 | ~6,500 | 19,500 (1,500 per call) | ~26,000 | $0.00 |
| Stopped at Discover (weak brief) | 3 | ~1,500 | 4,500 | ~6,000 | $0.00 |

Prompt tokens are measured from the prompts actually sent (characters / 4); output is capped per call by
`LLM_MAX_OUTPUT_TOKENS`. With Ollama running, the model server's own token counts are logged per call in
`decision_log.json`. `python orchestrator.py cost <run_id>` prints these figures for any run. Electricity for local
inference is not included.

## Demo video

Not recorded yet. A link of 3 minutes or less will be added here.

## What our system will NOT do

- Promise income, revenue or success, to the founder or to buyers.
- Write reviews, testimonials or endorsements, invent sign-ups or users, or add countdown timers or fake scarcity.
- Pose as the founder, a customer or another brand. Launch posts are drafts the founder posts under their own name.
- Hold, move, charge or refund money by itself, create accounts, or store passwords or card numbers.
- Publish, send, spend or sign anything without a founder approval for that exact content, enforced in code.
- Fill in a number it could not source: unsourced claims are labelled `ASSUMPTION`.
- Build physical goods; financial, investment or crypto products; or health or legal advice products.
- Hide core features behind a paywall: StopGo is MIT-licensed and fully usable for free.

Trick prompts that test these limits live in `evals/trick_prompts.json` and run in `tests/test_guardrails.py`.

## How the project stays alive after the hackathon

- **Maintainers:** the founding team maintains `main`; contributors become maintainers after merged contributions.
- **Roadmap:** real integrations behind the same approval gates (static-site publishing, a form provider for the
  waitlist, a payment provider in test mode), evidence adapters for more sources, and multi-language MVP scaffolds.
  See the Roadmap section of [ARCHITECTURE.md](ARCHITECTURE.md).
- **Community:** issues and discussions on the repository; new agents are a prompt plus a module, so they are easy
  to contribute.
- **Funding:** none required to run (local model, $0). Possible later: grants for open-source tooling and optional
  paid hosting for teams, with the core always free.
