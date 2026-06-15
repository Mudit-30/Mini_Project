# GridMind — Team Update & Working Manual
**Last Updated:** June 13, 2026 (Feature-Complete Demo Build)
**Project Status:** 💎 Production Demo Ready — Real Remote Execution, Carbon Proof & Fault Tolerance Live

---

## 🧭 What Are We Building?

**GridMind** is an adaptive, carbon-aware distributed workstation scheduling system. In plain English:

> We are turning ordinary student laptops on a shared Wi-Fi network into a free, intelligent mini-supercomputer that **only runs heavy tasks when the power grid is clean and no one is using the machine.**

There are four things that make GridMind different from anything else out there:
1. It works on **consumer laptops** (not data centers)
2. It uses **AI to detect user presence** — not a simple CPU threshold
3. It optimizes on **marginal grid carbon** (WattTime MOER; 8,929 rows of real CAISO history) before dispatching any task
4. It **actually runs real workloads** across the cluster — remote execution, fault-tolerant re-dispatch, and data-parallel job splitting (with a configurable carbon-replay fast-forward for demos)

---

## 🚀 Recent Upgrades (Now Done & Tested)

GridMind moved from "decides where a task *would* run" to **actually running real workloads end-to-end**:

- **Remote task execution** — submit a shell command, a `.py` upload, or a ZIP project; the server picks a safe idle node and streams live stdout back. Urgent tasks run immediately; deferrable tasks wait for a clean grid.
- **Battery & thermal protection** — a node is skipped (marked **"⛔ Protected"**) only if it's on battery **and below 30% charge**, or above 85 °C. A healthy on-battery laptop still gets work, so the cluster runs even with nobody plugged in. Active-user input also vetoes dispatch.
- **Fault-tolerant re-dispatch** — if a node drops mid-task, the task is re-queued (≤ 3 retries), tried on another node, and only then fails *honestly* with a real status.
- **Data-parallel job splitting** — split a job into N chunks (`GRIDMIND_CHUNK_INDEX` / `GRIDMIND_CHUNK_COUNT`), fan one chunk out per free node, and report a **measured speedup** when ≥ 2 nodes are available.
- **Marginal-emissions Carbon Proof** — every completed task reports emissions at submit-time vs. actual run-time (~50 W draw), showing **gCO₂ saved + % reduction** in tangible units.
- **Honest results** — real exit codes / statuses everywhere; cancelling a task sends `AbortTask` and kills the remote process.
- **Observer metadata endpoint** — exposes held-out accuracy + confusion matrix for the dashboard.

---

## 🏗️ System Architecture (3 Layers)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Node Agents (worker laptops)                      │
│  psutil + pynput → CPU, RAM, keyboard, mouse, battery, temp │
│  Streams telemetry out via gRPC; runs tasks locally :50052  │
└──────────────────────────┬──────────────────────────────────┘
                           │ gRPC telemetry stream → master :50051
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 2: Central Intelligence Server (master laptop)       │
│  FastAPI :8000 + async gRPC — in-memory registry + queue    │
│  Dispatcher loop every 2s; SQLite (WAL) via aiosqlite       │
│  Replays real CAISO marginal-emissions (WattTime CO2_MOER)  │
└──────────────────────────┬──────────────────────────────────┘
                           │ ML decisions
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 3: ML Decision Layer                                 │
│  Observer AI  → RandomForest: "Is this laptop safe?"       │
│  Dispatcher AI → DQN (Deep Q-Network): "Which one gets it?"│
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Folder Structure

```
Mini_Project/
├── data/
│   ├── generate_dataset.py      ← Script to regenerate the dataset
│   └── telemetry_dataset.csv    ← 10,000-row training dataset (see below)
│
├── gridmind_node/
│   ├── agent.py                 ← Node agent (telemetry + gRPC, runs on workers)
│   └── executor.py              ← Runs uploaded scripts/.py/ZIP locally (:50052)
│
├── gridmind_server/
│   ├── app/
│   │   ├── main.py              ← FastAPI entry point (:8000)
│   │   ├── core/                ← Business logic & config
│   │   ├── carbon/              ← CAISO marginal-emissions replay
│   │   └── db/                  ← Hand-rolled async aiosqlite layer (raw SQL)
│   └── alembic/                 ← (scaffolded, currently unused)
│
├── GridMind_Team_Onboarding.md  ← Original architecture doc
├── TEAM_UPDATE.md               ← This file — current working status
└── requirements.txt             ← All Python dependencies
```

---

## 📊 The Dataset — `data/telemetry_dataset.csv`

