"""
GridMind Telemetry Dataset Generator
=====================================
Generates a synthetic but realistic labeled dataset that mimics
real laptop telemetry for the GridMind Observer AI.

Three States (Labels):
  0 - idle           : Machine is unattended, low resources, safe to dispatch tasks
  1 - active_user    : A human is actively typing/using the machine — DO NOT disturb
  2 - busy_hardware  : High CPU/RAM (background job running, rendering, etc.) — unsafe to dispatch

Features (matching agent.py + carbon context):
  cpu_usage_pct         : CPU usage percentage (0–100)
  ram_usage_pct         : RAM usage percentage (0–100)
  kb_events_per_min     : Keyboard events counted per minute
  mouse_events_per_min  : Mouse movement/click events per minute
  net_io_bytes          : Network I/O bytes in the last sample window
  process_count         : Number of running processes
  carbon_intensity_gco2 : Carbon intensity of local grid (gCO2/kWh) from WattTime
"""

import numpy as np
import pandas as pd
import os

# ─── Reproducibility ──────────────────────────────────────────────────────────
RNG = np.random.default_rng(seed=42)

# ─── Config ───────────────────────────────────────────────────────────────────
N_IDLE         = 4000   # rows for idle state
N_ACTIVE_USER  = 4000   # rows for active_user state
N_BUSY_HW      = 2000   # rows for busy_hardware state  (less common)
TOTAL          = N_IDLE + N_ACTIVE_USER + N_BUSY_HW


def clip(arr, lo, hi):
    return np.clip(arr, lo, hi)


# ─── State 0: IDLE ────────────────────────────────────────────────────────────
# Machine left alone: low CPU, low RAM, no keyboard/mouse, minimal network
def gen_idle(n):
    cpu   = clip(RNG.normal(loc=6,  scale=4,   size=n), 0,  25)
    ram   = clip(RNG.normal(loc=30, scale=8,   size=n), 10, 55)
    kb    = clip(RNG.poisson(lam=1, size=n),            0,  10)
    mouse = clip(RNG.poisson(lam=2, size=n),            0,  15)
    net   = clip(RNG.exponential(scale=2_000,  size=n), 0,  50_000)
    procs = clip(RNG.normal(loc=80, scale=15,  size=n), 40, 130).astype(int)
    # Carbon intensity: could be any time of day
    carbon = clip(RNG.normal(loc=250, scale=80, size=n), 50, 600)
    label  = np.zeros(n, dtype=int)
    return cpu, ram, kb, mouse, net, procs, carbon, label


# ─── State 1: ACTIVE USER ─────────────────────────────────────────────────────
# Human is typing/browsing: medium-high CPU from browser, frequent keyboard & mouse
def gen_active_user(n):
    cpu   = clip(RNG.normal(loc=35, scale=15,  size=n), 10, 80)
    ram   = clip(RNG.normal(loc=55, scale=12,  size=n), 25, 90)
    kb    = clip(RNG.normal(loc=120, scale=40, size=n), 30, 400)
    mouse = clip(RNG.normal(loc=150, scale=50, size=n), 20, 500)
    net   = clip(RNG.exponential(scale=500_000, size=n), 5_000, 5_000_000)
    procs = clip(RNG.normal(loc=120, scale=20, size=n), 70, 200).astype(int)
    carbon = clip(RNG.normal(loc=250, scale=80, size=n), 50, 600)
    label  = np.ones(n, dtype=int)
    return cpu, ram, kb, mouse, net, procs, carbon, label


# ─── State 2: BUSY HARDWARE ───────────────────────────────────────────────────
# Background process running (compile, video render): very high CPU/RAM,
# but near-zero keyboard/mouse activity (user is "away" but hardware is maxed)
def gen_busy_hardware(n):
    cpu   = clip(RNG.normal(loc=78, scale=12,  size=n), 50, 100)
    ram   = clip(RNG.normal(loc=75, scale=10,  size=n), 55, 98)
    kb    = clip(RNG.poisson(lam=1, size=n),             0,  8)
    mouse = clip(RNG.poisson(lam=1, size=n),             0,  8)
    net   = clip(RNG.exponential(scale=100_000, size=n), 0,  2_000_000)
    procs = clip(RNG.normal(loc=100, scale=15, size=n), 60, 160).astype(int)
    carbon = clip(RNG.normal(loc=250, scale=80, size=n), 50, 600)
    label  = np.full(n, 2, dtype=int)
    return cpu, ram, kb, mouse, net, procs, carbon, label


# ─── Assemble DataFrame ───────────────────────────────────────────────────────
def assemble(*state_tuples):
    cols = [
        "cpu_usage_pct", "ram_usage_pct",
        "kb_events_per_min", "mouse_events_per_min",
        "net_io_bytes", "process_count",
        "carbon_intensity_gco2", "label"
    ]
    rows = []
    for tup in state_tuples:
        rows.append(np.stack(tup, axis=1))
    arr = np.vstack(rows)
    df = pd.DataFrame(arr, columns=cols)

    # Cast types
    for col in ["kb_events_per_min", "mouse_events_per_min", "process_count", "label"]:
        df[col] = df[col].astype(int)
    for col in ["cpu_usage_pct", "ram_usage_pct", "net_io_bytes", "carbon_intensity_gco2"]:
        df[col] = df[col].round(2)

    # Shuffle rows so states are not ordered
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    return df


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating GridMind telemetry dataset...")

    idle_data   = gen_idle(N_IDLE)
    active_data = gen_active_user(N_ACTIVE_USER)
    busy_data   = gen_busy_hardware(N_BUSY_HW)

    df = assemble(idle_data, active_data, busy_data)

    # Save
    out_path = os.path.join(os.path.dirname(__file__), "telemetry_dataset.csv")
    df.to_csv(out_path, index=False)

    print(f"\n✅ Dataset saved to: {out_path}")
    print(f"   Total rows  : {len(df):,}")
    print(f"\n── Class Distribution ──────────────────")
    label_map = {0: "idle", 1: "active_user", 2: "busy_hardware"}
    for lbl, name in label_map.items():
        count = (df["label"] == lbl).sum()
        print(f"   {name:<16}: {count:,} rows  ({count/len(df)*100:.1f}%)")

    print(f"\n── Feature Summary ─────────────────────")
    print(df.drop(columns=["label"]).describe().round(2).to_string())
