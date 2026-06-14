# GridMind

**Adaptive, Carbon-Aware Distributed Workstation Scheduling System.**

GridMind turns everyday laptops or workstations on a shared Wi-Fi network into a free, intelligent mini-supercomputer that **only runs heavy tasks when the power grid is clean and no one is using the machine.**

---

## 🌟 Key Features

| Feature | Detail |
|---|---|
| **Observer AI (RandomForest)** | Supervised `RandomForestClassifier` (7 features) classifies idle / active-user / busy-hardware at **99.2% held-out accuracy** (80/20 stratified split) + temporal smoothing (majority vote over a configurable window, default 6) — never interrupts a human. Heuristic fallback if no model is present. |
| **Carbon-Aware Dispatching** | Optimizes on **marginal emissions (WattTime CO₂ MOER)** — the CO₂ of the *next* MWh, the signal that actually changes when you shift load — deferring tasks out of dirty-grid windows. An ARIMA fit powers the explainable reasoning and the 2-hour grid outlook. |
| **Deep RL Dispatcher** | Dueling Double DQN (10-feature state → defer / dispatch) trained on real CAISO carbon data; loaded as a native PyTorch `.pt` state_dict on CPU, inference **<10ms**. Two transparent safety guardrails (urgent → run now; clean grid → dispatch). |
| **Remote Task Execution** | Submit a shell script, a single `.py` file (dashboard upload), or a ZIP workspace → runs on a safe idle node → **stdout streams back live**. Urgent tasks run immediately; deferrable ones wait for a clean grid. |
| **Battery & Thermal Protection** | Nodes report battery %, on-battery state, and CPU temperature; the dispatcher skips nodes that are on battery, **<20%**, or **>85°C**, surfaced as "⛔ Protected". |
| **Fault-Tolerant Re-Dispatch** | A node disconnecting or going unreachable mid-task auto-re-queues the task (≤3 retries) and re-dispatches it to another node; once retries are exhausted it reports an honest failure. |
| **Data-Parallel Job Splitting** | One job → N chunks (via `GRIDMIND_CHUNK_INDEX` / `GRIDMIND_CHUNK_COUNT`) fanned out one-per-free-node → run concurrently → measured speedup shown (only when ≥2 nodes share the work). |
| **Honest Results** | Real statuses and exit codes (no forced "completed"); cancel sends an `AbortTask` that actually kills the remote subprocess. |
| **Measured Carbon Proof** | Per completed task, emissions at submit-time (naive run-now baseline) vs run-time (GridMind) using a ~50W estimate; dashboard shows gCO₂ saved, % reduction, and tangible units (phone charges, metres not driven). |
| **Active-User Veto** | Human input → node classified `active_user` → excluded from dispatch until idle again. |
| **Live Dashboard** | Next.js 16 / React 19 + WebSocket — rolling Recharts carbon chart, dispatcher action log, task submission/upload UI, node health cards, and Observer metadata (held-out accuracy + confusion matrix). |
| **Low Footprint** | Node agents use **<2% CPU** via `psutil` + `pynput` daemon threads |
| **Resilient Nodes** | Exponential-backoff reconnection; nodes auto-recover if master server restarts |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Node Agents (worker laptops)                      │
│  agent.py  → psutil + pynput telemetry every 5s (out :50051)│
│  executor.py → receives + runs tasks (inbound :50052)       │
│  Reports battery % / on-battery / CPU-temp · streams stdout │
│  Active-user veto · burst-input abort · AbortTask kills proc│
└───────────────┬─────────────────────────────────▲───────────┘
   gRPC telemetry │ (port 50051)         dispatch tasks │ (port 50052)
┌───────────────▼─────────────────────────────────┴───────────┐
│  LAYER 2: Central Intelligence Server (FastAPI + aiosqlite) │
│  Observer AI  → RandomForest: "Is this laptop safe?"        │
│  Dispatcher AI→ Dueling Double DQN (.pt, CPU): defer/dispatch│
│  Dispatcher loop every 2s · battery/thermal protection      │
│  Fault-tolerant re-dispatch (≤3 retries) · job splitting    │
│  Carbon → WattTime MOER replay (8929 CAISO rows) + ARIMA    │
│  Task Queue   → hand-rolled async SQLite (WAL) REST API     │
│  WebSocket    → pushes live state to dashboard              │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket (port 8000)
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 3: Next.js 16 Dashboard (port 3005)                  │
│  Live Recharts carbon chart · Dispatcher log · Task submit  │
│  Node health/protection cards · Measured carbon-saved proof │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

