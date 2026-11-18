"""Reproducible local quality/timing observations; run from the source checkout."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from benchmarks.heuristic import plan_portfolio
from benchmarks.suite import SUITE_VERSION, cases, model_size
from capacity_planner.check import check_solution
from capacity_planner.model import SETTINGS, solve

METHODS = ('gurobi', 'greedy', 'portfolio')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def classify_error(status, error):
    if error and 'Gurobi error 10010;' in error:
        return 'restricted_license_model_limit'
    if status == 'solver_unavailable':
        return 'solver_or_license_unavailable'
    return None if status in {'optimal', 'feasible', 'heuristic_feasible'} else status


def timed_run(scenario, method, time_limit):
    start = time.perf_counter()
    try:
        if method == 'portfolio':
            solution, diagnostics = plan_portfolio(scenario)
            validation = check_solution(scenario, solution)
            elapsed = time.perf_counter() - start
            result = {'status': 'heuristic_feasible' if validation.valid else 'invalid_result',
                      'solution': solution.model_dump(), 'validation': validation.model_dump(),
                      'solver': None, 'settings': {}, 'error': None, 'diagnostics': diagnostics}
        else:
            native = solve(scenario, method, time_limit)
            # Serialization is outside the timed region for every method.
            elapsed = time.perf_counter() - start
            result = native.model_dump(exclude={'input'})
            return result, elapsed
        return result, elapsed
    except Exception as exc:
        return {'status': 'exception', 'solution': None, 'validation': None, 'solver': None,
                'error': f'{type(exc).__name__}: {exc}'}, time.perf_counter() - start


def summary_rows(records):
    rows = []
    names = list(dict.fromkeys(r['case'] for r in records))
    for name in names:
        group = [r for r in records if r['case'] == name]
        valid = [r for r in group if r['checked_feasible']]
        best = min((r['objective'] for r in valid), default=None)
        lower_bound = max((r['objective_bound'] for r in group if r['objective_bound'] is not None), default=None)
        for method in METHODS:
            runs = [r for r in group if r['method'] == method]
            objectives = [r['objective'] for r in runs if r['checked_feasible']]
            wall = [r['wall_seconds'] for r in runs]
            solver = [r['solver_seconds'] for r in runs if r['solver_seconds'] is not None]
            rows.append({'case': name, 'method': method, 'runs': len(runs),
                         'feasible_runs': sum(r['checked_feasible'] for r in runs),
                         'statuses': dict(Counter(r['status'] for r in runs)),
                         'terminations': dict(Counter(r['termination'] for r in runs if r['termination'])),
                         'failures': dict(Counter(r['failure_kind'] for r in runs if r['failure_kind'])),
                         'objective_min': min(objectives) if objectives else None,
                         'objective_max': max(objectives) if objectives else None,
                         'best_checked_objective_all_methods': best, 'best_gurobi_lower_bound': lower_bound,
                         'best_absolute_gap_to_bound': min(objectives) - lower_bound if objectives and lower_bound is not None else None,
                         'wall_seconds': {'min': min(wall), 'median': statistics.median(wall), 'max': max(wall)},
                         'solver_seconds': {'min': min(solver), 'median': statistics.median(solver), 'max': max(solver)} if solver else None})
    return rows


def installed_version(name):
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=Path('artifacts/benchmarks'))
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--time-limit', type=int, default=2)
    parser.add_argument('--case', action='append', help='Optional subset; repeat for several case IDs')
    args = parser.parse_args(argv)
    if not 1 <= args.repeats <= 20 or not 1 <= args.time_limit <= 60:
        parser.error('repeats must be 1..20 and time-limit 1..60')
    suite = cases()
    if args.case:
        unknown = set(args.case) - set(suite)
        if unknown:
            parser.error(f'Unknown cases: {sorted(unknown)}')
        suite = {name: s for name, s in suite.items() if name in args.case}
    out = args.output_dir.resolve()
    if out.exists():
        parser.error(f'Output directory already exists; use a fresh path: {out}')
    out.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    load_start = os.getloadavg()
    input_metadata = []
    for name, scenario in suite.items():
        data = (scenario.model_dump_json(indent=2) + '\n').encode()
        (out / 'fixtures').mkdir(exist_ok=True)
        (out / 'fixtures' / f'{name}.json').write_bytes(data)
        input_metadata.append({'case': name, 'sha256': digest(data), **model_size(scenario)})
    # Excluded per-method warmups remove first import/module initialization cost.
    # Each actual Gurobi call still creates and closes its own environment/model.
    warmup = []
    for method in METHODS:
        result, elapsed = timed_run(cases()['tiny'], method, args.time_limit)
        warmup.append({'method': method, 'status': result['status'], 'wall_seconds': elapsed,
                       'error': result.get('error')})
    records = []
    snapshots = []
    for case_index, (name, scenario) in enumerate(suite.items()):
        for repeat in range(args.repeats):
            offset = (case_index + repeat) % len(METHODS)
            order = METHODS[offset:] + METHODS[:offset]
            for position, method in enumerate(order):
                result, elapsed = timed_run(scenario, method, args.time_limit)
                solution = result.get('solution')
                # This audit is outside timing. Each implementation already ran
                # its independent checker inside timing; reparse saved quantities.
                from capacity_planner.schema import Solution
                check = check_solution(scenario, Solution.model_validate(solution)) if solution else None
                info = result.get('solver') or {}
                row = {'case': name, 'repeat': repeat + 1, 'order_position': position + 1, 'method': method,
                       'status': result['status'], 'termination': info.get('termination'),
                       'checked_feasible': bool(check and check.valid),
                       'objective': solution['objective'] if solution else None,
                       'final_backlog_units': solution['metrics']['final_backlog_units'] if solution else None,
                       'objective_bound': info.get('objective_bound'), 'relative_gap': info.get('relative_gap'),
                       'wall_seconds': elapsed, 'solver_seconds': info.get('solve_runtime_seconds'),
                       'failure_kind': classify_error(result['status'], result.get('error')), 'error': result.get('error')}
                records.append(row)
                snapshots.append((f'{name}-r{repeat+1}-{method}.json',
                                  {'benchmark_format_version': 1, 'case': name,
                                   'fixture': f'../fixtures/{name}.json', 'measurement': row, 'result': result}))
            print(f'{name} repeat {repeat+1}: ' + ', '.join(
                f"{r['method']}={r['objective']} ({r['status']}, {r['wall_seconds']:.4f}s)" for r in records[-3:]), flush=True)
    # Persist after measurement to avoid timed filesystem I/O between methods.
    for filename, snapshot in snapshots:
        dump(out / 'runs' / filename, snapshot)
    summary = summary_rows(records)
    dump(out / 'measurements.json', records)
    dump(out / 'summary.json', summary)
    code_paths = sorted([*ROOT.glob('src/**/*.py'), *ROOT.glob('benchmarks/*.py'), *ROOT.glob('tests/*.py'),
                         *ROOT.glob('scripts/*.py'), ROOT / 'pyproject.toml', ROOT / 'requirements.lock'])
    revision = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True)
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown') if Path('/proc/cpuinfo').exists() else platform.processor()
    metadata = {'suite_version': SUITE_VERSION, 'started_utc': started,
                'finished_utc': datetime.now(timezone.utc).isoformat(),
                'python': platform.python_version(), 'platform': platform.platform(), 'machine': platform.machine(),
                'cpu': cpu, 'logical_cpu_count': os.cpu_count(), 'load_average_start': load_start,
                'load_average_end': os.getloadavg(),
                'packages': {name: installed_version(name) for name in ('gurobipy', 'pydantic', 'fastapi', 'pytest')},
                'source_revision': revision.stdout.strip() if revision.returncode == 0 else 'uncommitted',
                'source_dirty': bool(dirty.stdout.strip()),
                'source_sha256': {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in code_paths},
                'repeats': args.repeats, 'case_ids': list(suite), 'inputs': input_metadata,
                'solver_settings': {**SETTINGS, 'TimeLimit': args.time_limit},
                'warmups_excluded': warmup, 'method_order': 'rotate (case_index + repeat_index) modulo 3',
                'timing_scope': 'perf_counter wall time: method generation/model/environment setup, extraction and checking; excludes fixture I/O, output serialization, saved-output audit and warmups. Same process; fresh Gurobi environment per run. Portfolio checks all candidates. Not equal compute budgets.',
                'license_scope': 'Actual outcomes recorded per run; no license-capacity claim beyond these tested model sizes.',
                'limitations': 'Synthetic predeclared cases, three-repeat default, shared host, no isolation or real-factory extrapolation. TimeLimit controls optimize only, not total wall time. Heuristics have no optimum certificate.'}
    dump(out / 'environment.json', metadata)
    print(f'Wrote {len(records)} measurements to {out}', flush=True)
    return 1 if any(r['status'] in {'invalid_result', 'exception'} or (r['objective'] is not None and not r['checked_feasible']) for r in records) else 0


if __name__ == '__main__':
    raise SystemExit(main())
