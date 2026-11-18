"""Check physical baseline behavior and benchmark accounting, without Gurobi."""
import pytest

from benchmarks.heuristic import plan_portfolio
from benchmarks.suite import cases, generated_case, model_size
from capacity_planner.check import check_solution
from capacity_planner.examples import load_example, with_outage
from capacity_planner.greedy import plan_greedy
from capacity_planner.schema import Scenario
from scripts.run_benchmarks import classify_error, summary_rows, timed_run


def test_portfolio_plans_ahead_and_keeps_original_greedy():
    s = load_example('lookahead')
    baseline = plan_greedy(s)
    plan, diagnostics = plan_portfolio(s)
    assert baseline.objective == 1 and plan.objective == 0
    assert diagnostics['candidate_objectives']['original_greedy'] == 1
    assert diagnostics['candidate_objectives'][diagnostics['selected_policy']] == 0
    assert check_solution(s, plan).valid


@pytest.mark.parametrize('edge', ['no_staff', 'no_eligibility', 'surplus_initial', 'outage'])
def test_portfolio_physical_edge_cases(edge):
    s = load_example('lookahead')
    data = s.model_dump()
    if edge == 'no_staff':
        for t in data['shifts']:
            t['available_operators'] = 0
    if edge == 'no_eligibility':
        data['processing_times'] = []
    if edge == 'surplus_initial':
        data['products'][0]['initial_inventory_units'] = 5
    if edge == 'outage':
        data = with_outage(s, s.cells[0].id, 1, 2).model_dump()
    s = Scenario.model_validate(data)
    before = s.model_dump()
    plan, _ = plan_portfolio(s)
    assert check_solution(s, plan).valid
    assert s.model_dump() == before
    assert plan.metrics.produced_units == 0
    assert plan.objective == (0 if edge == 'surplus_initial' else 1)


def test_seeded_suite_is_fixed_and_ceiling_counts_are_explicit():
    a, b = cases(), cases()
    assert len(a) == 13 and a == b
    assert model_size(a['disrupted-8p-6c-20t']) == {
        'products': 8, 'cells': 6, 'shifts': 20, 'eligible_pairs': 48,
        'variables': 1560, 'constraints': 1708}
    assert generated_case(3, 2, 4, 'disrupted', 12) != generated_case(3, 2, 4, 'disrupted', 13)
    with pytest.raises(ValueError):
        generated_case(3, 2, 4, 'unknown', 1)


def test_seeded_plans_are_feasible_deterministic_and_dominate_original():
    # Vary rate/eligibility, initial stock, zero-capacity outages and staffing.
    for seed in range(20):
        s = generated_case(3, 3, 4, 'disrupted' if seed % 2 else 'balanced', seed)
        plan, diagnostics = plan_portfolio(s)
        assert check_solution(s, plan).valid
        assert plan.objective <= plan_greedy(s).objective
        assert plan_portfolio(s) == (plan, diagnostics)


def test_timed_failure_and_status_classification(monkeypatch):
    def broken(*args):
        raise RuntimeError('test failure')
    monkeypatch.setattr('scripts.run_benchmarks.plan_portfolio', broken)
    result, elapsed = timed_run(load_example('tiny'), 'portfolio', 1)
    assert result['status'] == 'exception' and 'test failure' in result['error'] and elapsed >= 0
    assert classify_error('solver_error', 'Gurobi error 10010; model limits') == 'restricted_license_model_limit'
    assert classify_error('solver_unavailable', 'missing') == 'solver_or_license_unavailable'
    assert classify_error('no_solution', None) == 'no_solution'
    assert classify_error('feasible', None) is None


def test_summary_preserves_timeouts_missing_solutions_and_quality_ranges():
    rows = []
    for method, j, wall in [('gurobi', 5, 1.0), ('gurobi', 4, 1.1), ('greedy', 9, .01), ('portfolio', 6, .1)]:
        rows.append({'case': 'test', 'method': method, 'objective': j, 'checked_feasible': True,
                     'objective_bound': 2 if method == 'gurobi' else None, 'wall_seconds': wall,
                     'solver_seconds': .9 if method == 'gurobi' else None, 'status': 'feasible' if method == 'gurobi' else 'heuristic_feasible',
                     'termination': 'TIME_LIMIT' if method == 'gurobi' else None, 'failure_kind': None})
    rows.append({**rows[0], 'objective': None, 'checked_feasible': False, 'status': 'no_solution', 'failure_kind': 'no_solution'})
    summary = summary_rows(rows)
    assert summary[0]['runs'] == 3 and summary[0]['feasible_runs'] == 2
    assert summary[0]['terminations'] == {'TIME_LIMIT': 3}
    assert summary[0]['failures'] == {'no_solution': 1}
    assert summary[0]['objective_min'] == 4 and summary[0]['objective_max'] == 5
    assert summary[0]['best_gurobi_lower_bound'] == 2
    assert summary[2]['best_absolute_gap_to_bound'] == 4
