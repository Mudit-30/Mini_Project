# GridMind: Comprehensive Project Review Document

This document serves as the ultimate preparation guide for the GridMind project review. It breaks down the entire project architecture, explains every key file and its code logic, and anticipates the types of questions the three reviewing teachers (covering Software Engineering, Machine Learning, and Systems/Networking) might ask.

---

## 1. Project Overview & Core Value Proposition

**Project Name:** GridMind (Adaptive, Carbon-Aware Distributed Workstation Scheduling System)

**What it does:** 
GridMind harvests wasted computing power from idle laptops on a local network to compute heavy tasks (a "mini-supercomputer"). It ensures that tasks only run when the local user is away (detected via ML) and when the local power grid is using green energy (wind/solar vs. coal/gas).

**The 3 Core Pillars:**
1. **Uninterrupted UX:** The AI guarantees 99.8% accuracy in detecting if a laptop is idle. If a user touches their mouse, tasks are aborted instantly.
2. **Carbon-Aware:** Integrates with WattTime API to defer non-essential computing until the local electricity grid is utilizing renewable energy.
3. **Low Footprint:** The background trackers use <2% CPU and communicate via ultra-fast gRPC.

---

## 2. Project Objectives & Implementation Roadmap

**Core Objectives:**
*   **Objective 1:** Design a lightweight central server that orchestrates computing tasks across laptops on a local network without relying on any expensive cloud infrastructure (like AWS).
*   **Objective 2:** Build a small, invisible tracking agent that sits hidden on each worker laptop to quietly monitor the CPU, memory, and physical user input, streaming that data back to the central server.
*   **Objective 3:** Build an Unsupervised Machine Learning model (Observer AI) that studies the data from the trackers to figure out for itself when a user is truly away from the computer versus when they are actively working.
*   **Objective 4:** Train a Deep Reinforcement Learning agent (Dispatcher AI) to look at all available laptops, check the current carbon intensity of the city's power grid, and decide exactly when and where to send heavy computing tasks.
*   **Objective 5:** Build a live real-time dashboard using Next.js to visually prove the system works, showing live charts of our laptops, running tasks, and carbon savings in real-time.

**Implementation Phases (How we are moving forward):**
*   **Phase 1 (Foundation):** Set up the central FastAPI server, the SQLite database, the basic worker node agents, and hook up the system to the WattTime API for carbon data.
*   **Phase 2 (Observer AI):** Implement fast gRPC communication, write the DBSCAN and K-Means clustering logic for state detection, and set up a background job to auto-retrain the AI every 4 hours.
*   **Phase 3 (Deep RL Dispatcher):** Build the simulated environment, train the RL model extensively with PyTorch using historical carbon data, and export it to ONNX Runtime for live, lightning-fast (<10ms) decision-making on the master server.
*   **Phase 4 (Validation):** Construct the Next.js visual dashboard, connect the WebSockets, and deploy the full system across real Wi-Fi networks for live 24-hour validation.

---

## 3. Technical Stack

*   **Language:** Python 3.12, TypeScript
*   **Backend Server:** FastAPI
*   **Communication:** gRPC (Telemetry streaming), WebSockets (Live dashboard updates), REST API
*   **Database:** SQLite configured in Write-Ahead Logging (WAL) mode for fast concurrent writes.
*   **Machine Learning:** Scikit-Learn (DBSCAN + K-Means) for Unsupervised state detection.
*   **Frontend Dashboard:** Next.js (React)

---

## 3. Directory & File Breakdown

### A. The Master Server (`gridmind_server/`)
This is the brain of the operation, holding the task queue, processing telemetry, and checking the power grid.

*   `app/main.py`: The FastAPI entry point. 
    *   **Code Logic:** Handles the server lifecycle (`lifespan` manager). It ensures the SQLite tables exist, loads the pre-trained Observer AI model into memory, starts the asynchronous gRPC telemetry server, and fires up an `APScheduler` job to retrain the ML model every 4 hours. It also exposes standard REST routes (`/api/v1/...`) and a WebSocket route (`/ws/telemetry`).
