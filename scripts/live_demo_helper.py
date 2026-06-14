"""
scripts.live_demo_helper
========================
Starts the GridMind server and agent to show live state transitions.
"""
import subprocess
import time
import sys
import os
from pathlib import Path


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, IOError):
        pass

# Add project root to path
PROJECT_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

def run_live_demo():
    print("=" * 60)
    print("LIVE DEMO: GRIDMIND REAL-TIME INTERACTION")
    print("=" * 60)
    print("This will start the Server and the Agent concurrently.")
    print("Watch the terminal logs for 'state=' transitions.")
    print("\nINSTRUCTIONS:")
    print("1. Leave the mouse alone -> Watch for 'idle'")
    print("2. Type rapidly on your keyboard -> Watch for 'active_user'")
    print("3. (Optional) Run a heavy app like a game/render -> Watch for 'busy_hardware'")
    print("\nPress Ctrl+C to stop both.")
    print("=" * 60)

    # 1. Start Server
    server_cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(PROJECT_ROOT / "gridmind_server")]
    server_proc = subprocess.Popen(server_cmd, env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT)})

    # Wait for server to warm up
    time.sleep(3)

    # 2. Start Agent
    agent_cmd = [sys.executable, str(PROJECT_ROOT / "gridmind_node" / "agent.py")]
    agent_proc = subprocess.Popen(agent_cmd, cwd=str(PROJECT_ROOT / "gridmind_node"))

    try:
        while True:
            time.sleep(1)
            if server_proc.poll() is not None or agent_proc.poll() is not None:
                break
    except KeyboardInterrupt:
        print("\nStopping demo...")
    finally:
        agent_proc.terminate()
        server_proc.terminate()
        print("Demo stopped.")

if __name__ == "__main__":
    run_live_demo()
