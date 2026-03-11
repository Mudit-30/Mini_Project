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
            print(f"      Launching Node: {node_id}")
            # We override node_id by setting an environment variable or passing an arg
            # Looking at agent.py, it uses socket.gethostname(). 
            # I'll modify agent.py briefly to accept a --node-id flag for better simulation.
            
            cmd = [sys.executable, str(agent_script), "--node-id", node_id]
            proc = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT / "gridmind_node"))
            processes.append(proc)
            time.sleep(1) # Stagger connections

        print("\n🚀 Simulation running. Check the dashboard at http://localhost:3000")
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
