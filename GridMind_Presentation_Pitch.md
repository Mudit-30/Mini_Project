# 🧠 GridMind: Carbon-Aware AI-Driven Distributed Workstation Scheduler

GridMind is a next-generation distributed workstation scheduler that transforms ordinary, underutilized local laptops and workstations into a secure, carbon-intelligent, and high-performance computing (HPC) cluster. 

Unlike traditional cloud-based or rigid data-center cluster orchestrators, GridMind utilizes **Reinforcement Learning**, **Smart Human Observers**, and **Power Grid Forecasting** to schedule compute workloads across office computers—without ever interrupting the developers or office workers sitting in front of them.

---

## 🚀 The Core Innovation: What Makes GridMind Unique?

GridMind is built around **three primary pillars** that distinguish it from any existing solution on the market:

### 1. 🍃 Carbon-Aware Predictive Scheduling
Traditional schedulers are "green-blind"—they only look at how fast a computer is, ignoring where the electricity comes from. GridMind is **natively carbon-conscious**:
*   **Marginal Emissions Signal**: It uses **WattTime's marginal emissions (CO2_MOER)**—the carbon intensity of the *next* MWh the grid would burn to serve new load. This is the correct, decision-grade signal for load-shifting (far better than a grid-wide average), replayed from **8,929 real CAISO data rows**.
*   **Predictive Execution**: If the local power grid is currently burning coal, GridMind's **Dispatcher AI** will proactively **defer** non-urgent tasks (e.g., model retraining) and execute them when the grid transitions to solar, wind, or hydro energy.
*   **Measured Carbon Proof**: For every completed task, GridMind records the emissions a naive scheduler *would have* paid at submit-time versus what GridMind *actually* paid at run-time. Using a stated ~50 W per-node load estimate (applied identically to both sides), it reports the **measured grams of $CO_2$ saved**, the **percentage saved**, and tangible equivalents (phone charges, metres not driven) directly on the live dashboard.

### 2. 🛡️ Invisible Zero-Interrupt Co-Existence (Observer AI)
Traditional grids require dedicated, idle computers that nobody is using. If you run a background task on a developer's machine, it lags, frustrating the user. GridMind introduces **Human-Aware Co-existence**:
*   **Hardware State Classification**: An **Observer AI**—a supervised **scikit-learn RandomForest classifier (99.2% held-out accuracy)**—evaluates hardware telemetry (CPU, RAM, Net I/O) along with keyboard and mouse input event frequencies.
*   **Human Activity Burst Detection**: If a developer touches their keyboard or mouse, a background listener detects the burst.
*   **Emergency Abort & Deferral**: The Node Agent immediately sends a gRPC abort signal, stops the task subprocess instantly to free up 100% of resources for the developer, and the Dispatcher AI re-queues or migrates the task. The human never even realizes a background training task was running.
*   **Respect-the-Human Power & Thermal Protection**: Nodes also report **battery %, on-battery status, and CPU temperature**. The Dispatcher will never dispatch to a machine that is **running on battery, below 20% charge, or hotter than 85°C**—it marks them "⛔ Protected." GridMind borrows your idle compute, never your battery life or a comfortable lap.

### 3. 🤖 Smart Dispatcher (Reinforcement Learning)
Static rules (like assigning tasks in a simple loop) fail in dynamic office environments where computers turn off, go to sleep, or get used by humans at random.
*   **Deep Reinforcement Learning**: GridMind uses a **Dueling Double Deep Q-Network (DQN)** in PyTorch that maps a 10-feature normalized state space (telemetry, regional carbon index, queue sizes, and priority distributions) to optimal scheduling actions. The policy is served from a **native `.pt` state-dict on CPU** (no ONNX, no GPU dependency), returning a decision in **under 10 ms**.
*   **Adaptive Policy**: The agent learns over time which nodes are most reliable, when certain developers go to lunch (enabling larger window dispatches), and how to maximize carbon efficiency without missing task deadlines.

---

## 📊 Comparative Analysis: GridMind vs. The Industry

