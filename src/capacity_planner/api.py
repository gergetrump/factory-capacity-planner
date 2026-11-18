"""Local, synchronous adapter. The lock is intentionally limited to one API process."""
from threading import Lock

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .examples import EXAMPLE_IDS, load_example
from .model import solve
from .schema import Result, SolveRequest

app = FastAPI(title="Factory Capacity Planner", version="0.1.0", description="Synthetic aggregate allocation; one backlog objective")
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
solve_lock = Lock()


@app.get("/api/examples")
def examples():
    return [{"id": name, "scenario": load_example(name).model_dump()} for name in EXAMPLE_IDS]


@app.post("/api/solve", response_model=Result)
def solve_request(request: SolveRequest):
    if not solve_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A planning request is still running in this API process; retry when it finishes.")
    try:
        result = solve(request.scenario, request.algorithm, request.solver_time_limit_seconds)
        status_code = {"solver_unavailable": 503, "solver_error": 500, "invalid_result": 500}.get(result.status, 200)
        return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))
    finally:
        solve_lock.release()
