from importlib.resources import files

from .schema import Scenario

EXAMPLE_IDS = ("base", "tiny", "lookahead")


def load_example(name: str) -> Scenario:
    if name not in EXAMPLE_IDS:
        raise ValueError(f"Unknown example: {name}")
    return Scenario.model_validate_json(files("capacity_planner").joinpath("data", name + ".json").read_text())


def with_outage(s: Scenario, cell: str, start: int, end: int) -> Scenario:
    if cell not in {c.id for c in s.cells} or not 1 <= start <= end <= len(s.shifts):
        raise ValueError("Select a known cell and an ordered shift range within the horizon")
    data = s.model_dump()
    affected = {t.id for t in s.shifts if start <= t.index <= end}
    for r in data["capacity"]:
        if r["cell_id"] == cell and r["shift_id"] in affected:
            r["available_machine_minutes"] = 0
    suffix = f" · {cell} outage, shifts {start}–{end}"
    data["name"] = s.name[:160 - len(suffix)] + suffix
    return Scenario.model_validate(data)
