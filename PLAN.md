# GridMind — Pre-Demo Hardening Plan

**Context:** 5–10 min live presentation with 4 real nodes. Goal: make the system
*run real* (remove the illusions), clean & reliable, and stand out — without
introducing live-failure risk on stage.

**Top priority:** Phase 1 — the Carbon Proof (real, defensible savings number).

**Decisions locked:**
- Carbon ledger: **in-memory** (resets per server restart; fine for one demo run).
- Energy estimate: **flat 50 W per node under load**, documented as an explicit constant.
- File-execution demo: show **both** an *urgent* task (runs now) and a *deferrable*
  task (waits for the clean grid window).
- DQN override: **keep the carbon guardrail but label it** in the UI/broadcast as a
  "safety guardrail over the learned policy" (stop hiding it).

> No code is written until each phase is green-lit. Work top-to-bottom.

---

## Phase 0 — Safety net (~15 min)
> **Status:** Phases 0–5 complete, plus a full adversarial code audit (61 confirmed
> findings) and fixes applied afterward. This doc is the original plan, kept for history.

- [x] Commit untracked WIP to a `pre-demo-hardening` branch — SKIPPED (user manages git).
- [x] Fix `requirements.txt`: added `pandas==3.0.1`, `patsy==1.0.2`, `statsmodels==0.14.6`
      (forecaster deps) and removed unused `onnx`/`onnxruntime`.

## Phase 1 — 🎯 THE CARBON PROOF (priority #1)
Replace the fake `savings_pct` (dispatcher_loop.py:303 — just "% below dirty
threshold", moves even with zero tasks) with a real A/B accounting.

**Model (honest & explainable):** per completed task,
`energy_kWh = duration_secs/3600 × 0.05 kW`
- GridMind emissions = energy × grid_intensity_at_run_time
- Baseline emissions = energy × grid_intensity_at_submit_time (naive = run on submit)
- Saved = Σbaseline − ΣGridMind ; saved% = saved / Σbaseline

**Backend:**
- [ ] Module-level carbon ledger (in-memory): `total_baseline_g`, `total_gridmind_g`, `tasks_counted`.
- [ ] Add `submit_carbon_gco2` column to `tasks`; stamp it in `POST /api/v1/tasks`.
- [ ] Expose current `carbon_gco2` from the dispatcher loop so the route can read it.
- [ ] On task completion (task_dispatcher.py), compute both costs from `duration_secs`
      + submit/run-time carbon; add to ledger.
- [ ] Replace dispatcher_loop.py:303 with ledger's real `saved_pct`; broadcast
      `carbon_saved_g`, `baseline_g`, `gridmind_g`, `saved_pct`.

**Frontend:**
- [ ] Replace the "carbon savings" stat card with a live A/B counter
      (`GridMind X gCO₂ · Naive Y gCO₂ · saved Z%`) using `NumberTicker`.

## Phase 1.5 — Live file execution (demo requirement)
The send-script → dispatch-to-idle-node → execute → stream-output pipeline already
works. What we add:
- [ ] Frontend: `.py` file upload (picker + drag-drop) → reads contents into the
      existing `script` field; auto-fill task name from filename.
- [ ] Backend: urgent-bypass in dispatcher_loop.py — urgent task + idle node ⇒
      dispatch immediately regardless of carbon; deferrable/best-effort still wait
      for clean grid.
- [ ] Verify node LAN-IP capture across 4 real laptops (server must reach each
      node's `:50052`). **Highest real-machine risk — test explicitly before demo.**
- [ ] Verify live stdout streaming with a real multi-line script.

## Phase 2 — Make failures real (trust foundation)
- [ ] Remove silent-success overrides in executor.py (timeout/crash → forced
      exit_code=0) and task_dispatcher.py (conn error → status="completed").
- [ ] Add `demo_tasks/` with 3 vetted-to-succeed scripts (prime sieve, matrix
      multiply, image resize) so the happy path never fails live.
- [ ] Show real failed/aborted states in the dashboard task list.

## Phase 3 — Honest ML numbers
- [ ] observer_trainer.py:274-286 — add `train_test_split`; report held-out accuracy;
      save confusion-matrix PNG.
- [ ] Update model_metadata.json with honest test accuracy.
- [ ] Fix README's stale "99.8% / DBSCAN+K-Means" → "RandomForest, ~XX% held-out".

## Phase 4 — DQN honesty
- [ ] Label the carbon override (dispatcher_loop.py:272) as a "safety guardrail over
      learned policy" in the broadcast payload + UI.

## Phase 5 — Demo staging & polish
- [ ] Carbon fast-forward toggle: step CSV faster (N rows/tick) so a full dirty→clean
      swing happens in ~90s.
- [ ] Rehearse 7-min narrative: 4 nodes up → submit batch (dirty → DEFER + explain)
      → type on a node (active-user veto) → send urgent .py file (runs now) → send
      deferrable file (held until green) → fast-forward to clean → tasks run & stream
      → carbon A/B counter → honest-ML slide.

---

## Future work (explicitly NOT before demo — note on a slide)
gRPC TLS/auth, container sandboxing of executed scripts, artifact ZIP path-traversal
validation, horizontal scaling. High effort, invisible to the panel, live-failure risk.
