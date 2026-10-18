"""Assemble the price drawer: relevant items, the nearest market with enough history, and next-month direction."""
from __future__ import annotations

import threading
from datetime import date

import pandas as pd

from . import catalog, forecast, prices

CONTEXT_MONTHS = 36  # up to three years of monthly prices go to the model
MIN_MONTHS = 12  # fewer than this and no forecast is offered
FRESH_MONTHS = 3  # an area's series must reach within this many months of the newest data, else widen the area
MAX_AHEAD = 6  # no forecast further than this past the last observation
UNCERTAIN_SPREAD = 30  # percentage points between the 10% and 90% outcomes
HISTORY_MONTHS = 24  # the sparkline shows two years
CACHE_LIMIT = 256

_cache: dict[tuple, dict] = {}
_cache_lock = threading.Lock()


def _monthly(rows: pd.DataFrame) -> pd.Series:
    """Median price per month across the markets in an area, with short gaps filled by interpolation."""
    s = rows.groupby(rows["date"].dt.to_period("M"))["price"].median().sort_index()
    if s.empty:
        return s
    full = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    return full.interpolate(limit=2, limit_area="inside").dropna()


def _division_of(frame: pd.DataFrame, key: str) -> str | None:
    rows = frame[frame["admin2"].map(catalog.district_key) == key]
    return rows["admin1"].mode().iloc[0] if not rows.empty else None


def _area_series(frame: pd.DataFrame, district: str, commodity: str, cutoff: pd.Timestamp, fresh_from: pd.Period):
    """Nearest area (district, then division, then all markets) with enough recent, up-to-date months."""
    rows = frame[(frame["commodity"] == commodity) & (frame["date"] >= cutoff)]
    retail = rows[rows["pricetype"] == "Retail"]
    rows = retail if not retail.empty else rows
    if rows.empty:
        return None
    unit = rows["unit"].mode().iloc[0]
    rows = rows[rows["unit"] == unit]
    key = catalog.district_key(district)
    division = _division_of(frame, key)
    by_district = rows[rows["admin2"].map(catalog.district_key) == key]
    candidates = [("district", by_district, by_district["admin2"].iloc[0] if not by_district.empty else district),
                  ("division", rows[rows["admin1"] == division] if division else rows.iloc[0:0], division),
                  ("national", rows, "Bangladesh")]
    for level, sub, name in candidates:
        s = _monthly(sub)
        if len(s) >= MIN_MONTHS and s.index[-1] >= fresh_from:
            return {"level": level, "name": name, "series": s, "unit": unit, "pricetype": rows["pricetype"].iloc[0],
                    "markets": int(sub["market"].nunique())}
    return None


def _pct(new: float, old: float) -> float | None:
    return round((new / old - 1) * 100, 1) if old else None


def overview(district: str | None, business_type: str | None, today: date) -> dict:
    data = prices.load()
    prices.refresh_in_background()
    bt, items = catalog.basket(business_type)
    district = district or "Dhaka"
    engine = forecast.forecaster()
    target = pd.Period(today, freq="M") + 1  # "next month" from the owner's point of view
    key = (data.version, catalog.district_key(district), bt, str(target), engine.name)
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    frame = data.frame
    newest = frame["date"].max()
    cutoff = newest - pd.DateOffset(months=CONTEXT_MONTHS)
    fresh_from = pd.Period(newest, freq="M") - FRESH_MONTHS
    found = []
    for commodity in items:
        area = _area_series(frame, district, commodity, cutoff, fresh_from)
        if area:
            found.append((commodity, area))

    out_items = []
    if found:
        horizons = [max(1, (target - a["series"].index[-1]).n) for _, a in found]
        batch = [forecast.Series(values=a["series"].to_numpy(dtype=float)[-CONTEXT_MONTHS:], last_month=a["series"].index[-1].month)
                 for _, a in found]
        steps = engine.predict(batch, min(max(horizons), MAX_AHEAD))
        for (commodity, area), h, path in zip(found, horizons, steps):
            s = area["series"]
            last = float(s.iloc[-1])
            outlook = None
            if h <= MAX_AHEAD:
                step = path[h - 1]
                low, high = _pct(step.low, last), _pct(step.high, last)
                outlook = {"month": str(target), "price": round(step.median, 2), "change_pct": _pct(step.median, last),
                           "low_pct": low, "high_pct": high, "months_ahead": h,
                           "uncertain": high - low > UNCERTAIN_SPREAD}
            out_items.append({
                "id": commodity, "label": catalog.label(commodity), "unit": catalog.unit_label(area["unit"]),
                "pricetype": area["pricetype"].lower(), "price": round(last, 2), "observed": str(s.index[-1]),
                "change_1m_pct": _pct(last, float(s.iloc[-2])) if len(s) > 1 else None,
                "change_12m_pct": _pct(last, float(s.iloc[-13])) if len(s) > 12 else None,
                "area": {"level": area["level"], "name": area["name"], "markets": area["markets"]},
                "forecast": outlook,
                "history": [[str(p), round(float(v), 2)] for p, v in s.iloc[-HISTORY_MONTHS:].items()],
                "context_months": int(min(len(s), CONTEXT_MONTHS)),
            })

    result = {
        "business_type": bt, "district": district, "target_month": str(target),
        "latest_observation": data.latest[:7],
        "engine": {"name": engine.name, "kind": engine.kind},
        "source": {**prices.SOURCE, "origin": data.origin, "fetched_at": data.fetched_at},
        "note": catalog.NOTES.get(bt), "items": out_items,
    }
    with _cache_lock:
        if len(_cache) >= CACHE_LIMIT:
            _cache.clear()
        _cache[key] = result
    return result


def summary_line(item: dict, lang: str = "en") -> str:
    """One plain sentence for logs and the CLI; the drawer builds its own localized line from the numbers."""
    head = f"{item['label'][lang]}: ৳{item['price']:g} {item['unit'][lang]} ({item['observed']})"
    f = item["forecast"]
    if not f:
        return head + "; no forecast (data too old)"
    direction = "up" if (f["change_pct"] or 0) > 0.5 else "down" if (f["change_pct"] or 0) < -0.5 else "steady"
    return (f"{head}; likely {direction} {f['change_pct']:+.1f}% by {f['month']} "
            f"(range {f['low_pct']:+.1f}% to {f['high_pct']:+.1f}%{', uncertain' if f['uncertain'] else ''})")
