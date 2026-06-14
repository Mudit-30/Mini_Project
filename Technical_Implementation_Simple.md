# GridMind - Technical Implementation (Simplified for Defense)

This document explains exactly *how* GridMind is built, layer by layer, in simple but technically accurate terms. Use this to address questions about your technology stack, system architecture, and machine learning models.

---

## 1. The 3-Layer Architecture Overview

GridMind is built in three distinct layers that constantly talk to each other:

1.  **The Node Agents (The Workers):** Small Python scripts running on everyday laptops.
2.  **The Central Server (The Brain):** A web server managing the task queue, checking the power grid, and running heavy tasks remotely.
3.  **The Machine Learning Layer (The Decision Makers):** Two AI models that analyze data and decide what happens next.

A live **Next.js dashboard** sits on top of all three so judges can watch it happen in real time.

---

## 2. Layer 1: The Node Agents (Worker Laptops)

**What they do:**
These sit quietly in the background on the worker laptops. They have two jobs: (1) spy on the hardware and report back to the central server, and (2) actually run the heavy tasks they are sent. They answer the questions: "Is the user busy?" and "How much CPU power is available?"

**How we built them:**
*   **Language:** Python 3.12. The agent is split into two files: `agent.py` (telemetry + control) and `executor.py` (actually running the tasks it receives).
*   **Telemetry Tracking:** Using **`psutil`** (for CPU, memory, battery, temperature) and **`pynput`** (for keyboard and mouse activity), they constantly monitor the hardware and watch for real human input.
*   **Communication Layer:** We use **gRPC**.
    *   *Why gRPC?* Unlike normal website traffic (REST APIs) which requires a heavy "handshake" every time, gRPC acts like a permanent open pipe. It streams data back and forth incredibly fast and is very lightweight — it takes less than **2% of the laptop's CPU** to run.
    *   *Ports:* Each worker **sends** its telemetry out to the master on port **`50051`**, and **listens** for incoming tasks to run on its own port **`50052`**. (For the demo, all worker laptops are plugged into power.)

---

## 3. Layer 2: The Central Intelligence Server (Master Laptop)

**What it does:**
This is the master controller. It holds the "To-Do List" of heavy computing tasks. It checks the live power grid, looks at the telemetry sent by the workers, and decides when and where to run each task.

**How we built it:**
*   **The Web Framework:** We use **FastAPI** (Python) running on port **`8000`**, paired with an **async gRPC** server for the worker connections.
    *   *Why FastAPI?* It is built specifically for speed and "Asynchronous" operations, meaning it can handle many incoming telemetry streams from worker laptops simultaneously without freezing up.
*   **The Live Registry:** We keep the current state of every worker (online, busy, idle, protected) in a fast **in-memory registry**, so the server always has an instant, up-to-date picture of the cluster.
*   **The Database:** We use **SQLite** in "Write-Ahead Logging" (WAL) mode, accessed through our own **hand-rolled async layer built on `aiosqlite` with raw SQL**.
    *   *Why this way?* We deliberately did **not** use a heavyweight ORM (like SQLAlchemy). SQLite is just a local file, WAL mode lets multiple workers write at the same time without locking each other out, and writing the SQL by hand over `aiosqlite` keeps the data path simple, transparent, and fully asynchronous.
*   **The Dispatcher Loop:** A background loop wakes up **every 2 seconds**, re-reads the grid signal plus the worker registry, and decides what to dispatch next.
*   **The Carbon Checker:** The server makes its decisions on **marginal emissions** — the **WattTime CO2_MOER** signal (Marginal Operating Emissions Rate), which measures the carbon cost of the *next* megawatt-hour the grid would produce.
    *   *Why marginal and not average?* When we shift a workload to a different time, what actually changes is the *marginal* generation that responds to that extra demand — not the grid's blended average. Marginal/MOER is therefore the correct signal for load-shifting; using the average would over- or under-state the real savings.
*   **The Carbon Data:** For the demo, the server replays **8,929 real CAISO grid rows**. To keep a demo watchable, the replay runs at a **configurable fast-forward stride** (env `GRIDMIND_CARBON_STRIDE`) — it steps through the historical series faster than wall-clock instead of waiting hours for the real curve. An **ARIMA** model is fit to the series at startup, and the live "next 2 hours" outlook the dashboard shows is simply the upcoming slice of that replayed series.
*   **The Demo Orchestrator:** We built `start_gridmind.py` to launch the Backend, Frontend, and a node Agent together in one command.

---

## 4. Layer 3: The Machine Learning Layer

This is where the real innovation happens. We have two separate AI models doing two completely different jobs:

### Model A: The Observer AI (Detecting if the laptop is safe to use)
**The Problem:** Normal computers guess you are "idle" if your CPU is low. But you could be reading a PDF (low CPU, but you are busy), so raw CPU alone is a poor signal.

