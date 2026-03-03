"""
tests.ml.test_observer
=======================
Automated tests for the GridMind Observer AI training pipeline
and inference wrapper.

Run with:
    pytest tests/ml/test_observer.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

# Project root so relative imports work regardless of CWD
PROJECT_ROOT = Path(__file__).parents[2]

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def trained_model_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the training pipeline once into a temp directory and return its path.

    Using ``scope="module"`` ensures training runs only once for the whole
    test module, keeping the suite fast.
    """
    from gridmind_server.app.ml.observer_trainer import TrainerConfig, run_training

    out_dir = tmp_path_factory.mktemp("observer_model")
    config = TrainerConfig(
        dataset_path=PROJECT_ROOT / "data" / "telemetry_dataset.csv",
        output_dir=out_dir,
        # Use a smaller n_init to keep CI fast while still being deterministic
        kmeans_n_init=5,
    )
    run_training(config)
    return out_dir


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestTrainingProducesArtifacts:
    """Verify that the trainer emits exactly the expected artefact files."""

    def test_scaler_file_exists(self, trained_model_dir: Path) -> None:
        assert (trained_model_dir / "scaler.joblib").exists(), (
            "scaler.joblib was not created by the trainer."
        )

    def test_kmeans_file_exists(self, trained_model_dir: Path) -> None:
        assert (trained_model_dir / "kmeans.joblib").exists(), (
            "kmeans.joblib was not created by the trainer."
        )

    def test_metadata_file_exists(self, trained_model_dir: Path) -> None:
        assert (trained_model_dir / "model_metadata.json").exists(), (
            "model_metadata.json was not created by the trainer."
        )


class TestMetadataSchema:
    """Verify the metadata JSON contains the required keys and valid values."""

    @pytest.fixture(scope="class")
    def metadata(self, trained_model_dir: Path) -> dict:
        with (trained_model_dir / "model_metadata.json").open() as fh:
            return json.load(fh)

    def test_required_keys_present(self, metadata: dict) -> None:
        required = {
            "model_name", "version", "trained_at",
            "accuracy", "noise_ratio",
            "feature_columns", "label_map", "hyperparameters",
        }
        assert required.issubset(metadata.keys()), (
            f"Metadata missing keys: {required - metadata.keys()}"
        )

    def test_accuracy_meets_project_target(self, metadata: dict) -> None:
        acc = metadata["accuracy"]
        assert acc >= 0.85, (
            f"Observer AI accuracy {acc:.4f} is below the 0.85 project target. "
            "Retune DBSCAN/K-Means hyperparameters or review the dataset."
        )

    def test_label_map_has_three_entries(self, metadata: dict) -> None:
        assert len(metadata["label_map"]) == 3, (
            f"Expected 3 cluster→label mappings, got {len(metadata['label_map'])}."
        )

    def test_label_map_covers_all_states(self, metadata: dict) -> None:
        state_names = set(metadata["label_map"].values())
        assert state_names == {"idle", "active_user", "busy_hardware"}, (
            f"label_map states do not match expected set: {state_names}"
        )


class TestObserverInference:
    """Verify runtime behaviour of ObserverInference."""

    @pytest.fixture(scope="class")
    def observer(self, trained_model_dir: Path):
        from gridmind_server.app.ml.observer_inference import ObserverInference
        return ObserverInference(model_dir=trained_model_dir)

    # ── snapshot helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _idle_snapshot() -> dict:
        return {
            "cpu_usage_pct": 5.0,
            "ram_usage_pct": 28.0,
            "kb_events_per_min": 0,
            "mouse_events_per_min": 1,
            "net_io_bytes": 1000.0,
            "process_count": 75,
            "carbon_intensity_gco2": 220.0,
        }

    @staticmethod
    def _active_user_snapshot() -> dict:
        return {
            "cpu_usage_pct": 38.0,
            "ram_usage_pct": 58.0,
            "kb_events_per_min": 130,
            "mouse_events_per_min": 160,
            "net_io_bytes": 450_000.0,
            "process_count": 120,
            "carbon_intensity_gco2": 280.0,
        }

    @staticmethod
    def _busy_hw_snapshot() -> dict:
        return {
            "cpu_usage_pct": 85.0,
            "ram_usage_pct": 79.0,
            "kb_events_per_min": 0,
            "mouse_events_per_min": 0,
            "net_io_bytes": 80_000.0,
            "process_count": 105,
            "carbon_intensity_gco2": 310.0,
        }

    # ── output contract ───────────────────────────────────────────────────────

    def test_predict_returns_required_keys(self, observer) -> None:
        result = observer.predict(self._idle_snapshot())
        assert set(result.keys()) == {"label", "state", "confidence"}

    def test_confidence_in_valid_range(self, observer) -> None:
        result = observer.predict(self._idle_snapshot())
        assert 0.0 <= result["confidence"] <= 1.0, (
            f"Confidence {result['confidence']} is out of [0, 1] range."
        )

    def test_label_is_valid_int(self, observer) -> None:
        result = observer.predict(self._idle_snapshot())
        assert result["label"] in (0, 1, 2), (
            f"label {result['label']!r} is not one of {{0, 1, 2}}."
        )

    def test_state_matches_label(self, observer) -> None:
        label_to_state = {0: "idle", 1: "active_user", 2: "busy_hardware"}
        result = observer.predict(self._idle_snapshot())
        assert result["state"] == label_to_state[result["label"]], (
            f"state {result['state']!r} does not match label {result['label']}."
        )

    # ── semantic correctness ──────────────────────────────────────────────────

    def test_idle_snapshot_classified_as_idle(self, observer) -> None:
        result = observer.predict(self._idle_snapshot())
        assert result["state"] == "idle", (
            f"Expected 'idle', got {result['state']!r}. "
            "Check cluster→label mapping logic."
        )

    def test_active_user_snapshot_classified_correctly(self, observer) -> None:
        result = observer.predict(self._active_user_snapshot())
        assert result["state"] == "active_user", (
            f"Expected 'active_user', got {result['state']!r}."
        )

    def test_busy_hw_snapshot_classified_correctly(self, observer) -> None:
        result = observer.predict(self._busy_hw_snapshot())
        assert result["state"] == "busy_hardware", (
            f"Expected 'busy_hardware', got {result['state']!r}."
        )

    # ── error handling ────────────────────────────────────────────────────────

    def test_missing_feature_raises_value_error(self, observer) -> None:
        bad_snapshot = {k: v for k, v in self._idle_snapshot().items()
                        if k != "cpu_usage_pct"}
        with pytest.raises(ValueError, match="missing required keys"):
            observer.predict(bad_snapshot)

    def test_metadata_property_returns_dict(self, observer) -> None:
        meta = observer.metadata
        assert isinstance(meta, dict)
        assert "accuracy" in meta
