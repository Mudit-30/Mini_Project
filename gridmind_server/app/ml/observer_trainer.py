"""
gridmind_server.app.ml.observer_trainer
========================================
Offline training pipeline for the GridMind Observer AI.

Algorithm
---------
1. Load and validate `data/telemetry_dataset.csv`.
2. Scale all 7 feature columns with StandardScaler.
3. Run DBSCAN to identify and discard noise points.
4. Fit K-Means (k=3) on the clean, scaled data.
5. Auto-map cluster IDs → semantic labels by inspecting centroids:
       highest (kb + mouse)             → active_user  (1)
       highest (cpu + ram), low hid     → busy_hardware (2)
       remaining                        → idle          (0)
6. Evaluate accuracy against ground-truth labels.
7. Persist scaler, model, and a metadata JSON to models/observer/.

Usage
-----
    # From the project root (d:\\Mini_Project):
    python -m gridmind_server.app.ml.observer_trainer
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

import joblib
import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, KMeans
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.preprocessing import StandardScaler

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log: Final[logging.Logger] = logging.getLogger(__name__)

# ─── Constants ────────────────────────────────────────────────────────────────
LABEL_IDLE: Final[int] = 0
LABEL_ACTIVE_USER: Final[int] = 1
LABEL_BUSY_HW: Final[int] = 2

LABEL_NAMES: Final[dict[int, str]] = {
    LABEL_IDLE: "idle",
    LABEL_ACTIVE_USER: "active_user",
    LABEL_BUSY_HW: "busy_hardware",
}

FEATURE_COLS: Final[list[str]] = [
    "cpu_usage_pct",
    "ram_usage_pct",
    "kb_events_per_min",
    "mouse_events_per_min",
    "net_io_bytes",
    "process_count",
    "carbon_intensity_gco2",
]

LABEL_COL: Final[str] = "label"


# ─── Config ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TrainerConfig:
    """All tunable hyper-parameters and paths in one place.

    Parameters
    ----------
    dataset_path:
        Absolute or project-relative path to the telemetry CSV.
    output_dir:
        Directory where scaler, model, and metadata are saved.
    dbscan_eps:
        Neighbourhood radius for DBSCAN noise detection.
    dbscan_min_samples:
        Minimum samples in a DBSCAN neighbourhood to form a core point.
    kmeans_n_clusters:
        Number of clusters — must equal the number of distinct states.
    kmeans_n_init:
        Number of times K-Means runs with different centroid seeds.
    kmeans_random_state:
        RNG seed for K-Means reproducibility.
    accuracy_threshold:
        Minimum acceptable accuracy vs ground-truth labels (0–1).
    """

    dataset_path: Path = field(
        default_factory=lambda: Path(__file__).parents[3] / "data" / "telemetry_dataset.csv"
    )
    output_dir: Path = field(
        default_factory=lambda: Path(__file__).parents[3] / "models" / "observer"
    )
    dbscan_eps: float = 1.5
    dbscan_min_samples: int = 5
    kmeans_n_clusters: int = 3
    kmeans_n_init: int = 20
    kmeans_random_state: int = 42
    accuracy_threshold: float = 0.85


# ─── Data Loading ─────────────────────────────────────────────────────────────
def load_and_validate(path: Path) -> pd.DataFrame:
    """Load the telemetry CSV and validate its schema.

    Parameters
    ----------
    path:
        Path to the CSV file.

    Returns
    -------
    pd.DataFrame
        Validated dataframe with correct dtypes.

    Raises
    ------
    FileNotFoundError
        If the CSV does not exist at *path*.
    ValueError
        If required columns are missing or contain nulls.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Dataset not found at {path}. "
            "Run `python data/generate_dataset.py` first."
        )

    log.info("Loading dataset from %s", path)
    df = pd.read_csv(path)

    required_cols = set(FEATURE_COLS + [LABEL_COL])
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")

    null_counts = df[list(required_cols)].isnull().sum()
    if null_counts.any():
        raise ValueError(
            f"Dataset contains null values:\n{null_counts[null_counts > 0]}"
        )

    log.info(
        "Dataset loaded: %d rows × %d cols | classes: %s",
        len(df),
        len(df.columns),
        df[LABEL_COL].value_counts().to_dict(),
    )
    return df


