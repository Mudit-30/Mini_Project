# GridMind Project File Explainer

This document provides a comprehensive overview of the files and directories in the GridMind project, explaining their purpose and function within the system architecture.

GridMind is a **carbon-aware distributed scheduler**: an **Observer AI** (scikit-learn RandomForestClassifier, supervised, 99.2% held-out accuracy + temporal smoothing) decides when a workstation is truly idle, and a **Dispatcher AI** (PyTorch Dueling Double DQN, loaded as a native `.pt` state_dict on CPU) decides when and where to run queued work to minimize **marginal** carbon emissions (WattTime CO₂ MOER, 8,929 CAISO rows replayed, with an ARIMA forecast fit at startup).

## 🚀 Root Directory

| File / Directory | Description |
| :--- | :--- |
| `start_gridmind.py` | The main production orchestrator. Launches the FastAPI backend, Next.js frontend (production mode), and a local node agent in a single synchronized process. |
| `simulate_nodes.py` | A script used to mock multiple node agents simultaneously for testing the scalability and data handling of the central server. |
| `requirements.txt` | Lists all Python dependencies required for the project (FastAPI, aiosqlite, gRPC, scikit-learn, PyTorch, statsmodels, etc.). |
| `README.md` | Provides a high-level project overview, installation instructions, and key features. |
| `GridMind_Team_Onboarding.md` | Deep-dive documentation for new team members covering the technical blueprint and research gaps. |
| `TEAM_UPDATE.md` | Tracking document for team progress, current implementation status, and future roadmap. |
| `Technical_Implementation_Simple.md` | A simplified guide designed for project defense, explaining core concepts without heavy technical jargon. |
| `Panel_Discussion_Prep.md` | Preparation notes for project presentations and panel discussions. |
| `gridmind.db` | The primary SQLite database storing telemetry history, node information, and system states. |

---

## 🛰️ Node Agents (`gridmind_node/`)

The software that runs on individual workstations.

| File | Description |
| :--- | :--- |
| `agent.py` | The core agent logic. Monitors keyboard/mouse activity, CPU/memory usage, and system state. Sends telemetry to the master server via gRPC. |
| `executor.py` | Runs an assigned task in an isolated subprocess: writes the script to a temp file (or extracts a ZIP workspace), streams stdout line-by-line back to the server, and enforces a wall-clock timeout. Supports emergency abort, injects `GRIDMIND_CHUNK_INDEX`/`GRIDMIND_CHUNK_COUNT` for data-parallel jobs, and packages/uploads output artifacts. |
| `telemetry_pb2.py` | Generated Python code for telemetry message serialization. |
| `telemetry_pb2_grpc.py` | Generated Python code for the gRPC telemetry service interface. |

---

## 🧠 Central Intelligence Server (`gridmind_server/`)

The heart of the system, managing nodes, data, and AI decisions.

### `app/` (Core Logic)

| File / Subdir | Description |
| :--- | :--- |
| `main.py` | The FastAPI entry point. Wires up routes and uses the lifespan handler to start/stop background services (DB init, ARIMA fit, dispatcher loop). |
| `grpc_server.py` | Implements the gRPC telemetry receiver that nodes connect to for submitting telemetry and registering themselves. |
| `registry.py` | In-memory node state: tracks registration, heartbeats, status, and live telemetry per node. |
| `websockets.py` | Broadcasts real-time state (telemetry, dispatch decisions, carbon ledger) to the frontend dashboard over WebSockets. |
| `task_dispatcher.py` | Opens a gRPC channel to a node's `:50052`, sends the `TaskPayload`, and streams `TaskResult` events back to the dashboard. Persists the final status, and on node failure re-queues the task (fault tolerance, ≤3 retries). Cancellation is delivered as an `AbortTask` RPC. |
| `core/config.py` | Hardcoded and environment-based configuration settings for the server. |
| `db/database.py` | Hand-rolled async data layer over aiosqlite (raw SQL, **not** SQLAlchemy): schema creation + a lightweight query shim for telemetry, tasks, and dispatch logs. |

### `app/carbon/` (Carbon Accounting & Forecasting)

| File | Description |
| :--- | :--- |
| `ledger.py` | The carbon-savings ledger (the "carbon proof"). For each completed task it compares submit-time (naive baseline) emissions vs. run-time emissions using the real grid intensity at each moment, yielding the measured gCO₂ saved by deferring work into cleaner grid windows. |
| `forecaster.py` | An ARIMA(2,1,2) model (statsmodels) fit on historical WattTime MOER data; produces the forward carbon-intensity forecast that powers the explainable-decision reasoning. |

### `app/routes/` (REST API)

| File | Description |
| :--- | :--- |
| `tasks.py` | Task queue REST API: submit a script, submit-with-artifact (ZIP workspace), list/get tasks, cancel (→ `AbortTask`), and artifact upload/download. |
| `jobs.py` | Data-parallel jobs API: `POST /api/v1/jobs` splits one script into N chunk-tasks; `GET` endpoints report per-chunk status and the measured speedup. |
| `nodes.py` | REST endpoints exposing node registry state to the dashboard. |

