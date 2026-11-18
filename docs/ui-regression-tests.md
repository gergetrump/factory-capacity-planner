# UI regression tests

Three Playwright tests exercise the real React application in Chromium, including actual JSON downloads. HTTP responses are intercepted and replayed from checked saved results. No FastAPI server, Python environment, Gurobi installation or solver license is needed for this suite.

## Run

From the repository root:

```bash
cd frontend
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
npm run build
```

The browser install downloads Chromium and installs its operating-system dependencies; installing system packages can require administrator access. Once dependencies and the browser are installed, only `npm run test:e2e` is needed to rerun the tests. Playwright starts and stops its own loopback Vite server on port **4173**; keep that port free. It does not reuse a server that happens to be running there.

The GitHub Actions frontend job now builds the application, installs Chromium and runs these tests. Failed runs preserve screenshots and traces in `frontend/test-results/`, and CI is configured to upload them. This configuration has been checked locally; no remote CI execution is claimed.

## What is protected

| Test | Behavior and evidence |
| --- | --- |
| Saved snapshots, stale state and references | Run original capacity, then a C3 outage in shifts 5–6. Both methods must receive identical captured inputs. Selecting an end shift of 10 alone leaves the applied input unchanged; applying that edit makes the saved outage result stale. The rendered current-input JSON must show outage shifts 5–10, while actual downloaded Gurobi and greedy results must still equal the complete saved 5–6 results. Reset restores the original reference; the saved outage reference remains available. Editing/resetting must not silently solve again. |
| Solver unavailable | Replay a Gurobi `503` response with `solver_unavailable` and no solution. Show its diagnostic without an accepted plan or a false method comparison, then show/download the separately successful greedy plan. The unavailable result's input and null solution must also survive download. |
| Wrong response input | Replay a Gurobi result whose input differs from the request. Reject it rather than compare/display/export it as the requested plan; preserve the successful greedy outcome. |

The replay loads the [base and short-outage result files](results) directly. The Python outage helper appends an outage suffix to the scenario name; the browser preserves the base name. Tests normalize **only that display name**. A response is served only when the requested method and complete scenario equal a known fixture. The tests do not copy arbitrary request inputs into successful fixtures or generate fresh solver answers.

The main workflow compares the full downloaded JSON with its expected saved result, rather than checking only a headline metric or filename. This protects quantities, input, status and diagnostic metadata together. Selectors use accessible roles/names and visible content, avoiding React internals and screenshot snapshots.

## Verification on 18 November 2026

- All **three Chromium tests passed**, and the production TypeScript/Vite build passed.
- Two temporary deliberate regressions were detected: disabling the stale warning failed the visibility assertion; expanding only an exported outage's input through shift 10 failed the full-result equality assertion. Both application source files were restored byte-for-byte before the final passing run. These mutations are verification experiments, not permanent test helpers or application features.
- This Homeserver initially lacked Chromium's global `libatk` dependency. The local passing run used already available extracted browser libraries with the environment variable below. This path is machine-specific and may disappear; normal setup should use Playwright's dependency installation above. No such path is embedded in the project configuration.

```bash
# Homeserver workaround used for this verification, from frontend/:
LD_LIBRARY_PATH=/tmp/ayan-browser-libs-xsaqlmt7/root/usr/lib/x86_64-linux-gnu npm run test:e2e
```

## Limits

These are automated **frontend integration/regression tests with replayed HTTP responses**, not live end-to-end solver tests. They do not validate current FastAPI behavior, a Gurobi solve, HTTP timeout/cancellation, arbitrary scenario generation, other browsers, accessibility or load performance. Existing Python/API tests, independent result checks and documented live-browser evidence cover different boundaries. The regression suite supplements them rather than replacing them.
