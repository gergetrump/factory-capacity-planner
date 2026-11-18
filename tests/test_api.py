import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from capacity_planner import api
from capacity_planner.examples import load_example
from capacity_planner.model import solve
from capacity_planner.schema import Result

client = TestClient(api.app)


def payload(algorithm='greedy'):
    return {'scenario': load_example('tiny').model_dump(), 'algorithm': algorithm, 'solver_time_limit_seconds': 10}


def test_examples_and_greedy_without_gurobi(monkeypatch):
    def no_solver(name): raise AssertionError('Greedy must not initialize Gurobi')
    monkeypatch.setattr('capacity_planner.model.import_module', no_solver)
    examples = client.get('/api/examples')
    assert examples.status_code == 200 and [r['id'] for r in examples.json()] == ['base', 'tiny', 'lookahead']
    response = client.post('/api/solve', json=payload())
    r = Result.model_validate(response.json())
    assert response.status_code == 200 and r.status == 'heuristic_feasible'
    assert r.solver is None and r.settings == {} and r.validation.valid
    assert r.input == load_example('tiny')


@pytest.mark.parametrize('bad', [{'algorithm': 'other'}, {'solver_time_limit_seconds': True}, {'solver_time_limit_seconds': 61}])
def test_invalid_requests(bad):
    request = {**payload(), **bad}
    assert client.post('/api/solve', json=request).status_code == 422


def test_validation_failure_does_not_reserve_lock():
    request = payload(); request['scenario']['capacity'].pop()
    assert client.post('/api/solve', json=request).status_code == 422
    assert client.post('/api/solve', json=payload()).status_code == 200


def test_busy_and_release_after_execution_error(monkeypatch):
    entered, finish = threading.Event(), threading.Event()
    real = solve
    def blocked(s, algorithm, time_limit):
        entered.set()
        assert finish.wait(timeout=5)
        return real(s, algorithm, time_limit)
    monkeypatch.setattr(api, 'solve', blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/solve', json=payload())
        assert entered.wait(timeout=5)
        try:
            assert client.post('/api/solve', json=payload()).status_code == 409
        finally:
            finish.set()
        assert future.result(timeout=5).status_code == 200
    def crash(*args): raise RuntimeError('simulated programmer error')
    monkeypatch.setattr(api, 'solve', crash)
    with pytest.raises(RuntimeError): client.post('/api/solve', json=payload())
    monkeypatch.setattr(api, 'solve', real)
    assert client.post('/api/solve', json=payload()).status_code == 200


def test_license_error_is_not_greedy_fallback(monkeypatch):
    def missing(name): raise ImportError('absent')
    monkeypatch.setattr('capacity_planner.model.import_module', missing)
    response = client.post('/api/solve', json=payload('gurobi'))
    r = Result.model_validate(response.json())
    assert response.status_code == 503 and r.algorithm == 'gurobi'
    assert r.status == 'solver_unavailable' and r.solution is None
    assert client.post('/api/solve', json=payload()).status_code == 200


def test_frontend_origin_preflight():
    response = client.options('/api/solve', headers={'Origin': 'http://127.0.0.1:5173', 'Access-Control-Request-Method': 'POST'})
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'http://127.0.0.1:5173'
