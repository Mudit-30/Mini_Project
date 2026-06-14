import subprocess
import sys
import os
import time
import socket
import urllib.request
import urllib.error

import psutil
from pathlib import Path

# --- Configuration ---
PORTS = {"Backend": 8000, "Frontend": 3005, "gRPC": 50051, "NodeTaskServer": 50052}
BACKEND_READY_TIMEOUT = 60   # seconds — ARIMA fit can take ~15-20s on startup
BACKEND_URL = "http://127.0.0.1:8000/api/v1/health"

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
        if sys.platform == "win32":
            try:
                # Find the PID holding the port using netstat
                output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True).decode()
                for line in output.strip().split('\n'):
                    if 'LISTENING' in line:
                        parts = line.strip().split()
                        if len(parts) >= 5:
                            pid = int(parts[-1])
                            if pid > 0:
                                print(f"      [System] Terminating PID {pid} on port {port}...")
                                subprocess.call(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        else:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    for conn in proc.net_connections(kind='all'):
                        if conn.laddr.port == port:
                            print(f"      [System] Terminating PID {proc.info['pid']} on port {port}...")
                            p = psutil.Process(proc.info['pid'])
                            for child in p.children(recursive=True):
                                child.kill()
                            p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    continue

def wait_for_port_free(port: int, timeout: float = 10.0) -> bool:
    """Wait until the given port is no longer bound (after kill)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        result = s.connect_ex(("127.0.0.1", port))
        s.close()
        if result != 0:   # port is free
            return True
        time.sleep(0.5)
    return False

import http.client
from urllib.parse import urlparse

def wait_for_backend(url: str, timeout: float = BACKEND_READY_TIMEOUT) -> bool:
    """Poll the /health endpoint until it responds 200 or timeout."""
    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path or '/'
    deadline = time.time() + timeout
    print(f"      Waiting for backend at {url}...", end="", flush=True)
    while time.time() < deadline:
        try:
            conn = http.client.HTTPConnection(host, timeout=2)
            conn.request("GET", path)
            resp = conn.getresponse()
            if resp.status == 200:
                print(" OK")
                conn.close()
                return True
            conn.close()
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(1)
    print(" TIMEOUT")
    return False

def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(('localhost', port)) == 0

def run():
    PROJECT_ROOT = Path(__file__).parent.absolute()
    local_ip = get_local_ip()

    print("\n" + "=" * 70)
    print("   [*] GRIDMIND: MULTI-SERVICE ORCHESTRATOR")
    print(f"   [IP] Master Node IP: {local_ip}")
    print("=" * 70)

    # 1. Pre-flight: kill any lingering processes on our ports
    print("\n[Pre-flight] Clearing ports...")
    kill_port_owners(PORTS.values())

    # Wait for critical ports to be free before starting
    for name, port in PORTS.items():
        freed = wait_for_port_free(port, timeout=8.0)
        if not freed:
            print(f"      [WARNING] Port {port} ({name}) may still be in use — continuing anyway.")
        else:
            print(f"      Port {port} ({name}) is free.")

    processes = []

    try:
        # 2. Start Backend
        print("\n[1/3] Launching Backend Server (FastAPI + gRPC)...")
        backend_env = {
            **os.environ,
            "PYTHONPATH": str(PROJECT_ROOT / "gridmind_server"),
            "OMP_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            # Load the real RandomForest + DQN models (matches the demo's claims and
            # makes the active-user veto fire on real input). Falls back to the
            # heuristic if loading fails. Set GRIDMIND_LOAD_ML=0 on a low-RAM master.
            "GRIDMIND_LOAD_ML": os.environ.get("GRIDMIND_LOAD_ML", "1"),
        }
        backend_log = open(PROJECT_ROOT / "backend.log", "w", encoding="utf-8")
        backend_cmd = [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--app-dir", str(PROJECT_ROOT / "gridmind_server"),
            "--host", "0.0.0.0",
            "--port", "8000",
            "--reload",
        ]
        proc_backend = subprocess.Popen(
            backend_cmd, env=backend_env,
            stdout=backend_log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        processes.append(("Backend", proc_backend, backend_log))

        # Wait until backend is actually serving requests
        if not wait_for_backend(BACKEND_URL):
            print("   [ERROR] Backend failed to start within timeout — check backend.log")
            raise SystemExit(1)

        # 3. Start Frontend
        print("\n[2/3] Launching Frontend Dashboard (Port 3005)...")
        frontend_dir = PROJECT_ROOT / "frontend"

        # Clean environment — remove variables that confuse Next.js resolver
        frontend_env = os.environ.copy()
        for k in ["INIT_CWD", "NODE_ENV", "PYTHONPATH"]:
            frontend_env.pop(k, None)

        # Set NODE_OPTIONS to increase heap and suppress OOM on large builds
        frontend_env["NODE_OPTIONS"] = "--max-old-space-size=2048"

        frontend_log = open(PROJECT_ROOT / "frontend.log", "w", encoding="utf-8")
        frontend_cmd = f"{sys.executable.replace('python.exe', 'node.exe')} node_modules/next/dist/bin/next dev --port 3005"
        # Fallback if node isn't near python (though npm run dev assumes node is in PATH)
        frontend_cmd = "node node_modules/next/dist/bin/next dev --port 3005"
        proc_frontend = subprocess.Popen(
            frontend_cmd, cwd=str(frontend_dir), shell=True, env=frontend_env,
            stdout=frontend_log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        processes.append(("Frontend", proc_frontend, frontend_log))

        # 4. Start Node Agent (only after backend gRPC is ready)
        print("\n[3/3] Launching Local Node Agent...")
        # Wait for gRPC port to be open before starting the agent
        grpc_ready = False
        for _ in range(15):
            if is_port_open(50051):
                grpc_ready = True
                break
            time.sleep(1)
        if not grpc_ready:
            print("      [WARNING] gRPC port 50051 not responding — agent may retry automatically.")

        agent_script = PROJECT_ROOT / "gridmind_node" / "agent.py"
        agent_log = open(PROJECT_ROOT / "agent.log", "w", encoding="utf-8")
        proc_agent = subprocess.Popen(
            [sys.executable, str(agent_script)],
            cwd=str(PROJECT_ROOT / "gridmind_node"),
            stdout=agent_log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
        )
        processes.append(("Agent", proc_agent, agent_log))

        print("\n" + ">>" * 15)
        print("   GRIDMIND SYSTEM IS DEPLOYED")
        print(f"   Dashboard (Local):  http://localhost:3005")
        print(f"   Dashboard (Team):   http://{local_ip}:3005")
        print(f"   API Docs:           http://localhost:8000/docs")
        print("\n   [TEAMMATE COMMAND TO CONNECT NODE]")
        print(f"   python gridmind_node/agent.py --server {local_ip}:50051 --node-id \"Your Name\"")
        print(">>" * 15 + "\n")
        print("Logs: backend.log | frontend.log | agent.log")
        print("Press Ctrl+C to terminate all services.\n")

        # Monitor: restart agent if it dies, with crash-loop protection
        _frontend_restarts = 0
        _MAX_FRONTEND_RESTARTS = 3
        while True:
            time.sleep(3)
            for i, (name, proc, log) in enumerate(processes):
                if proc.poll() is not None:  # process has exited
                    print(f"\n[Monitor] {name} exited (code {proc.returncode})")
                    if name == "Agent":
                        time.sleep(2)
                        print("   Restarting Agent...")
                        log_new = open(PROJECT_ROOT / "agent.log", "a", encoding="utf-8")
                        new_proc = subprocess.Popen(
                            [sys.executable, str(agent_script)],
                            cwd=str(PROJECT_ROOT / "gridmind_node"),
                            stdout=log_new, stderr=subprocess.STDOUT,
                            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                        )
                        processes[i] = ("Agent", new_proc, log_new)
                    elif name == "Frontend":
                        _frontend_restarts += 1
                        if _frontend_restarts <= _MAX_FRONTEND_RESTARTS:
                            print(f"   Restarting Frontend ({_frontend_restarts}/{_MAX_FRONTEND_RESTARTS})... check frontend.log")
                            time.sleep(5)
                            log_new = open(PROJECT_ROOT / "frontend.log", "a", encoding="utf-8")
                            new_proc = subprocess.Popen(
                                f"npm run dev -- --port 3005",
                                cwd=str(frontend_dir), shell=True, env=frontend_env,
                                stdout=log_new, stderr=subprocess.STDOUT,
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                            )
                            processes[i] = ("Frontend", new_proc, log_new)
                        else:
                            print("   [CRITICAL] Frontend crash-looping — check frontend.log. Not restarting.")
                    elif name == "Backend":
                        print(f"   [CRITICAL] Backend crashed — check backend.log")

    except KeyboardInterrupt:
        print("\n\n[System] Graceful shutdown...")
    finally:
        for name, proc, log in processes:
            print(f"      Stopping {name}...")
            try:
                p = psutil.Process(proc.pid)
                for child in p.children(recursive=True):
                    child.kill()
                p.kill()
            except Exception:
                pass
            try:
                log.close()
            except Exception:
                pass
        print("[System] Done.")

if __name__ == "__main__":
    run()
