"""Typed JSON boundaries. Quantities are strict integers; IDs are references."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Id = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
Qty = Annotated[int, Field(strict=True, ge=0, le=10_000)]
Count = Annotated[int, Field(strict=True, ge=0)]
Bit = Annotated[int, Field(strict=True, ge=0, le=1)]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Product(Record):
    id: Id
    initial_inventory_units: Qty


class Cell(Record):
    id: Id
    crew_operators: Annotated[int, Field(strict=True, ge=1, le=1000)]


class ProcessingTime(Record):
    product_id: Id
    cell_id: Id
    minutes_per_unit: Annotated[int, Field(strict=True, ge=1, le=1440)]


class Shift(Record):
    id: Id
    index: Annotated[int, Field(strict=True, ge=1, le=20)]
    duration_minutes: Annotated[int, Field(strict=True, ge=1, le=1440)]
    available_operators: Annotated[int, Field(strict=True, ge=0, le=1000)]


class Capacity(Record):
    cell_id: Id
    shift_id: Id
    available_machine_minutes: Annotated[int, Field(strict=True, ge=0, le=1440)]


class Demand(Record):
    product_id: Id
    shift_id: Id
    due_units: Qty


class Scenario(Record):
    schema_version: Annotated[int, Field(strict=True, ge=1, le=1)]
    name: Annotated[str, StringConstraints(min_length=1, max_length=160)]
    data_origin: Literal["synthetic"]
    products: Annotated[list[Product], Field(min_length=1, max_length=8)]
    cells: Annotated[list[Cell], Field(min_length=1, max_length=6)]
    processing_times: Annotated[list[ProcessingTime], Field(max_length=48)]
    shifts: Annotated[list[Shift], Field(min_length=1, max_length=20)]
    capacity: Annotated[list[Capacity], Field(min_length=1, max_length=120)]
    demand: Annotated[list[Demand], Field(min_length=1, max_length=160)]

    @model_validator(mode="after")
    def check_references(self):
        def unique(values, description):
            if len(values) != len(set(values)):
                raise ValueError(f"Duplicate {description}")
            return set(values)

        p = unique([r.id for r in self.products], "product ID")
        c = unique([r.id for r in self.cells], "cell ID")
        t = unique([r.id for r in self.shifts], "shift ID")
        indices = unique([r.index for r in self.shifts], "shift index")
        if indices != set(range(1, len(t) + 1)):
            raise ValueError("Shift indices must be contiguous, starting at 1")
        pairs = unique([(r.product_id, r.cell_id) for r in self.processing_times], "processing pair")
        if not pairs <= {(a, b) for a in p for b in c}:
            raise ValueError("Processing times reference an unknown product or cell")
        capacity_keys = unique([(r.cell_id, r.shift_id) for r in self.capacity], "capacity pair")
        if capacity_keys != {(a, b) for a in c for b in t}:
            raise ValueError("Capacity must contain exactly one row per cell and shift")
        demand_keys = unique([(r.product_id, r.shift_id) for r in self.demand], "demand pair")
        if demand_keys != {(a, b) for a in p for b in t}:
            raise ValueError("Demand must contain exactly one row per product and shift")
        durations = {r.id: r.duration_minutes for r in self.shifts}
        if any(r.available_machine_minutes > durations[r.shift_id] for r in self.capacity):
            raise ValueError("Available machine minutes exceed shift duration")
        return self

    @property
    def ordered_shifts(self):
        return sorted(self.shifts, key=lambda r: r.index)


class Production(Record):
    product_id: Id
    cell_id: Id
    shift_id: Id
    units: Count


class Activity(Record):
    cell_id: Id
    shift_id: Id
    active: Bit


class Stock(Record):
    product_id: Id
    shift_id: Id
    inventory_units: Count
    backlog_units: Count


class CellUsage(Record):
    cell_id: Id
    shift_id: Id
    used_minutes: Count
    available_minutes: Count
    utilization: float | None


class Staffing(Record):
    shift_id: Id
    reserved_operators: Count
    available_operators: Count
    reservation_share: float | None


class Metrics(Record):
    backlog_unit_shifts: Count
    final_backlog_units: Count
    active_cell_shifts: Count
    inventory_unit_shifts: Count
    produced_units: Count
    machine_minutes_used: Count
    machine_minutes_available: Count
    capacity_utilization: float | None
    cell_usage: list[CellUsage]
    staffing: list[Staffing]


class Solution(Record):
    objective: Count
    production: list[Production]
    activity: list[Activity]
    stock: list[Stock]
    metrics: Metrics


class Validation(Record):
    valid: bool
    errors: list[str]


class SolverInfo(Record):
    version: str
    termination: str
    termination_code: int
    raw_objective: float | None
    objective_bound: float | None
    relative_gap: float | None
    solve_runtime_seconds: float


Algorithm = Literal["gurobi", "greedy"]
Status = Literal["optimal", "feasible", "heuristic_feasible", "no_solution",
                 "solver_unavailable", "solver_error", "invalid_result"]


class Result(Record):
    format_version: Literal[1] = 1
    input: Scenario
    algorithm: Algorithm
    status: Status
    settings: dict[str, int | float]
    solver: SolverInfo | None = None
    solution: Solution | None = None
    validation: Validation | None = None
    error: str | None = None


class SolveRequest(Record):
    scenario: Scenario
    algorithm: Algorithm = "gurobi"
    solver_time_limit_seconds: Annotated[int, Field(strict=True, ge=1, le=60)] = 10