| Feature / Aspect | Slurm / HTCondor | Kubernetes (K8s) | GridMind (Our Project) |
| :--- | :--- | :--- | :--- |
| **Primary Focus** | Bare-metal HPC performance | Cloud-native microservices | **Eco-Friendly Local Edge Computing** |
| **Grid Awareness** | ❌ None | ❌ None | **✅ Regional Carbon-Intensity Aware** |
| **Scheduling Engine** | Static Heuristics / Priority | Static Resource Limits (Go scheduler) | **🧠 Reinforcement Learning (DQL)** |
| **Co-Existence Concept** | Headless / Dedicated Nodes only | Hard Limits (Eviction under stress) | **🛡️ Real-Time Human Activity Burst Abort + Battery/Thermal Protection** |
| **Fault Tolerance** | Job requeue (operator-configured) | Pod reschedule (controller) | **♻️ Auto Re-Dispatch on Node Drop (≤3 retries, then honest failure)** |
| **Data-Parallel Speedup** | Manual job arrays / MPI setup | Manual sharding via manifests | **🔀 One-Click Job Splitting Across Free Nodes (measured speedup)** |
| **Target Infrastructure** | Dedicated Data Centers | AWS, GCP, Azure, Private Cloud | **💻 Existing Office Workstations & Laptops** |
| **Telemetry System** | Pull-based (cron/agent) | Metrics Server (Prometheus) | **⚡ Async gRPC + Real-Time WebSocket Streaming** |
| **Developer Experience** | Command line / CLI only | Complex YAML files | **🎨 Elegant Glassmorphism Next.js Dashboard** |

---

## 🛠️ Simple Explanations: The AI Under the Hood

To make GridMind work seamlessly, three specialized AI systems collaborate in real-time. Here is how they work in simple terms:

### 1. The Dispatcher AI (The Smart Traffic Controller)
*Analogy: An experienced logistics manager at a shipping company who learns over time which routes are fastest and cheapest.*

Instead of following rigid, pre-defined rules, the Dispatcher AI **learns by trial and error** using a technique called **Reinforcement Learning** (specifically a *Dueling Double Deep Q-Network*).

*   **How it Works**: It looks at 10 different signals (like how busy the workstations are, how clean the power grid is, and how urgent the task is) and decides which machine should execute the task.
*   **The "Dueling" Concept**: The AI splits its thinking into two paths:
    1.  **State Value**: It looks at the *overall situation* of the network to see if it is a good time to dispatch tasks at all.
    2.  **Action Advantage**: It looks at *which specific workstation* is the absolute best candidate for the job.
    *By separating these two questions, the AI makes smarter decisions much faster.*
*   **The "Double" Concept (The Two-Judge System)**: 
    Instead of relying on a single network to make a decision and grade its own work, GridMind uses a "two-judge" system. One network proposes where to send the task, and a second network double-checks that choice. This prevents the AI from making hasty, overly-optimistic scheduling errors.

### 2. The Observer AI (The Polite Roommate)
*Analogy: A polite roommate who immediately stops playing music the second they hear you walk into the room so they don't disturb you.*

The Observer AI runs silently in the background of each workstation to ensure that remote tasks never slow down the machine for the person sitting in front of it.

*   **How it Works**: It monitors 7 factors (like CPU, RAM, and how actively the keyboard and mouse are being used) and classifies the machine's state into:
    *   **Idle**: The user is away; it is 100% safe to run background work.
    *   **Active User**: A human is using the computer; stop all background tasks immediately!
    *   **Busy Hardware**: The machine is working on something else, but no human is actively sitting there.
*   **The "Waiting Window" (Temporal Smoothing)**: 
    If a user accidentally bumps their desk or hits a single key by mistake, we don't want to panic and abort a massive 2-hour job. The AI uses a "smoothing filter"—it observes activity over a brief, **configurable** temporal window (a rolling buffer of recent frames). It only triggers a task abort if it is highly confident, across that window, that a human is *actually* back at their computer actively working.

### 3. The Carbon Forecaster (The Green Weather App)
*Analogy: A weather forecast app that tells you it will stop raining in 30 minutes, so you wait to go for a walk.*

Rather than just reacting to the grid in the present moment, the Carbon Forecaster predicts the future to optimize green energy usage.

*   **How it Works**: It uses a classic time-series forecasting model (called **ARIMA**), fit at startup on the real WattTime marginal-emissions series. This same model powers the Dispatcher's **explainable reasoning** ("deferring because the grid is dirty now but a clean window opens soon").
*   **2-Hour Horizon**: It produces a rolling **2-hour outlook** of where the local grid's carbon footprint is heading.
*   **The Smart Delay**: If the model predicts that the grid is currently dirty (burning coal) but a wave of clean solar energy will hit the grid in 30 minutes, the Dispatcher AI will temporarily hold back non-urgent tasks in the queue. It dumps them onto the machines only when the clean window begins, maximizing carbon savings.

