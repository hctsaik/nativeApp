# LV BDD scenario completeness scoring

A scenario is only worth keeping if it actually *proves* something. Each of the
20 scenarios is scored 0–100 on **completeness** by a multi-agent panel (three
independent reviewers with different lenses: a strict QA auditor, an ML-domain
reviewer, a platform/integration reviewer). The suite is accepted when the
**average across all scenarios and reviewers ≥ 95**; otherwise the weakest
scenarios are strengthened and re-run/re-scored.

## Rubric (per scenario, 100 pts)

| Dimension | Pts | What earns full marks |
|-----------|-----|-----------------------|
| **Spec quality** | 20 | Gherkin Given/When/Then is unambiguous and grounded in real LV / labeling behaviour (real UI strings, real tool ids, real contract). |
| **E2E rigour** | 30 | Genuinely exercises the real system through the cim-gui MCP machinery (live launch + render + drive) and/or a deterministic contract against real LV code — never a stub/mock. |
| **Assertion strength** | 25 | Checks verify the actual behaviour, including guards / negatives / exact strings; would catch a real regression, not just "page is non-empty". |
| **Evidence & reproducibility** | 15 | A screenshot / CSV / artifact is captured; the result is deterministic and re-runnable from the documented command. |
| **Coverage value** | 10 | Covers a distinct, important user journey with no redundancy against the other 19. |

## Inputs each reviewer reads

- `features/*.feature` — the specs under review.
- `report.json` — the live result of the latest run (per-check pass/fail + evidence paths).
- `run_bdd.py` + `mcp_driver.py` — to judge whether the execution is rigorous or shallow.
- `evidence/*.png`, `report.md` — the captured proof.

## Acceptance

- Compute each scenario's mean across the three reviewers, then the suite mean.
- **Accept at suite-mean ≥ 95.** Below that, apply each reviewer's concrete
  "weakest scenarios + fixes", re-run `run_bdd.py`, and re-score.

This file plus `features/` are the durable record: re-run the panel any time the
LV plugin changes to confirm the journeys still hold.

## Iteration history

The suite was driven to the ≥95 bar by alternating live E2E runs with multi-agent
scoring and applying each round's concrete findings:

| Round | Live E2E | Panel avg | What changed |
|-------|----------|-----------|--------------|
| 1 | 17/20 → 19/20 → **20/20** | 88.4 | First green run; fixed cosine test vectors + render-race waits. |
| 2 | 20/20 | 93.8 | Strengthened weak assertions: S12 real `build_projection_figure` (2 traces/3 toggles), S07 selection→`records_to_csv` loop, S13 `coverage_health`, S15 on-disk newest-first reload, S18 real `module_010.scan_folder` ingest, S02/S03/S05 exact strings, S06 legend. |
| 3 | 20/20 | _(target ≥95)_ | Live guard triggers: S03 clicks Run→`請先選擇至少一個資料夾`, S04 bad-path→`資料夾不存在` + missing-model banner (distinguishable); S01 asserts the 13 MCP tools; S08 intermediate 0.5 value; S09 explicit self-exclusion; analysis-scenario screenshots. |
