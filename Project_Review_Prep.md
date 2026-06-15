# GridMind: Comprehensive Project Review Document

This document serves as the ultimate preparation guide for the GridMind project review. It breaks down the entire project architecture, explains every key file and its code logic, and anticipates the types of questions the three reviewing teachers (covering Software Engineering, Machine Learning, and Systems/Networking) might ask.

---

## 1. Project Overview & Core Value Proposition

**Project Name:** GridMind (Adaptive, Carbon-Aware Distributed Workstation Scheduling System)

**What it does:** 
GridMind harvests wasted computing power from idle laptops on a local network to compute heavy tasks (a "mini-supercomputer"). It ensures that tasks only run when the local user is away (detected via ML) and when the local power grid is using green energy (wind/solar vs. coal/gas).

**The 3 Core Pillars:**
1. **Uninterrupted UX:** The Observer AI is a supervised classifier scoring **99.2% accuracy on a held-out 20% test set** for detecting whether a laptop is idle. If the user shows a burst of deliberate activity (keys/clicks/scrolls), the running task is aborted — and a returning user is detected fast enough to vacate the machine well before they notice.
2. **Carbon-Aware:** Replays a 8,929-row real historical WattTime CAISO North dataset (marginal CO2 emissions) to defer non-essential computing until the local electricity grid is utilizing cleaner energy.
3. **Low Footprint:** The background trackers use <2% CPU and communicate via ultra-fast gRPC.
4. **Intelligent Dispatching:** Uses a Dueling Double DQN Reinforcement Learning agent to balance task throughput with carbon efficiency. 

---

## 2. Project Objectives & Implementation Roadmap

**Core Objectives:**
*   **Objective 1:** Design a lightweight central server that orchestrates computing tasks across laptops on a local network without relying on any expensive cloud infrastructure (like AWS).
*   **Objective 2:** Build a small, invisible tracking agent that sits hidden on each worker laptop to quietly monitor the CPU, memory, and physical user input, streaming that data back to the central server.
*   **Objective 3:** Build a Supervised Machine Learning model (Observer AI) that learns from labeled telemetry to distinguish when a user is truly away from the computer versus when they are actively working (vs. when the machine is busy with background hardware load).
*   **Objective 4:** Train a Deep Reinforcement Learning agent (Dispatcher AI) to look at all available laptops, check the current carbon intensity of the city's power grid, and decide exactly when and where to send heavy computing tasks.
*   **Objective 5:** Build a live real-time dashboard using Next.js to visually prove the system works, showing live charts of our laptops, running tasks, and carbon savings in real-time.

**Implementation Phases (How we are moving forward):**
*   **Phase 1 (Foundation):** Set up the central FastAPI server, the SQLite database, the basic worker node agents, and hook up the system to the WattTime API for carbon data.
*   **Phase 2 (Observer AI):** Implement fast gRPC communication, train a supervised `RandomForestClassifier` on labeled telemetry for state detection, add temporal smoothing + a heuristic fallback, and scaffold an *opt-in* auto-retrain job (deliberately disabled by default — see Q&A).
*   **Phase 3 (Deep RL Dispatcher):** Build the simulated environment, train the RL model extensively with PyTorch (Dueling Double DQN) using historical carbon data, and serve it as a native PyTorch `.pt` state_dict on CPU for live, lightning-fast (<10ms) decision-making on the master server.
*   **Phase 4 (Validation):** Construct the Next.js visual dashboard, connect the WebSockets, and deploy the full system across real Wi-Fi networks for live 24-hour validation.

---

## 3. Technical Stack

*   **Language:** Python 3.12, TypeScript
*   **Backend Server:** FastAPI (async gRPC servicer via `grpc.aio`)
*   **Communication:** gRPC (Telemetry streaming + task RunTask/AbortTask), WebSockets (Live dashboard updates), REST API
*   **Database:** SQLite configured in Write-Ahead Logging (WAL) mode for fast concurrent writes — accessed through a hand-rolled async **aiosqlite** raw-SQL layer (a tiny ORM-flavoured wrapper we wrote ourselves; **not** SQLAlchemy — alembic exists only as unused scaffolding).
*   **Observer ML:** Scikit-Learn (`RandomForestClassifier`) for Supervised state classification (idle / active_user / busy_hardware) using labeled telemetry ground truth, plus temporal smoothing and a heuristic fallback.
*   **Dispatcher ML:** PyTorch Dueling Double DQN, served from a native `.pt` state_dict on CPU (<10ms inference).
*   **Carbon:** Real WattTime CAISO North marginal-emissions (CO2_MOER) dataset replayed at a configurable stride; an ARIMA model is fit at startup to power explainable forecasting.
*   **Frontend Dashboard:** Next.js (React)

