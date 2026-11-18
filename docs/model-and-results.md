# Model, validation and interpretation

## Problem and units

Assign whole product units to compatible cells in ordered shifts. Processing and capacity use integer machine minutes. An active cell reserves its fixed crew for an entire shift, including unused time. Materials/storage are unlimited and switching losses are ignored. Production can satisfy demand due at the end of the same shift or be stored for later. Initial backlog is zero.

Demand is new demand per shift, not cumulative. Inventory and backlog are mutually exclusive at each shift end. The backlog objective counts overdue pieces at each bucket boundary, **not hours late**; all demonstration shifts within a case have equal duration. Final backlog is also shown because the finite horizon omits later delay.

All values are synthetic and chosen for a comprehensible demonstration. No industrial process or Tesla production data was used.

## Formulation

For products `p`, cells `c` and shifts `t`, input `a[p,c]` is minutes/unit for eligible pairs, `C[c,t]` is available machine minutes, `r[c]` crew, `W[t]` staffing, `d[p,t]` demand and `I0[p]` initial inventory. Derived bounds are:

```text
Q[p] = max(0, total horizon demand[p] - I0[p])
U[p,c,t] = min(Q[p], floor(C[c,t] / a[p,c]))
Icap[p] = I0[p] + Q[p]
Bcap[p,t] = cumulative demand[p] through t
```

`Q` is valid only because there is no initial backlog, terminal stock target, negative production incentive or demand beyond the horizon. Surplus initial inventory remains; no disposal is introduced.

Production `x` is integer in `[0,U]`; activation `y` and sign `z` are binary; inventory `I` and backlog `B` are bounded nonnegative integers. Ineligible production is zero.

```text
sum_p a[p,c] * x[p,c,t] <= C[c,t] * y[c,t]
x[p,c,t] <= U[p,c,t] * y[c,t]
y[c,t] <= sum_p x[p,c,t]
sum_c r[c] * y[c,t] <= W[t]
I[p,t] - B[p,t] = previous net stock + sum_c x[p,c,t] - d[p,t]
I[p,t] <= Icap[p] * z[p,t]
B[p,t] <= Bcap[p,t] * (1-z[p,t])
sum_c,t x[p,c,t] <= Q[p]
minimize sum_p,t B[p,t]
```

The sign constraints prevent fictitious simultaneous stock/backlog even in an unfinished incumbent. The nonempty-cell constraint makes activation counts meaningful. The model is **aggregate allocation**, with no operation ordering, detailed start/end times or employee identities.

Only service backlog is optimized. Inventory and activity may look unusual because many solutions tie at the optimum. They are useful descriptors, not minimized cost, staffing or energy measures. Adding a secondary policy would require an explicit model change and new objective-order tests.

## Tiny oracle and lookahead

The two-product/two-shift fixture permits five physical choices each shift: nothing, A1, A2, B1 or B2. One available operator prevents both dedicated cells running together. The test enumerates 25 sequences independently and discards infeasible combinations. Minimum backlog is 0; if second-shift staffing is zero it is 2; producing nothing yields 6. Tests compare primary values and feasibility rather than arbitrary tied allocations.

In the lookahead fixture, capacity `[1,0]` and demand `[0,1]` require preproduction. Greedy sees no due demand in the first shift and misses the only opportunity. Its backlog is 1, while a checked optimal plan has 0. This is an intentionally transparent weakness of the baseline, not evidence about sophisticated industrial heuristics.

## Interpreting the production scenarios

| Question | Explanation and expected mathematical limit |
| --- | --- |
| Can the base meet all demand? | Yes. C2 makes P1/P3 using 335 minutes; C3 makes P2/P4 using 290. Their combined crew is 6 of 7 available. Zero backlog is feasible and hence the primary optimum. |
| Can a C3 outage in shifts 5–6 be absorbed? | Yes. One construction makes five extra P4 units in each of shifts 1–4. C3 then uses 365 minutes; C2 uses 335; staffing is 6. During the outage C1 can make P1/P2 in 350 minutes and C2 makes P3 in 135, with 5 operators; stored P4 meets its demand. This proves backlog can remain zero. Actual solver allocations may differ. |
| What if C3 is absent all ten shifts? | P4 has no available eligible cell and no initial stock. Its backlog is 10,20,…,100, totaling 550 unit-shifts. Other products can all be made using C1/P1/P2 and C2/P3. Thus 550 is both a lower bound and feasible objective; final backlog is 100 units. |

The real results in [results/summary.json](results/summary.json) attain these primary objectives. Each JSON file includes its full input, parameters, raw solver termination/bound and checked plan. The greedy baseline matches the full-outage lower bound and tiny optimum, but loses on base, short outage and lookahead. Do not turn arbitrary activity/inventory differences into claims of improvements or compute a single score combining unrelated metrics.

The separate [expanded benchmark report](benchmark-report.md) preserves these demonstrations and adds a solver-free dispatch portfolio, seeded scale/difficulty fixtures, three timing repeats per method, and recorded solver bounds/time-limit outcomes. It uses the same single backlog objective and unchanged application model. Its stronger baseline can preproduce and compare crew-feasible cell subsets, but has no optimality guarantee. Complete benchmark wrappers link exact input fixtures and are rechecked with `check_solution`; their format is documented in that report.

## Validation and outcome semantics

`check.py` does not import Gurobi or model-building constraints. It checks dense row keys, integer quantities, eligibility, production caps, machine minutes, staffing, activation consistency, every stock state and recomputed metrics/objective. Solver inventory/backlog/activation values are extracted explicitly and checked; they are not replaced by reconstructed values to hide a model defect.

A near-integer decision is rounded only within `1e-5`, then checked with integer arithmetic. Optimal results require zero configured relative/absolute MIP gaps, an optimal Gurobi status and consistent raw objective/bound. Early-stop incumbents are labeled feasible. Missing incumbents and solver initialization failures provide no invented solution. Greedy has its own `heuristic_feasible` label, null solver metadata and no solver import.

Tests exercise schema rejection, mutation of valid plans, stock and staffing edge cases, objective ties, independent enumeration, real Gurobi integration and simulated status/error paths. API tests include concurrent admission and lock release. Runtime/environment values are observed locally, with no hard deadline or general speed guarantee.

## Reproduce and discuss

Use the README commands and `scripts/record_results.py`. The environment record states Python/platform, source revision (or `uncommitted`) and working-tree state. No source commit has been fabricated. The first local output was produced using Python 3.12.15/Gurobi 14.0.0 on Linux x86_64. Setup uses an isolated virtual environment and checked-in dependency locks.

Before claiming personal achievement, review the assisted implementation and make a small change. Useful exercises are reducing shift staffing, introducing initial stock, explaining why a shared cell reserves crew once, and discussing when the single service objective should gain a tie-breaker. Keep any new experiment's input and result together.
