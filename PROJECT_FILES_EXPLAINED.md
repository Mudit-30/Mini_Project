# GridMind Project File Explainer

This document provides a comprehensive overview of the files and directories in the GridMind project, explaining their purpose and function within the system architecture.

## 🚀 Root Directory

| File / Directory | Description |
| :--- | :--- |
| `start_gridmind.py` | The main production orchestrator. Launches the FastAPI backend, Next.js frontend (production mode), and a local node agent in a single synchronized process. |
| `simulate_nodes.py` | A script used to mock multiple node agents simultaneously for testing the scalability and data handling of the central server. |
| `requirements.txt` | Lists all Python dependencies required for the project (FastAPI, SQLAlchemy, gRPC, Scikit-learn, etc.). |
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
| `telemetry_pb2.py` | Generated Python code for telemetry message serialization. |
| `telemetry_pb2_grpc.py` | Generated Python code for the gRPC telemetry service interface. |

---

## 🧠 Central Intelligence Server (`gridmind_server/`)

The heart of the system, managing nodes, data, and AI decisions.

### `app/` (Core Logic)

| File / Subdir | Description |
| :--- | :--- |
| `main.py` | The entry point for the FastAPI web server. Defines API endpoints and integrates various modules. |
| `grpc_server.py` | Implements the gRPC service that nodes connect to for submitting telemetry and registering themselves. |
| `registry.py` | Manages node lifecycle, including registration, heartbeats, and status monitoring. |
| `websockets.py` | Handles real-time telemetry relaying to the frontend dashboard using WebSockets. |
| `core/config.py` | Hardcoded and environment-based configuration settings for the server. |
| `db/database.py` | Defines the database schema (SQLAlchemy models) for telemetry history, node status, and configuration. |

### `app/ml/` (AI & Machine Learning)

| File | Description |
| :--- | :--- |
| `observer_inference.py` | Logic for real-time inference using the "Observer" model to detect if a workstation is truly idle. |
| `observer_trainer.py` | Scripts for training and fine-tuning the unsupervised learning models (DBSCAN/K-Means). |
| `dispatcher_inference.py` | PyTorch-based inference engine for the DQN Dispatcher AI. Uses robust `state_dict` loading. |
| `dispatcher_trainer.py` | Training script for the Deep Reinforcement Learning (DQN) Dispatcher agent. |

### `app/jobs/` (Background Tasks)

| File | Description |
| :--- | :--- |
| `retrain.py` | A scheduled background job that periodically retrains models based on new telemetry data. |
| `dispatcher_loop.py` | The heart of the dispatch cycle. Orchestrates tasks via AI decisions, handles the real carbon intensity playback, and includes "Demo Mode" fast-forwarding logic. |

---

## 📊 Frontend Dashboard (`frontend/`)

A Next.js-powered visual interface.

| File / Directory | Description |
| :--- | :--- |
| `src/app/page.tsx` | The main dashboard page displaying real-time cluster health, node stats, and carbon footprint visualization. |
| `src/app/layout.tsx` | The root layout providing navigation, themes, and global components. |
| `src/app/globals.css` | Global styling including TailwindCSS directives and custom glassmorphism effects. |

---

## 🛠️ Ancillary Directories

| Directory | Description |
| :--- | :--- |
| `protos/` | Contains the `.proto` definitions that define the data schema for gRPC communication between nodes and the server. |
| `scripts/` | Helper scripts for demonstrations (e.g., `demonstrate_observer.py`) and development utilities. |
| `data/` | Storage for training datasets, including `watttime_carbon_data_CAISO_NORTH.csv` (8,929 rows of real grid history). |
| `models/` | The persistent storage directory for serialized AI models (`.pkl` or `.pt` files). |
| `tests/` | Unit and integration tests, particularly for the machine learning components and core server logic. |
| `docs/` | Additional setup guides and architectural diagrams (e.g., `setup_teammates.md`). |
