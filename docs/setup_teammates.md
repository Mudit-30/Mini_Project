# 💻 Connecting Your Laptop to GridMind

To turn your laptop into a GridMind worker node, follow this quick guide.

## 1. Prerequisites
- **Python 3.10 or higher** installed.
- **Git** installed.
- **Same Network**: You MUST be on the same Wi-Fi/Local Network as the Master Node laptop.

## 2. Quick Setup
Open your terminal/command prompt and run:

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd Mini_Project

# 2. Setup environment (Recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Mac/Linux

# 3. Install dependencies
pip install -r requirements.txt
```

## 3. Joining the Cluster
You need the **Master Node IP Address**. Ask the person running the primary `start_gridmind.py` script for the address shown in their terminal (e.g., `10.118.95.208`).

Run the agent with your name:
```bash
python gridmind_node/agent.py --server-ip <MASTER_IP> --node-id <YOUR_NAME>
```

### Example:
If the Master IP is `10.5.1.42` and your name is `Alex`:
```bash
python gridmind_node/agent.py --server-ip 10.5.1.42 --node-id Alex
```

## 4. How to Check If It's Working
Once the script says `[SUCCESS] Logged in to GridMind...`, you are live!
- Visit the Dashboard: `http://<MASTER_IP>:3005`
- You should see a card with your name (`Alex`) showing your live CPU and Memory usage.

## ⚠️ Troubleshooting
- **Connection Refused**: Make sure the Master laptop has its firewall set to allow Python/FastAPI/gRPC traffic, or that you typed the IP correctly.
- **Missing Module**: Ensure you ran `pip install -r requirements.txt`.
