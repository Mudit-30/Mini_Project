"""
gridmind_server.app.jobs.retrain
----------------------------------
APScheduler background job: retrain the Observer AI every 4 hours
using the latest telemetry records stored in SQLite.

How it works
------------
1. Query the 5,000 most recent TelemetryRecord rows from the DB.
2. Write them to a temporary CSV (matching the dataset schema).
3. Call ``run_training()`` with the temp CSV as input.
4. Hot-swap the loaded ``ObserverInference`` singleton in-place so the
   running server immediately benefits from the updated model —
   without any downtime or restart.
"""
from __future__ import annotations

import asyncio
import csv
import logging
import tempfile
from pathlib import Path

from app.db.database import AsyncSessionLocal, TelemetryRecord, select

logger = logging.getLogger("gridmind.retrain")

# How many recent records to pull for retraining
RETRAIN_SAMPLE_SIZE = 5_000

# Minimum records needed before attempting a retrain
MIN_RECORDS_REQUIRED = 500


async def _fetch_recent_records(n: int) -> list[TelemetryRecord]:
    """Fetch the ``n`` most recent TelemetryRecord rows from SQLite."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(TelemetryRecord)
            .order_by(TelemetryRecord.recorded_at.desc())
            .limit(n)
        )
        return result.scalars().all()


def _write_temp_csv(records: list[TelemetryRecord]) -> Path:
    """
    Write records to a temporary CSV that matches the training dataset schema.
    Returns the path to the temp file.
    """
    columns = [
        "cpu_usage_pct", "ram_usage_pct",
        "kb_events_per_min", "mouse_events_per_min",
        "net_io_bytes", "process_count",
        "carbon_intensity_gco2", "label",
    ]

    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    try:
        writer = csv.DictWriter(tmp, fieldnames=columns)
        writer.writeheader()
        for r in records:
            if r.predicted_label is None:
                continue   # skip rows where AI failed to classify
            writer.writerow({
                "cpu_usage_pct":        r.cpu_usage_pct,
                "ram_usage_pct":        r.ram_usage_pct,
                "kb_events_per_min":    r.kb_events_per_min,
                "mouse_events_per_min": r.mouse_events_per_min,
                "net_io_bytes":         r.net_io_bytes,
                "process_count":        r.process_count,
                "carbon_intensity_gco2": r.carbon_intensity_gco2,
                "label":                r.predicted_label,
            })
    finally:
        tmp.close()

    return Path(tmp.name)


async def retrain_observer(observer) -> None:
    """
    Async entry point called by APScheduler.

    Fetches recent DB records → writes temp CSV → runs training → hot-swaps model.
    Logs warnings and returns quietly on failure so the scheduler survives errors.

    Parameters
    ----------
    observer :
        The live ``ObserverInference`` singleton stored in ``app.state``.
    """
    logger.warning(
        "Auto-retrain uses the Observer's OWN predicted_label as ground truth "
        "(self-supervised) — it can reinforce existing errors. Treat held-out "
        "accuracy from this job as a stability signal, not true generalisation."
    )
    logger.info("Auto-retrain triggered. Fetching %d recent records…", RETRAIN_SAMPLE_SIZE)

    try:
        records = await _fetch_recent_records(RETRAIN_SAMPLE_SIZE)
    except Exception as exc:
        logger.error("Failed to fetch records for retrain: %s", exc)
        return

    if len(records) < MIN_RECORDS_REQUIRED:
        logger.warning(
            "Only %d records in DB — need at least %d. Skipping retrain.",
            len(records), MIN_RECORDS_REQUIRED,
        )
        return

    logger.info("Fetched %d records. Writing temp CSV…", len(records))
    csv_path = _write_temp_csv(records)

    try:
        from app.ml.observer_trainer import TrainerConfig, run_training

        config = TrainerConfig(
            dataset_path=csv_path,
            # Save new model to the same directory so server reads it on next reload
            output_dir=Path(__file__).parents[3] / "models" / "observer",
        )

        # run_training is blocking (CPU-bound) — run it in a thread pool
        loop = asyncio.get_running_loop()
        accuracy = await loop.run_in_executor(None, run_training, config)

        logger.info("Retrain complete. New accuracy = %.4f", accuracy)

        # Hot-swap: reload the model files the observer wraps
        observer.reload()
        logger.info("ObserverInference hot-swapped with new model.")

    except Exception as exc:
        logger.error("Retrain pipeline failed: %s", exc)

    finally:
        # Clean up the temp CSV
        try:
            csv_path.unlink(missing_ok=True)
        except Exception:
            pass