```bash
# 1. Clone and set up
git clone <repo-url>
cd Mini_Project
pip install -r requirements.txt

# 2. Train Observer AI (one-time, if models/ not present)
python gridmind_server/app/ml/observer_trainer.py

# 3. Train Dispatcher AI (one-time)
python gridmind_server/app/ml/dispatcher_trainer.py

# 4. Start everything (master laptop)
python start_gridmind.py

# 5. Connect teammate laptops (worker nodes)
python gridmind_node/agent.py --server <MASTER_IP>:50051 --node-id <your-name>
```

Open `http://localhost:3005` — the dashboard shows live node health, carbon intensity, and dispatcher decisions.

> **Firewall note (the #1 thing that breaks remote execution):** the master needs inbound **:50051** (telemetry in), and each **worker** needs inbound **:50052** so the master can dispatch tasks to it. Keep workers plugged in (nodes on battery are skipped for protection).

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Server liveness probe |
| `GET` | `/api/v1/nodes` | All connected nodes + current state |
| `GET` | `/api/v1/nodes/safe` | Idle nodes safe for dispatch |
| `GET` | `/api/v1/nodes/{id}` | Single node telemetry |
| `POST` | `/api/v1/tasks` | Submit a compute task |
| `POST` | `/api/v1/tasks/with-artifact` | Submit a task with a ZIP workspace |
| `GET` | `/api/v1/tasks` | List all tasks (filter by status) |
| `GET` | `/api/v1/tasks/{id}` | Get single task |
| `DELETE` | `/api/v1/tasks/{id}` | Cancel a pending, dispatched, or running task |
| `GET` | `/api/v1/tasks/{id}/artifact` | Download a task's input workspace ZIP (node) |
| `POST` | `/api/v1/tasks/{id}/artifact/output` | Upload a task's output workspace ZIP (node) |
| `GET` | `/api/v1/tasks/{id}/artifact/output` | Download a task's output workspace ZIP |
| `GET` | `/api/v1/observer/metadata` | Observer AI held-out accuracy + confusion matrix |
| `WS` | `/ws/telemetry` | Live push to dashboard |

Full Swagger docs: `http://localhost:8000/docs`

---

## 🎯 Success Metrics

| Metric | Target | Status |
|---|---|---|
| Carbon reduction vs. naive run-now baseline | ≥ 20% | ✅ Measured per task on marginal emissions (8929 real WattTime CAISO MOER rows) |
| Tasks completed without user interruption | ≥ 90% | ✅ Validated (active-user veto + burst-input abort) |
| Observer AI accuracy | ≥ 85% | ✅ 99.2% (held-out test set, not training data) |
| Dispatcher AI decision time | < 10ms | ✅ ~4ms (PyTorch `.pt` on CPU) |
| Node agent CPU footprint | < 2% | ✅ Confirmed |
| In-flight task recovery on node loss | re-dispatch | ✅ Auto re-queue, ≤3 retries, then honest failure |
| Battery / thermal node protection | skip unsafe | ✅ On-battery, <20%, or >85°C → ⛔ Protected |

---

## 📖 Documentation

| File | Purpose |
|---|---|
| [`TEAM_UPDATE.md`](./TEAM_UPDATE.md) | Full progress tracker + setup instructions |
| [`Project_Review_Prep.md`](./Project_Review_Prep.md) | Q&A defence guide (SE, ML, Systems teachers) |
| [`Technical_Implementation_Simple.md`](./Technical_Implementation_Simple.md) | Plain-English explanation for non-technical audience |
| [`GridMind_Team_Onboarding.md`](./GridMind_Team_Onboarding.md) | Architecture deep-dive + research rationale |
| [`docs/setup_teammates.md`](./docs/setup_teammates.md) | Step-by-step teammate onboarding |

---

*Built with Python 3.12 · FastAPI · async gRPC · aiosqlite (WAL) · Scikit-learn · PyTorch · statsmodels (ARIMA) · Next.js 16 / React 19 · Recharts*