---

## 3. Directory & File Breakdown

### A. The Master Server (`gridmind_server/`)
This is the brain of the operation, holding the task queue, processing telemetry, and checking the power grid.

*   `app/main.py`: The FastAPI entry point. 
    *   **Code Logic:** Handles the server lifecycle (`lifespan` manager). It ensures the SQLite tables/indexes exist, loads the pre-trained Observer AI model into memory, loads the Dispatcher DQN, starts the asynchronous gRPC telemetry server, and launches the 2-second background dispatcher loop. The Observer auto-retrain `APScheduler` job is wired up but **only registered when `GRIDMIND_ENABLE_RETRAIN=1`** — it is OFF by default (see Q&A on why). It also exposes REST routes (`/api/v1/...`), the `/api/v1/observer/metadata` endpoint, and a WebSocket route (`/ws/telemetry`).
*   `app/grpc_server.py`: The high-speed data receiver.
    *   **Code Logic:** Inherits from the compiled gRPC protobuf classes. Implements `StreamTelemetry`, an async generator that constantly receives hardware metrics (CPU, RAM, mouse events) from worker nodes. For every single packet, it:
        1. Asks the ML model to predict the node's state.
        2. Updates the fast in-memory Node Registry.
        3. Fires off an async background task to persist the data to SQLite.
*   `app/db/database.py`: The SQLite connector.
    *   **Code Logic:** A **hand-rolled async raw-SQL layer built on `aiosqlite`** — there is no SQLAlchemy. We wrote a small set of lightweight `MockSelect` / `MockUpdate` / `AsyncSession` helpers that read like an ORM but compile down to plain parameterised SQL strings. `create_tables()` applies `PRAGMA journal_mode=WAL` (plus `synchronous=NORMAL` and a page-cache bump) to prevent database locks when multiple laptops stream data simultaneously, and defines the `telemetry_records`, `tasks`, and `dispatch_log` tables with hot-path indexes.
*   `app/ml/observer_trainer.py`: The Supervised ML Pipeline.
    *   **Code Logic:** Run offline or on a schedule. It loads raw CSV telemetry mapped to ground-truth state labels. It scales features using `StandardScaler` and trains a **Random Forest Classifier**. This enables the model to map complex, non-linear relationships between hardware spikes and physical human inputs. It saves the resulting `rf_model.joblib`.
*   `app/ml/observer_inference.py`: The ML Runtime wrapper.
    *   **Code Logic:** Loaded once by `main.py`. Provides a rapid `.predict()` method that takes a telemetry dictionary, scales it, passes it to the loaded Random Forest model, and uses `predict_proba` for confidence. It then applies **temporal smoothing**: a per-node rolling window (default 6 frames, configurable via `GRIDMIND_SMOOTHING_WINDOW`) returns the majority-vote label so transient spikes can't flip the state, and the reported confidence is the fraction of the window that agrees. If the sklearn artifacts can't be loaded (or `GRIDMIND_LOAD_ML != 1`), it transparently falls back to a high-fidelity rule-based heuristic so the system never hard-fails.
*   `app/registry.py`: The In-Memory State store.
    *   **Code Logic:** A thread-safe dictionary (protected by `threading.Lock()`). The gRPC server writes to it thousands of times a second; the REST API and WebSockets read from it to serve the frontend dashboard without hitting the hard drive database every time.
*   `app/websockets.py`: The Broadcast manager.
    *   **Code Logic:** Keeps a list of active Next.js dashboard WebSocket connections. Provides a `broadcast()` method used by the gRPC server to push live data directly to the web dashboard.

### B. The Worker Agent (`gridmind_node/`)
This runs on the client "worker" laptops.

