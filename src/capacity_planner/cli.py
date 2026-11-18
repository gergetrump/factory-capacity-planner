import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from .check import check_solution
from .examples import EXAMPLE_IDS, load_example, with_outage
from .model import solve
from .schema import Result, Scenario


def _emit(value, output):
    text = json.dumps(value, indent=2, allow_nan=False) + "\n"
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text)
    else:
        sys.stdout.write(text)


def main():
    parser = argparse.ArgumentParser(description="Synthetic factory capacity allocation; one backlog objective")
    sub = parser.add_subparsers(dest="command", required=True)
    example = sub.add_parser("example", help="Export a bundled input scenario")
    example.add_argument("name", choices=EXAMPLE_IDS)
    example.add_argument("--output", "-o")
    validate = sub.add_parser("validate", help="Validate a scenario JSON file")
    validate.add_argument("input")
    run = sub.add_parser("solve", help="Solve a JSON input or bundled example")
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--input")
    source.add_argument("--example", choices=EXAMPLE_IDS)
    run.add_argument("--algorithm", choices=["gurobi", "greedy"], default="gurobi")
    run.add_argument("--time-limit", type=int, choices=range(1, 61), default=10, metavar="1..60")
    run.add_argument("--outage-cell")
    run.add_argument("--outage-start", type=int)
    run.add_argument("--outage-end", type=int)
    run.add_argument("--output", "-o")
    check = sub.add_parser("check", help="Check a saved result's feasibility and metrics (not optimality)")
    check.add_argument("result")
    args = parser.parse_args()
    try:
        if args.command == "example":
            _emit(load_example(args.name).model_dump(), args.output)
            return 0
        if args.command == "validate":
            scenario = Scenario.model_validate_json(Path(args.input).read_text())
            _emit({"valid": True, "name": scenario.name}, None)
            return 0
        if args.command == "check":
            result = Result.model_validate_json(Path(args.result).read_text())
            if result.solution is None:
                raise ValueError("Saved result has no accepted solution to check")
            report = check_solution(result.input, result.solution)
            _emit(report.model_dump(), None)
            return 0 if report.valid else 1
        s = load_example(args.example) if args.example else Scenario.model_validate_json(Path(args.input).read_text())
        if any(v is not None for v in (args.outage_cell, args.outage_start, args.outage_end)):
            if any(v is None for v in (args.outage_cell, args.outage_start, args.outage_end)):
                raise ValueError("An outage requires --outage-cell, --outage-start and --outage-end")
            s = with_outage(s, args.outage_cell, args.outage_start, args.outage_end)
        result = solve(s, args.algorithm, args.time_limit)
        _emit(result.model_dump(), args.output)
        return 0 if result.solution is not None else 1
    except (ValidationError, ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
