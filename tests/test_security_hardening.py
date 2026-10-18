"""Regression tests for issues found in the 2026-10 security review."""
import bcrypt

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


def test_spreadsheet_uploads_are_parsed_with_xml_bomb_protection():
    import openpyxl.xml

    assert openpyxl.xml.DEFUSEDXML, "install defusedxml (requirements.txt) so .xlsx uploads cannot expand XML bombs"