*   `agent.py`: The Telemetry Collector + Task Server.
    *   **Code Logic:** Uses `psutil` to check CPU/RAM/Network (and battery/thermal state where available). It uses non-blocking daemon threads via `pynput` to listen for physical mouse and keyboard input. It packages this into a protobuf message and streams it continuously to the server (outbound :50051), wrapped in an exponential-backoff reconnect loop. The same agent also *hosts* an inbound gRPC task server (:50052) exposing `RunTask` (streams live stdout back) and `AbortTask` (kills the remote subprocess). It runs the **burst-detection abort** logic: deliberate input events (keys/clicks/scrolls) are counted, and a burst over the threshold within the window aborts the running task.
*   `executor.py`: The Sandboxed Task Runner.
    *   **Code Logic:** Runs each task's script in an isolated subprocess (no shell, for safety), streams stdout line-by-line under a wall-clock timeout, and drains stderr concurrently to avoid pipe deadlock. Supports ZIP **workspace artifacts** (download → extract into a temp dir → run → re-zip outputs → upload). Injects `GRIDMIND_CHUNK_INDEX`/`GRIDMIND_CHUNK_COUNT` so a data-parallel script processes only its slice. Reports **honest statuses** — `completed` only on exit code 0, otherwise `failed`/`aborted`/timeout (exit 124) — and `abort_task` actually force-kills the whole process tree.
*   `telemetry_pb2.py` / `telemetry_pb2_grpc.py`: 
    *   **Code Logic:** Auto-generated files created by compiling the `protos/telemetry.proto` buffer file. They handle the hard work of serializing/deserializing the data for network transport.

### C. The Visual Dashboard (`frontend/`)
*   `src/app/page.tsx`: The Next.js UI.
    *   **Code Logic:** Connects to the FastAPI `ws/telemetry` WebSocket. Listens for live updates and renders complex real-time charts showing exactly which laptops are computing, which are idle, and the current carbon savings.

---

## 4. Expected Review Questions & How to Answer Them

Depending on the specialty of the teacher reviewing you, expect questions in these three categories:

### 👨‍🏫 Teacher 1: Systems, Architecture & Networking Focus

**Q1: Why did you use gRPC for the node agents instead of standard REST APIs (HTTP/JSON)?**
*Answer:* REST APIs require setting up a separate HTTP connection for every single message, which adds massive overhead given we are sending telemetry every few seconds from multiple laptops. gRPC runs on HTTP/2, allowing us to hold a single, persistent bi-directional pipe open. It also uses Protocol Buffers (binary data) instead of JSON (text), making it dramatically smaller and faster to send over the network. 

