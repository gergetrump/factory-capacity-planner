# Learn the planner by tracing one unit

Start with `lookahead`: one product A, one cell C1, two shifts. One unit takes
one machine minute; an active cell reserves one operator. Initial inventory is
zero. Capacity is **[1, 0] minutes**, new demand is **[0, 1] units**, and each
shift has one operator. All data is synthetic.

This guide and its recorded runs were prepared and executed by Codex on
18 November 2026. They do not establish George's independent understanding or
personal implementation contribution. Use the unfinished checklist below to
turn the example into your own learning evidence.

## 1. Trace input → decisions → checked result → screen

Read these functions with the lookahead JSON beside you:

| Stop | What to follow | Concrete question and answer |
| --- | --- | --- |
| [Fixture](../src/capacity_planner/data/lookahead.json) → [schema.py](../src/capacity_planner/schema.py) | `Scenario`, `check_references`, `ordered_shifts` | Why is T2 capacity explicitly zero? Every cell/shift needs a row. A missing row is invalid, not an outage. Quantities must be integers; IDs/references and contiguous shift indices are checked. |
| [model.py](../src/capacity_planner/model.py) | `solve`, from data dictionaries through `setObjective` | Where can A be made? Only eligible product/cell pairs get `x`; T2's production upper bound is zero. |
| [model.py](../src/capacity_planner/model.py) → [check.py](../src/capacity_planner/check.py) | Solver extraction → `make_solution` → `assess_solver_result` → `check_solution` | Is stock inferred to make an incorrect solver plan look valid? No: actual solver inventory, backlog and activation values are passed explicitly, then independently checked. |
| [greedy.py](../src/capacity_planner/greedy.py) | `plan_greedy`, especially `shortage` | Why miss T1? New demand and existing shortage are zero, so greedy makes nothing. It does not anticipate T2 demand. |
| [api.py](../src/capacity_planner/api.py) | `SolveRequest` → `solve_request` → the same `solve` | Does HTTP use another optimizer? No. A nonblocking lock admits one solve per API process and is released in `finally`. Invalid requests return 422; busy returns 409; unavailable solver returns 503. |
| [App.tsx](../frontend/src/App.tsx) → [api.ts](../frontend/src/api.ts) → [Results.tsx](../frontend/src/Results.tsx) | `runComparison` → request → `ResultDetails` | Are the methods compared on the same data? `runComparison` copies the draft once and sends Gurobi, then greedy that snapshot. The client checks method/input identity. Tables and downloads use the returned saved input. Later edits mark results stale. |

The CLI in [cli.py](../src/capacity_planner/cli.py) is another adapter to the same
core. `planner check` loads the included input and recomputes feasibility and
metrics; it does not independently prove optimality or authenticate metadata.
The browser timeout does not cancel a backend solve. No UI changes are part of
this lesson.

## 2. Say what the maths means

Indices are product `p`, cell `c`, shift `t`. Inputs are processing minutes/unit
`a`, available minutes `C`, crew `r`, available operators `W`, newly due units
`d`, and initial inventory `I0`. Demand is **new each shift**, not cumulative.

| Variable or bound | Meaning | Lookahead value/example |
| --- | --- | --- |
| `x[p,c,t]`, nonnegative integer | Units produced in that cell/shift | Make 1 A in C1/T1 to prepare for T2. |
| `y[c,t]`, binary | Cell active, reserving its entire crew | T1 is 1 if producing; T2 is 0. |
| `I[p,t]`, nonnegative integer | Units stored at shift end | With preparation: `[1,0]`. |
| `B[p,t]`, nonnegative integer | Units overdue at shift end | With preparation: `[0,0]`. |
| `z[p,t]`, binary sign selector | Allows stock or backlog, never both positive | `z=1` allows inventory; `z=0` allows backlog. At zero stock/backlog either may fit. |
| `Q=max(0,total demand-I0)` | Maximum useful horizon production | 1; there is no terminal stock target or future demand. |
| `U=min(Q,floor(C/a))` | Production bound for an eligible pair/shift | `[1,0]`. |
| `Icap=I0+Q`, `Bcap=cumulative demand` | Finite state bounds | Inventory bound 1; backlog bounds `[0,1]`. |

