"""Deterministic due-demand allocation with no preproduction/lookahead."""
from .check import make_solution
from .schema import Scenario


def plan_greedy(s: Scenario):
    rates = {(r.product_id, r.cell_id): r.minutes_per_unit for r in s.processing_times}
    cap = {(r.cell_id, r.shift_id): r.available_machine_minutes for r in s.capacity}
    demand = {(r.product_id, r.shift_id): r.due_units for r in s.demand}
    crews = {r.id: r.crew_operators for r in s.cells}
    ps = sorted(p.id for p in s.products)
    cs = sorted(c.id for c in s.cells)
    net = {p.id: p.initial_inventory_units for p in s.products}
    remaining_q = {p.id: max(0, sum(r.due_units for r in s.demand if r.product_id == p.id) - p.initial_inventory_units)
                   for p in s.products}
    production = {}
    for t in s.ordered_shifts:
        minutes = {c: cap[c, t.id] for c in cs}
        active = set()
        staff = t.available_operators
        shortage = {p: max(0, demand[p, t.id] - net[p]) for p in ps}
        order = sorted(ps, key=lambda p: (sum((p, c) in rates and minutes[c] >= rates[p, c] for c in cs), -shortage[p], p))
        for p in order:
            cells = sorted([c for c in cs if (p, c) in rates], key=lambda c: (c not in active, rates[p, c], c))
            for c in cells:
                if c not in active and crews[c] > staff:
                    continue
                q = min(shortage[p], minutes[c] // rates[p, c], remaining_q[p])
                if q <= 0:
                    continue
                if c not in active:
                    active.add(c)
                    staff -= crews[c]
                production[p, c, t.id] = q
                minutes[c] -= q * rates[p, c]
                shortage[p] -= q
                remaining_q[p] -= q
        for p in ps:
            net[p] += sum(production.get((p, c, t.id), 0) for c in cs) - demand[p, t.id]
    return make_solution(s, production)
