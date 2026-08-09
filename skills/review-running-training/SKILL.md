---
name: review-running-training
description: Review one normalized RunCrew activity together with recent training history and an optional planned session. Use for questions about workout completion, seven-day load change, pace anomalies, lap stability, missing evidence, or replaying an earlier running review. Return the validated TrainingReviewResult contract and never infer medical diagnoses.
---

# Review Running Training

Produce a replayable, evidence-backed training review from RunCrew Domain data. Keep metric calculation in deterministic services; use an LLM only to summarize validated findings.

## Workflow

1. Select one normalized target activity from the RunCrew repository. Do not read raw COROS text or `data/private/` unless the user explicitly requests debugging.
2. Collect same-provider activities from the requested lookback window, anchored to the target activity timestamp rather than the current clock.
3. Add a planned distance or duration only when the user supplied it. Never invent a plan.
4. Run the deterministic review:

```powershell
runcrew training review --latest --provider coros
```

Include known plan targets when available:

```powershell
runcrew training review --latest --provider coros `
  --planned-distance-km 8 --planned-duration-minutes 45
```

5. Validate inputs against [input.schema.json](references/input.schema.json) and outputs against [output.schema.json](references/output.schema.json).
6. Return all three findings: `training_completion`, `load_change`, and `training_anomaly`. Preserve `unknown` findings and their `requires` evidence when data is missing.
7. If a narrative is requested, paraphrase the validated messages and cite their evidence values. Do not calculate new metrics, change levels, or hide missing data.

## Evidence rules

- Treat `input_hash` plus `ruleset_version` as the replay identity.
- Require a non-empty `evidence` object for every finding.
- Treat absent plan, incomplete load windows, and insufficient lap/history pace as data limitations, not negative athlete judgments.
- Do not turn load change or pace anomalies into injury or medical claims.
- Do not expose provider external IDs, GPS coordinates, access tokens, or signed URLs in summaries.

## Failure handling

- If the target activity is missing, stop with an explicit lookup error.
- If history is sparse, still return a valid result with downgraded confidence.
- If Schema validation fails, return the validation error; do not emit partially structured prose as a substitute.
