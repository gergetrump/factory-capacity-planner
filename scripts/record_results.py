"""Record a small reproducible demonstration, not a general performance benchmark."""
import json
import platform
import subprocess
import time
from pathlib import Path

from capacity_planner.check import check_solution
from capacity_planner.examples import load_example, with_outage
from capacity_planner.model import solve


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'docs/results'
    out.mkdir(parents=True, exist_ok=True)
    base = load_example('base')
    cases = {'base': base, 'short_outage': with_outage(base, 'C3', 5, 6),
             'full_outage': with_outage(base, 'C3', 1, 10),
             'lookahead': load_example('lookahead'), 'tiny': load_example('tiny')}
    summary = []
    for name, scenario in cases.items():
        for algorithm in ('gurobi', 'greedy'):
            start = time.perf_counter()
            result = solve(scenario, algorithm)
            elapsed = time.perf_counter() - start
            if result.solution is None:
                raise RuntimeError(f'{name}/{algorithm}: {result.status}: {result.error}')
            if not check_solution(result.input, result.solution).valid:
                raise RuntimeError(f'{name}/{algorithm}: invalid result')
            (out / f'{name}-{algorithm}.json').write_text(result.model_dump_json(indent=2) + '\n')
            metrics = result.solution.metrics
            row = {'scenario': name, 'algorithm': algorithm, 'status': result.status,
                   'backlog_unit_shifts': result.solution.objective, 'final_backlog_units': metrics.final_backlog_units,
                   'inventory_unit_shifts': metrics.inventory_unit_shifts, 'active_cell_shifts': metrics.active_cell_shifts,
                   'observed_wall_seconds': round(elapsed, 6),
                   'solver_seconds': result.solver.solve_runtime_seconds if result.solver else None}
            summary.append(row)
            print(f'{name:14} {algorithm:7} backlog={result.solution.objective:4} final={metrics.final_backlog_units:3} {result.status}')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    revision = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=root, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=root, capture_output=True, text=True)
    meta = {'python': platform.python_version(), 'system': platform.system(), 'machine': platform.machine(),
            'source_revision': revision.stdout.strip() if revision.returncode == 0 else 'uncommitted',
            'source_dirty': bool(dirty.stdout.strip()),
            'scope': 'Single observations in fixed case order; not a repeated speed comparison.'}
    (out / 'environment.json').write_text(json.dumps(meta, indent=2) + '\n')


if __name__ == '__main__':
    main()
