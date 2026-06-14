"""
gridmind_server.app.ml.observer_trainer
========================================
Offline training pipeline for the GridMind Observer AI.

Algorithm
---------
1. Load and validate `data/telemetry_dataset.csv`.
2. Scale all 7 feature columns with StandardScaler.
3. Train a RandomForestClassifier on the scaled data and ground-truth labels.
4. Evaluate accuracy against ground-truth labels.
5. Persist scaler, model, and a metadata JSON to models/observer/.

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

# Fix Windows console encoding for emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, IOError):
        pass

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
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
    rf_n_estimators:
        Number of trees in the forest.
    rf_max_depth:
        Maximum depth of the tree.
    rf_random_state:
        RNG seed for RandomForest reproducibility.
    accuracy_threshold:
        Minimum acceptable accuracy vs ground-truth labels (0–1).
    """

    dataset_path: Path = field(
        default_factory=lambda: Path(__file__).parents[3] / "data" / "telemetry_dataset.csv"
    )
    output_dir: Path = field(
        default_factory=lambda: Path(__file__).parents[3] / "models" / "observer"
    )
    rf_n_estimators: int = 100
    rf_max_depth: int | None = None
    rf_random_state: int = 42
    accuracy_threshold: float = 0.85


# ─── Data Loading ─────────────────────────────────────────────────────────────
def load_and_validate(path: Path) -> pd.DataFrame:
    """Load the telemetry CSV and validate its schema."""
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
    """Fit a StandardScaler and return scaled features and raw labels."""
    X: np.ndarray = df[FEATURE_COLS].to_numpy(dtype=np.float64)
    y_true: np.ndarray = df[LABEL_COL].to_numpy(dtype=np.int32)

    scaler = StandardScaler()
    X_scaled: np.ndarray = scaler.fit_transform(X)

    log.info("Features scaled with StandardScaler (mean=0, std=1).")
    return X_scaled, y_true, scaler


# ─── Random Forest Training ───────────────────────────────────────────────────
def fit_random_forest(
    X_train: np.ndarray,
    y_train: np.ndarray,
    n_estimators: int,
    max_depth: int | None,
    random_state: int,
) -> RandomForestClassifier:
    """Fit RandomForest on the scaled data."""
    log.info(
        "Fitting Random Forest (n_estimators=%d, max_depth=%s, random_state=%d) on %d samples …",
        n_estimators,
        max_depth,
        random_state,
        len(X_train),
    )
    t0 = time.perf_counter()
    rf = RandomForestClassifier(
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=random_state,
        n_jobs=1,
    )
    rf.fit(X_train, y_train)
    elapsed = time.perf_counter() - t0
    log.info("Random Forest fitted in %.2fs", elapsed)
    return rf


# ─── Evaluation ───────────────────────────────────────────────────────────────
def evaluate(
    model: RandomForestClassifier,
    X_test: np.ndarray,
    y_test: np.ndarray,
    threshold: float,
) -> dict:
    """Score predictions on the held-out test set and return a full metrics dict."""
    y_pred = model.predict(X_test)
    label_names = [LABEL_NAMES[i] for i in sorted(LABEL_NAMES)]

    acc = float(accuracy_score(y_test, y_pred))
    log.info("Held-out test accuracy: %.4f (%.1f%%) on %d samples", acc, acc * 100, len(y_test))

    report_text = classification_report(y_test, y_pred, target_names=label_names)
    log.info("Classification report (held-out test set):\n%s", report_text)

    cm = confusion_matrix(y_test, y_pred)
    log.info("Confusion matrix (held-out test set):\n%s", cm)

    if acc < threshold:
        log.warning(
            "Accuracy %.4f is below the project target of %.2f. "
            "Consider retuning hyperparameters or enriching the dataset.",
            acc,
            threshold,
        )
    else:
        log.info("✅ Accuracy target (≥ %.2f) met.", threshold)

    report_dict = classification_report(
        y_test, y_pred, target_names=label_names, output_dict=True
    )
    return {
        "accuracy": acc,
        "confusion_matrix": cm.tolist(),
        "confusion_matrix_labels": label_names,
        "classification_report": report_dict,
        "test_samples": int(len(y_test)),
    }


