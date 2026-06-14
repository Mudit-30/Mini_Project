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
import sys

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, IOError):
        pass

# ─── Reproducibility ──────────────────────────────────────────────────────────
RNG = np.random.default_rng(seed=42)

# ─── Config ───────────────────────────────────────────────────────────────────
# Each class is split into "clear" examples + realistic "boundary" examples that
# overlap a neighbouring class. Real telemetry is fuzzy at the edges; modelling
# that is what makes the held-out accuracy honest (and < 100%).
N_IDLE_CLEAR        = 3400   # obviously-idle rows
N_IDLE_BACKGROUND   = 600    # idle but a background job bumps CPU (looks busy_hardware)
N_ACTIVE_CLEAR      = 3200   # obviously-active (typing/clicking) rows
N_ACTIVE_PASSIVE    = 800    # present but reading/watching: low input (looks idle)
N_BUSY_HW           = 2000   # background job maxing hardware, no user
TOTAL = (N_IDLE_CLEAR + N_IDLE_BACKGROUND + N_ACTIVE_CLEAR
         + N_ACTIVE_PASSIVE + N_BUSY_HW)


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


# ─── Boundary: IDLE but background job running ────────────────────────────────
# No user (kb/mouse ~0) but a background process (updater, indexer, sync) bumps
# CPU/RAM. Ground truth is IDLE (safe to dispatch) — but it can look like
# busy_hardware. This is a low-cost error if the model gets it wrong.
def gen_idle_background(n):
    cpu   = clip(RNG.normal(loc=42, scale=14,  size=n), 20, 70)
    ram   = clip(RNG.normal(loc=50, scale=12,  size=n), 30, 80)
    kb    = clip(RNG.poisson(lam=1, size=n),            0,  8)
    mouse = clip(RNG.poisson(lam=2, size=n),            0,  12)
    net   = clip(RNG.exponential(scale=80_000, size=n), 0,  1_500_000)
    procs = clip(RNG.normal(loc=95, scale=18,  size=n), 50, 160).astype(int)
    carbon = clip(RNG.normal(loc=250, scale=80, size=n), 50, 600)
    label  = np.zeros(n, dtype=int)
    return cpu, ram, kb, mouse, net, procs, carbon, label


# ─── Boundary: ACTIVE USER but passive (reading / watching) ───────────────────
# A human IS present but barely touching input — reading a long doc, watching a
# video. Low kb/mouse makes it look idle. Ground truth is ACTIVE_USER: getting
# this wrong means INTERRUPTING a real person — the costly error the Observer
# exists to avoid. We want the confusion matrix to expose exactly this.
def gen_active_user_passive(n):
    cpu   = clip(RNG.normal(loc=22, scale=12,  size=n), 5,  60)
    ram   = clip(RNG.normal(loc=50, scale=12,  size=n), 25, 85)
    kb    = clip(RNG.poisson(lam=6, size=n),            0,  35)
    mouse = clip(RNG.normal(loc=18, scale=12,  size=n), 0,  60).astype(int)
    net   = clip(RNG.exponential(scale=300_000, size=n), 2_000, 4_000_000)
    procs = clip(RNG.normal(loc=115, scale=20, size=n), 70, 200).astype(int)
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

    idle_data        = gen_idle(N_IDLE_CLEAR)
    idle_background  = gen_idle_background(N_IDLE_BACKGROUND)
    active_data      = gen_active_user(N_ACTIVE_CLEAR)
    active_passive   = gen_active_user_passive(N_ACTIVE_PASSIVE)
    busy_data        = gen_busy_hardware(N_BUSY_HW)

    df = assemble(idle_data, idle_background, active_data, active_passive, busy_data)

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
