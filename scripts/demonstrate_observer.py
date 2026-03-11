"""
scripts.demonstrate_observer
============================
Proves the GridMind Observer AI correctly classifies laptop states.
"""
import sys
import os
from pathlib import Path

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, IOError):
        pass

# Add project root to path
PROJECT_ROOT = Path(__file__).parents[1]
sys.path.append(str(PROJECT_ROOT))

import logging
from gridmind_server.app.ml.observer_trainer import run_training
from gridmind_server.app.ml.observer_inference import ObserverInference

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("demo")

def run_demo():
    print("=" * 60)
    print("DEMO: GRIDMIND OBSERVER AI (Objective 3)")
    print("Goal: Prove we can detect User-Awareness via ML.")
    print("=" * 60)

    # 1. Train Model
    print("\n[Step 1] Training the Observer AI model...")
    run_training()

    # 2. Load Model
    print("\n[Step 2] Loading inference engine...")
    observer = ObserverInference()

    # 3. Test Scenarios
    scenarios = [
        {
            "name": "IDLE (Safe to Dispatch)",
            "data": {
                "cpu_usage_pct": 5.0,
                "ram_usage_pct": 25.0,
                "kb_events_per_min": 0,
                "mouse_events_per_min": 1,
                "net_io_bytes": 1024,
                "process_count": 80,
                "carbon_intensity_gco2": 0.0
            }
        },
        {
            "name": "ACTIVE USER (Do Not Disturb)",
            "data": {
                "cpu_usage_pct": 35.0,
                "ram_usage_pct": 55.0,
                "kb_events_per_min": 150,
                "mouse_events_per_min": 200,
                "net_io_bytes": 50000,
                "process_count": 110,
                "carbon_intensity_gco2": 0.0
            }
        },
        {
            "name": "BUSY HARDWARE (Unsafe Outreach)",
            "data": {
                "cpu_usage_pct": 85.0,
                "ram_usage_pct": 80.0,
                "kb_events_per_min": 0,
                "mouse_events_per_min": 2,
                "net_io_bytes": 1000000,
                "process_count": 150,
                "carbon_intensity_gco2": 0.0
            }
        }
    ]

    print("\n[Step 3] Running Simulation Scenarios:")
    for s in scenarios:
        print(f"\n--- Scenario: {s['name']} ---")
        pred = observer.predict(s['data'])
        print(f"  Result:     {pred['state'].upper()}")
        print(f"  Label ID:   {pred['label']}")
        print(f"  Confidence: {pred['confidence']:.2%}")
        
        # Validation Logic
        expected = s['name'].split(" ")[0].lower()
        if pred['state'] == expected or (expected == "active" and pred['state'] == "active_user") or (expected == "busy" and pred['state'] == "busy_hardware"):
            print("  ✅ Status: MATCHED EXPECTATION")
        else:
            print(f"  ❌ Status: MISMATCH (Expected {expected})")

    print("\n" + "=" * 60)
    print("Demo execution complete.")
    print("=" * 60)

if __name__ == "__main__":
    run_demo()
