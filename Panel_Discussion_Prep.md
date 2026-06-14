# GridMind - Panel Discussion & Defense Preparation

This document provides crystal-clear, straightforward answers to the two most important questions the panel will ask: **What are you actually making?** and **Specifically, what problems does it solve?**

---

## 1. WHAT WE ARE MAKING (The Core Concept)

**The Short Answer:**
We are building a software system that links ordinary laptops on a local Wi-Fi network into a single "supercomputer" that automatically runs heavy background computing tasks **ONLY** when the laptops are truly free and safe to use **AND** when the local power grid is clean.

**The Technical Definition for the Panel:**
GridMind is an adaptive, carbon-aware distributed task scheduling system. It uses **federated telemetry**, a **supervised Machine Learning behavioral classifier**, and **deep reinforcement learning** to run tasks across consumer hardware.

**How to explain the name:**
*   **"Grid"**: Refers to our system's active tracking of the local power grid's *marginal* carbon intensity (knowing whether the *next* unit of electricity we'd consume comes from clean sources like solar/wind vs. dirty sources like coal).
*   **"Mind"**: Refers to the Artificial Intelligence layer we built to make real-time decisions, rather than relying on basic, hardcoded "if/then" rules.

---

## 2. THE PROBLEMS WE ARE SOLVING (The "Why")

When the panel asks *why* this project is necessary or what research gaps it fills, present these specific, measurable problems and our solutions:

### Problem 1: Wasted Consumer Hardware
*   **The Flaw:** Almost all existing "green computing" research focuses on optimizing massive corporate data centers. Nobody is focusing on consumer hardware.
*   **Our Solution:** Millions of everyday laptops sit idle for hours every day on local Wi-Fi networks (libraries, offices, homes). We are harvesting that wasted computing power without needing expensive cloud servers like AWS.

### Problem 2: Flawed "Idle" Detection Causes User Disruption
*   **The Flaw:** Current systems use a hardcoded rule to decide if a computer is idle (e.g., "If CPU usage is under 25%, the computer is idle"). This is completely wrong. A user might be reading a long PDF or downloading a file. If a system sends a heavy task based on low CPU, it disrupts the user's laptop.
*   **Our Solution:** We trained a **supervised Machine Learning model (scikit-learn RandomForestClassifier)** that continually monitors CPU, memory, network I/O, mouse activity, and keystrokes. It classifies each machine into one of three states — *idle*, *active user*, or *busy hardware*. Evaluated honestly on a held-out test set (80/20 split), it reaches **99.2% accuracy**. We layer a **configurable temporal-smoothing window** on top so a single noisy frame never flips the decision, plus a **heuristic fallback** that keeps the node safe if the model can't load.

### Problem 3: Static, Unresponsive Task Scheduling
*   **The Flaw:** Current task managers are static. They are programmed once. If the local power grid unexpectedly surges with dirty energy, the system doesn't know how to react and keeps computing blindly. Many also use *average* grid intensity, which is the wrong signal — it doesn't tell you the carbon cost of the work you are about to add.
*   **Our Solution:** We schedule against **marginal emissions** — WattTime's **CO2_MOER** signal, the CO₂ of the *next* MWh the grid would dispatch. This is the correct signal for load-shifting decisions. We validated the system on a **8,929-row real CAISO dataset**, replayed with a **configurable fast-forward stride** so the panel can watch the AI react to a full day of grid swings in a short demo window.

### Problem 4: Failing to Balance Conflicting Priorities
*   **The Flaw:** Existing systems either focus entirely on speed (getting the job done fast) OR entirely on green energy. No one successfully balances all the factors without bothering the human user.
*   **Our Solution:** We trained a **Deep Reinforcement Learning Dispatcher (PyTorch Dueling Double DQN)**. It looks at the waiting tasks, the real-time marginal carbon data, and the list of safe laptops, and calculates the optimal decision in **under 10 milliseconds (~4ms)** on plain CPU. It penalizes itself heavily if it disrupts a human user or uses dirty energy. (The model ships as a native PyTorch `.pt` state_dict loaded on CPU — no ONNX, no GPU required.)

---

## 3. WHAT'S NEW (Beyond Scheduling — the features that make it real)
*These are done and tested. Lead with them when the panel asks "but does it actually do anything?"*

### Remote Task Execution
A user uploads a script, a `.py` file, or a ZIP. The server routes it to a safe idle node over gRPC, runs it, and streams **live stdout** back to the dashboard. Urgent tasks dispatch immediately; deferrable tasks wait for a clean grid window.

### Battery & Thermal Protection (the "⛔ Protected" guard)
We are running on someone's *personal* laptop, so we never drain or cook it. A node is skipped if it is **on battery**, **below 20% charge**, or **above 85°C**. The dashboard shows a "⛔ Protected" pill, and the dispatcher reports "DEFERRING — Protecting Node Battery/Temp."

### Fault-Tolerant Re-Dispatch
If a worker node drops mid-task, the server automatically **re-queues** the task and sends it to another node — up to **3 retries**. If it still can't complete, we report an **honest failure** (real status, real exit code) rather than pretending it worked.

### Data-Parallel Job Splitting (the mini-supercomputer)
A heavy job can be split into **N chunks** (set via env). The dispatcher **fans out one chunk per free node**, so the cluster chews through the work in parallel and we get a **measured speedup whenever ≥2 nodes are available**. This is the literal "many laptops = one supercomputer" demo.

### Measured Carbon Proof
We don't just *claim* savings — we **measure** them. For every completed task we compare the emissions of a naive "run-it-the-moment-it-was-submitted" baseline against what GridMind *actually* emitted by waiting for a cleaner window (at ~50W per node). The dashboard reports **grams of CO₂ saved**, the **percentage** saved, and **tangible equivalents** (e.g. "≈ N phone charges · M metres not driven").

---

## 4. HOW IT ACTUALLY WORKS (The 7-Step Walkthrough)
*If they ask: "Walk me through what happens when I submit a job."*

1.  **Submission:** A heavy computing task is submitted to our central FastAPI server with a priority tier (**urgent**, **deferrable**, or **best-effort**). We stamp it with the current grid intensity so we can prove savings later.
2.  **Carbon Check:** The dispatcher loop reads the current **marginal carbon intensity (WattTime CO2_MOER)** — the CO₂ of the next MWh, the correct load-shifting signal.
3.  **Deferral (If Dirty):** If the grid is dirty *and* the task is deferrable, the server holds it and waits for cleaner energy (wind/solar) to pick up. **Urgent tasks skip the wait** and dispatch right away.
4.  **Idle & Safety Check (If Clean):** The server asks our Observer AI: *"Are any worker laptops in the confidently-idle state?"* — and then filters out any node that's on battery, low on charge, or running hot (the "⛔ Protected" guard).
5.  **Dispatch:** Our DQN Dispatcher decides defer-vs-dispatch in **~4ms** and the task is sent over gRPC. For a **data-parallel** job, it **fans out one chunk to each free node** so the cluster works in parallel.
6.  **Background Compute:** Each laptop runs its task silently in the background, streaming live output back. If a node disconnects, the task is automatically **re-queued to another node** (up to 3 retries).
7.  **Active-User Veto (Abort):** While a task runs, the worker watches for a **burst of deliberate input** — keystrokes, clicks, or scrolls (a configurable threshold within a short window; *mere mouse-movement does not count*). When a real burst is detected, it issues an **AbortTask** that actually **kills the remote subprocess**, instantly handing the machine back to the human.

---

## 5. MEASURABLE OUTCOMES (Success Criteria)
*If they ask: "How are you going to prove this is successful?"*

1.  **≥ 20% Carbon Reduction:** ✅ **Measured.** The Carbon Proof ledger compares a naive run-on-submit baseline against GridMind's actual run-time emissions and reports real grams + % saved.
2.  **High Undisrupted Success Rate:** ✅ **Validated.** Our Observer AI hits **99.2% accuracy on a held-out test set**, and the burst-detection active-user veto kills tasks the moment a human deliberately returns.
3.  **< 10 Millisecond AI:** ✅ **Validated.** DQN inference takes **~4ms** on CPU via PyTorch.
4.  **< 2% Overhead:** ✅ **Validated.** Node agents use **<2% CPU**.

---

## Appendix: Honest Technical Notes (in case the panel probes the stack)

*   **Observer AI:** scikit-learn **RandomForestClassifier**, *supervised*, 80/20 split, **99.2% held-out** + configurable temporal smoothing + heuristic fallback. (Not DBSCAN/K-Means, not unsupervised.)
*   **Dispatcher AI:** PyTorch **Dueling Double DQN**, native **`.pt` state_dict on CPU** (no ONNX), <10ms inference.
*   **Database:** hand-rolled async **aiosqlite** (raw SQL) in WAL mode (not SQLAlchemy).
*   **Carbon:** **marginal emissions (WattTime CO2_MOER)**, **8,929 real CAISO rows** replayed with a configurable fast-forward stride.
*   **Auto-retrain:** optional and **OFF by default** (self-supervised on the model's own labels; enable with `GRIDMIND_ENABLE_RETRAIN=1`). We do not claim an always-on retrain loop.
