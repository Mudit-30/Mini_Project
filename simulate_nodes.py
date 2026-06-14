"""
simulate_nodes.py
==================
Simulates multiple GridMind nodes connecting to the local server.
Useful for verifying multi-node UI and backend scalability.
"""
import subprocess
import sys
import time
from pathlib import Path

def run_simulation(num_nodes=3):
    PROJECT_ROOT = Path(__file__).parent.absolute()
    agent_script = PROJECT_ROOT / "gridmind_node" / "agent.py"
    
    print(f"[*] Starting simulation with {num_nodes} nodes...")
    processes = []

    try:
        for i in range(num_nodes):
            node_id = f"Teammate_{i+1}"
            # Each simulated agent on THIS machine needs its own task-server port
            # (they'd otherwise all collide on 50052 and only one could bind).
            task_port = 50052 + i
            print(f"      Launching Node: {node_id} (task-port {task_port})")
            cmd = [
                sys.executable, str(agent_script),
                "--node-id", node_id,
                "--task-port", str(task_port),
            ]
            proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT / "gridmind_node"))
            processes.append(proc)
            time.sleep(1)  # Stagger connections

        # NOTE: the server currently dispatches to every node on the default port
        # (50052), so on a single machine only the first node actually receives
        # tasks. This script is for telemetry/UI scale testing; true multi-node
        # dispatch is exercised with real laptops (each on its own 50052).
        print("\n🚀 Simulation running. Check the dashboard at http://localhost:3005")
        print("Press Ctrl+C to stop simulation.")
        
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping simulation...")
    finally:
        for proc in processes:
            proc.terminate()
        print("Simulation stopped.")

if __name__ == "__main__":
    run_simulation()