---

## ⚙️ How GridMind Works Under the Hood

```mermaid
graph TD
    User([Developer / User]) -->|Uploads ZIP Workspace / Script| FE[Next.js Dashboard]
    FE -->|HTTP API POST| BE[FastAPI Central Intelligence]
    
    subgraph Central Intelligence Node
        BE -->|Store telemetry / queue| DB[(SQLite Database)]
        BE -->|Carbon Forecasts| CF[Carbon Forecaster: ARIMA]
        BE -->|State Space Input| D_AI[Dispatcher AI: Smart Controller]
    end

    subgraph Teammate / Worker Nodes
        N1[Teammate Node A] -->|gRPC Telemetry Port 50051| BE
        N2[Teammate Node B] -->|gRPC Telemetry Port 50051| BE
        
        BE -->|gRPC Dispatch Port 50052| N1
        N1 -->|Streams stdout line-by-line| BE
        
        Obs[Observer AI: Smart Roommate] -->|Classifies User State| N1
        Input[KB / Mouse Listeners] -->|Burst Triggered| Obs
    end
    
    BE -->|Live Terminal Stream| FE
```

### 1. The Real-Time Connection (gRPC & WebSockets)
To coordinate computers seamlessly without lagging:
*   **Continuous Check-in (gRPC Telemetry)**: Every 5 seconds, each workstation checks in with the master server, sharing its hardware load and whether a human is active.
*   **Live Output Streaming (gRPC to WebSockets)**: When a node is running a task, it doesn't wait until the task is fully finished to show the results. It streams the console output line-by-line in real-time directly to the dashboard, making it look like a live terminal.

### 2. Workspace Artifact System & Flexible Remote Execution
Developers submit work three ways: a **raw script**, a **single `.py` file** (drag-and-drop upload from the dashboard), or a **fully packaged `.zip` workspace**. For a workspace, the worker node automatically downloads it, extracts it locally, executes the entry script in an isolated subprocess, packages the generated artifacts (e.g., trained weight files, graphs, CSVs), and uploads the output workspace back to the server for the user to download.

### 3. Fault-Tolerant Re-Dispatch
Office laptops are unreliable by nature—someone closes a lid, drops Wi-Fi, or walks away. GridMind treats this as a first-class case, not a crash:
*   If a node **disconnects mid-task**, the task is automatically **re-queued** and a different free node picks it up and finishes it.
*   This retries up to **3 times**. If every attempt is exhausted, GridMind reports an **honest failure** rather than silently dropping the work.

### 4. Data-Parallel Job Splitting (The Mini-Supercomputer Payoff)
This is where a room full of laptops becomes a single machine. A user can split **one job into N chunks**, and GridMind fans them out **one-per-free-node** to run concurrently:
*   Each node receives its slice of the work via the `GRIDMIND_CHUNK_INDEX` / `GRIDMIND_CHUNK_COUNT` environment variables, so the same script knows exactly which portion to compute.
*   When **two or more nodes share the work**, the dashboard surfaces the **measured speedup**—turning idle desks into tangible, parallel horsepower.

### 5. Honest, Real Results
GridMind never fakes success. Every task reports its **real status and exit code** straight from the remote subprocess. When a user clicks cancel, the server sends an **`AbortTask`** RPC that genuinely kills the remote subprocess—stop means stop.

---

## 🌟 Why GridMind is the Future of Edge Computing

1. **Zero Hardware Costs**: Organizations do not need to buy expensive servers. They can use the idle computing power of their developers' and designers' existing machines (which sit idle 70-80% of the day).
2. **True ESG Compliance**: Instead of greenwashing, companies can actively schedule heavy machine learning workloads and simulations to run *only* when the grid power is clean, directly contributing to carbon footprint reduction.
3. **Frictionless Integration**: Teammates can connect their local machine to the master orchestrator in literally one second with a single terminal command:
   ```bash
   python gridmind_node/agent.py --server <MASTER_IP>:50051 --node-id "Your_Name"
   ```

GridMind represents a paradigm shift: **making distributed computing smart, green, and completely invisible.**