Read each constraint in `solve` aloud:

| Constraint | Physical meaning |
| --- | --- |
| `sum(a*x) <= C*y` | Products share machine minutes; an inactive cell produces nothing. |
| `x <= U*y` | Link each production decision to cell activation with a tight bound. |
| `y <= sum(x)` | A reported active cell must actually produce at least one unit. |
| `sum(r*y) <= W` | Reserve crew once per active cell, even when it makes several products. |
| `I-B = previous I-B + production-d` | Conserve net stock. The first previous value is initial inventory, with zero initial backlog. |
| `I <= Icap*z`, `B <= Bcap*(1-z)` | Prevent simultaneous positive inventory and backlog for the same product/shift. |
| `sum(x) <= Q` | Do not make surplus beyond remaining horizon demand. |
| `min sum(B)` | Minimize backlog **unit-shifts**: a piece overdue at two boundaries counts twice. |

Only backlog is optimized. Final backlog is a separate end-of-horizon measure;
inventory and active cell-shifts describe a plan, with no secondary objective.
This is aggregate allocation, with unlimited storage/materials and no setup
losses, employee identities or detailed start times.

| Result status | What you can claim |
| --- | --- |
| `optimal` | Checked feasible plan; Gurobi optimal termination, zero configured gaps and consistent objective/bound. |
| `feasible` | Checked incumbent after another accepted termination; minimum unproven. |
| `heuristic_feasible` | Checked greedy plan; no optimizer bound. |
| `no_solution` | No accepted incumbent; a bound alone is not a plan. |
| `solver_unavailable` | Solver import/initialization/license unavailable; no automatic greedy substitution. |
| `solver_error` | Execution, termination or objective/bound consistency problem. |
| `invalid_result` | Extracted decisions or independent validation failed. |

## 3. Predict, then reproduce the existing experiment

**Before running:** can T2 demand be met without T1 production? No: T2 has zero
capacity. Predict Gurobi objective **0**, with one unit stored after T1; greedy
objective **1**, with one unit overdue after T2. Nonnegative backlog gives a
lower bound of zero, so constructing the first plan proves its optimum by hand.

Run from the project root using its existing environment and usable local
Gurobi license. These commands were executed successfully; `docs/results` was
preserved. For your own repetition, change every output prefix to
`artifacts/my-learning/` to preserve this recorded run too.

```bash
.venv/bin/planner example lookahead --output docs/learning-results/lookahead-input.json
.venv/bin/planner validate docs/learning-results/lookahead-input.json
.venv/bin/planner solve --input docs/learning-results/lookahead-input.json --algorithm gurobi --output docs/learning-results/lookahead-gurobi.json
.venv/bin/planner solve --input docs/learning-results/lookahead-input.json --algorithm greedy --output docs/learning-results/lookahead-greedy.json
.venv/bin/planner check docs/learning-results/lookahead-gurobi.json
.venv/bin/planner check docs/learning-results/lookahead-greedy.json
```

**Observed:** `optimal / 0` and `heuristic_feasible / 1`; both checks valid.
Both saved input snapshots were also compared with the exported input and
matched. [Reproduction summary](learning-results/reproduction-summary.json)
records predictions, observations, environment and source hashes. Each result
includes its exact input, settings, solver metadata (Gurobi only), decisions and
validation. This is one small correctness demonstration, not a speed benchmark.

## 4. Change one model rule

[learning_inventory_limit.py](../scripts/learning_inventory_limit.py) builds a
separate, fixed one-product/two-shift Gurobi model matching the fixture. It
refuses changed fixture data. Read the variable definitions and balance first,
then find the single line named `no_preproduction`:

```python
model.addConstr(inventory["T1"] == 0, name="no_preproduction")
```