# ─── Preprocessing ────────────────────────────────────────────────────────────
def scale_features(
    df: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, StandardScaler]:
    """Fit a StandardScaler and return scaled features and raw labels.

    The scaler is fit *only* on the feature columns; labels are never
    seen during unsupervised training.

    Parameters
    ----------
    df:
        Validated dataframe containing feature and label columns.

    Returns
    -------
    X_scaled : np.ndarray, shape (n_samples, n_features)
        Standardised feature matrix.
    y_true : np.ndarray, shape (n_samples,)
        Ground-truth labels (used only for final evaluation).
    scaler : StandardScaler
        Fitted scaler instance (must be persisted for inference).
    """
    X: np.ndarray = df[FEATURE_COLS].to_numpy(dtype=np.float64)
    y_true: np.ndarray = df[LABEL_COL].to_numpy(dtype=np.int32)

    scaler = StandardScaler()
    X_scaled: np.ndarray = scaler.fit_transform(X)

    log.info("Features scaled with StandardScaler (mean=0, std=1).")
    return X_scaled, y_true, scaler


# ─── DBSCAN Denoising ─────────────────────────────────────────────────────────
def remove_noise(
    X_scaled: np.ndarray,
    y_true: np.ndarray,
    eps: float,
    min_samples: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Use DBSCAN to identify and remove noise points before clustering.

    DBSCAN labels noise points as -1. These are genuine outliers — e.g.
    a CPU spike during a context switch — that would skew K-Means centroids
    if left in.

    Parameters
    ----------
    X_scaled:
        Scaled feature matrix.
    y_true:
        Ground-truth labels for the same rows.
    eps:
        DBSCAN neighbourhood radius (in scaled feature space).
    min_samples:
        Core-point neighbourhood size.

    Returns
    -------
    X_clean : np.ndarray
        Rows where DBSCAN did *not* assign label -1.
    y_clean : np.ndarray
        Corresponding ground-truth labels for clean rows.
    noise_ratio : float
        Fraction of total rows identified as noise (0–1).
    """
    log.info("Running DBSCAN (eps=%.2f, min_samples=%d) …", eps, min_samples)
    db = DBSCAN(eps=eps, min_samples=min_samples, n_jobs=-1)
    db_labels: np.ndarray = db.fit_predict(X_scaled)

    mask: np.ndarray = db_labels != -1
    noise_count = int((~mask).sum())
    noise_ratio = noise_count / len(X_scaled)

    log.info(
        "DBSCAN complete: %d noise points removed (%.1f%% of dataset).",
        noise_count,
        noise_ratio * 100,
    )

    if noise_ratio > 0.20:
        log.warning(
            "Noise ratio %.1f%% is high (>20%%). Consider tuning eps/min_samples.",
            noise_ratio * 100,
        )

    return X_scaled[mask], y_true[mask], noise_ratio


# ─── K-Means Clustering ───────────────────────────────────────────────────────
def fit_kmeans(
    X_clean: np.ndarray,
    n_clusters: int,
    n_init: int,
    random_state: int,
) -> KMeans:
    """Fit K-Means on the denoised, scaled data.

    Parameters
    ----------
    X_clean:
        Denoised, scaled feature matrix.
    n_clusters:
        Number of clusters (must equal 3 for Observer AI).
    n_init:
        Number of random initialisations to try.
    random_state:
        RNG seed for reproducibility.

    Returns
    -------
    KMeans
        A trained KMeans estimator.
    """
    log.info(
        "Fitting K-Means (k=%d, n_init=%d, random_state=%d) on %d samples …",
        n_clusters,
        n_init,
        random_state,
        len(X_clean),
    )
    t0 = time.perf_counter()
    km = KMeans(
        n_clusters=n_clusters,
        n_init=n_init,
        random_state=random_state,
        algorithm="lloyd",
    )
    km.fit(X_clean)
    elapsed = time.perf_counter() - t0
    log.info(
        "K-Means converged in %.2fs | inertia = %.2f", elapsed, float(km.inertia_)
    )
    return km


# ─── Cluster → Label Mapping ──────────────────────────────────────────────────
def build_cluster_label_map(
    km: KMeans, scaler: StandardScaler
) -> dict[int, int]:
    """Map K-Means cluster IDs to semantic label integers.

    The mapping is derived purely from centroid positions in the *original*
    (unscaled) feature space so it is human-interpretable and deterministic.

    Rules (applied in priority order):
      1. Highest sum of ``kb_events_per_min`` + ``mouse_events_per_min``
         → active_user (1)
      2. Of the remaining two, highest sum of ``cpu_usage_pct`` + ``ram_usage_pct``
         → busy_hardware (2)
      3. Remaining cluster → idle (0)

    Parameters
    ----------
    km:
        Trained K-Means model.
    scaler:
        The fitted StandardScaler used to inverse-transform centroids.

    Returns
    -------
    dict[int, int]
        Maps K-Means cluster ID → GridMind label int.
    """
    # Inverse-transform centroids back to original feature scale
    centroids_orig: np.ndarray = scaler.inverse_transform(km.cluster_centers_)

    # Feature indices into the fixed FEATURE_COLS order
    idx_cpu   = FEATURE_COLS.index("cpu_usage_pct")
    idx_ram   = FEATURE_COLS.index("ram_usage_pct")
    idx_kb    = FEATURE_COLS.index("kb_events_per_min")
    idx_mouse = FEATURE_COLS.index("mouse_events_per_min")

    # Score every cluster on human-interaction signal and hardware load
    hid_score: np.ndarray = centroids_orig[:, idx_kb] + centroids_orig[:, idx_mouse]
    hw_score:  np.ndarray = centroids_orig[:, idx_cpu] + centroids_orig[:, idx_ram]

    remaining: list[int] = list(range(len(centroids_orig)))
    mapping: dict[int, int] = {}

    # ── Rule 1: active_user — highest keyboard + mouse activity ───────────────
    # Score only the clusters still in `remaining`; argmax gives an index
    # *into that sub-list*, so we must retrieve the actual cluster ID via
    # remaining[idx].
    hid_scores_remaining = [hid_score[c] for c in remaining]
    active_idx_in_remaining = int(np.argmax(hid_scores_remaining))
    active_cluster_id = remaining[active_idx_in_remaining]
    mapping[active_cluster_id] = LABEL_ACTIVE_USER
    remaining.remove(active_cluster_id)

    # ── Rule 2: busy_hardware — of the rest, highest CPU + RAM ────────────────
    hw_scores_remaining = [hw_score[c] for c in remaining]
    busy_idx_in_remaining = int(np.argmax(hw_scores_remaining))
    busy_cluster_id = remaining[busy_idx_in_remaining]
    mapping[busy_cluster_id] = LABEL_BUSY_HW
    remaining.remove(busy_cluster_id)

    # ── Rule 3: idle — the last cluster standing ───────────────────────────────
    mapping[remaining[0]] = LABEL_IDLE

    log.info(
        "Cluster → label map: %s",
        {k: LABEL_NAMES[v] for k, v in sorted(mapping.items())},
    )
    return mapping


# ─── Evaluation ───────────────────────────────────────────────────────────────
def evaluate(
    km: KMeans,
    cluster_label_map: dict[int, int],
    X_clean: np.ndarray,
    y_clean: np.ndarray,
    threshold: float,
) -> float:
    """Score predictions against ground-truth labels and log a full report.

    Parameters
    ----------
    km:
        Trained K-Means model.
    cluster_label_map:
        Mapping from cluster IDs to GridMind label ints.
    X_clean:
        Clean, scaled feature matrix.
    y_clean:
        Ground-truth labels for the same rows.
    threshold:
        Minimum acceptable accuracy (raises warning if not met).

    Returns
    -------
    float
        Overall accuracy score.
    """
    raw_clusters: np.ndarray = km.predict(X_clean)
    y_pred = np.vectorize(cluster_label_map.__getitem__)(raw_clusters)

    acc = float(accuracy_score(y_clean, y_pred))
    log.info("Accuracy vs ground-truth labels: %.4f (%.1f%%)", acc, acc * 100)

    report = classification_report(
        y_clean,
        y_pred,
        target_names=[LABEL_NAMES[i] for i in sorted(LABEL_NAMES)],
    )
    log.info("Classification report:\n%s", report)

    cm = confusion_matrix(y_clean, y_pred)
    log.info("Confusion matrix:\n%s", cm)

    if acc < threshold:
        log.warning(
            "Accuracy %.4f is below the project target of %.2f. "
            "Consider retuning DBSCAN/K-Means hyperparameters or enriching the dataset.",
            acc,
            threshold,
        )
    else:
        log.info("✅ Accuracy target (≥ %.2f) met.", threshold)

    return acc


# ─── Persistence ──────────────────────────────────────────────────────────────
def save_artifacts(
    scaler: StandardScaler,
    km: KMeans,
    cluster_label_map: dict[int, int],
    noise_ratio: float,
    accuracy: float,
    config: TrainerConfig,
) -> None:
    """Persist all model artefacts to the output directory.

    Creates `output_dir` if it does not already exist. Saves:
      - ``scaler.joblib``        : fitted StandardScaler
      - ``kmeans.joblib``        : trained KMeans model
      - ``model_metadata.json``  : version, accuracy, noise%, timestamp, hyperparams

    Parameters
    ----------
    scaler:
        Fitted StandardScaler.
    km:
        Trained KMeans model.
    cluster_label_map:
        Mapping from cluster IDs to GridMind label ints.
    noise_ratio:
        Fraction of dataset removed by DBSCAN.
    accuracy:
        Accuracy score vs ground-truth labels.
    config:
        Trainer configuration (used for metadata).
    """
    config.output_dir.mkdir(parents=True, exist_ok=True)

    scaler_path   = config.output_dir / "scaler.joblib"
    kmeans_path   = config.output_dir / "kmeans.joblib"
    metadata_path = config.output_dir / "model_metadata.json"

    joblib.dump(scaler, scaler_path)
    log.info("Scaler saved → %s", scaler_path)

    joblib.dump(km, kmeans_path)
    log.info("K-Means model saved → %s", kmeans_path)

    metadata: dict = {
        "model_name": "observer_ai",
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": round(accuracy, 6),
        "noise_ratio": round(noise_ratio, 6),
        "feature_columns": FEATURE_COLS,
        "label_map": {str(k): LABEL_NAMES[v] for k, v in cluster_label_map.items()},
        "hyperparameters": {
            "dbscan_eps": config.dbscan_eps,
            "dbscan_min_samples": config.dbscan_min_samples,
            "kmeans_n_clusters": config.kmeans_n_clusters,
            "kmeans_n_init": config.kmeans_n_init,
            "kmeans_random_state": config.kmeans_random_state,
        },
    }

    with metadata_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
    log.info("Metadata saved → %s", metadata_path)


# ─── Orchestration ────────────────────────────────────────────────────────────
def run_training(config: TrainerConfig | None = None) -> float:
    """End-to-end Observer AI training pipeline.

    Parameters
    ----------
    config:
        Optional configuration override. If ``None``, defaults are used.

    Returns
    -------
    float
        Final accuracy score against ground-truth labels.
    """
    if config is None:
        config = TrainerConfig()

    log.info("═" * 60)
    log.info("GridMind Observer AI — Training Pipeline")
    log.info("═" * 60)

    df                      = load_and_validate(config.dataset_path)
    X_scaled, y_true, scaler = scale_features(df)
    X_clean, y_clean, noise_ratio = remove_noise(
        X_scaled, y_true, config.dbscan_eps, config.dbscan_min_samples
    )
    km                     = fit_kmeans(
        X_clean,
        config.kmeans_n_clusters,
        config.kmeans_n_init,
        config.kmeans_random_state,
    )
    cluster_label_map       = build_cluster_label_map(km, scaler)
    accuracy                = evaluate(
        km, cluster_label_map, X_clean, y_clean, config.accuracy_threshold
    )
    save_artifacts(scaler, km, cluster_label_map, noise_ratio, accuracy, config)

    log.info("═" * 60)
    log.info("Training complete. Artifacts → %s", config.output_dir)
    log.info("═" * 60)

    return accuracy


# ─── Entry-point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_training()
