# Repeated synthetic benchmarks — 18 November 2026

The checked suite contains **13 fixed inputs × 3 methods × 3 measured repeats = 117 runs**. All 117 returned independently feasible plans. Gurobi proved optimality in 33 runs; the other six hit the two-second optimization time limit with feasible incumbents **not proven optimal**. There were no solver/license failures, missing solutions or skipped model sizes.

This extends the original five demonstration comparisons with repeated timing observations, a stronger solver-free baseline, and generated scale/difficulty cases. It does not establish industrial performance or real factory improvements.

## Reproduce and inspect

From the source checkout with the README environment installed:

```bash
.venv/bin/python scripts/run_benchmarks.py --output-dir artifacts/my-benchmarks --repeats 3 --time-limit 2
.venv/bin/python -m pytest -q
```

Use a **new** output path; the runner refuses to overwrite an existing directory. Optional repeated `--case` arguments select a subset, for example `--case tiny --case disrupted-6p-4c-12t`. A subset run is not the complete suite. `--time-limit` controls Gurobi optimization, not end-to-end elapsed time.

The recorded run is [benchmarks/2026-11-18](benchmarks/2026-11-18):

- [environment.json](benchmarks/2026-11-18/environment.json): versions, hardware, load averages, solver settings, excluded warmups, source hashes, fixture hashes and model sizes.
- [measurements.json](benchmarks/2026-11-18/measurements.json): every measured run, order, objective, bound/gap, status, feasibility, error and timing.
- [summary.json](benchmarks/2026-11-18/summary.json): per-case/method objective ranges, status counts, and minimum/median/maximum times.
- `fixtures/`: the exact scenario JSON files. `runs/`: each full plan, checked result, timing record and relative fixture link; portfolio results also record all candidate objectives and the selected policy.

Benchmark snapshots use their own wrapper and link their input fixture; they are not the app's standalone `planner check` format. Recheck them using the same solver-independent arithmetic checker:

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
from capacity_planner.check import check_solution
from capacity_planner.schema import Scenario, Solution
root = Path('docs/benchmarks/2026-11-18')
count = 0
for path in sorted((root / 'runs').glob('*.json')):
    snapshot = json.loads(path.read_text())
    scenario = Scenario.model_validate_json((path.parent / snapshot['fixture']).read_text())
    result = snapshot['result']
    if result['solution'] is not None:
        report = check_solution(scenario, Solution.model_validate(result['solution']))
        assert report.valid, (path, report.errors)
        count += 1
