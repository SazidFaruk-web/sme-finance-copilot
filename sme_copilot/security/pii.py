"""PII detection and reversible masking.

Before any prompt goes to an *external* LLM API, phone numbers, account / wallet numbers,
NID numbers, TINs, emails and card numbers are replaced with stable placeholders such as
``[PHONE_1]``. The mapping stays in memory for that one request (``PIIVault``) so the reply and
any tool arguments can be restored locally. Placeholders never reach disk unmasked in logs
(see ``mask_text``, which masks irreversibly).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Bangladesh mobile: 01[3-9]XXXXXXXX locally, +880 1[3-9]XXXXXXXX internationally.
_PHONE = r"(?<![\d+])(?:\+?880[-\s]?|0)1[3-9]\d{2}[-\s]?\d{6}(?!\d)"
_EMAIL = r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"
_CARD = r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
# NID: 10, 13 or 17 digits; TIN: 12 digits. Labelled forms first so they are classed correctly.
_NID = r"(?i)\b(?:nid|national\s*id)\s*(?:no\.?|number|#)?\s*[:\-]?\s*\d{10,17}\b"
_TIN = r"(?i)\b(?:e-?tin|tin)\s*(?:no\.?|number|#)?\s*[:\-]?\s*\d{12}\b"
# Bank account / wallet: labelled numbers, or any long digit run (9-18 digits).
_ACCOUNT_LABELLED = r"(?i)\b(?:a/c|acc(?:ount)?|wallet|bkash|nagad|rocket)\s*(?:no\.?|number|#)?\s*[:\-]?\s*\d[\d-]{7,20}\d\b"
_LONG_DIGITS = r"\b\d{9,18}\b"

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(_EMAIL)),
    ("CARD", re.compile(_CARD)),
    ("NID", re.compile(_NID)),
    ("TIN", re.compile(_TIN)),
    ("ACCOUNT", re.compile(_ACCOUNT_LABELLED)),
    ("PHONE", re.compile(_PHONE)),
    ("ACCOUNT", re.compile(_LONG_DIGITS)),
]

_PLACEHOLDER = re.compile(r"\[(EMAIL|CARD|NID|TIN|ACCOUNT|PHONE)_\d+\]")


@dataclass
class PIIVault:
    """Per-request reversible mapping placeholder -> original value."""

    forward: dict[str, str] = field(default_factory=dict)  # original -> placeholder
    reverse: dict[str, str] = field(default_factory=dict)  # placeholder -> original
    counts: dict[str, int] = field(default_factory=dict)

    def _token(self, kind: str, value: str) -> str:
        if value in self.forward:
            return self.forward[value]
        self.counts[kind] = self.counts.get(kind, 0) + 1
        tok = f"[{kind}_{self.counts[kind]}]"
        self.forward[value] = tok
        self.reverse[tok] = value
        return tok

    def mask(self, text: str) -> str:
        if not text:
            return text
        for kind, pat in PATTERNS:
            text = pat.sub(lambda m, k=kind: self._token(k, m.group(0)), text)
        return text

    def unmask(self, text: str) -> str:
        if not text or not self.reverse:
            return text
        return _PLACEHOLDER.sub(lambda m: self.reverse.get(m.group(0), m.group(0)), text)

    def unmask_obj(self, obj):
        if isinstance(obj, str):
            return self.unmask(obj)
        if isinstance(obj, dict):
            return {k: self.unmask_obj(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.unmask_obj(v) for v in obj]
        return obj


def mask_text(text: str) -> str:
    """Irreversible masking for logs and datasets."""
    return PIIVault().mask(text) if text else text


def chat_with_pii(provider, messages, **kwargs):
    """Apply the app's masking policy to direct model helpers, restoring replies locally.

    A request-local vault preserves the same placeholder across every message. Do
    not mutate the caller's messages or share this mapping between owners.
    """
    from dataclasses import replace
    import json
    from sme_copilot.config import get_settings

    if not (getattr(provider, "external", False) and get_settings().mask_pii):
        return provider.chat(messages, **kwargs)
    vault = PIIVault()
    masked = [replace(m, content=vault.mask(m.content), tool_calls=[
        replace(tc, arguments=json.loads(vault.mask(json.dumps(tc.arguments, ensure_ascii=False))))
        for tc in m.tool_calls]) for m in messages]
    response = provider.chat(masked, **kwargs)
    response.content = vault.unmask(response.content)
    for tc in getattr(response, "tool_calls", []):
        tc.arguments = vault.unmask_obj(tc.arguments)
    return response


def mask_obj(obj):
    if isinstance(obj, str):
        return mask_text(obj)
    if isinstance(obj, dict):
        return {k: mask_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_obj(v) for v in obj]
    return obj


def mask_account(value: str | None, keep: int = 4) -> str:
    """Display masking: '01712345678' -> '*******5678'."""
    if not value:
        return ""
    v = str(value)
    if len(v) <= keep:
        return "*" * len(v)
    return "*" * (len(v) - keep) + v[-keep:]


def contains_pii(text: str) -> bool:
    return any(p.search(text or "") for _, p in PATTERNS)
