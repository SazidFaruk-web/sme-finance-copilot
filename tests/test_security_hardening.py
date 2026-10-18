"""Regression tests for issues found in the 2026-10 security review."""
import bcrypt
import pytest

from sme_copilot.security import auth


def test_unknown_usernames_cost_the_same_as_wrong_passwords(seeded, monkeypatch):
    """An unknown user used to be checked against a cheaper hash, so timing revealed which accounts exist."""
    costs = []
    real_checkpw = bcrypt.checkpw

    def spy(password, hashed):
        costs.append(hashed.decode().split("$")[2])
        return real_checkpw(password, hashed)

    monkeypatch.setattr(auth.bcrypt, "checkpw", spy)
    db = seeded["db"]
    for username in ("owner", "no-such-user"):
        try:
            auth.authenticate(db, username, "wrong-password-1")
        except auth.AuthError:
            pass
    assert len(costs) == 2 and costs[0] == costs[1]


@pytest.mark.parametrize("app_env,flag,expected", [
    ("demo", None, True),          # judges and demos see labelled financing matching
    ("production", None, False),   # real owners never get illustrative loan terms by default
    ("dev", None, False),
    ("demo", "false", False),      # an explicit "false" wins even in demo
    ("production", "true", True),
])
def test_illustrative_guidance_follows_the_mode_unless_set(monkeypatch, app_env, flag, expected):
    from sme_copilot.config import get_settings, reset_settings_cache

    monkeypatch.setenv("APP_ENV", app_env)
    if flag is None:
        monkeypatch.delenv("ALLOW_ILLUSTRATIVE_GUIDANCE", raising=False)
    else:
        monkeypatch.setenv("ALLOW_ILLUSTRATIVE_GUIDANCE", flag)
    reset_settings_cache()
    try:
        assert get_settings().illustrative_guidance is expected
    finally:
        monkeypatch.undo()
        reset_settings_cache()


def test_accountant_can_neither_probe_nor_cancel_the_owners_payment(seeded):
    """The role used to be checked after the amount and password, so an accountant could cancel an owner's
    pending payment by "confirming" it with the right amount."""
    from fastapi.testclient import TestClient

    from sme_copilot.agent.executor import execute
    from sme_copilot.api.main import create_app
    from sme_copilot.models import PendingAction
    from sme_copilot.security.http import limiter
    from tests.conftest import make_ctx

    limiter.reset()
    out = execute(make_ctx(seeded), "sandbox_transfer", {"recipient_name": "X Co", "amount": 60_000})
    with TestClient(create_app()) as c:
        def headers(user, pw):
            return {"Authorization": "Bearer " + c.post("/api/auth/login", json={"username": user, "password": pw}).json()["token"]}

        acct = headers("accountant", "acct-pass-123")
        for amount in (1, 60_000):  # a wrong amount must not reveal "amount mismatch" either
            r = c.post(f"/api/actions/{out.pending_action_id}/confirm",
                       json={"confirm_amount": amount, "password": "acct-pass-123"}, headers=acct)
            assert r.status_code == 403 and "owner must confirm" in r.text
        db = seeded["db"]
        db.expire_all()
        assert db.get(PendingAction, out.pending_action_id).status == "pending"
        r = c.post(f"/api/actions/{out.pending_action_id}/confirm",
                   json={"confirm_amount": 60_000, "password": "owner-pass-123"}, headers=headers("owner", "owner-pass-123"))
        assert r.status_code == 200, r.text


def test_spreadsheet_uploads_are_parsed_with_xml_bomb_protection():
    import openpyxl.xml

    assert openpyxl.xml.DEFUSEDXML, "install defusedxml (requirements.txt) so .xlsx uploads cannot expand XML bombs"
