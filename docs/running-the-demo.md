# Running and recording the demo run

The committed `outputs/` and `decision_log.json` are the output of one real pipeline run per demo brief.
To regenerate them with the local model (recommended once the model has downloaded):

```bash
docker compose up -d                      # starts Ollama, pulls the model, starts the app
docker compose logs -f ollama-pull        # wait until the pull finishes

# Weak idea: the Discover gate recommends STOP; answer "stop" at the prompt.
docker compose run --rm app python orchestrator.py run briefs/devtool_weak.json

# Strong idea: answer each prompt as the founder (approve / go / repeat / pivot / stop).
docker compose run --rm app python orchestrator.py run briefs/devtool_strong.json

# Copy both runs into outputs/ and decision_log.json (run ids are printed by the commands above,
# or list them with: docker compose run --rm app python orchestrator.py list)
docker compose run --rm app python orchestrator.py export <strong_run_id> --reset-log
docker compose run --rm app python orchestrator.py export <weak_run_id> --suffix _weak-idea
docker compose run --rm app python claims.py outputs     # must print PASS
```

Delete the old files in `outputs/` first so no file from an earlier run is left behind.

## What each label means

- **STUBBED**: the model-written text in that file came from the deterministic stub because no model was
  reachable. Numbers and gate logic are unaffected.
- **MOCKED**: no real payment, publication, delivery or posting happened.
- **DEMO FIXTURE**: the founder-reported numbers (interviews, waitlist) come from a demo brief in `briefs/`,
  not from real interviews or sign-ups.
- **ASSUMPTION**: a claim without a source URL.
- **founder-cited**: a URL the founder put in the brief; StopGo did not fetch or verify it.
- **unavailable**: a public evidence source could not be reached; no number was filled in.

## Live demo with an unseen brief

Paste the brief into the form on the home page. With no evidence in the brief, the Discover gate recommends
REPEAT and the interview kit tells the founder what to collect. Enter interview results in the evidence form to
re-run the gate.
