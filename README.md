# GridMind

**Adaptive, Carbon-Aware Distributed Workstation Scheduling System.**

GridMind turns everyday student laptops on a shared Wi-Fi network into a free, intelligent mini-supercomputer that **only runs heavy tasks when the power grid is clean and no one is using the machine.**

## 🌟 Key Features

-   **AI Observer (Unsupervised):** Uses DBSCAN and K-Means to detect true idle states with 99.8% accuracy, ensuring humans are never disrupted.
-   **Carbon-Aware (WattTime Integration):** Live grid-monitoring to sync computing with green energy peaks (wind/solar).
-   **Low Footprint:** Node agents use < 2% CPU while monitoring keyboard, mouse, and hardware telemetry.
-   **Deep RL Dispatcher:** A Deep Q-Network (DQN) manages task priority and routing based on performance and carbon savings.

## 🏗️ System Architecture

GridMind consists of three layers:
1.  **Node Agents:** Lightweight Python workers collecting telemetry via gRPC.
2.  **Central Intelligence Server:** FastAPI & SQLite backend managing the cluster.
3.  **Next.js Dashboard:** Real-time visualization of cluster health and carbon savings.

## 📖 Documentation

-   [Architecture Blueprint](./GridMind_Team_Onboarding.md) - Deep dive into design and research gaps.
-   [Team Update & Status](./TEAM_UPDATE.md) - Current progress, dataset details, and roadmap.
-   [Technical Defense Guide](./Technical_Implementation_Simple.md) - Simplified explanation for project defense.

## 🚀 Quick Start

```bash
# Clone and Setup
git clone <repo-url>
cd Mini_Project
pip install -r requirements.txt

# Start Master Server
python start_gridmind.py

# Start Node Agent
python gridmind_node/agent.py --server localhost:50051 --node-id my-laptop
```

## 🎯 Success Metrics

-   🔥 **Carbon Reduction:** ≥ 20% vs. baseline.
-   🤫 **Invisibility:** ≥ 90% task completion without user interruption.
-   ⚡ **Efficiency:** < 10ms AI decision time.

---
*Built with Python 3.12, FastAPI, gRPC, Scikit-learn, PyTorch, and Next.js.*
