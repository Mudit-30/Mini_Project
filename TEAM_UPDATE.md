# GridMind — Team Update & Working Manual
**Last Updated:** March 13, 2026  
**Project Status:** 🟢 Foundation Complete — Phase 2 (Intelligence) Finalised

---

## 🧭 What Are We Building?

**GridMind** is an adaptive, carbon-aware distributed workstation scheduling system. In plain English:

> We are turning ordinary student laptops on a shared Wi-Fi network into a free, intelligent mini-supercomputer that **only runs heavy tasks when the power grid is clean and no one is using the machine.**

There are three things that make GridMind different from anything else out there:
1. It works on **consumer laptops** (not data centers)
2. It uses **AI to detect user presence** — not a simple CPU threshold
3. It **checks live carbon data** from the power grid before dispatching any task

---

## 🏗️ System Architecture (3 Layers)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Node Agents (worker laptops)                      │
│  Small Python script → collects CPU, RAM, keyboard, mouse  │
│  Streams data to server via gRPC                            │
└──────────────────────────┬──────────────────────────────────┘
                           │ gRPC telemetry stream
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 2: Central Intelligence Server (master laptop)       │
│  FastAPI + SQLite — holds task queue                        │
│  Calls WattTime API every minute for carbon data            │
└──────────────────────────┬──────────────────────────────────┘
                           │ ML decisions
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 3: ML Decision Layer                                 │
│  Observer AI  → DBSCAN + K-Means: "Is this laptop safe?"   │
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
│   └── agent.py                 ← Node agent (runs on worker laptops)
│
├── gridmind_server/
│   ├── app/
│   │   ├── main.py              ← FastAPI entry point
│   │   ├── core/                ← Business logic
│   │   └── db/                  ← Database models & sessions
│   └── alembic/                 ← Database migrations
│
├── GridMind_Team_Onboarding.md  ← Original architecture doc
├── TEAM_UPDATE.md               ← This file — current working status
└── requirements.txt             ← All Python dependencies
```

---

## 📊 The Dataset — `data/telemetry_dataset.csv`

This is the most important update. We now have a training dataset ready for the Observer AI.

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

The key insight: **busy_hardware looks like idle on keyboard/mouse but has high CPU/RAM** — this is exactly why a simple "CPU < 25%" threshold fails, and why we need unsupervised clustering.

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
| 1 | SQLite DB + Alembic migrations setup | ✅ Done |
| 1 | Node agent telemetry collection (`agent.py`) | ✅ Done (with pynput) |
| 1 | Observer AI training dataset | ✅ Done (10k rows) |
| 2 | gRPC communication between nodes and server | ✅ Done |
| 2 | DBSCAN + K-Means Observer AI training | ✅ Done (accuracy: 99.8%) |
| 2 | Auto-retrain pipeline (every 4 hours) | ✅ Done |
| 3 | DQN Dispatcher simulation environment | 🟡 In Progress |
| 3 | DQN training with carbon penalty rewards | ⬜ Not started |
| 3 | ONNX export for < 5ms inference | ⬜ Not started |
| 4 | Next.js dashboard + WebSocket live charts | ✅ Done (Port 3005) |
| 4 | 3-laptop real deployment & 24hr test | 🟡 In Progress |

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
| Backend Server | Python 3.12, FastAPI, SQLAlchemy |
| Database | SQLite (WAL mode) |
| Node ↔ Server comms | gRPC (telemetry), REST (task submit), WebSocket (dashboard) |
| Observer AI | scikit-learn (DBSCAN, K-Means) |
| Dispatcher AI | PyTorch (training) → ONNX Runtime (production inference) |
| Carbon Data API | WattTime (free academic tier) |
| Frontend Dashboard | Next.js |

---

## ⚡ Immediate Next Steps (This Week)

1. **Dispatcher Simulation** — Finalize the environment for training the DQN agent.
2. **DQN Training** — Start training sessions with historical carbon data.
3. **Hardware Deployment** — Test the automatic emergency pause on real hardware interaction.

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
python agent.py --server-ip <MASTER_IP> --node-id <YOUR_NAME>
```

---

## 🛠️ How to Connect Your Laptop (Teammates)

To join the GridMind cluster, you only need to run the **Node Agent**. Follow these steps:

1. **Prerequisites**: Ensure you have Python 3.10+ installed and you are on the **same Wi-Fi network** as the Master laptop.
2. **Setup**:
   ```bash
   git clone <repo-url>
   cd Mini_Project
   pip install -r requirements.txt
   ```
3. **Run the Agent**:
   Find the **Master Node IP** (e.g., `10.118.95.208`) from the Master laptop's `start_gridmind.py` output. Then run:
   ```bash
   python gridmind_node/agent.py --server-ip 10.118.95.208 --node-id teammate_name
   ```
4. **Verify**: Open `http://<MASTER_IP>:3005` in your browser to see your laptop pop up on the dashboard!

---

*For architecture details, see [`GridMind_Team_Onboarding.md`](./GridMind_Team_Onboarding.md)*  
*For dataset code, see [`data/generate_dataset.py`](./data/generate_dataset.py)*
