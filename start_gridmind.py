"""
start_gridmind.py
=================
Simplified, robust startup script for the GridMind system.
Starts the FastAPI Backend (8000), Next.js Frontend (3005), and Local Node Agent.
"""
import subprocess
import sys
import os
import time
import socket
import psutil
from pathlib import Path

# --- Configuration ---
# Use 3005 for frontend to safely avoid conflicts with other local projects
PORTS = {"Backend": 8000, "Frontend": 3005, "gRPC": 50051}

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def kill_port_owners(ports):
    for port in ports:
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for conn in proc.net_connections(kind='inet'):
                    if conn.laddr.port == port:
                        print(f"      [System] Terminating PID {proc.info['pid']} on port {port}...")
                        p = psutil.Process(proc.info['pid'])
                        for child in p.children(recursive=True):
                            child.kill()
                        p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('localhost', port)) == 0

def run():
    PROJECT_ROOT = Path(__file__).parent.absolute()
    local_ip = get_local_ip()
    
    print("\n" + "=" * 70)
    print("   🌐 GRIDMIND: MULTI-SERVICE ORCHESTRATOR")
    print(f"   📍 Master Node IP: {local_ip}")
    print("=" * 70)

    # 1. Pre-flight Check
    kill_port_owners(PORTS.values())

    processes = []

    try:
        # 2. Start Backend
        print("\n[1/3] Launching Backend Server (FastAPI + gRPC)...")
        backend_env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "gridmind_server")}
        backend_cmd = [
            sys.executable, "-m", "uvicorn", "app.main:app", 
            "--app-dir", str(PROJECT_ROOT / "gridmind_server"), 
            "--port", "8000"
        ]
        proc_backend = subprocess.Popen(
            backend_cmd, env=backend_env, 
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        processes.append(("Backend", proc_backend))

        # Wait a moment for backend
        time.sleep(3)

        # 3. Start Frontend
        print("\n[2/3] Launching Frontend Dashboard (Port 3005)...")
        frontend_dir = PROJECT_ROOT / "frontend"
        
        # Clean environment to prevent Next.js from resolving paths in parent dir
        frontend_env = os.environ.copy()
        for k in ["INIT_CWD", "NODE_ENV", "PYTHONPATH"]:
            frontend_env.pop(k, None)

        frontend_cmd = "npm run dev -- --port 3005"
        proc_frontend = subprocess.Popen(
            frontend_cmd, cwd=str(frontend_dir), shell=True, env=frontend_env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        processes.append(("Frontend", proc_frontend))

        # 4. Start Local Agent
        print("\n[3/3] Launching Local Node Agent...")
        agent_script = PROJECT_ROOT / "gridmind_node" / "agent.py"
        proc_agent = subprocess.Popen(
            [sys.executable, str(agent_script)], cwd=str(PROJECT_ROOT / "gridmind_node"),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        processes.append(("Agent", proc_agent))

        print("\n" + "🚀" * 15)
        print("   GRIDMIND SYSTEM IS DEPLOYED")
        print(f"   Dashboard:  http://localhost:3005")
        print(f"   Master IP:  http://{local_ip}:3005 (For teammates)")
        print(f"   API Docs:   http://localhost:8000/docs")
        print("🚀" * 15 + "\n")

        print("Press Ctrl+C to terminate services.\n")

        # Keep alive
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n[System] Graceful shutdown...")
    finally:
        for name, proc in processes:
            print(f"      Stopping {name}...")
            try:
                p = psutil.Process(proc.pid)
                for child in p.children(recursive=True): child.kill()
                p.kill()
            except: pass
        print("[System] Done.")

if __name__ == "__main__":
    run()
