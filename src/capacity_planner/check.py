"""Independent arithmetic validation: this module never imports the optimizer."""
from itertools import product

from .schema import Activity, CellUsage, Metrics, Production, Scenario, Solution, Staffing, Stock, Validation


def make_solution(s: Scenario, production: dict[tuple[str, str, str], int], *, activity=None, stock=None) -> Solution:
    """Dense reporting; explicit solver states are retained so the checker can catch mistakes."""
    ps = sorted(p.id for p in s.products)
    cs = sorted(c.id for c in s.cells)
    ts = [t.id for t in s.ordered_shifts]
    rates = {(r.product_id, r.cell_id): r.minutes_per_unit for r in s.processing_times}
    capacities = {(r.cell_id, r.shift_id): r.available_machine_minutes for r in s.capacity}
    crews = {r.id: r.crew_operators for r in s.cells}
    demand = {(r.product_id, r.shift_id): r.due_units for r in s.demand}
    rows = [Production(product_id=p, cell_id=c, shift_id=t, units=production.get((p, c, t), 0))
            for p, c, t in product(ps, cs, ts)]
    if activity is None:
        activity = {(c, t): int(any(production.get((p, c, t), 0) for p in ps)) for c, t in product(cs, ts)}
    if stock is None:
        stock = {}
        for p in s.products:
            net = p.initial_inventory_units
            for t in ts:
                net += sum(production.get((p.id, c, t), 0) for c in cs) - demand[p.id, t]
                stock[p.id, t] = (max(net, 0), max(-net, 0))
    active_rows = [Activity(cell_id=c, shift_id=t, active=activity[c, t]) for c, t in product(cs, ts)]
    stock_rows = [Stock(product_id=p, shift_id=t, inventory_units=stock[p, t][0], backlog_units=stock[p, t][1])
                  for p, t in product(ps, ts)]
    usage = []
    for c, t in product(cs, ts):
        used = sum(rates.get((p, c), 0) * production.get((p, c, t), 0) for p in ps)
        cap = capacities[c, t]
        usage.append(CellUsage(cell_id=c, shift_id=t, used_minutes=used, available_minutes=cap,
                               utilization=used / cap if cap else None))
    staffing = []
    for t in s.ordered_shifts:
        reserved = sum(crews[c] * activity[c, t.id] for c in cs)
        staffing.append(Staffing(shift_id=t.id, reserved_operators=reserved, available_operators=t.available_operators,
                                 reservation_share=reserved / t.available_operators if t.available_operators else None))
    j = sum(r.backlog_units for r in stock_rows)
    used, cap = sum(r.used_minutes for r in usage), sum(r.available_minutes for r in usage)
    metrics = Metrics(backlog_unit_shifts=j, final_backlog_units=sum(stock[p, ts[-1]][1] for p in ps),
                      active_cell_shifts=sum(activity.values()), inventory_unit_shifts=sum(r.inventory_units for r in stock_rows),
                      produced_units=sum(r.units for r in rows), machine_minutes_used=used, machine_minutes_available=cap,
                      capacity_utilization=used / cap if cap else None, cell_usage=usage, staffing=staffing)
    return Solution(objective=j, production=rows, activity=active_rows, stock=stock_rows, metrics=metrics)


def check_solution(s: Scenario, solution: Solution) -> Validation:
    errors = []
    ps, cs = {p.id for p in s.products}, {c.id for c in s.cells}
    ts = {t.id for t in s.shifts}
    xkeys = [(r.product_id, r.cell_id, r.shift_id) for r in solution.production]
    ykeys = [(r.cell_id, r.shift_id) for r in solution.activity]
    skeys = [(r.product_id, r.shift_id) for r in solution.stock]
    for name, keys, expected in [("production", xkeys, set(product(ps, cs, ts))),
                                  ("activity", ykeys, set(product(cs, ts))),
                                  ("stock", skeys, set(product(ps, ts)))]:
        if len(keys) != len(set(keys)) or set(keys) != expected:
            errors.append(f"{name}: duplicate, missing or unknown keys")
    quantities = [r.units for r in solution.production] + [r.active for r in solution.activity]
    quantities += [v for r in solution.stock for v in (r.inventory_units, r.backlog_units)]
    if any(type(v) is not int or v < 0 for v in quantities):
        errors.append("Decisions/states must be nonnegative integers")
    if any(type(r.active) is not int or r.active not in (0, 1) for r in solution.activity):
        errors.append("Activity must be binary")
    if errors:
        return Validation(valid=False, errors=errors)
    x = {(r.product_id, r.cell_id, r.shift_id): r.units for r in solution.production}
    y = {(r.cell_id, r.shift_id): r.active for r in solution.activity}
    rates = {(r.product_id, r.cell_id): r.minutes_per_unit for r in s.processing_times}
    for p in s.products:
        demand = sum(r.due_units for r in s.demand if r.product_id == p.id)
        limit = max(0, demand - p.initial_inventory_units)
        if sum(q for (pid, _, _), q in x.items() if pid == p.id) > limit:
            errors.append(f"{p.id}: useful-production limit exceeded")
    for (p, c, t), q in x.items():
        if q and (p, c) not in rates:
            errors.append(f"{p}/{c}/{t}: ineligible production")
    for row in s.capacity:
        c, t = row.cell_id, row.shift_id
        used = sum(rates.get((p, c), 0) * x[p, c, t] for p in ps)
        if used > row.available_machine_minutes:
            errors.append(f"{c}/{t}: machine capacity exceeded")
        if y[c, t] != int(any(x[p, c, t] for p in ps)):
            errors.append(f"{c}/{t}: activity/output mismatch")
    for t in s.shifts:
        if sum(c.crew_operators * y[c.id, t.id] for c in s.cells) > t.available_operators:
            errors.append(f"{t.id}: staffing exceeded")
    expected = make_solution(s, x)
    for row, truth in zip(sorted(solution.stock, key=lambda r: (r.product_id, r.shift_id)),
                          sorted(expected.stock, key=lambda r: (r.product_id, r.shift_id))):
        if row != truth:
            errors.append(f"{row.product_id}/{row.shift_id}: inventory/backlog balance or exclusivity violated")
    if solution.objective != expected.objective:
        errors.append("Reported objective does not match recomputed backlog")
    if solution.metrics != expected.metrics:
        errors.append("Reported metrics do not match recomputation")
    return Validation(valid=not errors, errors=errors)
