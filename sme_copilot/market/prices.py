"""Public monthly market prices of everyday goods in Bangladesh.

Source: World Food Programme, "Bangladesh - Food Prices" on HDX (CC BY-IGO): retail prices of about
60 everyday items in about 110 markets, monthly. The newest month usually trails today by one to two
months, so every answer carries the month it was observed.

The file is public and the request carries no business data. It is refreshed in the background at most
every MARKET_REFRESH_DAYS and never in LOCAL_ONLY_MODE; a bundled snapshot covers offline use and new installs.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pandas as pd

from sme_copilot.config import get_settings

LOG = logging.getLogger(__name__)

HDX_PACKAGE = "https://data.humdata.org/api/3/action/package_show?id=wfp-food-prices-for-bangladesh"
SOURCE = {"name": "World Food Programme (WFP), via HDX", "license": "CC BY-IGO",
          "url": "https://data.humdata.org/dataset/wfp-food-prices-for-bangladesh"}
SNAPSHOT = Path(__file__).parent / "snapshot" / "wfp_bgd_prices.csv.gz"
COLUMNS = ["date", "admin1", "admin2", "market", "commodity", "unit", "pricetype", "price"]
MAX_DOWNLOAD_BYTES = 60 * 1024 * 1024
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


@dataclass(frozen=True)
class PriceData:
    frame: pd.DataFrame
    origin: str  # "download" | "snapshot"
    fetched_at: str | None
    latest: str  # newest observation, YYYY-MM-DD
    version: str  # changes whenever the underlying file changes


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Validated, typed rows. Raises ValueError for a file that is not the expected price table."""
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"market price file is missing columns: {missing}")
    if "currency" in df.columns:
        df = df[df["currency"].astype(str) == "BDT"]
    if "priceflag" in df.columns:
        df = df[df["priceflag"].astype(str).str.contains("actual|aggregate", regex=True)]
    df = df[COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    for col in ("admin1", "admin2", "market", "commodity", "unit", "pricetype"):
        df[col] = df[col].astype(str).str.strip()
    df = df.dropna(subset=["date", "price"])
    return df[(df["price"] > 0) & (df["date"] >= "2000-01-01")].reset_index(drop=True)


def _cache_file() -> Path:
    return get_settings().data_dir / "market" / "wfp_food_prices_bgd.csv"


def _meta_file() -> Path:
    return get_settings().data_dir / "market" / "meta.json"


def _read_meta() -> dict:
    try:
        return json.loads(_meta_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_load_lock = threading.Lock()
_loaded: tuple[tuple[str, int], PriceData] | None = None


def load() -> PriceData:
    """The downloaded file when present and valid, otherwise the bundled snapshot (cached per file version)."""
    global _loaded
    cached = _cache_file()
    path, origin = (cached, "download") if cached.exists() else (SNAPSHOT, "snapshot")
    key = (str(path), path.stat().st_mtime_ns)
    with _load_lock:
        if _loaded and _loaded[0] == key:
            return _loaded[1]
        try:
            frame = normalize_frame(pd.read_csv(path))
        except (OSError, ValueError) as e:
            if origin == "snapshot":
                raise
            LOG.warning("market price cache unreadable (%s); using the bundled snapshot", e)
            path, origin = SNAPSHOT, "snapshot"
            key = (str(path), path.stat().st_mtime_ns)
            frame = normalize_frame(pd.read_csv(path))
        meta = _read_meta() if origin == "download" else {}
        data = PriceData(frame=frame, origin=origin, fetched_at=meta.get("fetched_at"),
                         latest=frame["date"].max().date().isoformat(), version=f"{origin}:{key[1]}")
        _loaded = (key, data)
        return data


def refresh_allowed() -> bool:
    s = get_settings()
    return s.market_refresh and not s.local_only_mode


def is_stale(now: datetime | None = None) -> bool:
    if not _cache_file().exists():
        return True
    fetched = _read_meta().get("fetched_at")
    if not fetched:
        return True
    try:
        age = (now or datetime.now(timezone.utc)) - datetime.fromisoformat(fetched)
    except ValueError:
        return True
    return age.total_seconds() > get_settings().market_refresh_days * 86400


def _trusted(url: str) -> bool:
    """HDX pages, or HDX's own file store that its download links redirect to."""
    u = urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https":
        return False
    if host == "data.humdata.org" or host.endswith(".humdata.org"):
        return True
    return host.endswith(".amazonaws.com") and u.path.startswith("/hdx-production-filestore/")


def _resolve_url(client: httpx.Client) -> str:
    configured = get_settings().market_data_url
    if configured:
        return configured  # operator-set; not influenced by any request
    r = client.get(HDX_PACKAGE)
    r.raise_for_status()
    for res in r.json()["result"]["resources"]:
        url = str(res.get("url", ""))
        if url.endswith("wfp_food_prices_bgd.csv") and _trusted(url):
            return url
    raise ValueError("HDX package has no Bangladesh price CSV")


def refresh(force: bool = False, explicit: bool = False) -> bool:
    """Download the latest public file. Returns True when a new file was stored.

    ``explicit`` is the operator's own command (``cli market --setup``), allowed even in LOCAL_ONLY_MODE;
    the web app only refreshes automatically when that mode is off."""
    if not (explicit or refresh_allowed()) or (not force and not is_stale()):
        return False
    target = _cache_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    with httpx.Client(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "sme-copilot/market-prices"}) as client:
        url = _resolve_url(client)
        size = 0
        with client.stream("GET", url) as r:
            r.raise_for_status()
            if not _trusted(str(r.url)) and not get_settings().market_data_url:
                raise ValueError(f"price download redirected to an unexpected host: {r.url.host}")
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes():
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise ValueError("price download exceeded the size limit")
                    f.write(chunk)
    try:
        frame = normalize_frame(pd.read_csv(tmp))  # never replace good data with a broken file
        if len(frame) < 1000:
            raise ValueError(f"price download has only {len(frame)} usable rows")
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, target)
    _meta_file().write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "url": url,
                                        "rows": len(frame)}), encoding="utf-8")
    LOG.info("market prices refreshed: %s rows, newest %s", len(frame), frame["date"].max().date())
    return True


_refresh_lock = threading.Lock()


def refresh_in_background() -> None:
    """Start one refresh thread when the data is stale; the current request keeps using what is loaded."""
    if not refresh_allowed() or not is_stale() or _refresh_lock.locked():
        return

    def run() -> None:
        with _refresh_lock:
            try:
                refresh()
            except Exception as e:  # network, HDX format or disk problems never break the drawer
                LOG.warning("market price refresh failed: %s", e)

    threading.Thread(target=run, name="market-refresh", daemon=True).start()
