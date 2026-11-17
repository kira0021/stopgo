> **STUBBED**: model-written text in this file came from the deterministic stub, not a model.
> **DEMO FIXTURE**: founder-reported numbers in this run come from a demo brief, not from real interviews or sign-ups.

# Phase 1 / Step 1: Opportunities

**Founder's idea:** A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy

Scores use only numbers fetched from the linked public sources plus the founder-fit rubric. A source that could not be reached shows `unavailable`; no number is filled in.

| # | Candidate | Search phrase | Stack Overflow questions | Top free alternative (GitHub stars) | Score |
|---|---|---|---|---|---|
| 1 | A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy | `checks project's env file` | unavailable | unavailable | n/a |
| 2 | A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy (narrowed to one language ecosystem) | `checks project's env file` | unavailable | unavailable | n/a |
| 3 | Hosted check for: A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy | `checks project's env file ci` | unavailable | unavailable | n/a |

**Score formula:** no public evidence available; not scored

## Why these alternatives

- ASSUMPTION: A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy: Founder's starting idea (sharpened).
- ASSUMPTION: A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy (narrowed to one language ecosystem): Smaller scope ships faster for a solo founder.
- ASSUMPTION: Hosted check for: A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy: Teams may prefer a CI step over a local CLI.

## Founder fit (rubric, 0-1)

Score: **1.0**

- founder-reported brief: +0.4 founder can write software (needed for a developer tool)
- founder-reported brief: +0.3 12 h/week is enough for a small MVP
- founder-reported brief: +0.15 budget $50 is enough: StopGo itself costs $0 to run
- founder-reported brief: +0.15 target market is technical users the founder can reach

## Founder-cited sources (from the brief; not fetched or verified by StopGo)

- dotenv-linter: Open-source linter for .env files; checks syntax, not drift against .env.example (https://github.com/dotenv-linter/dotenv-linter)
- The Twelve-Factor App: III. Config: Recommends storing deploy config in environment variables, the practice this tool supports (https://12factor.net/config)

## Hacker News discussion (starting idea)

- Hacker News unavailable for this run (unavailable (URLError)); not used in scoring. Search: https://hn.algolia.com/?q=checks%20project%27s%20env%20file&type=story