**The Technical Solution:** We built a **supervised machine-learning classifier** using **scikit-learn's `RandomForestClassifier`**.
*   **Supervised, with labels:** We trained it on labelled telemetry so it learns the difference between "human is actively using this machine," "machine is busy with its own work," and "machine is genuinely idle and safe to borrow."
*   **Honest evaluation:** We used an **80/20 stratified train/test split** and report accuracy only on the **held-out 20% it never saw during training**, where it scores **99.2%**.
*   **Temporal smoothing:** Predictions are smoothed over a short rolling window (configurable, default **6** samples, env `GRIDMIND_SMOOTHING_WINDOW`) so one stray reading — a momentary spike from a background virus scan, for example — can't flip the decision and yank a task off a perfectly idle machine.
*   **Heuristic fallback:** If the model is ever unavailable, the system falls back to a safe rule-based heuristic instead of failing.

### Model B: The Dispatcher AI (Routing the task)
**The Problem:** If we have tasks, clean energy, and safely idle laptops, who gets the job, and when?

**The Technical Solution:** We built a **Deep Reinforcement Learning** model — specifically a **Dueling Double DQN** (Deep Q-Network) — in **PyTorch**.
*   **How it works:** It acts like a video-game agent. We trained it entirely in a simulation first using historical data. It earns "points" for completing tasks on clean power and is penalized for using dirty power or for disturbing a user who is active.
*   **Execution in Production:** The trained model is loaded as a native PyTorch **`.pt` state_dict running on the CPU**. (We previously experimented with exporting to ONNX but **removed it** — the native CPU state_dict is simpler and already fast enough.) This lets the Dispatcher make a routing decision in **under 10 milliseconds** without needing an expensive, power-hungry GPU.

> **A note on retraining:** GridMind *can* auto-retrain the Observer, but this is **OFF by default** (env `GRIDMIND_ENABLE_RETRAIN=1` to turn it on). We keep it off on purpose: left running, the model would start training on its own predictions and drift. So we do **not** claim a continuously running retrain cycle — the shipped model is the validated 99.2% one.

---

## 5. What GridMind Actually Does With a Task (Implemented & Tested Features)

Beyond just *deciding*, GridMind genuinely runs the work. These behaviours are all implemented and tested:

*   **Remote Task Execution:** You can submit a one-line script, upload a `.py` file, or upload a whole `.zip` workspace. The server routes it to a safe, idle node, the node runs it, and the **stdout streams back live** to the dashboard as it happens. **Urgent** tasks run immediately; **deferrable** tasks wait for the grid to get cleaner before they go.
*   **Active-User Veto:** If the Observer detects real input on a candidate node, that node is marked **`active_user`** and is **excluded** from receiving work — the human always wins.
*   **Battery & Thermal Protection:** Nodes are **skipped** if they are on battery, below **20% charge**, or running hotter than **85°C**. The dashboard flags them as **"⛔ Protected"** so we never burn someone's battery or cook their laptop.
*   **Fault Tolerance:** If a node drops mid-task, the task is automatically **re-queued and retried (up to 3 times)** on another node. If every retry is exhausted, the system reports an **honest failure** rather than pretending it succeeded.
*   **Data-Parallel Job Splitting:** A single job can be split into **N chunks** (via env `GRIDMIND_CHUNK_INDEX` / `GRIDMIND_CHUNK_COUNT`), fanned out **one chunk per free node**, and run **concurrently**. When **2 or more nodes** are free, we show a **measured speedup**.
*   **Honest Results:** We surface the **real exit codes and statuses** from the remote processes — no faked "success." Hitting cancel sends an **`AbortTask`** signal that actually **kills the remote subprocess**.
*   **Measured Carbon Proof:** For each task we compare a **naive baseline** (what the carbon would have been if it ran immediately at submit time, using a ~50W estimate) against the **actual GridMind run-time** carbon. We report the **grams of CO₂ saved**, the **percentage saved**, and a tangible real-world equivalent — all computed on the marginal (MOER) signal, with a target of **≥20% carbon reduction**.
*   **Observer Metadata Endpoint:** A dedicated endpoint exposes the Observer's **held-out accuracy and confusion matrix**, so the model's quality is inspectable, not just asserted.

---

## 6. The Emergency Abort Mechanism (Crucial Feature)

Teachers will ask: *"What if the task is running in the background and I come back to my laptop to work? Won't it lag?"*

**How we technically solved this:**
While a heavy task runs on a worker laptop, the Node Agent keeps watching the keyboard and mouse locally. We use **burst detection**: when it sees a **burst of deliberate input** — keystrokes, clicks, or scrolls — within a short window, it instantly sends an abort signal back to the server, which kills the remote subprocess and hands the laptop's full power back to the human.

*   **Important nuance:** It is **not** triggered by a single millisecond mouse-bump or mere mouse movement. We deliberately require a *burst* of real interaction so that an accidental nudge of the trackpad doesn't needlessly throw away in-progress work. Real human activity aborts; noise does not.

---

## 7. The User Interface (Proving it works)

**What it does:** We need a way to show the panel this is actually happening.

**How we built it:**
We built a live dashboard using **Next.js** (a React framework) running on port **`3005`**. The central FastAPI server pushes live data constantly over **WebSockets**. This lets us display, in real time: the carbon we are saving right now, which laptops are computing, which are idle, which are "⛔ Protected," and the live stdout of tasks as they run.
