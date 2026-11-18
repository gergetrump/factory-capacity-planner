import copy
from itertools import product

import pytest
from pydantic import ValidationError

from capacity_planner.check import check_solution, make_solution
from capacity_planner.examples import load_example, with_outage
from capacity_planner.model import SETTINGS, assess_solver_result, solve
from capacity_planner.schema import Result, Scenario, SolverInfo


def one_product(demand=(0, 1), capacity=(1, 0), initial=0, staff=(1, 1)):
    data = load_example('lookahead').model_dump()
    data['products'][0]['initial_inventory_units'] = initial
    for i, row in enumerate(data['demand']): row['due_units'] = demand[i]
    for i, row in enumerate(data['capacity']): row['available_machine_minutes'] = capacity[i]
    for i, row in enumerate(data['shifts']):
        row['duration_minutes'] = max(1, capacity[i])
        row['available_operators'] = staff[i]
    return Scenario.model_validate(data)


def tiny_enumeration(s):
    # Enumerates physical choices directly; no optimizer/checker/helper expressions.
    best = None
    ds = {(r.product_id, r.shift_id): r.due_units for r in s.demand}
    cs = {(r.cell_id, r.shift_id): r.available_machine_minutes for r in s.capacity}
    shifts = s.ordered_shifts
    for seq in product([(0, 0), (1, 0), (2, 0), (0, 1), (0, 2)], repeat=2):
        if any(sum(v > 0 for v in xs) > t.available_operators for xs, t in zip(seq, shifts)): continue
        if any(xs[i] > cs[c, t.id] for xs, t in zip(seq, shifts) for i, c in enumerate(['C1', 'C2'])): continue
        if any(sum(xs[i] for xs in seq) > sum(ds[p, t.id] for t in shifts) for i, p in enumerate(['A', 'B'])): continue
        net = [0, 0]; j = 0
        for xs, t in zip(seq, shifts):
            for i, p in enumerate(['A', 'B']):
                net[i] += xs[i] - ds[p, t.id]
                j += max(-net[i], 0)
        best = j if best is None else min(best, j)
    return best


@pytest.mark.parametrize('bad', [-1, 0.5, True, '1', float('nan')])
def test_strict_quantities(bad):
    data = load_example('tiny').model_dump()
    data['demand'][0]['due_units'] = bad
    with pytest.raises(ValidationError): Scenario.model_validate(data)


@pytest.mark.parametrize('change', ['duplicate', 'missing', 'reference', 'duration', 'indices', 'unknown'])
def test_invalid_structures(change):
    data = load_example('tiny').model_dump()
    if change == 'duplicate': data['products'].append(copy.deepcopy(data['products'][0]))
    if change == 'missing': data['capacity'].pop()
    if change == 'reference': data['processing_times'][0]['cell_id'] = 'unknown'
    if change == 'duration': data['capacity'][0]['available_machine_minutes'] = 3
    if change == 'indices': data['shifts'][0]['index'] = 2
    if change == 'unknown': data['shifts'][0]['extra'] = 1
    with pytest.raises(ValidationError): Scenario.model_validate(data)


def test_greedy_is_solver_free(monkeypatch):
    def unexpected_import(name): raise AssertionError('Greedy must not import Gurobi')
    monkeypatch.setattr('capacity_planner.model.import_module', unexpected_import)
    r = solve(load_example('lookahead'), 'greedy')
    assert r.status == 'heuristic_feasible' and r.solver is None and r.settings == {}
    assert r.validation.valid and r.solution.objective == 1
    assert Result.model_validate_json(r.model_dump_json()) == r


def test_missing_solver_is_explicit(monkeypatch):
    def missing(name): raise ImportError('absent')
    monkeypatch.setattr('capacity_planner.model.import_module', missing)
    r = solve(load_example('tiny'))
    assert r.status == 'solver_unavailable' and r.solution is None and r.algorithm == 'gurobi'


def test_tiny_oracle_and_zero_production():
    s = load_example('tiny')
    assert tiny_enumeration(s) == 0
    z = make_solution(s, {})
    assert z.objective == 6 and check_solution(s, z).valid
    data = s.model_dump(); data['shifts'][1]['available_operators'] = 0
    assert tiny_enumeration(Scenario.model_validate(data)) == 2
    assert solve(s, 'greedy').solution.objective == 0


@pytest.mark.parametrize('corrupt', ['capacity', 'staff', 'activation', 'stock', 'keys', 'objective', 'metrics', 'fractional'])
def test_checker_rejects_corruption(corrupt):
    s = load_example('tiny')
    p = solve(s, 'greedy').solution.model_copy(deep=True)
    if corrupt == 'capacity':
        next(r for r in p.production if r.product_id == 'A' and r.cell_id == 'C1' and r.shift_id == 'T1').units = 3
    if corrupt == 'staff':
        next(r for r in p.production if r.product_id == 'B' and r.cell_id == 'C2' and r.shift_id == 'T1').units = 1
        next(r for r in p.activity if r.cell_id == 'C2' and r.shift_id == 'T1').active = 1
    if corrupt == 'activation': p.activity[0].active = 0
    if corrupt == 'stock': p.stock[0].inventory_units = 1; p.stock[0].backlog_units = 1
    if corrupt == 'keys': p.production.pop()
    if corrupt == 'objective': p.objective = 99
    if corrupt == 'metrics': p.metrics.capacity_utilization = .999
    if corrupt == 'fractional': p.production[0].units = 1.5
    assert not check_solution(s, p).valid


