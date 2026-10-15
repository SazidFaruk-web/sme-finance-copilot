"""Request bodies (validated; length-capped to limit abuse)."""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=80)
    password: str = Field(..., min_length=1, max_length=200)


class SignupIn(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=120)
    full_name: str = Field(..., min_length=1, max_length=120)
    username: str = Field(..., min_length=3, max_length=40, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(..., min_length=8, max_length=200)


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_id: int | None = None
    profile: str | None = Field(None, max_length=60, description="provider profile override from providers.yaml")
    language: Literal["en", "bn", "banglish"] | None = None


class FeedbackIn(BaseModel):
    interaction_id: str = Field(..., max_length=40)
    rating: Literal["up", "down"]
    correction: str | None = Field(None, max_length=4000)


class PasteIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=500_000)
    doc_type: Literal["auto", "sales", "expenses", "bank", "wallet", "invoices", "ledger"] = "auto"


class EntryIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=300)
    confirmed: bool = False


class TxnPatch(BaseModel):
    category: str | None = Field(None, max_length=40)
    is_duplicate: bool | None = None
    txn_date: date | None = None
    amount: float | None = Field(None, gt=0, le=1e10)
    direction: Literal["in", "out"] | None = None
    description: str | None = Field(None, max_length=500)
    counterparty: str | None = Field(None, max_length=200)


class ToolCallIn(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


class ConfirmIn(BaseModel):
    confirm_amount: float | None = Field(None, description="Money actions: the user re-types the amount")
    password: str | None = Field(None, max_length=200)  # step-up for large payments


class CancelIn(BaseModel):
    action: str = Field(..., min_length=1, max_length=60)
    summary: str = Field("", max_length=300)


class DeleteDataIn(BaseModel):
    password: str = Field(..., max_length=200)
    confirm: Literal["DELETE MY DATA"]


class SettingsIn(BaseModel):
    number_style: Literal["lakh", "intl"] | None = None
    low_balance_threshold: float | None = Field(None, ge=0, le=1e9)
    language: Literal["en", "bn", "banglish"] | None = None
