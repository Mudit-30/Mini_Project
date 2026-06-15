# GridMind — Demo Runbook (4 laptops, ~7 min)

Everything to run the live demo and defend it. Read once before the room.

---

## 0. Pre-flight — the day before (DON'T skip)

### On every WORKER laptop (the teammates)
1. `pip install -r requirements.txt`
2. **Open the firewall for port 50052** — the #1 thing that breaks the demo. Without
   it the master can't reach the laptop to run tasks. In an **Admin** PowerShell, once:
   ```powershell
   New-NetFirewallRule -DisplayName "GridMind Node 50052" -Direction Inbound -LocalPort 50052 -Protocol TCP -Action Allow
   ```
   (Or just click "Allow" when Windows prompts for `python.exe`.)
3. Same **Wi-Fi** as the master. Battery is fine — just keep charge **above 30%** (a low/hot laptop is skipped by protection).

### On the MASTER laptop (you)
1. `pip install -r requirements.txt`
2. (Optional) snappier active-user veto and faster carbon swings:
   ```powershell
   $env:GRIDMIND_SMOOTHING_WINDOW = "3"   # active-user veto flips in ~10s (default 6 ≈ 20s)
   $env:GRIDMIND_CARBON_STRIDE   = "6"    # one dirty<->clean grid swing ≈ 90s (raise to go faster)
   # GRIDMIND_LOAD_ML=1 is already the default (real RandomForest + DQN). Set "0" only if low on RAM.
   ```
3. Start on a **freshly-booted** master (avoids memory pressure). Note the LAN IP it prints.

---

## 1. ✅ Prove cross-machine execution works (2-minute test, do this first)

This is the only thing I (the build) can't verify for you — it depends on each
laptop's firewall + network. Prove it before the audience is watching:

1. **Master:** `python start_gridmind.py` → open `http://localhost:3005`
2. **One teammate:** `python gridmind_node/agent.py --server <MASTER_IP>:50051 --node-id "Bob"`
3. Confirm **Bob's card** appears on the dashboard.
4. On the dashboard, drop **`demo_tasks/00_which_node.py`** and submit it as **Urgent** (priority 7–10).
5. **The proof:** the task output reads **`THIS TASK RAN ON: <Bob's hostname>`**.
   - Shows Bob's hostname → ✅ remote execution works. Repeat for each laptop.
   - Shows the master's hostname, or the task fails/re-queues → ❌ that laptop's
     **firewall is blocking 50052** (fix it, then retry).

---

## 2. Launch (demo time)

**Master:** `python start_gridmind.py` → wait for `GRIDMIND SYSTEM IS DEPLOYED` → open `http://localhost:3005`
**Each teammate:** `python gridmind_node/agent.py --server <MASTER_IP>:50051 --node-id "Your Name"`
Watch all 4 node cards appear.

---

## 3. The ~7-minute narrative

| # | Action | What to say |
|---|--------|-------------|
| 1 | 4 node cards live, telemetry streaming | "4 real laptops, each reporting CPU/RAM/input/battery every 5s over gRPC." |
| 2 | **Drop a `.py` file → submit Urgent → it runs on a teammate's laptop, output streams back** | "I submit work here; GridMind picks a safe, free laptop and runs it there — output live. *(00_which_node.py proves which machine ran it.)*" ← **headline** |
| 3 | Submit a **Parallel Job** (Parallel Compute panel, 4 chunks) | "One job, split across all 4 laptops, running at once — **Nx speedup**, measured." |
| 4 | **Ctrl+C one teammate's agent** mid-task (don't close the lid — Ctrl+C is instant) | "A node just dropped — GridMind re-queues its task and another laptop finishes it. Fault-tolerant." |
| 5 | **Unplug** a laptop | "It flips to ⛔ Protected — we never drain a teammate's battery." |
| 6 | **Type** on a laptop (~10–15s) | "The Observer sees a human and pulls it from the pool — we never interrupt someone." |
| 7 | Point at **Carbon Proof** + the **Observer confusion matrix** | "Measured CO₂ saved vs a naive scheduler, on *marginal* emissions — the right number. And honest ML: 99.2% on a held-out test, here's the confusion matrix." |

> Tight on time? #2 + #3 + #4 are the must-shows (remote exec, speedup, resilience). #5/#6/#7 are 20–30s each.

---

## 4. Q&A defenses
- **"Is the carbon saving real?"** Measured per task: grid intensity at submit-time
  (naive baseline) vs run-time (GridMind), on **marginal emissions (WattTime MOER)** —
  the CO₂ of the next MWh, the only signal that changes when you shift load.
- **"Does the AI really work?"** Observer = RandomForest, **99.2% on a held-out test**
  (confusion matrix on the dashboard). Dispatcher = a Dueling-DQN policy with two
  transparent safety guardrails (urgent, clean-grid) shown live.
- **"What if a laptop dies?"** It re-queues and another node finishes (you just saw it).
- **"Security?"** Trusted-LAN demo; gRPC TLS/auth + script sandboxing are future work.

---

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| Task runs on the **master**, not the teammate | Teammate firewall blocking 50052 (see §0). |
| Node card never appears | Wrong master IP, or not on the same Wi-Fi. |
| Task stays "pending" | No *free + idle + power-safe* node — check active-user / low-battery (<30%) / temp state. |
| Parallel speedup shows "sequential" | Needs ≥2 free nodes at submit time. |
| Active-user veto too slow | Set `GRIDMIND_SMOOTHING_WINDOW=3` before launch. |
| Grid carbon barely moves | Raise `GRIDMIND_CARBON_STRIDE` (e.g. 12). |
| Backend won't start / sluggish | Fresh-boot the master; `GRIDMIND_LOAD_ML=0` if very low RAM. |
| Don't edit files while running | `uvicorn --reload` re-runs model load and can stall — start once, leave it. |

---

## 6. Demo task files (`demo_tasks/`)
- `00_which_node.py` — proves which laptop ran it (use for the §1 check + headline).
- `01_calculate_pi.py` (real Monte Carlo), `02_ml_training.py` (real neural net trained from scratch with backprop — loss falls, accuracy ~95%), `03_financial_backtest.py` (real SMA-crossover backtest vs buy-and-hold) — vetted single-node tasks that do genuine computation (stdlib only, run on any node), not scripted output.
- `parallel_primes.py` — the data-parallel job (counts primes, split across nodes).
- `submit_tasks.py` — batch-submit the single-node tasks from the CLI.