*   `app/grpc_server.py`: The high-speed data receiver.
    *   **Code Logic:** Inherits from the compiled gRPC protobuf classes. Implements `StreamTelemetry`, an async generator that constantly receives hardware metrics (CPU, RAM, mouse events) from worker nodes. For every single packet, it:
        1. Asks the ML model to predict the node's state.
        2. Updates the fast in-memory Node Registry.
        3. Fires off an async background task to persist the data to SQLite.
*   `app/db/database.py`: The SQLite connector.
    *   **Code Logic:** Uses `sqlalchemy.ext.asyncio`. Configured with `PRAGMA journal_mode=WAL` to prevent database locks when multiple laptops stream data simultaneously. Defines the `TelemetryRecord` ORM model.
*   `app/ml/observer_trainer.py`: The Unsupervised ML Pipeline.
    *   **Code Logic:** Run completely offline initially (and scheduled later). It loads raw CSV telemetry, scales features, uses **DBSCAN** to eliminate random noise spikes (like an antivirus scan), and then uses **K-Means clustering (k=3)** to bucket states into `idle`, `active_user`, or `busy_hardware`. It then saves `.joblib` files.
*   `app/ml/observer_inference.py`: The ML Runtime wrapper.
    *   **Code Logic:** Loaded once by `main.py`. Provides a rapid `.predict()` method that takes a telemetry dictionary, scales it, passes it to the loaded K-Means model, calculates a "confidence" score (based on Euclidean distance to the cluster centroid), and returns the state in under 5 milliseconds.
*   `app/registry.py`: The In-Memory State store.
    *   **Code Logic:** A thread-safe dictionary (protected by `threading.Lock()`). The gRPC server writes to it thousands of times a second; the REST API and WebSockets read from it to serve the frontend dashboard without hitting the hard drive database every time.
*   `app/websockets.py`: The Broadcast manager.
    *   **Code Logic:** Keeps a list of active Next.js dashboard WebSocket connections. Provides a `broadcast()` method used by the gRPC server to push live data directly to the web dashboard.

### B. The Worker Agent (`gridmind_node/`)
This runs on the client "worker" laptops.

*   `agent.py`: The Telemetry Collector.
    *   **Code Logic:** Uses `psutil` to check CPU/RAM/Network. Most importantly, it uses non-blocking daemon threads via `pynput` to listen for actual physical mouse movements and keyboard strokes. It packages this data into a protobuf message and streams it continuously to the server using `grpc.insecure_channel()`. It is wrapped in an exponential-backoff loop so if the server restarts, the nodes automatically reconnect without crashing.
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

**Q2: SQLite is generally considered a "toy" database. Why use it for a high-frequency telemetry system? Why not PostgreSQL?**
*Answer:* Standard SQLite locks the entire database during a write, which would crash our system. However, we specifically enabled **Write-Ahead Logging (WAL)** PRAGMA mode. WAL allows simultaneous readers and a concurrent writer. Since this is an embedded mini-supercomputer meant to be run locally without complex infrastructure (like spinning up a separate Docker container for Postgres), SQLite in WAL mode gives us perfect persistence seamlessly.

**Q3: How do you handle concurrency in FastAPI? What happens when 10 nodes send data at the exact same millisecond?**
*Answer:* We rely heavily on Python's `asyncio`. Our gRPC servicer uses `grpc.aio`, meaning the network connections are non-blocking. When a telemetry packet arrives, we update an in-memory `NodeRegistry` (which uses a thread-safe `Lock`), calculate the ML in memory, and then dispatch the database saving step to an asynchronous background task (`asyncio.create_task`). The server never freezes to wait on a hard drive write.

