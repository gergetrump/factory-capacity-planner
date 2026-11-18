# Independent implementation review

Reviewed locally on 18 November 2026 against revision 2 of the approved Factory Capacity Planner plan. Scope: input validation, formulation, independent arithmetic checker, greedy baseline, outcome reporting, CLI/API, recorded evidence and React input/result pairing. Review used Codex directly; no additional agents or external publication.

No unresolved material correctness finding was identified in the reviewed implementation. The model implements the single accumulated-backlog objective, fixed whole-shift crews and dense checked outputs. Inventory/activity are reported without hidden optimization priorities. Shortages remain feasible through backlog; unavailable Gurobi is not replaced by a mislabeled heuristic.

## Findings resolved during review

| Severity | Location | Reproduction and correction |
| --- | --- | --- |
| Low | `src/capacity_planner/examples.py:22–23`, `with_outage` | A valid 160-character scenario name with a valid 64-character cell ID produced an outage name longer than the schema's 160-character limit. The helper now budgets the original-name prefix against the actual suffix. The original failing case and regression test pass. |
| Low | `frontend/src/App.tsx:44–60`, example-loading effect | StrictMode cleanup could let an aborted earlier request update the load error/loading state after the replacement effect began. An effect-local active flag now guards state changes after cleanup; the final live load succeeded without a load alert. |
| Low | `frontend/src/App.tsx:82`, `runComparison` / live status | After applying an outage and completing both methods, the old “Run the comparison to evaluate this input” message masked completion. Clearing the control message when a comparison starts fixes this; the live completed-outage message was independently verified. |

## Verification performed independently

- Final Python suite: **47 passed**, including the real licensed Gurobi tests. One Starlette/httpx deprecation warning remains; it did not fail these checks.
- Independently enumerated **80 seeded small scenarios**, varying eligibility, processing rates, initial inventory, demand, capacity, crew and staffing. All Gurobi primary objectives matched enumeration; every greedy output passed arithmetic validation. This scratch oracle did not reuse optimizer expressions or checker reconstruction.
- Reparsed and rechecked all **10 saved results**. All five Gurobi/greedy pairs contain identical validated inputs; saved Gurobi status/objective/bound assessment is consistent.
- Reviewed lock acquisition/release and exercised the suite's competing-request, malformed-request and release-after-error cases. The documented limit remains per API process; client disconnect does not promise solver cancellation.
- Live Chromium against the local React/Vite and FastAPI servers reproduced base backlog **0 / 51**, short-outage backlog **0 / 128**, and lookahead backlog **0 / 1** (Gurobi / greedy). No browser page errors occurred in the final walkthrough.
- After solving the short outage, changed the outage end to shift 10 and reapplied it. The UI marked the saved run stale; its downloaded JSON exactly matched the earlier Gurobi response and retained only the original T5–T6 outage. Reset selected the retained original reference without a false stale warning. Scenario selection and method separation were also inspected.
- Reviewed resource display calculations and zero-denominator behavior, solver/error presentation, exact-snapshot exports and separate original/outage views against the backend contract.

## Limits

The independent mathematical oracle covers small instances, not every permitted input. Early-stop/no-incumbent and unavailable-solver cases were checked through the supplied adapter/API tests and code review; this review did not induce a real hardware-dependent timeout or remove the working license. The final browser walkthrough used desktop Chromium, not a cross-browser accessibility audit. Clean-install/wheel and mobile checks were performed separately by the implementation owner and are not represented here as independently repeated. Local results establish a synthetic portfolio demonstration, not industrial performance, public hosting suitability or George's independent mastery of the implementation.
