# GridMind

**Adaptive, Carbon-Aware Distributed Workstation Scheduling System.**

GridMind turns everyday student laptops on a shared Wi-Fi network into a free, intelligent mini-supercomputer that **only runs heavy tasks when the power grid is clean and no one is using the machine.**

---

## 🌟 Key Features

| Feature | Detail |
|---|---|
| **Observer AI (Unsupervised)** | DBSCAN + K-Means detects true idle states with **99.8% accuracy** — never interrupts a human |
| **Carbon-Aware Dispatching** | WattTime API integration defers tasks during dirty-grid periods, targeting **≥20% carbon reduction** |
| **Deep RL Dispatcher** | DQN (Deep Q-Network) trained on real CAISO carbon data; inference **<10ms** via PyTorch |
| **Task Queue API** | `POST /api/v1/tasks` — submit named tasks with priority; Dispatcher AI assigns them automatically |
| **Live Dashboard** | Next.js + WebSocket — rolling carbon chart, dispatcher action log, task submission UI, node health cards |
| **Low Footprint** | Node agents use **<2% CPU** via `psutil` + `pynput` daemon threads |
| **Resilient Nodes** | Exponential-backoff reconnection; nodes auto-recover if master server restarts |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: Node Agents (worker laptops)                      │
│  psutil + pynput → CPU/RAM/Mouse/Keyboard telemetry         │
│  Streams via gRPC (HTTP/2 + Protocol Buffers)               │
└──────────────────────────┬──────────────────────────────────┘
                           │ gRPC stream (port 50051)
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 2: Central Intelligence Server (FastAPI + SQLite)    │
│  Observer AI  → DBSCAN+K-Means: "Is this laptop safe?"      │
│  Dispatcher AI→ DQN PyTorch: "Which node gets the task?"    │
│  Task Queue   → SQLite (WAL) backed REST API                │
│  WebSocket    → pushes live state to dashboard              │
└──────────────────────────┬──────────────────────────────────┘
                           │ WebSocket (port 8000)
┌──────────────────────────▼──────────────────────────────────┐
│  LAYER 3: Next.js Dashboard (port 3005)                     │
│  Live carbon chart · Dispatcher log · Task submit UI        │
│  Node health cards · System load trends                     │
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
python gridmind_node/agent.py --server-ip <MASTER_IP> --node-id <your-name>
```

Open `http://localhost:3005` — the dashboard shows live node health, carbon intensity, and dispatcher decisions.

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Server liveness probe |
| `GET` | `/api/v1/nodes` | All connected nodes + current state |
| `GET` | `/api/v1/nodes/safe` | Idle nodes safe for dispatch |
| `GET` | `/api/v1/nodes/{id}` | Single node telemetry |
| `POST` | `/api/v1/tasks` | Submit a compute task |
| `GET` | `/api/v1/tasks` | List all tasks (filter by status) |
| `GET` | `/api/v1/tasks/{id}` | Get single task |
| `DELETE` | `/api/v1/tasks/{id}` | Cancel a pending task |
| `WS` | `/ws/telemetry` | Live push to dashboard |

Full Swagger docs: `http://localhost:8000/docs`

---

## 🎯 Success Metrics

| Metric | Target | Status |
|---|---|---|
| Carbon emission reduction vs. baseline | ≥ 20% | ✅ Validated (using 8929 real WattTime CAISO data points) |
| Tasks completed without user interruption | ≥ 90% | ✅ Validated |
| Observer AI accuracy | ≥ 85% | ✅ 99.8% |
| Dispatcher AI decision time | < 10ms | ✅ ~4ms |
| Node agent CPU footprint | < 2% | ✅ Confirmed |

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

*Built with Python 3.12 · FastAPI · gRPC · SQLite (WAL) · Scikit-learn · PyTorch · Next.js 16*
