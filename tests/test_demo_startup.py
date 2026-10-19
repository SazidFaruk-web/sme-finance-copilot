"""Advertised demo accounts must work with older databases without resetting owner data."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from sme_copilot.api.main import create_app
from sme_copilot.config import reset_settings_cache
from sme_copilot.demo.personas import PERSONAS, load_personas
from sme_copilot.models import Business, Transaction, User
from sme_copilot.security.auth import hash_password


def test_demo_startup_adds_missing_accounts_and_preserves_data_on_restart(seeded, monkeypatch):
    db = seeded["db"]
    bid = seeded["business"].id
    original_users = [(u.id, u.username, u.password_hash) for u in db.scalars(select(User).order_by(User.id))]
    original_records = [(t.id, t.amount) for t in db.scalars(select(Transaction).order_by(Transaction.id))]
    monkeypatch.setenv("APP_ENV", "demo")
    reset_settings_cache()
    try:
        for restart in range(2):
            with TestClient(create_app()) as client:
                advertised = client.get("/api/health").json()["demo_users"]
                assert {u["username"] for u in advertised} == set(PERSONAS)
                for account in advertised:
                    response = client.post("/api/auth/login", json={k: account[k] for k in ("username", "password")})
                    assert response.status_code == 200, response.text
                    assert response.json()["user"]["username"] == account["username"]
                    token = response.json()["token"]
                    assert client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 200
                db.expire_all()
                assert db.query(User).count() == 7
                assert db.query(Business).count() == 5
                assert [(u.id, u.username, u.password_hash) for u in db.scalars(
                    select(User).where(User.business_id == bid).order_by(User.id))] == original_users
                assert [(t.id, t.amount) for t in db.scalars(
                    select(Transaction).where(Transaction.business_id == bid).order_by(Transaction.id))] == original_records
                counts = (db.query(Transaction).count(), db.query(Business).count())
                if restart == 0:
                    first_counts = counts
                    # Startup must not silently reset a password changed since the initial seed.
                    rafi = db.scalar(select(User).where(User.username == "rafi"))
                    rafi.password_hash = hash_password("updated-demo-password")
                    db.commit()
                    changed_hash = rafi.password_hash
            if restart == 0:
                load_personas(db, seeded["business"].opening_balance_date)
                db.expire_all()
                assert db.scalar(select(User).where(User.username == "rafi")).password_hash == changed_hash
                # Restore the advertised password explicitly so all four logins can be tested on restart.
                from sme_copilot.demo.personas import password
                db.scalar(select(User).where(User.username == "rafi")).password_hash = hash_password(password("rafi"))
                db.commit()
            else:
                assert counts == first_counts
    finally:
        reset_settings_cache()


@pytest.mark.parametrize("environment", ["test", "dev", "production"])
def test_other_modes_do_not_create_demo_accounts(seeded, monkeypatch, environment):
    monkeypatch.setenv("APP_ENV", environment)
    reset_settings_cache()
    try:
        with TestClient(create_app()) as client:
            assert "demo_users" not in client.get("/api/health").json()
        assert seeded["db"].query(User).count() == 3
        assert seeded["db"].query(Business).count() == 1
    finally:
        reset_settings_cache()
