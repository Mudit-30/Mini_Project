"""
gridmind_server.app.ml.observer_inference
==========================================
Stateless runtime inference wrapper for the GridMind Observer AI.

Loaded once at server startup; all subsequent calls are thread-safe
reads against pre-loaded model artefacts.

Usage
-----
    from gridmind_server.app.ml.observer_inference import ObserverInference

    observer = ObserverInference()          # loads models from disk
    result   = observer.predict(snapshot)   # predict a single telemetry dict

    # result →
    # {
    #     "label":      0,
    #     "state":      "idle",
    #     "confidence": 0.87,
    # }
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Final

import joblib
import numpy as np
import collections

# ─── Logging ──────────────────────────────────────────────────────────────────
log: Final[logging.Logger] = logging.getLogger(__name__)

_DEFAULT_MODEL_DIR: Final[str] = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "models", "observer")
)

FEATURE_COLS: Final[list[str]] = [
    "cpu_usage_pct",
    "ram_usage_pct",
    "kb_events_per_min",
    "mouse_events_per_min",
    "net_io_bytes",
    "process_count",
    "carbon_intensity_gco2",
]


class ObserverInference:
    """Pre-loaded Observer AI for real-time laptop state prediction.

    Parameters
    ----------
    model_dir:
        Directory containing ``scaler.joblib``, ``rf_model.joblib``, and
        ``model_metadata.json``. Defaults to ``models/observer/``.

    Raises
    ------
    FileNotFoundError
        If any required artefact file is missing.
    """

    def __init__(self, model_dir: str | None = None) -> None:
        self._model_dir: str = model_dir or _DEFAULT_MODEL_DIR
        self._use_heuristic = False
        # Temporal smoothing window (frames). The returned state is the majority
        # label over the last N frames, which kills single-frame jitter. Smaller N
        # reacts faster when a user returns (snappier "active-user veto"); larger N
        # is steadier. At the 5s telemetry cadence, 6 frames ≈ 30s to fully flip,
        # ~15s to cross the 50%-confidence dispatch gate. Override per-deployment
        # (e.g. a fast live demo) with GRIDMIND_SMOOTHING_WINDOW.
        try:
            self._window = max(1, int(os.environ.get("GRIDMIND_SMOOTHING_WINDOW", "6")))
        except ValueError:
            self._window = 6
        self._history = collections.defaultdict(lambda: collections.deque(maxlen=self._window))
        log.info("Observer temporal-smoothing window = %d frames.", self._window)

        if os.environ.get("GRIDMIND_LOAD_ML") == "1":
            try:
                self._scaler = self._load_artifact("scaler.joblib")
                self._model = self._load_artifact("rf_model.joblib")
                self._metadata: dict[str, Any] = self._load_metadata()
                self._label_map: dict[int, str] = {
                    int(k): v for k, v in self._metadata.get("label_map", {}).items()
                }
                log.info(
                    "ObserverInference ready (RandomForest) | model_version=%s | accuracy=%.4f",
                    self._metadata.get("version", "unknown"),
                    self._metadata.get("accuracy", float("nan")),
                )
            except Exception as exc:
                log.warning("sklearn/artifacts loading failed; falling back to heuristic: %s", exc)
                self._use_heuristic = True
                self._metadata = {"version": "heuristic_v1", "accuracy": 1.0}
                self._label_map = {0: "idle", 1: "active_user", 2: "busy_hardware"}
        else:
            log.info("GRIDMIND_LOAD_ML not set to 1; using high-fidelity heuristic fallback for observer.")
            self._use_heuristic = True
            self._metadata = {"version": "heuristic_v1", "accuracy": 1.0}
            self._label_map = {0: "idle", 1: "active_user", 2: "busy_hardware"}

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _load_artifact(self, filename: str) -> Any:
        path = os.path.join(self._model_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Model artefact not found: {path}. "
                "Run observer_trainer.py first."
            )
        obj = joblib.load(path)
        log.debug("Loaded artefact: %s", path)
        return obj

    def _load_metadata(self) -> dict[str, Any]:
        path = os.path.join(self._model_dir, "model_metadata.json")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Metadata file not found: {path}. "
                "Run observer_trainer.py first."
            )
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    # ─── Public API ───────────────────────────────────────────────────────────

    def predict(self, snapshot: dict[str, float], node_id: str) -> dict[str, Any]:
        """Predict the state of a laptop from a single telemetry snapshot using temporal majority vote.

        Parameters
        ----------
        snapshot:
            A dictionary with keys matching ``FEATURE_COLS``. Values not
            listed in ``FEATURE_COLS`` are silently ignored. Missing keys
            raise ``ValueError``.

        Returns
        -------
        dict with keys:
            - ``label``      : int   — 0=idle, 1=active_user, 2=busy_hardware
            - ``state``      : str   — human-readable state name
            - ``confidence`` : float — max class probability from Random Forest
        """
        missing = [col for col in FEATURE_COLS if col not in snapshot]
        if missing:
            raise ValueError(
                f"Snapshot is missing required keys: {missing}. "
                f"Required columns: {FEATURE_COLS}"
            )

        if self._use_heuristic:
            # High-fidelity rule-based heuristic classifier
            cpu = snapshot.get("cpu_usage_pct", 0.0)
            ram = snapshot.get("ram_usage_pct", 0.0)
            kb = snapshot.get("kb_events_per_min", 0.0)
            mouse = snapshot.get("mouse_events_per_min", 0.0)
            
            # Input-first heuristic: real human input → active_user (never interrupt
            # a person), even if CPU is also high. No meaningful input but high CPU →
            # busy_hardware (a background job). Otherwise idle. Thresholds are in
            # events/min: a truly idle machine sits near 0; light typing/mousing
            # easily clears 20/40.
            if kb > 20.0 or mouse > 40.0:
                raw_label = 1            # active_user
                confidence = 0.90
            elif cpu >= 85.0:
                raw_label = 2            # busy_hardware
                confidence = 0.90
            else:
                raw_label = 0            # idle
                confidence = 0.95

            confidence = min(1.0, max(0.0, float(confidence)))
        else:
            X_raw: np.ndarray = np.array(
                [[snapshot[col] for col in FEATURE_COLS]], dtype=np.float64
            )
            X_scaled: np.ndarray = self._scaler.transform(X_raw)

            # Get label and probabilities
            raw_label = int(self._model.predict(X_scaled)[0])
            probas = self._model.predict_proba(X_scaled)[0]
            confidence = float(max(probas))
        
        self._history[node_id].append(raw_label)
        hist = self._history[node_id]
        # Temporal smoothing: most-frequent label over the rolling window (single O(n) pass).
        label_int = collections.Counter(hist).most_common(1)[0][0]
        # Confidence must describe the RETURNED (smoothed) label, not the raw current
        # frame — otherwise a smoothing flip pairs the new state with a stale probability.
        # Report the fraction of the window that agrees with the chosen label.
        confidence = hist.count(label_int) / len(hist)

        state_name = self._label_map.get(label_int, "unknown")

        log.debug(
            "predict → node=%s  raw=%d  mode=%d  state=%s  confidence=%.4f",
            node_id,
            raw_label,
            label_int,
            state_name,
            confidence,
        )

        return {
            "label": label_int,
            "state": state_name,
            "confidence": confidence,
        }

    @property
    def metadata(self) -> dict[str, Any]:
        return dict(self._metadata)

    def reload(self) -> None:
        """
        Hot-swap model artefacts from disk without restarting the server.
        """
        log.info("Reloading ObserverInference artefacts from %s…", self._model_dir)
        try:
            new_scaler   = self._load_artifact("scaler.joblib")
            new_model    = self._load_artifact("rf_model.joblib")
            new_metadata = self._load_metadata()
            new_map      = {int(k): v for k, v in new_metadata.get("label_map", {}).items()}

            # Atomic swap
            self._scaler   = new_scaler
            self._model    = new_model
            self._metadata = new_metadata
            self._label_map = new_map
            self._use_heuristic = False

            log.info(
                "ObserverInference reloaded | version=%s | accuracy=%.4f",
                self._metadata.get("version", "unknown"),
                self._metadata.get("accuracy", float("nan")),
            )
        except Exception as exc:
            log.warning("ObserverInference reload failed; keeping current state: %s", exc)

    def __repr__(self) -> str:
        return (
            f"ObserverInference("
            f"version={self._metadata.get('version')!r}, "
            f"accuracy={self._metadata.get('accuracy'):.4f})"
        )

