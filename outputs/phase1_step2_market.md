> **STUBBED**: model-written text in this file came from the deterministic stub, not a model.
> **DEMO FIXTURE**: founder-reported numbers in this run come from a demo brief, not from real interviews or sign-ups.

# Phase 1 / Step 2: Market definition

**Idea:** A small CLI that checks a project's .env file against .env.example and flags missing, empty or unused variables before deploy

## Target customer
- ASSUMPTION: Solo developers and small teams described in the brief.
## Where they are
- ASSUMPTION: GitHub issues, Stack Overflow and developer forums.
## Market size
- ASSUMPTION: Not estimated: no sourced figure available for this run.
## Existing alternatives
- ASSUMPTION: See the GitHub column in phase1_step1_opportunities.md.

## Sourced signals

- GitHub search unavailable for this run (unavailable (HTTPError)): https://github.com/search?q=checks%20project%27s%20env%20file&type=repositories&s=stars&o=desc
- Stack Overflow search unavailable for this run (unavailable (URLError)): https://stackoverflow.com/search?q=checks%20project%27s%20env%20file
- Founder-cited (not fetched by StopGo): dotenv-linter: Open-source linter for .env files; checks syntax, not drift against .env.example (https://github.com/dotenv-linter/dotenv-linter)
- Founder-cited (not fetched by StopGo): The Twelve-Factor App: III. Config: Recommends storing deploy config in environment variables, the practice this tool supports (https://12factor.net/config)
