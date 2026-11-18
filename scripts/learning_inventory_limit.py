"""Teaching model for the fixed lookahead fixture; no production app changes.

Run from the project root with .venv/bin/python. Each export wraps its Result
with the policy and raw evidence: the standard checker does not know this rule.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform

import gurobipy as gp

from capacity_planner.check import check_solution, make_solution
from capacity_planner.examples import load_example
from capacity_planner.model import SETTINGS, _integer, assess_solver_result
from capacity_planner.schema import SolverInfo


def solve_teaching(no_preproduction: bool, lp_path: Path):
    """Same physical decisions as lookahead, optionally add I[T1] == 0."""
    scenario = load_example("lookahead")
    # Deliberately fixed, readable two-shift data; refuse a changed fixture.
    assert [p.id for p in scenario.products] == ["A"]
    assert scenario.products[0].initial_inventory_units == 0
    assert [(c.id, c.crew_operators) for c in scenario.cells] == [("C1", 1)]
    assert [(r.product_id, r.cell_id, r.minutes_per_unit)
            for r in scenario.processing_times] == [("A", "C1", 1)]
    shifts = [t.id for t in scenario.ordered_shifts]
    assert shifts == ["T1", "T2"]
    capacity = {r.shift_id: r.available_machine_minutes for r in scenario.capacity}
    demand = {r.shift_id: r.due_units for r in scenario.demand}
    assert capacity == {"T1": 1, "T2": 0} and demand == {"T1": 0, "T2": 1}
    assert [t.available_operators for t in scenario.ordered_shifts] == [1, 1]
    with gp.Env(empty=True) as env:
        env.setParam("OutputFlag", 0)
        env.start()
        with gp.Model("learning_inventory_limit", env=env) as model:
            for name, value in SETTINGS.items():
                model.setParam(name, value)
            x = model.addVars(shifts, vtype=gp.GRB.INTEGER, ub=capacity, name="x")
            y = model.addVars(shifts, vtype=gp.GRB.BINARY, name="y")
            inventory = model.addVars(shifts, vtype=gp.GRB.INTEGER, ub=1, name="I")
            backlog = model.addVars(shifts, vtype=gp.GRB.INTEGER,
                                    ub={"T1": 0, "T2": 1}, name="B")
            sign = model.addVars(shifts, vtype=gp.GRB.BINARY, name="sign")
            model.addConstr(x.sum() <= 1, name="useful_production")
            previous_net = 0
            for t in shifts:
                model.addConstr(x[t] <= capacity[t] * y[t], name=f"capacity_{t}")
                model.addConstr(y[t] <= x[t], name=f"nonempty_{t}")
                model.addConstr(y[t] <= 1, name=f"staff_{t}")  # one crew, one operator
                model.addConstr(inventory[t] - backlog[t] == previous_net + x[t] - demand[t],
                                name=f"balance_{t}")
                model.addConstr(inventory[t] <= sign[t], name=f"inventory_sign_{t}")
                model.addConstr(backlog[t] <= (1 - sign[t]), name=f"backlog_sign_{t}")
                previous_net = inventory[t] - backlog[t]
            if no_preproduction:
                # The entire teaching change: prohibit stock carried out of T1.
                model.addConstr(inventory["T1"] == 0, name="no_preproduction")
            model.setObjective(backlog.sum(), gp.GRB.MINIMIZE)
            model.write(str(lp_path))
            model.optimize()
            if model.Status != gp.GRB.OPTIMAL or model.SolCount == 0:
                raise RuntimeError(f"Teaching solve failed: Gurobi status {model.Status}")
            raw = {v.VarName: float(v.X) for v in model.getVars()}
            # Pass actual solver states; do not reconstruct stock or activity.
            plan = make_solution(
                scenario, {("A", "C1", t): _integer(x[t].X) for t in shifts},
                activity={("C1", t): _integer(y[t].X) for t in shifts},
                stock={("A", t): (_integer(inventory[t].X), _integer(backlog[t].X))
                       for t in shifts},
            )
            info = SolverInfo(version=".".join(map(str, gp.gurobi.version())),
                              termination="OPTIMAL", termination_code=model.Status,
                              raw_objective=float(model.ObjVal), objective_bound=float(model.ObjBound),
                              relative_gap=float(model.MIPGap), solve_runtime_seconds=float(model.Runtime))
            result = assess_solver_result(scenario, info, plan, dict(SETTINGS))
    base_check = check_solution(scenario, plan)
    t1_inventory = next(r.inventory_units for r in plan.stock if r.shift_id == "T1")
    policy_satisfied = abs(raw["I[T1]"]) <= 1e-7 and t1_inventory == 0
    extra_check = {"constraint": "I[T1] == 0", "applied": no_preproduction,
                   "raw_inventory_T1": raw["I[T1]"], "reported_inventory_T1": t1_inventory,
                   "satisfied": policy_satisfied,
                   "valid_for_applied_policy": not no_preproduction or policy_satisfied}
    if result.status != "optimal" or not base_check.valid or not extra_check["valid_for_applied_policy"]:
        raise RuntimeError("Teaching output failed validation")
    # Hand oracle: T2 has zero capacity. Only x[T1]=0 or 1 can be feasible;
    # backlog is respectively 1 or 0. The policy excludes x[T1]=1.
    expected = 1 if no_preproduction else 0
    if plan.objective != expected:
        raise RuntimeError(f"Expected objective {expected}, got {plan.objective}")
    return result, {"raw_variables": raw, "base_validation": base_check.model_dump(),
                    "extra_constraint_validation": extra_check, "predicted_objective": expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/learning-results/inventory-policy"))
    args = parser.parse_args()
    # A new directory makes repeat runs explicit and preserves earlier evidence.
    args.output_dir.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    sources = [Path(__file__), *sorted((root / "src/capacity_planner").glob("*.py")),
               root / "src/capacity_planner/data/lookahead.json"]
    experiment = {"scope": "Fixed educational model; added policy is outside the app schema/checker",
                  "assistance": "Prepared and executed by Codex; George's independent understanding is unverified",
                  "recorded_utc": datetime.now(timezone.utc).isoformat(),
                  "environment": {"python": platform.python_version(), "system": platform.system(),
                                  "machine": platform.machine(), "gurobi": ".".join(map(str, gp.gurobi.version()))},
                  "source_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sources}, "cases": {}}
    for name, restricted in [("storage-allowed", False), ("no-preproduction", True)]:
        result, evidence = solve_teaching(restricted, args.output_dir / f"{name}.lp")
        export = {"format": "learning-model-result-v1",
                  "model_scope": "Isolated teaching model. Nested optimal status applies to the base constraints plus additional_constraints; base checker establishes feasibility only.",
                  "additional_constraints": ["I[T1] == 0"] if restricted else [],
                  "result": result.model_dump(mode="json"), **evidence}
        (args.output_dir / f"{name}.json").write_text(json.dumps(export, indent=2) + "\n")
        experiment["cases"][name] = {"result_file": f"{name}.json", **evidence}
        print(f"{name}: objective={result.solution.objective}; base check valid; "
              f"applied policy valid={evidence['extra_constraint_validation']['valid_for_applied_policy']}")
    (args.output_dir / "experiment.json").write_text(json.dumps(experiment, indent=2) + "\n")


if __name__ == "__main__":
    main()
