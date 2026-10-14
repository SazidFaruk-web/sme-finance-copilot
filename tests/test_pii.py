from sme_copilot.security.pii import PIIVault, contains_pii, mask_account, mask_obj, mask_text


def test_masks_bd_phone_wallet_email_and_restores():
    v = PIIVault()
    text = "Send 5000 to Karim 01712345678 via bKash 01898765432, email karim@example.com"
    masked = v.mask(text)
    assert "01712345678" not in masked and "01898765432" not in masked and "karim@example.com" not in masked
    assert "[PHONE_1]" in masked and "[ACCOUNT_1]" in masked and "[EMAIL_1]" in masked
    assert "5000" in masked  # amounts are not PII
    assert v.unmask(masked) == text


def test_same_value_gets_same_placeholder():
    v = PIIVault()
    m = v.mask("call 01712345678 or 01712345678")
    assert m.count("[PHONE_1]") == 2


def test_unmask_tool_arguments():
    v = PIIVault()
    v.mask("+8801712345678")
    args = {"recipient": "[PHONE_1]", "nested": ["[PHONE_1]"], "amount": 100}
    out = v.unmask_obj(args)
    assert out["recipient"] == "+8801712345678" and out["nested"][0] == "+8801712345678" and out["amount"] == 100


def test_nid_tin_account_and_card():
    t = "NID: 1234567890123 TIN 123456789012 A/C No 1234-5678-9012 card 4111 1111 1111 1111"
    m = mask_text(t)
    for raw in ("1234567890123", "123456789012", "1234-5678-9012", "4111 1111 1111 1111"):
        assert raw not in m
    assert contains_pii(t) and not contains_pii("sold 12 shirts for 6000 taka")


def test_mask_account_display_and_obj():
    assert mask_account("01712345678") == "*******5678"
    assert mask_obj({"a": ["01712345678"]}) == {"a": ["[PHONE_1]"]}