**Q1b: Walk me through the network topology and the ports involved.**
*Answer:* Telemetry flows *out* from each worker to the master on **:50051** (the master's inbound gRPC telemetry server). Task control flows the other way: each worker *hosts* its own inbound gRPC server on **:50052** that the master calls to `RunTask` and `AbortTask`. The dashboard talks to the master over plain HTTP/WebSocket on :8000. Workers can run on battery (the guardrail only backs off below 30% or over 85°C). The REST/WS surface the master exposes is small and purpose-built: `/api/v1/tasks` (+ `/tasks/with-artifact` and the artifact upload/download routes), `/api/v1/jobs` (data-parallel jobs + measured speedup), `/api/v1/observer/metadata` (held-out accuracy + confusion matrix), `/api/v1/nodes`, and the `/ws/telemetry` WebSocket.

**Q2: SQLite is generally considered a "toy" database. Why use it for a high-frequency telemetry system? Why not PostgreSQL?**
*Answer:* Standard SQLite locks the entire database during a write, which would crash our system. However, we specifically enabled **Write-Ahead Logging (WAL)** PRAGMA mode. WAL allows simultaneous readers and a concurrent writer. Since this is an embedded mini-supercomputer meant to be run locally without complex infrastructure (like spinning up a separate Docker container for Postgres), SQLite in WAL mode gives us perfect persistence seamlessly.

**Q3: How do you handle concurrency in FastAPI? What happens when 10 nodes send data at the exact same millisecond?**
*Answer:* We rely heavily on Python's `asyncio`. Our gRPC servicer uses `grpc.aio`, meaning the network connections are non-blocking. When a telemetry packet arrives, we update an in-memory `NodeRegistry` (which uses a thread-safe `Lock`), calculate the ML in memory, and then dispatch the database saving step to an asynchronous background task (`asyncio.create_task`). The server never freezes to wait on a hard drive write.

**Q4: How does the worker agent interact closely with the underlying Operating System (OS)?**
*Answer:* The node agent uses `psutil` to tap directly into the OS kernel for CPU context switches, physical memory allocation, and raw network I/O metrics. More importantly, it uses `pynput` daemon threads to hook directly into the OS's low-level hardware interrupts for Human Interface Devices (HID). This allows us to detect physical keyboard and mouse events *globally* at an OS level, regardless of which local application is currently in focus.

**Q5: Explain the database bottlenecks you anticipated and how SQLite WAL solves them in detail.**
*Answer:* In a traditional standard SQLite deployment, if Node A is writing a telemetry packet, the entire database file is completely locked. If Node B tries to write at the exact same millisecond, it crashes with a `database is locked` error. We execute `PRAGMA journal_mode=WAL` (and `synchronous=NORMAL`) directly through our `aiosqlite` connection in `create_tables()` — we do not use SQLAlchemy; the DB layer is a small raw-SQL wrapper we wrote ourselves. In WAL mode the engine writes changes to a separate Write-Ahead Log (`gridmind.db-wal`) file instead of mutating the main file directly. This permits high-frequency concurrent writes from worker agents while allowing the dashboard to simultaneously perform asynchronous reads.

**Q5b: A worker laptop dies mid-task — does that task just vanish?**
*Answer:* No, it's fault-tolerant. Every task carries a `retry_count`. When a node disconnects (or a dispatch attempt fails to reach it), `requeue_node_tasks` flips any of its in-flight (`dispatched`/`running`) tasks back to `pending`, clears the assignment, and increments `retry_count` — so the dispatcher picks it up on the next cycle and sends it to a *different* idle node. This is capped at **3 retries**; once a task exceeds the cap it is marked `failed` with an honest "node disconnected and retry limit reached" message rather than being retried forever. The re-queue UPDATE is guarded by `status IN ('dispatched','running')` so the disconnect path and the dispatch-failure path are idempotent — whichever fires first wins and the other no-ops. Crucially, for a genuinely *remote* node we never silently fall back to running the task on the master (`127.0.0.1`) — that would mask a closed firewall — we fail honestly and re-queue.

**Q5c: Can a single big job actually run faster by using multiple laptops, and can you prove the speedup?**
*Answer:* Yes — that's our data-parallel job splitting. The `/api/v1/jobs` endpoint splits a job into N chunk-tasks that share a `parent_job_id`; each chunk runs the *same* script but receives `GRIDMIND_CHUNK_INDEX` / `GRIDMIND_CHUNK_COUNT` env vars so it processes only its slice of the data. The dispatcher loop fans out **one task per free idle node** per cycle (a node already running a task is skipped), so the chunks run concurrently across the cluster. The `GET /api/v1/jobs/{job_id}` endpoint reports a **measured** speedup: `serial_secs` (sum of chunk durations — what one node would take back-to-back) divided by `wall_secs` (actual elapsed from first dispatch to last completion). We only report the multiplier when **≥2 nodes actually shared the work** — on a single node the chunks run sequentially, so a "speedup" number there would be meaningless, and we deliberately suppress it rather than fake it.

### 👨‍🏫 Teacher 2: Machine Learning & AI Focus

**Q6: Tell me about your "Observer AI." Why use a Supervised Random Forest instead of just checking if CPU < 20%?**
*Answer:* CPU alone is a flawed metric. A user reading a long PDF has 2% CPU usage but is actively working; interrupting them is bad. A computer running a background virus scan has 90% CPU usage but no human is present. Instead of hardcoded rules, we train a **Random Forest Classifier** on labeled telemetry data (hardware + human HID inputs). Random Forests are highly capable of learning non-linear boundaries between these edge cases, ensuring we don't accidentally interrupt users.

**Q7: How does your ML pipeline output reliable confidence scores for the Dispatcher AI to use?**
*Answer:* When streaming real-time telemetry, the `ObserverInference` layer uses the Random Forest's `predict_proba` method to get the probability of the predicted class. To prevent rapid state-flipping from transient CPU spikes, we apply a sliding-window temporal majority vote (default 6 frames, configurable via `GRIDMIND_SMOOTHING_WINDOW`), and the confidence we report is the fraction of that window that agrees with the smoothed label. The dispatcher only treats a node as available when it is classified `idle` with confidence ≥ 0.50, so a node must be *consistently* idle across the window before it gets work.

**Q8: How do you handle complex tasks requiring many files rather than just simple commands?**
*Answer:* We implemented an Artifact Workspace system. Users can upload a ZIP workspace containing datasets and code scripts. The server saves this binary artifact to the database. When the Dispatcher AI finds an idle node, it streams the ZIP artifact to the worker, which automatically extracts it into an isolated temporary directory, executes the payload, streams the outputs back, and packages any generated files into an output artifact for download.

**Q12: Your Observer reports 99.2% accuracy. Where does that number come from, and isn't it suspiciously high?**
*Answer:* It is the accuracy on a **held-out 20% test set** from an 80/20 *stratified* train/test split — stored in `model_metadata.json` along with the full confusion matrix and a per-class classification report, and exposed live at `/api/v1/observer/metadata`. The number is high because the three classes — `idle`, `active_user`, `busy_hardware` — are genuinely well-separated in feature space: real human HID input is a very strong signal for `active_user`, and the dataset is clean. We are careful to quote held-out accuracy, not the (perfect) training accuracy, precisely so we're not overstating it. (Note: it is 99.2%, not the older "99.8%" figure that appears in some stale docs.)

**Q13: Your Dispatcher is a Dueling Double DQN. Why that architecture, and how do you serve it fast enough for a live loop?**
*Answer:* The dispatcher decides DEFER vs. DISPATCH from a 10-feature normalised state vector (queue depth, carbon, idle/active/busy node ratios, avg CPU/RAM, priority-tier ratios). We use a **Dueling** DQN because it separately estimates state-value and per-action advantage, which is well-suited to states where the action barely matters (e.g. empty queue) versus states where it's pivotal. **Double** DQN decouples action selection from evaluation to reduce the Q-value over-estimation vanilla DQN suffers from. At serve time we load the trained weights as a **native PyTorch `.pt` state_dict on CPU** and run a single `no_grad()` forward pass — comfortably <10ms. We do **not** use ONNX (an earlier export path was removed; the native state_dict is simpler and fast enough). If PyTorch or the weights are unavailable, it falls back to a transparent rule-based heuristic.

**Q14: Your carbon data is "marginal emissions." Why not just use the grid's average carbon intensity?**
*Answer:* Because the question a load-shifting scheduler actually asks is *"if I run one more MWh right now, how dirty is the power that serves it?"* — and that is the **marginal** signal, not the average. We use WattTime's `CO2_MOER` (Marginal Operating Emissions Rate): the CO₂ of the *next* MWh of demand, i.e. the generator that ramps up to serve new load. Average intensity blends in baseload (nuclear/hydro) that won't change regardless of what we do, so it systematically misattributes savings. MOER is the correct signal for deciding *when* to shift deferrable work. We replay 8,929 real CAISO North rows (5-min resolution) at a configurable stride, keep the raw lbs/MWh and convert to g/kWh at display time.

**Q15: You mentioned an auto-retrain job. Is the model retraining itself in production every 4 hours?**
*Answer:* No — and this is a deliberate design decision, not a missing feature. The auto-retrain `APScheduler` job exists in the codebase but is **OFF by default**; it only registers when `GRIDMIND_ENABLE_RETRAIN=1`. The reason: in production the only "labels" available are the Observer's *own* predicted labels, so retraining on them is self-supervised on model output — a classic **feedback loop** that would reinforce its own errors and drift, while a held-out accuracy from such a run measures stability, not true generalisation. The honest thing is to retrain offline on properly labeled data, so we gate the loop behind an explicit opt-in flag and log a loud warning when it's enabled.

### 👨‍🏫 Teacher 3: Software Engineering & User Experience Focus

**Q9: The major flaw in peer-to-peer computing is interrupting the user. What is your emergency abort mechanism?**
*Answer:* The `gridmind_node` agent runs `pynput` daemon threads hooked into the OS-level keyboard and mouse events. We deliberately use **burst detection, not a hair-trigger**: a single accidental keystroke — or merely nudging the mouse — does NOT abort. We count *deliberate* input events (keys, clicks, scrolls; bare mouse-*move* is treated as telemetry only) and abort only when a burst exceeds the threshold (currently 12 events) within a short window (10 s). When that burst fires, the agent immediately calls `abort_task`, which kills the running subprocess tree on that machine (`taskkill /F /T` on Windows, `SIGTERM` to the process group on POSIX). This is layered on top of the slower Observer-AI path (the `active_user` classification eventually vetoes new dispatches via temporal smoothing) so a genuinely-returning user gets the machine back fast without false-aborting on a stray bump.

**Q10: What happens if the Master Server restarts? Do all the worker laptops crash?**
*Answer:* No. The client connection in `agent.py` is wrapped in an infinite `while` loop with an **exponential backoff** strategy. If the gRPC connection drops, it catches the `RpcError`, waits 2 seconds, and tries again. If it fails, it waits 4 seconds, then 8 seconds, up to a maximum of 60 seconds. When the server comes back online, all agents automatically silently reconnect.

**Q11: How are you managing state in the FastAPI server so the Next.js visual dashboard feels "real-time" without freezing the browser?**
*Answer:* The FastAPI server uses WebSockets (`app/websockets.py`). Every time the gRPC server receives an update, it calls an asynchronous `broadcast()` method. On the React frontend, we implemented **Data Throttling**. Instead of calling `setState` instantly (which would cause massive React re-renders under heavy load), incoming JSON packets are stored in mutable `useRef` buffers and synchronously flushed to the DOM exactly 4 times a second using a `setInterval` loop. This guarantees perfectly smooth 60fps performance on the client regardless of backend traffic.

**Q12: These are people's personal laptops. What stops you from draining someone's battery or overheating their machine?**
*Answer:* The dispatcher applies an explicit power/thermal guardrail (`_power_ok`) before treating any idle node as available. A node is skipped if it is **on battery AND below 30% charge**, or if its **CPU temperature is above 85°C** (the temperature check only applies when the sensor reports a value). Running on battery is allowed while the charge is healthy, so the cluster works even when nobody is plugged in — we only back off from a laptop that's genuinely low or hot. The dashboard shows a distinct "DEFERRING — Protecting Node Battery/Temp" state so it's visibly intentional, not a bug.

**Q13: You claim "carbon savings." Is that a real measurement or a marketing number?**
*Answer:* It's a measured ledger, not a slogan. For every task we stamp the real grid intensity at *submit* time (what a naive "run it immediately" scheduler would have paid) and the real grid intensity at *run* time (when GridMind actually executed it, ideally in a greener window). Per completed task we compute `energy_kWh = duration_secs/3600 × node_power`, then `baseline_g = energy × submit_intensity` and `gridmind_g = energy × run_intensity`; the saved CO₂ is `Σ(baseline) − Σ(gridmind)`, also expressed as a percentage and tangible units on the dashboard. We're transparent that `node_power` is a single documented estimate (~50 W under sustained load), not a per-machine wattmeter reading — but since the *same* estimate appears on both sides of the subtraction it cancels out of the percentage and only scales the absolute grams. We also only count tasks that genuinely succeeded (`completed`, exit code 0), so the savings reflect real work.

**Q14: How do I know a task "completed" actually succeeded? Couldn't you just always report success on the dashboard?**
*Answer:* We deliberately report **honest statuses** end-to-end. The executor marks a task `completed` *only* when the subprocess exits with code 0; a non-zero exit becomes `failed`, a timeout becomes `failed` with the conventional exit code 124, and a user/abort becomes `aborted`. There is no code path that forces a "completed" — the real exit code and stderr are streamed live and persisted to the DB. Cancellation is real too: hitting cancel sends a gRPC `AbortTask` to the worker which actually force-kills the remote subprocess *tree* (not just the local stream), and the task is recorded as `cancelled`. This honesty is the whole point — a distributed scheduler that lies about task outcomes is worse than useless.
