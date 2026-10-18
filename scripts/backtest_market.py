"""Backtest the Home price drawer's forecasts on real WFP price series.

Hides the last H months of every market/item series with at least 30 months, forecasts them, and compares the
model, the statistical estimate and "no change". Reports typical error, direction accuracy for moves over 2%,
and how often each engine's 10-90% range contained the real price (ideal: about 80%).

    python scripts/backtest_market.py [months_ahead]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sme_copilot.market import forecast, prices, service  # noqa: E402

H = int(sys.argv[1]) if len(sys.argv) > 1 else 3

frame = prices.load().frame
frame = frame[frame["pricetype"] == "Retail"]
newest = pd.Period(frame["date"].max(), freq="M")
series = []
for _, rows in frame.groupby(["market", "commodity", "unit"]):
    s = service._monthly(rows)
    s = s[s.index >= s.index.max() - 47]
    if len(s) >= 30 and s.index.max() >= newest - service.FRESH_MONTHS:
        series.append(s)
print(f"{len(series)} market/item series with at least 30 months; forecasting {H} months ahead")

hist = [forecast.Series(values=s.to_numpy(float)[-(36 + H):-H], last_month=s.index[-H - 1].month) for s in series]
truth = np.array([s.to_numpy(float)[-1] for s in series])
last = np.array([h.values[-1] for h in hist])
moved = np.abs(truth / last - 1) > 0.02
engines = {"statistical": forecast.Statistical()}
model = forecast.forecaster(wait=True)
if model.kind == "model":
    engines[model.name] = model

rows = [("no change", last, None)]
for name, engine in engines.items():
    steps = [p[H - 1] for p in engine.predict(hist, H)]
    rows.append((name, np.array([s.median for s in steps]), steps))
for name, pred, steps in rows:
    ape = np.abs(pred / truth - 1) * 100
    line = f"{name:20} median error {np.median(ape):5.2f}%  mean {np.mean(ape):5.2f}%"
    if steps is not None:
        right = np.mean(np.sign(pred[moved] - last[moved]) == np.sign(truth[moved] - last[moved])) * 100
        inside = np.mean([s.low <= t <= s.high for s, t in zip(steps, truth)]) * 100
        line += f"  direction right {right:4.1f}% of {moved.sum()} moves  range held {inside:4.1f}%"
    print(line)
