"""One backlog objective. Gurobi is imported only when explicitly requested."""
from importlib import import_module
import math
from itertools import product

from .check import check_solution, make_solution
from .greedy import plan_greedy
from .schema import Result, Scenario, Solution, SolverInfo

SETTINGS = {"TimeLimit": 10, "MIPGap": 0.0, "MIPGapAbs": 0.0,
            "Threads": 1, "Seed": 0, "FeasibilityTol": 1e-7, "IntFeasTol": 1e-6}


def _integer(value: float) -> int:
    if not math.isfinite(value) or abs(value - round(value)) > 1e-5:
        raise ValueError("Solver returned a decision outside integer extraction tolerance")
    return int(round(value))


def _finite(value):
    return float(value) if value is not None and math.isfinite(value) else None


def assess_solver_result(s: Scenario, info: SolverInfo, candidate: Solution | None, settings: dict) -> Result:
    """Separate status interpretation from the solver so early-stop/error paths can be tested."""
    common = dict(input=s.model_copy(deep=True), algorithm="gurobi", settings=settings, solver=info)
    if info.termination in {"INFEASIBLE", "INF_OR_UNBD", "UNBOUNDED", "NUMERIC"}:
        return Result(**common, status="solver_error", error="Solver failed on a model with a known zero-production feasible plan; inspect the formulation or numerical diagnostics.")
    if candidate is None:
        if info.termination == "OPTIMAL":
            return Result(**common, status="solver_error", error="Optimal termination without a candidate solution")
        return Result(**common, status="no_solution")
    report = check_solution(s, candidate)
    if not report.valid:
        return Result(**common, status="invalid_result", validation=report, error="Solver output failed independent validation")
    j, raw, bound = candidate.objective, info.raw_objective, info.objective_bound
    if raw is None or abs(raw - j) > 1e-5 or (bound is not None and bound > j + 1e-6):
        return Result(**common, status="solver_error", validation=report, error="Solver objective/bound disagrees with the independently checked solution")
    if info.termination == "OPTIMAL":
        if settings.get("MIPGap") != 0 or settings.get("MIPGapAbs") != 0 or bound is None or abs(bound - j) > 1e-5:
            return Result(**common, status="solver_error", validation=report, error="Optimality settings or objective bound are inconsistent")
        status = "optimal"
    else:
        status = "feasible"
    return Result(**common, status=status, solution=candidate, validation=report)