This is the labeled dataset used to train the (supervised) Observer AI via an 80/20 train/test split.

### Why we made our own dataset
There is no public dataset of laptop telemetry with carbon-grid data that matches our exact setup. So we generated one synthetically using **realistic statistical distributions** (the same way research teams in production do when hardware isn't deployed yet). Once our node agents are running on real laptops, we will **replace/augment** this data with real telemetry.

### Dataset Details

| Property | Value |
|---|---|
| **Total Rows** | 10,000 |
| **Total Columns** | 8 |
| **File** | `data/telemetry_dataset.csv` |

### Features (Columns)

| Column | Type | Description |
|---|---|---|
| `cpu_usage_pct` | float | CPU usage percentage (0–100) |
| `ram_usage_pct` | float | RAM usage percentage (0–100) |
| `kb_events_per_min` | int | Keyboard events counted per minute |
| `mouse_events_per_min` | int | Mouse move/click events per minute |
| `net_io_bytes` | float | Network I/O bytes in the sample window |
| `process_count` | int | Number of running OS processes |
| `carbon_intensity_gco2` | float | Grid carbon intensity in gCO₂/kWh (from WattTime) |
| `label` | int | **The target label** — see below |

### Labels (What the AI Must Learn to Classify)

| Label | Class Name | Count | Meaning |
|---|---|---|---|
| `0` | `idle` | 4,000 | ✅ Machine is unattended — **safe to dispatch a task** |
| `1` | `active_user` | 4,000 | 🚫 Human is actively typing/clicking — **do not disturb** |
| `2` | `busy_hardware` | 2,000 | ⚠️ High CPU/RAM from background process — **unsafe to use** |

### What the distributions look like

| Feature | Idle (label=0) | Active User (label=1) | Busy HW (label=2) |
|---|---|---|---|
| CPU % | ~6% (low) | ~35% (medium) | ~78% (high) |
| RAM % | ~30% (low) | ~55% (medium) | ~75% (high) |
| Keyboard events/min | ~1 | ~120 | ~1 |
| Mouse events/min | ~2 | ~150 | ~1 |

The key insight: **busy_hardware looks like idle on keyboard/mouse but has high CPU/RAM** — this is exactly why a simple "CPU < 25%" threshold fails, and why we train a multi-feature classifier (RandomForest) instead.

### How to Regenerate the Dataset
```bash
cd d:\Mini_Project
python data/generate_dataset.py
```

---

## ✅ What Has Been Done (Progress Tracker)

| Phase | Task | Status |
|---|---|---|
| 1 | Central FastAPI server skeleton | ✅ Done |
| 1 | SQLite (WAL) DB via hand-rolled aiosqlite layer | ✅ Done |
| 1 | Node agent telemetry collection (`agent.py`) | ✅ Done (with pynput) |
| 1 | Observer AI training dataset | ✅ Done (10k rows) |
| 2 | gRPC communication between nodes and server | ✅ Done |
| 2 | RandomForest Observer AI training (supervised, 80/20 split) | ✅ Done (99.2% held-out) |
| 2 | Temporal smoothing over Observer predictions (configurable window, default 6) | ✅ Done |
| 2 | Self-supervised retrain pipeline | ✅ Done (OFF by default; opt-in via `GRIDMIND_ENABLE_RETRAIN=1`) |
| 3 | DQN Dispatcher simulation environment | ✅ Done |
| 3 | DQN training with carbon penalty rewards | ✅ Done (Dueling Double DQN, PyTorch) |
| 3 | PyTorch `.pt` state_dict on CPU for <10ms inference | ✅ Done |
| 4 | Next.js dashboard + WebSocket live charts | ✅ Done (Port 3005) |
| 4 | Live Carbon Intensity chart (rolling window) | ✅ Done |
| 4 | Dispatcher Action Log (live event feed) | ✅ Done |
| 4 | Task Queue API (`POST /api/v1/tasks`) | ✅ Done |
| 4 | Task Submit UI on dashboard | ✅ Done |
| 4 | Dispatcher reads real DB queue | ✅ Done |
| 5 | Remote task execution (shell / `.py` upload / ZIP → idle node → live stdout) | ✅ Done |
| 5 | Active-user veto + battery & thermal protection ("⛔ Protected") | ✅ Done |
| 5 | Fault-tolerant re-dispatch (node drop → re-queue ≤3 retries → honest fail) | ✅ Done |
| 5 | Data-parallel job splitting (N chunks, one-per-free-node, measured speedup) | ✅ Done |
| 5 | Marginal-emissions Carbon Proof (submit vs run-time gCO₂ saved + %) | ✅ Done |
| 5 | Honest results + cancel→AbortTask kills remote process | ✅ Done |
| 5 | Observer metadata endpoint (held-out accuracy + confusion matrix) | ✅ Done |
| 5 | 3-laptop real deployment & 24hr test | 🟡 In Progress |

---

## 🎯 Success Metrics We Must Hit

| Metric | Target |
|---|---|
| Carbon emission reduction vs. baseline | ≥ 20% |
| Tasks completed without user interruption | ≥ 90% |
| Observer AI accuracy (vs. human observation) | ≥ 85% |
| Dispatcher AI decision time | < 10ms |
| Node agent CPU footprint while idle | < 2% |

---

## 🔧 Tech Stack Reference

| Layer | Technology |
|---|---|
| Backend Server | Python 3.12, FastAPI |
| Database | SQLite (WAL mode) via hand-rolled aiosqlite layer (raw SQL, not SQLAlchemy) |
| Node ↔ Server comms | gRPC (telemetry), REST (task submit), WebSocket (dashboard) |
| Observer AI | scikit-learn `RandomForestClassifier` — **supervised**, 80/20 train/test split, **99.2% held-out** + temporal smoothing (configurable window, default 6) |
| Dispatcher AI | PyTorch **Dueling Double DQN**, native `.pt` **state_dict loaded on CPU** for <10 ms inference (no ONNX) |
| Carbon Data | **Marginal emissions** — WattTime `CO2_MOER`; **8,929 real CAISO rows** replayed (configurable stride); ARIMA fit at startup |
| Frontend Dashboard | Next.js (Port 3005, WebSocket) |

---

## ⚡ Immediate Next Steps (This Week)

1. **Hardware Deployment** — Run `start_gridmind.py` on the master laptop and `agent.py --server <MASTER_IP>:50051` on each teammate's machine to begin 24-hour live validation.
2. **Validation Metrics** — Monitor the dashboard for 24 hours and record carbon savings %, task completion rate, and inference latency.
3. **Project Defense** — Use `Project_Review_Prep.md` and `Technical_Implementation_Simple.md` as the Q&A reference.

---

## 🛠️ Setup Instructions (For New Team Members)

```bash
# 1. Clone the repo
git clone <your-github-repo-url>
cd Mini_Project

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # Mac/Linux

# 3. Install all dependencies
pip install -r requirements.txt

# 4. Run the GridMind System (Master Only)
python start_gridmind.py

# 5. Connect Teammate Laptops (Worker Nodes)
# Ask the Master for their current Node IP (shown in start_gridmind.py logs)
cd gridmind_node
python agent.py --server <MASTER_IP>:50051 --node-id <YOUR_NAME>
```

> **Network / firewall:** The **master** must allow **inbound :50051** (telemetry gRPC).
> Each **worker** must allow **inbound :50052** (so the master can dispatch tasks to it).
> Workers can run **on battery** — only a low (**<30%**) or hot (**>85°C**) laptop is auto-skipped by battery/thermal protection.

---

## 🛠️ How to Connect Your Laptop (Teammates)

To join the GridMind cluster, you only need to run the **Node Agent**. Follow these steps:

1. **Prerequisites**: Ensure you have Python 3.10+ installed, you are on the **same Wi-Fi network** as the Master laptop, and your firewall allows **inbound :50052** (the master dispatches tasks to your machine on this port). Battery is fine — just keep charge **above 30%**.
2. **Setup**:
   ```bash
   git clone <repo-url>
   cd Mini_Project
   pip install -r requirements.txt
   ```
3. **Run the Agent**:
   Find the **Master Node IP** (e.g., `10.118.95.208`) from the Master laptop's `start_gridmind.py` output. Then run:
   ```bash
   python gridmind_node/agent.py --server 10.118.95.208:50051 --node-id teammate_name
   ```
4. **Verify**: Open `http://<MASTER_IP>:3005` in your browser to see your laptop pop up on the dashboard! Once idle and on a clean grid, the master can dispatch real tasks to you and stream their output back.

> **Battery is OK:** a node is only skipped (shown as **"⛔ Protected"**) when it's on battery **and below 30% charge**, or above 85 °C. A healthy on-battery laptop still receives tasks.

---

*For architecture details, see [`GridMind_Team_Onboarding.md`](./GridMind_Team_Onboarding.md)*  
*For dataset code, see [`data/generate_dataset.py`](./data/generate_dataset.py)*
