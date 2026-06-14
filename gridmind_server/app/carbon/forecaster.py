"""
gridmind_server.app.carbon.forecaster
--------------------------------------
Trains an ARIMA(2,1,2) model on historical WattTime CAISO NORTH data
and provides 2-hour ahead forecasts in real units.

Role in the running system: the model is fit once at startup as the project's
forecasting artifact. The live dashboard "2-hour Grid Outlook" strip is driven by
the replayed CSV series (computed per-cycle in dispatcher_loop), NOT by this model,
so these forecast methods are not called in the hot decision loop.

CSV schema (watttime_carbon_data_CAISO_NORTH.csv):
    point_time  — ISO timestamp (5-minute resolution)
    value       — carbon intensity in lbs CO2/MWh

We convert to g CO2/kWh for display:
    g/kWh = lbs/MWh * 0.453592
"""
import os
import numpy as np
import pandas as pd

# statsmodels (ARIMA) is an OPTIONAL forecasting artifact, fit once at startup.
# The live "2-hour Grid Outlook" is driven by the replayed CSV series in
# dispatcher_loop, NOT by this model — so a missing statsmodels must NOT take
# down the whole dispatcher loop (which imports this module). Degrade gracefully:
# fit() raises a clear error only if it is actually called without statsmodels.
try:
    # pyrefly: ignore [missing-import]
    from statsmodels.tsa.arima.model import ARIMA
except ImportError:  # pragma: no cover - depends on the runtime environment
    ARIMA = None

# Conversion factor: 1 lb/MWh = 0.453592 g/kWh
LBS_MWH_TO_GCO2_KWH = 0.453592


class CarbonForecaster:
    """Trains on historical WattTime data, forecasts next 2h at 5-min resolution."""

    HORIZON = 24   # 24 x 5 min = 2 hours

    def __init__(self):
        self._model_result = None
        self._last_value_lbs: float = 600.0   # sensible default (~272 g/kWh)

    def fit(self, csv_path: str | None = None):
        if ARIMA is None:
            raise RuntimeError(
                "statsmodels is not installed — ARIMA forecaster unavailable. "
                "The dispatcher loop still runs on the replayed carbon series; "
                "install statsmodels to enable the ARIMA artifact."
            )
        if csv_path is None:
            csv_path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "watttime_carbon_data_CAISO_NORTH.csv"
            ))
        df = pd.read_csv(csv_path)
        df = df.sort_values("point_time").dropna(subset=["value"])
        series = df["value"].values[-2000:]   # last 2000 rows (~7 days)
        self._last_value_lbs = float(series[-1])
        self._model_result = ARIMA(series, order=(2, 1, 2)).fit()

    # ── Raw lbs/MWh helpers ───────────────────────────────────────────────────

    def forecast_lbs(self) -> list[float]:
        """Return HORIZON-step forecast in lbs CO2/MWh."""
        if self._model_result is None:
            raise RuntimeError("Call fit() first")
        raw = self._model_result.forecast(steps=self.HORIZON).tolist()
        return [round(max(0.0, v), 1) for v in raw]

    # ── Converted g/kWh helpers ───────────────────────────────────────────────

    def forecast_gco2(self) -> list[float]:
        """Return HORIZON-step forecast in g CO2/kWh (preferred unit for display)."""
        return [round(v * LBS_MWH_TO_GCO2_KWH, 1) for v in self.forecast_lbs()]

    def current_gco2(self) -> float:
        """Most recent observed value converted to g/kWh."""
        return round(self._last_value_lbs * LBS_MWH_TO_GCO2_KWH, 1)

    def two_hour_average_gco2(self) -> float:
        """Mean of the 2-hour forecast in g/kWh."""
        return round(float(np.mean(self.forecast_gco2())), 1)

    def next_clean_window_minutes(self, threshold_gco2: float = 450.0) -> int | None:
        """Return minutes until next sub-threshold forecast window (g/kWh), or None."""
        forecast = self.forecast_gco2()
        for i, val in enumerate(forecast):
            if val < threshold_gco2:
                return i * 5   # each step = 5 minutes
        return None