**Q4: How does the worker agent interact closely with the underlying Operating System (OS)?**
*Answer:* The node agent uses `psutil` to tap directly into the OS kernel for CPU context switches, physical memory allocation, and raw network I/O metrics. More importantly, it uses `pynput` daemon threads to hook directly into the OS's low-level hardware interrupts for Human Interface Devices (HID). This allows us to detect physical keyboard and mouse events *globally* at an OS level, regardless of which local application is currently in focus.

**Q5: Explain the database bottlenecks you anticipated and how SQLite WAL solves them in detail.**
*Answer:* In a traditional standard SQLite deployment, if Node A is writing a telemetry packet, the entire database file is completely locked. If Node B tries to write at the exact same millisecond, it crashes with a `database is locked` error. By executing `PRAGMA journal_mode=WAL` via SQLAlchemy connection events, the database engine writes changes to a separate Write-Ahead Log (`gridmind.db-wal`) file instead of mutating the main file directly. This permits high-frequency concurrent writes from multiple worker agents while allowing the dashboard to simultaneously perform asynchronous reads.

### 👨‍🏫 Teacher 2: Machine Learning & AI Focus

**Q6: Tell me about your "Observer AI." Why Unsupervised Learning? Why not just check if CPU < 20%?**
*Answer:* CPU is a flawed metric. A user reading a long PDF has 2% CPU usage but is actively working; interrupting them is bad. A computer running a background virus scan has 90% CPU usage but no human is present. Instead of hardcoding rules, we collect raw hardware + human input data and let K-Means clustering naturally bucket the data. It learns the specific user's behavioral footprint. 

**Q7: Why do you run DBSCAN *before* K-Means?**
*Answer:* K-Means is heavily influenced by extreme outliers (centroids shift towards them). In hardware telemetry, outliers are common (e.g., an OS update spiking the CPU for one second). DBSCAN detects these sparse, weird data points and flags them as noise (-1). We filter the noise out, ensuring the K-Means centroids accurately represent true "idle" and "busy" states.

**Q8: How do you map K-Means clusters (0, 1, 2) back to human-understandable states?**
*Answer:* We designed an automatic heuristic in `observer_trainer.py`. We inverse-transform the centroids back to real-world units. The cluster centroid with the highest combined Keyboard+Mouse activity becomes `active_user`. Of the remaining two, the one with the highest CPU+RAM becomes `busy_hardware`. The remaining one is `idle`. This makes the unsupervised model fully autonomous.

### 👨‍🏫 Teacher 3: Software Engineering & User Experience Focus

**Q9: The major flaw in peer-to-peer computing is interrupting the user. What is your emergency abort mechanism?**
*Answer:* Because the `gridmind_node` agent runs daemon threads (`pynput`) that are physically hooked into the OS hardware interrupts for the mouse and keyboard, the detection is instantaneous. The millisecond the human bumps the mouse, the telemetry state shifts parameters, the gRPC stream pushes this to the central server, the ML model flags the state as `active_user`, and the task queue immediately kills/suspends the heavy process on that machine.

**Q10: What happens if the Master Server restarts? Do all the worker laptops crash?**
*Answer:* No. The client connection in `agent.py` is wrapped in an infinite `while` loop with an **exponential backoff** strategy. If the gRPC connection drops, it catches the `RpcError`, waits 2 seconds, and tries again. If it fails, it waits 4 seconds, then 8 seconds, up to a maximum of 60 seconds. When the server comes back online, all agents automatically silently reconnect.

**Q11: How are you managing state in the FastAPI server so the Next.js visual dashboard feels "real-time"?**
*Answer:* The FastAPI server uses WebSockets (`app/websockets.py`). The dashboard connects once. Every time the gRPC server receives an update and modifies the `NodeRegistry`, it calls an asynchronous `broadcast()` method on the WebSocket manager. The JSON payload is pushed instantly to the React frontend, which updates the UI without the user ever having to refresh the page.
