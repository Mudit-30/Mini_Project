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
    #     "confidence": 0.87,     # 1.0 = perfectly at centroid
    # }
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Final

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

# ─── Logging ──────────────────────────────────────────────────────────────────
log: Final[logging.Logger] = logging.getLogger(__name__)

# ─── Defaults ─────────────────────────────────────────────────────────────────
_DEFAULT_MODEL_DIR: Final[Path] = (
    Path(__file__).parents[3] / "models" / "observer"
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

_CONF_MAX_DISTANCE: Final[float] = 10.0  # clamp denominator for confidence calc


class ObserverInference:
    """Pre-loaded Observer AI for real-time laptop state prediction.

    Parameters
    ----------
    model_dir:
        Directory containing ``scaler.joblib``, ``kmeans.joblib``, and
        ``model_metadata.json``. Defaults to ``models/observer/``.

    Raises
    ------
    FileNotFoundError
        If any required artefact file is missing.
    """

    def __init__(self, model_dir: Path | None = None) -> None:
        self._model_dir: Path = model_dir or _DEFAULT_MODEL_DIR
        self._scaler: StandardScaler = self._load_artifact("scaler.joblib")
        self._km: KMeans = self._load_artifact("kmeans.joblib")
        self._metadata: dict[str, Any] = self._load_metadata()

        # cluster_id (int) → label_int (int) and label_name (str)
        self._cluster_to_label: dict[int, int] = self._parse_label_map()

        log.info(
            "ObserverInference ready | model_version=%s | accuracy=%.4f",
            self._metadata.get("version", "unknown"),
            self._metadata.get("accuracy", float("nan")),
        )

    # ─── Private helpers ──────────────────────────────────────────────────────

    def _load_artifact(self, filename: str) -> Any:
        """Load a joblib artefact from the model directory.

        Parameters
        ----------
        filename:
            Filename relative to ``self._model_dir``.

        Returns
        -------
        Any
            Deserialised object.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        """
        path = self._model_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Model artefact not found: {path}. "
                "Run observer_trainer.py first."
            )
        obj = joblib.load(path)
        log.debug("Loaded artefact: %s", path)
        return obj

    def _load_metadata(self) -> dict[str, Any]:
        """Load model metadata JSON from disk.

        Returns
        -------
        dict[str, Any]
            Parsed metadata dictionary.

        Raises
        ------
        FileNotFoundError
            If metadata JSON is absent.
        """
        path = self._model_dir / "model_metadata.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Metadata file not found: {path}. "
                "Run observer_trainer.py first."
            )
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _parse_label_map(self) -> dict[int, int]:
        """Convert the string-keyed label map in metadata to int keys.

        The metadata stores ``{"0": "idle", "1": "active_user", ...}`` where
        the keys are K-Means cluster IDs and values are semantic state names.
        This method inverts the label_names lookup to return cluster_id → label_int.

        Returns
        -------
        dict[int, int]
            Maps K-Means cluster ID → GridMind label integer.
        """
        label_name_to_int: dict[str, int] = {
            "idle": 0,
            "active_user": 1,
            "busy_hardware": 2,
        }
        raw: dict[str, str] = self._metadata.get("label_map", {})
        if not raw:
            raise ValueError(
                "label_map missing from model_metadata.json. "
                "Re-run observer_trainer.py."
            )
        return {int(k): label_name_to_int[v] for k, v in raw.items()}

    @staticmethod
    def _compute_confidence(
        X_scaled: np.ndarray, cluster_id: int, km: KMeans
    ) -> float:
        """Compute normalised confidence as inverse distance to assigned centroid.

        A sample exactly at the centroid has confidence 1.0. As distance
        increases, confidence drops toward 0.0.

        Parameters
        ----------
        X_scaled:
            Single-row scaled feature array, shape (1, n_features).
        cluster_id:
            The cluster ID predicted by K-Means.
        km:
            Trained KMeans instance (for centroid access).

        Returns
        -------
        float
            Confidence in [0.0, 1.0].
        """
        centroid = km.cluster_centers_[cluster_id]
        dist = float(np.linalg.norm(X_scaled - centroid))
        confidence = max(0.0, 1.0 - dist / _CONF_MAX_DISTANCE)
        return round(confidence, 4)

    # ─── Public API ───────────────────────────────────────────────────────────

    def predict(self, snapshot: dict[str, float]) -> dict[str, Any]:
        """Predict the state of a laptop from a single telemetry snapshot.

        Parameters
        ----------
        snapshot:
            A dictionary with keys matching ``FEATURE_COLS``.  Values not
            listed in ``FEATURE_COLS`` are silently ignored.  Missing keys
            raise ``ValueError``.

        Returns
        -------
        dict with keys:
            - ``label``      : int   — 0=idle, 1=active_user, 2=busy_hardware
            - ``state``      : str   — human-readable state name
            - ``confidence`` : float — 0.0 (far from centroid) → 1.0 (at centroid)

        Raises
        ------
        ValueError
            If any required feature column is missing from *snapshot*.
        """
        missing = [col for col in FEATURE_COLS if col not in snapshot]
        if missing:
            raise ValueError(
                f"Snapshot is missing required keys: {missing}. "
                f"Required columns: {FEATURE_COLS}"
            )

        X_raw: np.ndarray = np.array(
            [[snapshot[col] for col in FEATURE_COLS]], dtype=np.float64
        )
        X_scaled: np.ndarray = self._scaler.transform(X_raw)

        cluster_id = int(self._km.predict(X_scaled)[0])
        label_int = self._cluster_to_label[cluster_id]
        state_name = {0: "idle", 1: "active_user", 2: "busy_hardware"}[label_int]
        confidence = self._compute_confidence(X_scaled, cluster_id, self._km)

        log.debug(
            "predict → cluster=%d  state=%s  confidence=%.4f",
            cluster_id,
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
        """Return a copy of the model metadata dictionary."""
        return dict(self._metadata)

    def __repr__(self) -> str:
        return (
            f"ObserverInference("
            f"version={self._metadata.get('version')!r}, "
            f"accuracy={self._metadata.get('accuracy'):.4f})"
        )
