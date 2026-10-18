"""Build the bundled market-price snapshot from the WFP Bangladesh CSV published on HDX.

The app refreshes this data itself (weekly, unless LOCAL_ONLY_MODE is on). The snapshot keeps the
price drawer working offline and on a fresh install. Rebuild it when releasing:

    python scripts/build_market_snapshot.py path/to/wfp_food_prices_bgd.csv

Source: World Food Programme, "Bangladesh - Food Prices" on HDX, licensed CC BY-IGO.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sme_copilot.market.prices import SNAPSHOT, normalize_frame  # noqa: E402

SINCE = "2022-01-01"  # 3+ years: two years of context plus a year of seasonality


def main(src: str) -> None:
    import pandas as pd

    df = normalize_frame(pd.read_csv(src))
    df = df[df["date"] >= SINCE]
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(SNAPSHOT, index=False, compression="gzip", date_format="%Y-%m-%d")
    print(f"{len(df)} rows, {df['date'].min().date()} to {df['date'].max().date()} -> {SNAPSHOT} "
          f"({SNAPSHOT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
