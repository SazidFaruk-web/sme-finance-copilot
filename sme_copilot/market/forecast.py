"""Price direction for the coming months from a monthly price series.

Primary engine: Amazon Chronos-Bolt (Apache-2.0), a small time-series foundation model (48M parameters for
"small") that runs on CPU. It reads up to three years of monthly prices and returns quantiles. It is optional:
install it with requirements-forecast.txt. Weights are fetched from Hugging Face once, never in LOCAL_ONLY_MODE.

Fallback engine, always available: a damped trend plus month-of-year pattern on log prices. Both engines return
the median and a 10-90% range, and the drawer shows the range so a forecast never reads as a promise.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from dataclasses import dataclass

import numpy as np

from sme_copilot.config import get_settings

LOG = logging.getLogger(__name__)
QUANTILES = [0.1, 0.5, 0.9]
Z90 = 1.2816  # 10th/90th percentile of a normal distribution
RETRY_AFTER_SECONDS = 1800


@dataclass(frozen=True)
class Step:
    median: float
    low: float
    high: float


@dataclass(frozen=True)
class Series:
    values: np.ndarray  # monthly prices, oldest first, no gaps
    last_month: int  # calendar month (1-12) of the last value


def _seasonal_offsets(y: np.ndarray, last_month: int) -> np.ndarray:
    """Average log deviation from a centred 12-month mean, by calendar month (index 0 = January)."""
    out = np.zeros(12)
    if len(y) < 24:
        return out
    trend = np.convolve(y, np.ones(12) / 12, mode="same")
    dev, counts = np.zeros(12), np.zeros(12)
    for i in range(6, len(y) - 6):  # the moving average is only centred away from the ends
        m = (last_month - 1 - (len(y) - 1 - i)) % 12
        dev[m] += y[i] - trend[i]
        counts[m] += 1
    seen = counts > 0
    out[seen] = dev[seen] / counts[seen]
    out -= out[seen].mean() if seen.any() else 0
    return 0.5 * out  # shrink: two or three years of data overstate seasonality


def statistical(series: Series, horizon: int) -> list[Step]:
    y = np.log(series.values.astype(float))
    recent = y[-12:]
    slope = float(np.polyfit(np.arange(len(recent)), recent, 1)[0]) if len(recent) >= 4 else 0.0
    diffs = np.diff(y[-25:])
    sigma = float(np.std(diffs)) if len(diffs) >= 3 else 0.05
    sigma = max(sigma, 0.01)
    season = _seasonal_offsets(y, series.last_month)
    base_m = series.last_month - 1
    phi, damp, steps = 0.8, 0.0, []
    for h in range(1, horizon + 1):
        damp += phi ** h
        mu = y[-1] + slope * damp + season[(base_m + h) % 12] - season[base_m]
        sd = sigma * math.sqrt(h)
        steps.append(Step(math.exp(mu), math.exp(mu - Z90 * sd), math.exp(mu + Z90 * sd)))
    return steps


class Statistical:
    name, kind = "statistical", "statistical"

    def predict(self, batch: list[Series], horizon: int) -> list[list[Step]]:
        return [statistical(s, horizon) for s in batch]


class Chronos:
    kind = "model"

    def __init__(self, model_id: str, local_only: bool):
        import torch
        from chronos import BaseChronosPipeline

        self.name = model_id.split("/")[-1]
        self._torch = torch
        # safetensors only: a weights file can never run code when it is loaded.
        self.pipeline = BaseChronosPipeline.from_pretrained(model_id, device_map="cpu", torch_dtype=torch.float32,
                                                            local_files_only=local_only, use_safetensors=True)

    def predict(self, batch: list[Series], horizon: int) -> list[list[Step]]:
        inputs = [self._torch.tensor(s.values, dtype=self._torch.float32) for s in batch]
        with self._torch.no_grad():
            q, _mean = self.pipeline.predict_quantiles(inputs, prediction_length=horizon, quantile_levels=QUANTILES)
        q = q.numpy()  # [series, horizon, quantile]
        out = []
        for row in q:
            steps = []
            for lo, med, hi in row:
                lo, med, hi = sorted((float(lo), float(med), float(hi)))
                steps.append(Step(med, lo, hi))
            out.append(steps)
        return out


_lock = threading.Lock()
_model: Chronos | None = None
_failed_at = 0.0
_loading = False


def _load_model() -> None:
    global _model, _failed_at, _loading
    s = get_settings()
    try:
        model = Chronos(s.market_forecast_model, local_only=s.local_only_mode)
        with _lock:
            _model = model
        LOG.info("market forecast model loaded: %s", s.market_forecast_model)
    except Exception as e:  # not installed, no cached weights offline, or a download problem
        with _lock:
            _failed_at = time.monotonic()
        LOG.warning("market forecast model unavailable (%s); using the statistical estimate", e)
    finally:
        with _lock:
            _loading = False


def download_model() -> str | None:
    """Operator step (``cli market --setup``): fetch the weights into the local cache, then load them."""
    global _model, _failed_at
    model_id = get_settings().market_forecast_model
    if not model_id:
        return None
    try:
        model = Chronos(model_id, local_only=False)
    except Exception as e:
        LOG.warning("could not download %s: %s", model_id, e)
        return None
    with _lock:
        _model, _failed_at = model, 0.0
    return model.name


def forecaster(wait: bool = False):
    """The model when it is loaded; otherwise the statistical engine while the model loads in the background."""
    global _loading
    if not get_settings().market_forecast_model:
        return Statistical()
    with _lock:
        if _model is not None:
            return _model
        retry = not _failed_at or time.monotonic() - _failed_at > RETRY_AFTER_SECONDS
        start = retry and not _loading
        if start:
            _loading = True
    if start:
        if wait:
            _load_model()
            return _model or Statistical()
        threading.Thread(target=_load_model, name="market-model", daemon=True).start()
    return Statistical()