### `app/ml/` (AI & Machine Learning)

| File | Description |
| :--- | :--- |
| `observer_inference.py` | Real-time inference using the supervised "Observer" RandomForest model (plus temporal smoothing) to decide whether a workstation is truly idle. |
| `observer_trainer.py` | Trains the supervised RandomForest classifier (**not** DBSCAN/K-Means) with an 80/20 stratified train/test split; saves the model, scaler, and held-out metrics. |
| `dispatcher_inference.py` | PyTorch inference engine for the Dueling Double DQN Dispatcher AI. Loads the native `.pt` `state_dict` on CPU (no ONNX). |
| `dispatcher_trainer.py` | Training script for the Deep Reinforcement Learning (Dueling Double DQN) Dispatcher agent. |

### `app/jobs/` (Background Tasks)

| File | Description |
| :--- | :--- |
| `dispatcher_loop.py` | The 2-second decision loop. Counts the queue, snapshots node state (including battery/thermal), looks up the marginal carbon intensity, runs the DQN, fans tasks out to free idle nodes, and broadcasts the explainable decision + carbon ledger. |
| `retrain.py` | An **optional** Observer retrain job (OFF by default; a self-supervised concern reserved for future iterations). |

---

## 📊 Frontend Dashboard (`frontend/`)

A Next.js-powered visual interface.

| File / Directory | Description |
| :--- | :--- |
| `src/app/page.tsx` | The main dashboard page displaying real-time cluster health, node stats, and carbon footprint visualization. |
| `src/app/layout.tsx` | The root layout providing navigation, themes, and global components. |
| `src/app/globals.css` | Global styling including TailwindCSS directives and custom glassmorphism effects. |
| `src/hooks/useGridMindSocket.ts` | React hook that opens the WebSocket to the server and exposes the live cluster/carbon state stream to the dashboard. |
| `src/lib/api.ts` | Thin REST client wrappers for the tasks/jobs/nodes endpoints. |
| `src/lib/types.ts` | Shared TypeScript types for nodes, tasks, jobs, and carbon/decision payloads. |
| `src/lib/utils.ts` | Small UI helper utilities (e.g., class-name merging). |

### `src/components/dashboard/` (Dashboard Components)

| Component | Description |
| :--- | :--- |
| `NodeCard.tsx` | Per-node card showing live status, telemetry, and idle/busy state. |
| `CarbonChart.tsx` | Time-series chart of grid carbon intensity. |
| `CarbonProof.tsx` | Surfaces the measured gCO₂ saved (from the carbon ledger) vs. the naive baseline. |
| `DispatchLog.tsx` | Live feed of dispatch decisions and task lifecycle events. |
| `TaskPanel.tsx` | UI for submitting, listing, and cancelling single-node tasks. |
| `JobPanel.tsx` | UI for submitting and tracking data-parallel jobs (per-chunk status + speedup). |
| `ConfusionMatrix.tsx` | Visualizes the Observer model's held-out confusion matrix / accuracy. |
| `AIDecisionStrip.tsx` | Compact strip rendering the latest explainable AI decision and its reasoning. |
| `CarbonGauge.tsx` | Gauge displaying the current marginal carbon intensity. |
| `CarbonForecastStrip.tsx` | Strip showing the ARIMA carbon-intensity forecast. |
| `SystemLoadTrends.tsx` | Cluster-wide load / utilization trend visualization. |

---

## 🛠️ Ancillary Directories

| Directory | Description |
| :--- | :--- |
| `protos/` | Contains the `.proto` definitions for the data schema used in gRPC communication between nodes and the server. |
| `demo_tasks/` | Vetted demo scripts that do **real** computation (pure-stdlib, so they run on any node): `00_which_node.py` (proves which laptop ran a task), `parallel_primes.py` (data-parallel demo), `01_calculate_pi.py` (real Monte Carlo Pi), `02_ml_training.py` (a real 1-hidden-layer neural net trained from scratch with backprop — loss falls, ~95% test accuracy), `03_financial_backtest.py` (a real SMA-crossover backtest benchmarked vs buy-and-hold), and `submit_tasks.py` (helper to submit them). |
| `scripts/` | Helper scripts for demonstrations (e.g., `demonstrate_observer.py`) and development utilities. |
| `data/` | Storage for training datasets, including the real WattTime CAISO grid history (8,929 rows of marginal-emissions MOER data). |
| `models/` | Persistent storage for serialized AI models: `observer/rf_model.joblib` + `observer/scaler.joblib` + `observer/model_metadata.json` (held-out accuracy + confusion matrix) for the Observer, and `dispatcher_dqn.pt` (PyTorch DQN state_dict) for the Dispatcher. |
| `tests/` | Unit and integration tests, particularly for the machine learning components and core server logic. |
| `docs/` | Additional setup guides and architectural diagrams (e.g., `setup_teammates.md`). |
