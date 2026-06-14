"""
GridMind demo task submitter.

Batch-submits the three vetted demo scripts to the running server so you can
watch them dispatch and run on the dashboard. Dependency-free (stdlib only).

Usage:
    python demo_tasks/submit_tasks.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

API_URL = "http://localhost:8000/api/v1/tasks"


def submit_task(filepath: str, name: str, priority_str: str = "deferrable") -> None:
    with open(filepath, "r", encoding="utf-8") as f:
        script_content = f.read()

    payload = {
        "name": name,
        "script": script_content,
        "priority_str": priority_str,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )

    print(f"Submitting {os.path.basename(filepath)} (priority={priority_str})...")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        task = result.get("task", {})
        print(f"  -> queued: task_id={task.get('task_id')} status={task.get('status')}\n")
    except urllib.error.URLError as e:
        print(f"  -> ERROR: could not reach GridMind server at {API_URL}: {e}")
        print("     Is the backend running?  python start_gridmind.py")
        sys.exit(1)
    except Exception as e:
        print(f"  -> Failed to submit task: {e}\n")


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))

    print("=== GridMind Demo Task Submitter ===\n")

    # (filename, display name, priority) — mixes tiers to exercise the dispatcher:
    #   urgent     -> runs immediately on any idle node (bypasses carbon)
    #   deferrable -> waits for a clean-grid window
    files = [
        ("01_calculate_pi.py", "Monte Carlo Pi Estimation", "deferrable"),
        ("02_mock_ml_training.py", "Mock Neural-Net Training", "urgent"),
        ("03_financial_backtest.py", "Algo-Trading Backtest", "best_effort"),
    ]

    for filename, name, priority in files:
        filepath = os.path.join(current_dir, filename)
        if os.path.exists(filepath):
            submit_task(filepath, name, priority)
            time.sleep(1)
        else:
            print(f"Could not find {filename}")

    print("All tasks submitted. Watch them dispatch on the dashboard (http://localhost:3005).")