# ─── Persistence ──────────────────────────────────────────────────────────────
def save_artifacts(
    scaler: StandardScaler,
    model: RandomForestClassifier,
    metrics: dict,
    train_accuracy: float,
    config: TrainerConfig,
) -> None:
    """Persist all model artefacts + honest evaluation metadata."""
    config.output_dir.mkdir(parents=True, exist_ok=True)

    scaler_path   = config.output_dir / "scaler.joblib"
    model_path    = config.output_dir / "rf_model.joblib"
    metadata_path = config.output_dir / "model_metadata.json"

    joblib.dump(scaler, scaler_path)
    log.info("Scaler saved → %s", scaler_path)

    joblib.dump(model, model_path)
    log.info("Random Forest model saved → %s", model_path)

    metadata: dict = {
        "model_name": "observer_ai",
        "version": "1.2.0",  # Bumped: honest held-out evaluation
        "trained_at": datetime.now(timezone.utc).isoformat(),
        # `accuracy` is the held-out TEST accuracy — the number we quote.
        "accuracy": round(metrics["accuracy"], 6),
        "train_accuracy": round(train_accuracy, 6),
        "evaluation": "80/20 stratified train/test split — accuracy is on the held-out 20%",
        "test_samples": metrics["test_samples"],
        "confusion_matrix": metrics["confusion_matrix"],
        "confusion_matrix_labels": metrics["confusion_matrix_labels"],
        "classification_report": metrics["classification_report"],
        "feature_columns": FEATURE_COLS,
        "label_map": {str(k): v for k, v in LABEL_NAMES.items()},
        "hyperparameters": {
            "rf_n_estimators": config.rf_n_estimators,
            "rf_max_depth": config.rf_max_depth,
            "rf_random_state": config.rf_random_state,
        },
    }

    with metadata_path.open("w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=2)
    log.info("Metadata saved → %s", metadata_path)


# ─── Orchestration ────────────────────────────────────────────────────────────
def run_training(config: TrainerConfig | None = None) -> float:
    """End-to-end Observer AI training pipeline."""
    if config is None:
        config = TrainerConfig()

    log.info("═" * 60)
    log.info("GridMind Observer AI — Training Pipeline")
    log.info("═" * 60)

    df = load_and_validate(config.dataset_path)
    X_scaled, y_true, scaler = scale_features(df)

    # Honest evaluation: train on 80%, measure accuracy on a held-out 20% test set.
    # Stratify keeps the class balance in both splits; fall back if a class is too small.
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y_true, test_size=0.2,
            random_state=config.rf_random_state, stratify=y_true,
        )
    except ValueError:
        log.warning("Stratified split not possible (small/imbalanced data) — using a plain split.")
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y_true, test_size=0.2, random_state=config.rf_random_state,
        )

    model = fit_random_forest(
        X_train,
        y_train,
        config.rf_n_estimators,
        config.rf_max_depth,
        config.rf_random_state,
    )

    # Train accuracy too — so the train/test gap (overfit check) is visible.
    train_accuracy = float(accuracy_score(y_train, model.predict(X_train)))
    log.info("Train accuracy: %.4f (%.1f%%)", train_accuracy, train_accuracy * 100)

    metrics = evaluate(model, X_test, y_test, config.accuracy_threshold)
    save_artifacts(scaler, model, metrics, train_accuracy, config)

    log.info("═" * 60)
    log.info("Training complete. Artifacts → %s", config.output_dir)
    log.info("Held-out test accuracy: %.4f | Train accuracy: %.4f", metrics["accuracy"], train_accuracy)
    log.info("═" * 60)

    return metrics["accuracy"]


# ─── Entry-point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_training()
