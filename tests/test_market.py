"""Home price drawer: public price data, nearest-area choice, forecasts and the download safeguards."""
from datetime import date

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from sme_copilot.api.main import create_app
from sme_copilot.market import catalog, forecast, prices, service

TODAY = date(2026, 10, 19)  # the bundled snapshot ends in August 2026


def monthly(values, last_month=8):
    return forecast.Series(values=np.asarray(values, dtype=float), last_month=last_month)


def test_statistical_forecast_gives_an_ordered_range_for_every_month():
    steps = forecast.statistical(monthly([50 + (i % 3) for i in range(30)]), 3)
    assert len(steps) == 3
    for s in steps:
        assert 0 < s.low <= s.median <= s.high
    assert steps[2].high - steps[2].low > steps[0].high - steps[0].low  # uncertainty grows with the horizon


def test_statistical_forecast_follows_a_steady_rise():
    rising = [100 * 1.02 ** i for i in range(24)]
    assert forecast.statistical(monthly(rising), 1)[0].median > rising[-1]


def test_baskets_and_district_names():
    assert catalog.basket("other:mobile phone repair") == ("other", catalog.STAPLES)
    assert catalog.basket("unknown")[0] == "other" and catalog.basket(None)[0] == "other"
    assert "Meat (chicken, broiler)" in catalog.basket("restaurant_food")[1]
    assert catalog.district_key("Chattogram") == catalog.district_key("Chittagong")
    assert catalog.district_key("Dhaka South") == catalog.district_key("Dhaka") == "dhaka"
    assert set(catalog.label("Sugar")) == {"en", "bn", "zh"}


def test_overview_uses_recent_prices_from_the_nearest_area():
    r = service.overview("Dhaka", "retail", TODAY)
    assert r["business_type"] == "retail" and r["target_month"] == "2026-11" and r["engine"]["kind"] == "statistical"
    assert r["source"]["origin"] == "snapshot" and r["source"]["license"] == "CC BY-IGO"
    assert len(r["items"]) >= 8
    newest = pd.Period(r["latest_observation"], "M")
    for item in r["items"]:
        assert item["area"]["level"] in ("district", "division", "national")
        assert pd.Period(item["observed"], "M") >= newest - service.FRESH_MONTHS  # never a stale series
        assert item["price"] > 0 and set(item["label"]) == {"en", "bn", "zh"}
        f = item["forecast"]
        assert f["month"] == "2026-11" and f["low_pct"] <= f["change_pct"] <= f["high_pct"]
        assert f["uncertain"] == (f["high_pct"] - f["low_pct"] > service.UNCERTAIN_SPREAD)
    assert any(i["area"]["level"] == "district" and i["area"]["name"] == "Dhaka" for i in r["items"])


def test_unknown_district_falls_back_to_the_national_average():
    r = service.overview("Atlantis", "other", TODAY)
    assert r["items"] and all(i["area"]["level"] in ("national", "division") for i in r["items"])


def test_garment_businesses_are_told_why_their_inputs_are_missing():
    r = service.overview("Gazipur", "garments_trims", TODAY)
    assert "fabric and trims" in r["note"]["en"] and r["note"]["zh"]


def test_no_forecast_far_beyond_the_latest_data():
    r = service.overview("Dhaka", "retail", date(2027, 9, 1))
    assert r["items"] and all(i["forecast"] is None for i in r["items"])
    assert "data too old" in service.summary_line(r["items"][0])


def test_no_download_in_local_only_mode_or_when_refresh_is_off(monkeypatch):
    from sme_copilot.config import reset_settings_cache

    def boom(*a, **kw):
        raise AssertionError("network used")

    monkeypatch.setattr(prices.httpx, "Client", boom)
    for env in ({"MARKET_REFRESH": "false"}, {"MARKET_REFRESH": "true", "LOCAL_ONLY_MODE": "true"}):
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        reset_settings_cache()
        assert prices.refresh(force=True) is False
        prices.refresh_in_background()  # returns without starting a thread
    reset_settings_cache()


@pytest.mark.parametrize("url,ok", [
    ("https://data.humdata.org/dataset/x/download/wfp_food_prices_bgd.csv", True),
    ("https://s3.us-east-1.amazonaws.com/hdx-production-filestore/resources/x/wfp_food_prices_bgd.csv", True),
    ("http://data.humdata.org/x.csv", False),
    ("https://s3.amazonaws.com/someone-else/x.csv", False),
    ("https://humdata.org.evil.example/x.csv", False),
])
def test_only_hdx_hosts_are_trusted(url, ok):
    assert prices._trusted(url) is ok


def test_refresh_keeps_good_data_and_rejects_a_broken_file(tmp_path, monkeypatch):
    from sme_copilot.config import reset_settings_cache

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("MARKET_REFRESH", "true")
    monkeypatch.setenv("LOCAL_ONLY_MODE", "false")
    reset_settings_cache()
    csv_url = "https://data.humdata.org/dataset/x/resource/y/download/wfp_food_prices_bgd.csv"
    good = pd.read_csv(prices.SNAPSHOT).head(2000).to_csv(index=False).encode()
    body = {"value": b"a,b\n1,2\n"}

    def handler(request: httpx.Request) -> httpx.Response:
        if "package_show" in str(request.url):
            return httpx.Response(200, json={"result": {"resources": [{"url": csv_url}]}})
        return httpx.Response(200, content=body["value"])

    real = httpx.Client
    monkeypatch.setattr(prices.httpx, "Client", lambda *a, **kw: real(*a, transport=httpx.MockTransport(handler), **kw))
    with pytest.raises(ValueError):
        prices.refresh(force=True)
    assert not (tmp_path / "market" / "wfp_food_prices_bgd.csv").exists()
    assert prices.load().origin == "snapshot"

    body["value"] = good
    assert prices.refresh(force=True) is True
    data = prices.load()
    assert data.origin == "download" and data.fetched_at and len(data.frame) > 1000
    assert prices.is_stale() is False
    reset_settings_cache()


@pytest.fixture
def client(seeded):
    from sme_copilot.security.http import limiter
    limiter.reset()
    with TestClient(create_app()) as c:
        yield c


def _login(client, user, pw):
    r = client.post("/api/auth/login", json={"username": user, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_market_endpoint_needs_login_and_serves_every_role(client):
    assert client.get("/api/market/prices").status_code == 401
    for user, pw in (("owner", "owner-pass-123"), ("viewer", "viewer-pass-123")):
        r = client.get("/api/market/prices", headers=_login(client, user, pw))
        assert r.status_code == 200, r.text
        assert r.json()["items"] and r.json()["source"]["name"].startswith("World Food Programme")
    assert client.get("/api/health").json()["market_prices"] is True


def test_market_endpoint_can_be_turned_off(client, monkeypatch):
    from sme_copilot.config import reset_settings_cache

    h = _login(client, "owner", "owner-pass-123")
    monkeypatch.setenv("MARKET_PRICES_ENABLED", "false")
    reset_settings_cache()
    assert client.get("/api/market/prices", headers=h).status_code == 404
    assert client.get("/api/health").json()["market_prices"] is False
    monkeypatch.delenv("MARKET_PRICES_ENABLED")
    reset_settings_cache()
