"""Solver-free dispatch portfolio; no optimality guarantee or industrial claim."""
from itertools import combinations

from capacity_planner.check import check_solution, make_solution
from capacity_planner.greedy import plan_greedy
from capacity_planner.schema import Scenario


def _dispatch(s: Scenario, window: int, priority: str):
    ps = sorted(p.id for p in s.products)
    cs = sorted(c.id for c in s.cells)
    ts = s.ordered_shifts
    rates = {(r.product_id, r.cell_id): r.minutes_per_unit for r in s.processing_times}
    cap = {(r.cell_id, r.shift_id): r.available_machine_minutes for r in s.capacity}
    demand = {(r.product_id, r.shift_id): r.due_units for r in s.demand}
    crew = {c.id: c.crew_operators for c in s.cells}
    net = {p.id: p.initial_inventory_units for p in s.products}
    production = {}
    for i, t in enumerate(ts):
        end = min(len(ts), i + window)
        usable = [c for c in cs if cap[c, t.id] and any((p, c) in rates for p in ps)]
        subsets = [subset for size in range(len(usable) + 1)
                   for subset in combinations(usable, size)
                   if sum(crew[c] for c in subset) <= t.available_operators]
        best = None
        for subset in subsets:
            minutes = {c: cap[c, t.id] for c in subset}
            made = {p: 0 for p in ps}
            allocation = {}
            while True:
                choices = []
                for p in ps:
                    cumulative = 0
                    for j in range(i, end):
                        cumulative += demand[p, ts[j].id]
                        shortage = cumulative - net[p] - made[p]
                        if shortage > 0:
                            break
                    else:
                        continue
                    eligible = [c for c in subset if (p, c) in rates and minutes[c] >= rates[p, c]]
                    for c in eligible:
                        flexibility = sum((other, c) in rates for other in ps)
                        if priority == 'urgency':
                            key = (j, len(eligible), flexibility, rates[p, c], p, c)
                        else:
                            key = (int(j > i), len(eligible), j, flexibility, rates[p, c], p, c)
                        choices.append((key, p, c, min(shortage, minutes[c] // rates[p, c])))
                if not choices:
                    break
                _, p, c, quantity = min(choices)
                made[p] += quantity
                minutes[c] -= quantity * rates[p, c]
                allocation[p, c, t.id] = allocation.get((p, c, t.id), 0) + quantity
            # Lookahead score assumes no further production inside this window.
            # It is a dispatch proxy, not a solved downstream planning problem.
            projected = 0
            for p in ps:
                stock = net[p] + made[p]
                for j in range(i, end):
                    stock -= demand[p, ts[j].id]
                    projected += max(-stock, 0)
            current_backlog = sum(max(demand[p, t.id] - net[p] - made[p], 0) for p in ps)
            key = (projected, current_backlog, tuple(sorted(allocation.items())))
            if best is None or key < best[0]:
                best = (key, allocation, made)
        _, allocation, made = best
        production.update(allocation)
        for p in ps:
            net[p] += made[p] - demand[p, t.id]
    return make_solution(s, production)


def plan_portfolio(s: Scenario):
    """Select lowest actual full-horizon backlog among checked deterministic plans.

    Includes the app's original greedy plan, so cannot have a worse objective.
    All variants know the same full deterministic demand input as Gurobi.
    Selection is retrospective over these candidate plans, not an optimum proof.
    """
    candidates = [('original_greedy', plan_greedy(s))]
    for window in sorted({1, 2, len(s.shifts)}):
        for priority in ('urgency', 'scarcity'):
            candidates.append((f'window_{window}_{priority}', _dispatch(s, window, priority)))
    for name, candidate in candidates:
        report = check_solution(s, candidate)
        if not report.valid:
            raise ValueError(f'Portfolio candidate {name} failed independent validation: {report.errors}')
    selected, solution = min(candidates, key=lambda item: (item[1].objective, item[0]))
    return solution, {'selected_policy': selected, 'candidate_count': len(candidates),
                      'candidate_objectives': {name: plan.objective for name, plan in candidates}}
