# Bundled market price snapshot

`wfp_bgd_prices.csv.gz` holds monthly prices from January 2022 to August 2026, filtered and reduced to the
columns the price drawer uses (`date, admin1, admin2, market, commodity, unit, pricetype, price`).

**Source:** World Food Programme (WFP), "Bangladesh - Food Prices", published on the Humanitarian Data Exchange:
<https://data.humdata.org/dataset/wfp-food-prices-for-bangladesh>. Licence: Creative Commons Attribution for
Intergovernmental Organisations (CC BY-IGO). Downloaded 2026-10-19.

The app replaces this snapshot with a fresh download at runtime (weekly, unless `LOCAL_ONLY_MODE` is on).
Rebuild it for a release with `python scripts/build_market_snapshot.py path/to/wfp_food_prices_bgd.csv`.
