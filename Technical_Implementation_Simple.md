# GridMind - Technical Implementation (Simplified for Defense)

This document explains exactly *how* GridMind is built, layer by layer, in simple but technically accurate terms. Use this to address questions about your technology stack, system architecture, and machine learning models.

---

## 1. The 3-Layer Architecture Overview

GridMind is built in three distinct layers that constantly talk to each other:

1.  **The Node Agents (The Workers):** Small Python scripts running on everyday laptops.
2.  **The Central Server (The Brain):** A web server managing the task queue and checking the power grid.
3.  **The Machine Learning Layer (The Decision Makers):** Two AI models that analyze data and decide what happens next.

---

## 2. Layer 1: The Node Agents (Worker Laptops)

**What they do:** 
These sit quietly in the background on the worker laptops. Their only job is to spy on the hardware and report back to the central server. They ask: "Is the user busy?" and "How much CPU power is available?"

**How we built them:**
*   **Language:** Python 3.12.
*   **Telemetry Tracking:** They constantly monitor CPU usage, memory usage, and specifically look for mouse bumps and keyboard strokes.
*   **Communication Layer:** We use **gRPC** to send this data.
    *   *Why gRPC?* Unlike normal website traffic (REST APIs) which requires a heavy "handshake" every time, gRPC acts like a permanent open pipe. It streams data back and forth incredibly fast and is very lightweight. It takes less than 2% of the laptop's CPU to run.

---

## 3. Layer 2: The Central Intelligence Server (Master Laptop)

**What it does:** 
This is the master controller. It holds the "To-Do List" of heavy computing tasks. It checks the live power grid, looks at the telemetry sent by the workers, and decides when to assign tasks.

**How we built it:**
*   **The Web Framework:** We use **FastAPI** (Python). 
    *   *Why FastAPI?* It is built specifically for speed and "Asynchronous" operations, meaning it can handle hundreds of incoming telemetry streams from worker laptops simultaneously without freezing up.
*   **The Database:** We use **SQLite** configured in "Write-Ahead Logging" (WAL) mode.
    *   *Why SQLite WAL?* We didn't need a massive, heavy database server. SQLite is just a local file, but WAL mode allows multiple worker laptops to write their telemetry data at the exact same time without locking each other out.
*   **The Carbon Checker:** Every 60 seconds, the server uses a REST API to call **WattTime**, an external service that tells us exactly how "dirty" (coal/gas) or "clean" (wind/solar) the local electricity grid is right at that second.

---

## 4. Layer 3: The Machine Learning Layer

This is where the real innovation happens. We have two separate AI models doing two completely different jobs:

### Model A: The Observer AI (Detecting if the laptop is safe to use)
**The Problem:** Normal computers guess you are "idle" if your CPU is low. But you could be reading a PDF (low CPU, but you are busy). 
**The Technical Solution:** We built an **Unsupervised Machine Learning model**. Unsupervised means it learns automatically on its own. 
*   **Algorithm 1: DBSCAN.** This filters out weird, random hardware spikes (like a virus scan kicking in for 2 seconds) so the AI doesn't get confused.
*   **Algorithm 2: K-Means Clustering.** This takes the clean data and groups it into 3 buckets: "Human is actively typing", "Computer is too busy," or "Computer is completely idle". 
*   **The Result:** It adapts to each individual user's specific habits, achieving **99.8% confirmed accuracy** in predicting if a laptop is safe to receive a heavy task. We built this using **scikit-learn**.

### Model B: The Dispatcher AI (Routing the task)
**The Problem:** If we have tasks, clean energy, and safely idle laptops, who gets the job?
**The Technical Solution:** We built a **Deep Reinforcement Learning (RL)** model (specifically a Deep Q-Network).
*   **How it works:** It acts like a video game agent. We trained it entirely in a simulation first using historical data. It gets "points" for completing tasks and gets "penalties" if it uses dirty power or accidentally sends a task to a user who is typing.
*   **Execution in Production:** Once trained using **PyTorch**, we exported the "brain" to run on **ONNX Runtime**. This is crucial: it allows the server to make the final AI decision in under 10 milliseconds without needing an expensive, power-hungry Graphics Card (GPU).

---

## 5. The Emergency Abort Mechanism (Crucial Feature)

Teachers will ask: *"What if the task is running in the background and I come back to my laptop to work? Won't it lag?"*

**How we technically solved this:**
While the heavy task is running on a worker laptop, the Node Agent is still watching the mouse and keyboard locally. The millisecond the human bumps the mouse, the Python script catches the "mouse event" and instantly sends an emergency abort signal via gRPC back to the central server. The heavy task is instantly frozen, giving the laptop 100% of its power back to the human.

---

## 6. The User Interface (Proving it works)

**What it does:** We need a way to show the panel this is actually happening. 
**How we built it:** 
We built a live dashboard using **Next.js** (a React framework). The central FastAPI server pushes live data constantly using **WebSockets**. This allows us to display real-time charts showing the exact carbon we are saving right now, which laptops are computing, and which laptops are idle.