def solve(s: Scenario, algorithm="gurobi", time_limit=10) -> Result:
    if algorithm not in ("gurobi", "greedy"):
        raise ValueError("Algorithm must be gurobi or greedy")
    if type(time_limit) is not int or not 1 <= time_limit <= 60:
        raise ValueError("Solver time limit must be an integer from 1 to 60 seconds")
    if algorithm == "greedy":
        candidate = plan_greedy(s)
        report = check_solution(s, candidate)
        return Result(input=s.model_copy(deep=True), algorithm="greedy", settings={},
                      status="heuristic_feasible" if report.valid else "invalid_result",
                      solution=candidate if report.valid else None, validation=report,
                      error=None if report.valid else "Greedy plan failed independent validation")
    settings = {**SETTINGS, "TimeLimit": time_limit}
    common = dict(input=s.model_copy(deep=True), algorithm="gurobi", settings=settings)
    try:
        gp = import_module("gurobipy")
    except ImportError:
        return Result(**common, status="solver_unavailable", error="Install the optional solver dependencies to run Gurobi; greedy planning remains available.")
    initialized = False
    try:
        with gp.Env(empty=True) as env:
            env.setParam("OutputFlag", 0)
            env.start()
            initialized = True
            with gp.Model("synthetic_capacity", env=env) as m:
                for k, v in settings.items():
                    m.setParam(k, v)
                ps = sorted(p.id for p in s.products)
                cs = sorted(c.id for c in s.cells)
                ts = [t.id for t in s.ordered_shifts]
                rates = {(r.product_id, r.cell_id): r.minutes_per_unit for r in s.processing_times}
                cap = {(r.cell_id, r.shift_id): r.available_machine_minutes for r in s.capacity}
                demand = {(r.product_id, r.shift_id): r.due_units for r in s.demand}
                initial = {p.id: p.initial_inventory_units for p in s.products}
                qmax = {p: max(0, sum(demand[p, t] for t in ts) - initial[p]) for p in ps}
                imax = {p: initial[p] + qmax[p] for p in ps}
                bmax = {(p, t): sum(demand[p, u] for u in ts[:i + 1]) for p in ps for i, t in enumerate(ts)}
                upper = {(p, c, t): min(qmax[p], cap[c, t] // rates[p, c]) for p, c in rates for t in ts}
                x = {k: m.addVar(vtype=gp.GRB.INTEGER, ub=u, name=f"x[{','.join(k)}]") for k, u in upper.items()}
                y = {(c, t): m.addVar(vtype=gp.GRB.BINARY, name=f"y[{c},{t}]") for c, t in product(cs, ts)}
                inv = {(p, t): m.addVar(vtype=gp.GRB.INTEGER, ub=imax[p], name=f"I[{p},{t}]") for p, t in product(ps, ts)}
                back = {(p, t): m.addVar(vtype=gp.GRB.INTEGER, ub=bmax[p, t], name=f"B[{p},{t}]") for p, t in product(ps, ts)}
                z = {(p, t): m.addVar(vtype=gp.GRB.BINARY, name=f"sign[{p},{t}]") for p, t in product(ps, ts)}
                for c, t in product(cs, ts):
                    eligible = [p for p in ps if (p, c) in rates]
                    m.addConstr(gp.quicksum(rates[p, c] * x[p, c, t] for p in eligible) <= cap[c, t] * y[c, t], name=f"capacity[{c},{t}]")
                    m.addConstr(y[c, t] <= gp.quicksum(x[p, c, t] for p in eligible), name=f"nonempty[{c},{t}]")
                    for p in eligible:
                        m.addConstr(x[p, c, t] <= upper[p, c, t] * y[c, t], name=f"activation[{p},{c},{t}]")
                for t in s.ordered_shifts:
                    m.addConstr(gp.quicksum(c.crew_operators * y[c.id, t.id] for c in s.cells) <= t.available_operators, name=f"staff[{t.id}]")
                for p in ps:
                    eligible = [c for c in cs if (p, c) in rates]
                    m.addConstr(gp.quicksum(x[p, c, t] for c in eligible for t in ts) <= qmax[p], name=f"useful[{p}]")
                    for i, t in enumerate(ts):
                        prev = initial[p] if i == 0 else inv[p, ts[i - 1]] - back[p, ts[i - 1]]
                        m.addConstr(inv[p, t] - back[p, t] == prev + gp.quicksum(x[p, c, t] for c in eligible) - demand[p, t], name=f"balance[{p},{t}]")
                        m.addConstr(inv[p, t] <= imax[p] * z[p, t], name=f"inventory_sign[{p},{t}]")
                        m.addConstr(back[p, t] <= bmax[p, t] * (1 - z[p, t]), name=f"backlog_sign[{p},{t}]")
                m.setObjective(gp.quicksum(back.values()), gp.GRB.MINIMIZE)
                m.optimize()
                names = {getattr(gp.GRB, n): n for n in ("OPTIMAL", "INFEASIBLE", "INF_OR_UNBD", "UNBOUNDED", "TIME_LIMIT", "INTERRUPTED", "NUMERIC", "SUBOPTIMAL", "WORK_LIMIT", "NODE_LIMIT", "MEM_LIMIT", "SOLUTION_LIMIT")}
                has_solution = m.SolCount > 0
                try:
                    bound = _finite(m.ObjBound)
                except (gp.GurobiError, AttributeError):
                    bound = None
                info = SolverInfo(version=".".join(map(str, gp.gurobi.version())), termination=names.get(m.Status, f"STATUS_{m.Status}"),
                                  termination_code=m.Status, raw_objective=_finite(m.ObjVal) if has_solution else None,
                                  objective_bound=bound, relative_gap=_finite(m.MIPGap) if has_solution else None,
                                  solve_runtime_seconds=float(m.Runtime))
                candidate = None
                if has_solution:
                    try:
                        # Preserve raw solver state decisions: never reconstruct them to conceal a model error.
                        candidate = make_solution(s, {k: _integer(v.X) for k, v in x.items()},
                                                  activity={k: _integer(v.X) for k, v in y.items()},
                                                  stock={k: (_integer(inv[k].X), _integer(back[k].X)) for k in inv})
                    except ValueError:
                        return Result(**common, solver=info, status="invalid_result", error="Solver decisions could not be extracted as valid integers")
                return assess_solver_result(s, info, candidate, settings)
    except gp.GurobiError as exc:
        status = "solver_unavailable" if not initialized or exc.errno == 10009 else "solver_error"
        return Result(**common, status=status, error=f"Gurobi error {exc.errno}; check the local installation/license and model limits. Greedy planning is available separately.")
