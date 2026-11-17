# Founder briefs

A brief is JSON with: `idea` (required), `skills` (list or comma-separated), `budget_usd`, `hours_per_week`,
`target_market`, `values`, optional `known_alternatives` (tools or pages the founder has found, each with
`name`, `url`, `note`; shown as founder-cited and not fetched by StopGo), and optional `evidence` the founder
already has:

```json
{"evidence": {"interviews": {"completed": 8, "problem_confirmed": 6, "notes": ["..."]},
              "waitlist": {"target": 100, "window_days": 14, "signups": 40},
              "real_buyers": 0}}
```

A plain-text file or a one-line idea also works; missing evidence makes the gates recommend REPEAT until the
founder reports it.

The two demo briefs are marked `"demo_fixture": true`. Their founder-reported numbers are illustrative test
inputs, not real evidence, and every output that uses them says so.
