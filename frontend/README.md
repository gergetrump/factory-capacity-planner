# Local React interface

Requires Node.js 20.19+ or 22.12+ (verified with Node.js 24.21.0).

```bash
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Vite forwards `/api` to the local API at
http://127.0.0.1:8011. Start the Python API separately using the project README.
The app uses local system fonts and makes no external asset requests.

```bash
npm run typecheck
npm run build
```

Run the original scenario to save a reference. Select a cell and first/last
shift, apply the outage, then run again. Applying an outage always begins with
the original example and replaces the previous outage window. Reset restores
original capacity and retains both saved result collections. Changing the
example clears those collections.

Each comparison captures one input and calls Gurobi followed by greedy. Method
failures remain visible separately. The client has a 45-second timeout for each
request, which does not cancel backend work. The Gurobi optimization limit is
10 seconds; it is not an end-to-end timeout. Input editing and duplicate
comparisons are disabled while the sequential requests are running.

The scenario cards compare original versus outage outcomes with each method
kept separately. Method tabs inspect a result and the method difference uses
only matching input snapshots. Edited inputs mark the corresponding saved run
stale. Download exports the selected method's complete backend result and its
exact solved input, including unsuccessful solver outcomes when returned.

All examples are synthetic. Backlog unit-shifts are the only objective.
Inventory and active cell-shifts are descriptive and have no tie-breaking
priority. Whole-shift staffing reservation is not measured worker utilization.