**Before running:** prohibiting stock after T1 removes the only way to meet T2
demand. Predict objective **0 → 1**, with first-shift inventory **1 → 0**. The
objective stays `min sum(B)`; this changes the feasible plans, not their scoring.

```bash
.venv/bin/python scripts/learning_inventory_limit.py --output-dir artifacts/my-inventory-policy
```

**Observed:** both solves optimal, objectives 0 and 1, both base checks valid.
The recorded run used the default `docs/learning-results/inventory-policy`
directory, which now already exists. The command above uses a fresh ignored
directory for your repetition. The script refuses an existing output directory;
choose a new one for a further repetition, for example:

```bash
.venv/bin/python scripts/learning_inventory_limit.py --output-dir artifacts/my-inventory-policy-2
```

| Plan | Production T1/T2 | Inventory T1/T2 | Backlog T1/T2 | Objective |
| --- | --- | --- | --- | ---: |
| Storage allowed | 1 / 0 | 1 / 0 | 0 / 0 | 0 |
| No preproduction | 0 / 0 | 0 / 0 | 0 / 1 | 1 |

Policy tradeoff: less carried stock sacrifices service when capacity is lost
later. The restriction does not make this case infeasible because backlog is
allowed. It also does not establish a storage cost saving: no monetary costs
are modeled.

Each teaching JSON is a **self-contained wrapper**, with model scope, additional
constraints, a nested app-format result, raw variables and policy validation.
The standard app format has no inventory-policy field. The nested `optimal`
status applies to the listed teaching constraints; the restricted optimum is
not the optimum for the original input alone. Do not pass these wrappers to
`planner check`, which reads ordinary app results and knows only base constraints.
Recheck the recorded nested plans and additional rule explicitly. To check
your own repetition instead, replace the directory in this snippet with
`artifacts/my-inventory-policy`:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from capacity_planner.check import check_solution
from capacity_planner.schema import Result
for path in sorted(Path('docs/learning-results/inventory-policy').glob('*.json')):
    if path.name == 'experiment.json':
        continue
    saved = json.loads(path.read_text())
    result = Result.model_validate(saved['result'])
    assert check_solution(result.input, result.solution).valid
    if saved['additional_constraints']:
        assert saved['additional_constraints'] == ['I[T1] == 0']
        assert abs(saved['raw_variables']['I[T1]']) <= 1e-7
        assert next(r.inventory_units for r in result.solution.stock if r.shift_id == 'T1') == 0
    print(path.name, 'base feasibility and applied policy valid')
PY
```

[experiment.json](learning-results/inventory-policy/experiment.json) also records
environment/source hashes and the rule check for both cases. The allowed plan
fails that hypothetical rule, as expected; the restricted plan satisfies it.
The script checks these outcomes and the hand-derived objective predictions.
Its `.lp` files expose the exact two formulations. Solver activity and stock
are extracted directly before checking, never reconstructed to conceal errors.
No production schema, model defaults, API or UI were changed.

Existing regression checks were also run:

```bash
.venv/bin/python -m pytest -q tests/test_core.py tests/test_api.py
```

All **47 passed**, including real Gurobi execution; no skips. One dependency
deprecation warning concerned FastAPI's test client. The API/UI trace above is
a code walkthrough; no new manual browser verification is claimed.

## 5. Your hands-on checklist

- [ ] Without opening the answers, draw both shifts and predict both methods.
- [ ] Trace one `x` and its `I/B` states through `solve`, extraction and checker;
  explain why a valid check alone cannot prove optimality.
- [ ] Reproduce into your own output folder and compare exact inputs/statuses.
- [ ] Run the teaching model yourself; locate the added constraint in the LP.
- [ ] In your own script copy, change the policy RHS from 0 to 1. Predict first:
  objective returns to 0. Update the policy validation/expected objective too;
  otherwise the old assertions should complain. Save the modified source and outputs.
- [ ] Explain why banning storage can create backlog without infeasibility, and
  why fewer active cells does not prove staffing or energy savings.
- [ ] Write down what you personally ran, changed and can explain, and what was
  assisted. Only then update any account of your contribution with that evidence.