def test_snapshot_and_outage_do_not_mutate_input():
    s = load_example('base'); before = s.model_dump()
    outage = with_outage(s, 'C3', 5, 6)
    assert s.model_dump() == before
    assert sum(r.available_machine_minutes == 0 for r in outage.capacity) == 2
    r = solve(s, 'greedy')
    s.products[0].initial_inventory_units = 123
    assert r.input.products[0].initial_inventory_units == 0


def test_outage_preserves_valid_max_length_names_and_ids():
    data = load_example('lookahead').model_dump()
    data['name'] = 'N' * 160
    cell = 'C' * 64
    data['cells'][0]['id'] = cell
    for row in data['processing_times'] + data['capacity']:
        row['cell_id'] = cell
    scenario = Scenario.model_validate(data)
    changed = with_outage(scenario, cell, 1, 1)
    assert len(changed.name) == 160 and cell in changed.name
    assert changed.capacity[0].available_machine_minutes == 0
    assert scenario.name == 'N' * 160


def info(termination='OPTIMAL', objective=6.0, bound=6.0):
    codes = {'OPTIMAL': 2, 'TIME_LIMIT': 9, 'INFEASIBLE': 3, 'NUMERIC': 12}
    return SolverInfo(version='fake', termination=termination, termination_code=codes[termination],
                      raw_objective=objective, objective_bound=bound, relative_gap=None, solve_runtime_seconds=0.01)


@pytest.mark.parametrize('termination,candidate,expected', [
    ('OPTIMAL', True, 'optimal'), ('TIME_LIMIT', True, 'feasible'),
    ('TIME_LIMIT', False, 'no_solution'), ('INFEASIBLE', False, 'solver_error'),
    ('NUMERIC', True, 'solver_error'), ('OPTIMAL', False, 'solver_error')])
def test_status_interpretation(termination, candidate, expected):
    s = load_example('tiny'); plan = make_solution(s, {}) if candidate else None
    meta = info(termination, 6.0 if candidate else None, 6.0 if termination == 'OPTIMAL' else 0.0)
    r = assess_solver_result(s, meta, plan, SETTINGS)
    assert r.status == expected


def test_false_optimality_and_invalid_output_rejected():
    s = load_example('tiny'); plan = make_solution(s, {})
    assert assess_solver_result(s, info(bound=0.), plan, SETTINGS).status == 'solver_error'
    assert assess_solver_result(s, info(), plan, {**SETTINGS, 'MIPGap': .1}).status == 'solver_error'
    plan.objective = 4
    assert assess_solver_result(s, info(), plan, SETTINGS).status == 'invalid_result'


@pytest.fixture
def licensed():
    gp = pytest.importorskip('gurobipy')
    try:
        with gp.Env(empty=True) as e:
            e.setParam('OutputFlag', 0); e.start()
    except gp.GurobiError:
        pytest.skip('A local Gurobi license is unavailable')


@pytest.mark.gurobi
def test_real_solver_oracle(licensed):
    s = load_example('tiny')
    for shortage in (False, True):
        data = s.model_dump()
        if shortage: data['shifts'][1]['available_operators'] = 0
        case = Scenario.model_validate(data)
        r = solve(case)
        assert r.status == 'optimal' and r.validation.valid
        assert r.solution.objective == tiny_enumeration(case)
    r = solve(load_example('lookahead'))
    assert r.status == 'optimal' and r.solution.objective == 0


@pytest.mark.gurobi
def test_default_and_disruptions(licensed):
    base = load_example('base')
    for s, expected in [(base, 0), (with_outage(base, 'C3', 5, 6), 0), (with_outage(base, 'C3', 1, 10), 550)]:
        r = solve(s)
        assert r.status == 'optimal', r.error
        assert r.solution.objective == expected and r.validation.valid


@pytest.mark.gurobi
def test_shared_cell_crew_counted_once(licensed):
    data = load_example('tiny').model_dump()
    data['cells'] = [{'id': 'C1', 'crew_operators': 1}]
    data['shifts'] = data['shifts'][:1]
    data['processing_times'] = [{'product_id': p, 'cell_id': 'C1', 'minutes_per_unit': 1} for p in ['A', 'B']]
    data['capacity'] = [{'cell_id': 'C1', 'shift_id': 'T1', 'available_machine_minutes': 2}]
    data['demand'] = [{'product_id': p, 'shift_id': 'T1', 'due_units': 1} for p in ['A', 'B']]
    r = solve(Scenario.model_validate(data))
    assert r.status == 'optimal' and r.solution.objective == 0
    assert r.solution.metrics.staffing[0].reserved_operators == 1
    assert [p.units for p in r.solution.production] == [1, 1]


@pytest.mark.gurobi
@pytest.mark.parametrize('s,expected', [
    (one_product(initial=5), 0), (one_product(staff=(0, 0)), 1),
    (one_product(demand=(0, 0)), 0), (one_product(demand=(1, 1), capacity=(2, 2)), 0)])
def test_inventory_shortage_and_primary_ties(licensed, s, expected):
    r = solve(s)
    assert r.status == 'optimal' and r.solution.objective == expected and r.validation.valid
    if s.products[0].initial_inventory_units == 5:
        assert r.solution.metrics.produced_units == 0
        assert r.solution.metrics.inventory_unit_shifts == 9


@pytest.mark.gurobi
def test_no_eligible_products_is_feasible(licensed):
    data = one_product().model_dump(); data['processing_times'] = []
    r = solve(Scenario.model_validate(data))
    assert r.status == 'optimal' and r.solution.objective == 1
    assert r.solution.metrics.active_cell_shifts == 0
