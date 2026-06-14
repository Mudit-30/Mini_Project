"""
gridmind_server.app.carbon.ledger
----------------------------------
Real carbon-savings accounting (the "carbon proof").

We compare, per completed task, what GridMind *actually* emitted against what a
naive scheduler ("run the task immediately when it was submitted") *would have*
emitted — using the real grid intensity at each point in time.

Per task:
    energy_kWh = duration_secs / 3600 * NODE_POWER_KW
    baseline_g = energy_kWh * grid_intensity_at_SUBMIT_time   (naive: run on submit)
    gridmind_g = energy_kWh * grid_intensity_at_RUN_time       (GridMind: ran when green)

Saved = Σ(baseline) − Σ(gridmind). This is genuine avoided CO₂: the gap exists only
because GridMind deferred work out of dirty grid windows into cleaner ones.

Notes
-----
* NODE_POWER_KW is a single, documented estimate (a laptop under sustained compute
  load draws roughly 50 W). It is not measured per-machine — it is an honest,
  stated assumption, identical for the baseline and the GridMind side, so it
  cancels out of the *percentage* and only scales the absolute grams.
* The ledger is in-memory: totals reset when the server restarts. That is fine for
  a single demo/run. Swap in a DB table later if cross-restart history is wanted.
"""
from __future__ import annotations

import threading

# A node under sustained compute load draws ~50 W = 0.05 kW (documented estimate).
NODE_POWER_KW: float = 0.05

# ── Current grid intensity (shared between dispatcher loop and the tasks route) ──
# The dispatcher loop computes the real grid intensity every cycle and publishes it
# here so that the task-submission route can stamp each task with the intensity that
# a naive "run-now" scheduler would have paid.
_current_lock = threading.Lock()
_current_carbon_gco2: float = 0.0


def set_current_carbon(gco2: float) -> None:
    global _current_carbon_gco2
    with _current_lock:
        _current_carbon_gco2 = float(gco2)


def get_current_carbon() -> float:
    with _current_lock:
        return _current_carbon_gco2


# ── The savings ledger ───────────────────────────────────────────────────────────
class CarbonLedger:
    """Thread-safe accumulator of baseline-vs-GridMind emissions across completed tasks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.total_baseline_g: float = 0.0
        self.total_gridmind_g: float = 0.0
        self.tasks_counted: int = 0

    def record_task(
        self,
        duration_secs: float | None,
        submit_gco2: float | None,
        run_gco2: float | None,
    ) -> None:
        """Add one completed task's baseline and actual emissions to the running totals."""
        if not duration_secs or duration_secs <= 0:
            return
        run = float(run_gco2 or 0.0)
        # If we never stamped a submit-time intensity, fall back to run-time
        # (yields zero savings for that task — the honest default).
        submit = float(submit_gco2) if submit_gco2 else run

        energy_kwh = (duration_secs / 3600.0) * NODE_POWER_KW
        baseline_g = energy_kwh * submit
        gridmind_g = energy_kwh * run

        with self._lock:
            self.total_baseline_g += baseline_g
            self.total_gridmind_g += gridmind_g
            self.tasks_counted += 1

    def snapshot(self) -> dict:
        """Return the current totals plus derived savings (grams + percentage)."""
        with self._lock:
            baseline = self.total_baseline_g
            gridmind = self.total_gridmind_g
            counted = self.tasks_counted
        saved = max(0.0, baseline - gridmind)
        saved_pct = (saved / baseline * 100.0) if baseline > 0 else 0.0
        return {
            "baseline_g": round(baseline, 4),
            "gridmind_g": round(gridmind, 4),
            "saved_g": round(saved, 4),
            "saved_pct": round(saved_pct, 1),
            "tasks_counted": counted,
        }

    def reset(self) -> None:
        with self._lock:
            self.total_baseline_g = 0.0
            self.total_gridmind_g = 0.0
            self.tasks_counted = 0


# Module-level singleton, imported by dispatcher_loop and task_dispatcher.
carbon_ledger = CarbonLedger()