print(f'{count} plans independently checked')
PY
```

## Methods and timing protocol

All methods use the same complete deterministic input, including future demand and outages. The app's Gurobi formulation and original greedy algorithm are unchanged. The new portfolio lives only in `benchmarks/`; it is not an added dashboard/API method.

**Gurobi:** the existing single-objective MILP, with `TimeLimit=2`, `Threads=1`, `Seed=0`, `MIPGap=0`, `MIPGapAbs=0`, `FeasibilityTol=1e-7`, and `IntFeasTol=1e-6`. Each call creates and disposes its own environment/model. There is no portfolio warm start or incumbent sharing between methods/repeats. The app's usual default time limit remains ten seconds.

**Original greedy:** the existing deterministic due-demand planner, with no preproduction. It is deliberately simple and is retained for continuity with the demonstration.

**Dispatch portfolio:** compare original greedy with dispatch plans for lookahead windows of one shift, two shifts, and the complete horizon; duplicate window lengths are removed. For each window, try urgency-first and scarcity-first priorities. There are seven candidates for horizons longer than two shifts, and five for the two-shift tiny and lookahead inputs. At each shift, each dispatch plan:

1. Enumerates cell subsets whose full-shift crews fit available staffing; at most 64 subsets at the schema ceiling of six cells.
2. Allocates integer batches on compatible cells, respecting machine minutes, current net inventory, and demand inside its window. Both priorities address current demand before future demand; urgency prefers earlier due buckets, while scarcity prioritizes products with fewer currently usable cells. Ties favor less flexible cells, then faster processing and stable IDs.
3. Scores each subset by projected accumulated backlog in the window **assuming no further production**, then current backlog and a stable allocation tie break. This is a greedy proxy, not a downstream optimization solve.
4. Advances one shift and repeats. The independent checker validates every completed candidate; the portfolio selects the lowest actual full-horizon backlog, breaking ties by policy name.

This is retrospective selection among a small set of policies with full known demand, not an online policy or an optimality oracle. Including original greedy guarantees that the portfolio cannot have a worse checked objective than that baseline. This guarantee is a construction property, not empirical evidence of universal superiority. The portfolio can still miss useful preproduction and resource combinations.

Each method has one excluded warmup on the tiny input. These warmups remove initial import/module startup effects; Gurobi environment setup is still repeated inside every measured call. Fixtures are generated/validated before measurement. The method order rotates by `(case_index + repeat_index) modulo 3`, so each method occupies each position once per case. Measurements run sequentially in one process; no benchmark methods run concurrently. Output files are written after all measurements.

`perf_counter` wall time covers planning/model/environment setup, extraction and feasibility checking, and excludes fixture/output I/O, output serialization, and the additional saved-output audit. The portfolio checks all candidates and rechecks its selection within timing. Gurobi's `Runtime` is recorded separately and covers `optimize`, including presolve; it is not total application time. The methods have **different compute budgets**: Gurobi has a two-second optimization limit; the portfolio has a fixed candidate set with no wall-time cap. API/HTTP and React rendering are outside the benchmark.

## Suite and size coverage

The five bundled demonstrations are preserved. Eight generated inputs use two predeclared profiles at four scales; no inputs were removed after inspecting results. `balanced` uses seed 1729 and full staffing; `disrupted` uses seed 2718, tighter staffing and deterministic zero-capacity patterns. Integer rates, variable demand and small initial inventory come from Python's seeded RNG. The largest scale is deliberately dense. [suite.py](../benchmarks/suite.py) defines the exact generation rules; saved fixture JSON and SHA-256 identify the actual inputs even if a future Python/RNG implementation changes.

| Case | Products / cells / shifts | Variables / constraints before presolve |
| --- | --- | --- |
| Base, short outage, full outage | 4 / 3 / 10 | 220 / 264 each |
| Lookahead | 1 / 1 / 2 | 10 / 15 |
| Tiny | 2 / 2 / 2 | 20 / 28 |
| Balanced / disrupted small | 2 / 2 / 4 | 48 / 62 each |
| Balanced medium | 4 / 3 / 8 | 184 / 220 |
| Disrupted medium | 4 / 3 / 8 | 168 / 204 |
| Balanced larger | 6 / 4 / 12 | 456 / 522 |
| Disrupted larger | 6 / 4 / 12 | 444 / 510 |
| Balanced / disrupted ceiling | 8 / 6 / 20 | 1,560 / 1,708 each |

Counts follow the current model's explicit variable/constraint construction, including production variables with zero upper bounds. All sizes were actually attempted and solved with the available license; none hit a restricted-license model limit. The schema was not expanded. Runs on another machine explicitly record unavailable licenses or Gurobi error 10010 as `restricted_license_model_limit`; this run does not establish that a different license supports larger models.

## Solution quality

Values are accumulated backlog in **unit-shifts**, lower is better. Each method's objective was identical across its three repeats in this run. The raw records preserve ranges for future runs where a time-limited incumbent varies.

| Input | Gurobi | Original greedy | Dispatch portfolio | Gurobi lower bound / termination |
| --- | ---: | ---: | ---: | --- |
| Base | 0 | 51 | 0 | 0 / optimal |
| Short C3 outage | 0 | 128 | 10 | 0 / optimal |
| Full C3 outage | 550 | 550 | 550 | 550 / optimal |
| Lookahead | 0 | 1 | 0 | 0 / optimal |
| Tiny | 0 | 0 | 0 | 0 / optimal |
| Balanced 2p / 2c / 4t | 0 | 0 | 0 | 0 / optimal |
| Disrupted 2p / 2c / 4t | 90 | 112 | 92 | 90 / optimal |
| Balanced 4p / 3c / 8t | 0 | 0 | 0 | 0 / optimal |
| Disrupted 4p / 3c / 8t | 594 | 869 | 773 | 594 / optimal |
| Balanced 6p / 4c / 12t | 0 | 0 | 0 | 0 / optimal |
| Disrupted 6p / 4c / 12t | 702 | 1,611 | 1,121 | 699 / time limit |
| Balanced 8p / 6c / 20t | 0 | 0 | 0 | 0 / optimal |
| Disrupted 8p / 6c / 20t | 13 | 3,064 | 573 | 0 / time limit |

Gurobi's checked incumbents beat the stronger portfolio on five inputs and tie on eight; the portfolio improves on original greedy on seven inputs and ties on six. These are descriptive counts over this fixed synthetic suite, not an estimate of a population win rate.

For disrupted 6p/4c/12t the three Gurobi runs have bound 699, incumbent 702 and relative gap `3/702 ≈ 0.4274%`. For disrupted 8p/6c/20t they have bound 0, incumbent 13 and reported relative gap 100%. The latter does **not** mean a 100% improvement is available; the lower bound is weak and the true optimum is only known to lie in `[0,13]`. Neither time-limited result is called optimal. Heuristics have no solver bound/certificate of their own. The summary's absolute gap to a Gurobi bound uses the best recorded bound on the exact same fixed input; feasibility checking alone cannot prove optimality.

Backlog is the only objective. No inventory, staffing, cost, energy or environmental improvement is inferred from tied or untied plans. Do not combine unrelated cases' objective totals into an industrial improvement percentage.

## Timing observations

Medians of three measurements, seconds; additional decimal places identify the observation and do not imply statistical precision. Full minimum/maximum ranges are in `summary.json`.

| Input | Gurobi wall | Gurobi optimize Runtime | Original greedy wall | Portfolio wall |
| --- | ---: | ---: | ---: | ---: |
| Base | 0.01410 | 0.00421 | 0.00258 | 0.02732 |
| Short outage | 0.01448 | 0.00409 | 0.00247 | 0.02529 |
| Full outage | 0.01433 | 0.00299 | 0.00286 | 0.01988 |
| Lookahead | 0.00198 | 0.00017 | 0.00027 | 0.00093 |
| Tiny | 0.00286 | 0.00051 | 0.00042 | 0.00165 |
| Balanced 2p / 2c / 4t | 0.00543 | 0.00183 | 0.00069 | 0.00437 |
| Disrupted 2p / 2c / 4t | 0.00493 | 0.00141 | 0.00065 | 0.00397 |
| Balanced 4p / 3c / 8t | 0.01319 | 0.00375 | 0.00240 | 0.02391 |
| Disrupted 4p / 3c / 8t | 0.02096 | 0.01251 | 0.00217 | 0.01369 |
| Balanced 6p / 4c / 12t | 0.02743 | 0.00930 | 0.00481 | 0.12501 |
| Disrupted 6p / 4c / 12t | 2.01968 | 2.00009 | 0.00471 | 0.04653 |
| Balanced 8p / 6c / 20t | 0.09654 | 0.03867 | 0.01430 | 2.06760 |
| Disrupted 8p / 6c / 20t | 2.05603 | 2.00034 | 0.01267 | 0.52418 |

The quality/runtime tradeoff depends on the case: the portfolio's full-horizon dispatch and subset enumeration cost about 2.068 seconds on the largest balanced input, where original greedy and Gurobi both find zero backlog much faster. On the largest disrupted input the portfolio takes about 0.524 seconds but leaves backlog 573, versus Gurobi's incumbent 13 after about 2.056 seconds. Its feasibility does not make it a substitute for an optimum proof. Even a two-second solver limit leads to wall times above two seconds due to other work.

## Validation and practical limits

The run used Python 3.12.15, gurobipy 14.0.0, Pydantic 2.14.3 and an Intel Core i5-6500T with four logical CPUs on Linux x86_64. Exact package versions, platform and observed host load are in the environment record. The nested repository had no committed `HEAD`; metadata says `uncommitted` and records SHA-256 for source, tests and dependency files instead of inventing a revision.

All **56 Python tests passed**, including eight real Gurobi integration cases and nine new benchmark checks. The new tests cover lookahead benefit, initial stock, missing eligibility, zero staffing/outages, deterministic generation, 20 additional seeded feasibility/dominance cases, explicit failure accounting and time-limited summary ranges. The coordinating Codex agent separately rechecked all 117 saved plans, objectives/bounds, fixture/source hashes, method rotation, and summary timing ranges/medians. This audit checks the recorded arithmetic and experiment bookkeeping; it does not independently solve the large MILPs or certify solver optimality claims.

This is a modest synthetic benchmark on a shared host, without CPU isolation, confidence intervals, many random replications, concurrency/API load or industrial datasets. Three timing repeats reveal local variability but are insufficient for general speed claims. There is one generation seed per profile, not a sampled performance distribution. The two profiles and four scales cover the current application ceiling, but scale cases change demand, rates and eligibility density; the largest is deliberately fully dense. These rows are not a controlled asymptotic scaling experiment or a monotonic difficulty ladder, and the dense balanced cases are deliberately easy. Larger models, broader instance families, rolling/uncertain demand, stronger local-search baselines and deployment/load testing remain future work. No changes to George's CV or personal contribution claims are implied by this assisted implementation.
