"""Load and validate the editable financing catalog (config/financing/*.yaml)."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from sme_copilot.config import CONFIG_DIR

Purpose = Literal["working_capital", "inventory", "equipment", "expansion", "seasonal", "receivables_gap"]


class Eligibility(BaseModel):
    min_business_age_months: int = 0
    max_business_age_months: int | None = None
    min_avg_monthly_revenue: float = 0
    max_revenue_cv: float = 10
    min_dscr: float = 1.0
    min_months_of_records: int = 0
    requires_trade_license: bool = False
    requires_tin: bool = False
    requires_bank_account: bool = False
    women_led_only: bool = False
    requires_open_receivables: bool = False
    advance_rate: float = 1.0
    max_amount_vs_monthly_purchases: float | None = None


class Product(BaseModel):
    id: str
    name: str
    lender_type: str
    product_type: str
    purposes: list[Purpose]
    min_amount: float = Field(ge=0)
    max_amount: float = Field(gt=0)
    interest_rate_min_pct: float = Field(ge=0, le=60)
    interest_rate_max_pct: float = Field(ge=0, le=60)
    rate_method: Literal["reducing", "flat"] = "reducing"
    fees_pct: float = Field(0, ge=0, le=10)
    tenure_months_min: int = Field(ge=1)
    tenure_months_max: int = Field(ge=1)
    collateral: str = ""
    collateral_required: bool = False
    collateral_coverage_min: float = Field(0, ge=0, le=3)
    speed_days: int = 30
    documents_required: list[str] = Field(default_factory=list)
    eligibility: Eligibility = Field(default_factory=Eligibility)
    notes: str = ""
    source_url: str | None = None
    last_verified_date: date | None = None
    verified: bool = False
    illustrative: bool = True

    @model_validator(mode="after")
    def _ranges(self):
        if self.max_amount < self.min_amount:
            raise ValueError(f"{self.id}: max_amount < min_amount")
        if self.interest_rate_max_pct < self.interest_rate_min_pct:
            raise ValueError(f"{self.id}: rate max < min")
        if self.tenure_months_max < self.tenure_months_min:
            raise ValueError(f"{self.id}: tenure max < min")
        return self

    @property
    def mid_rate(self) -> float:
        return round((self.interest_rate_min_pct + self.interest_rate_max_pct) / 2, 2)

    @property
    def verify_label(self) -> str:
        return "Verified" if self.verified else "Illustrative - verify with lender"


class Catalog(BaseModel):
    products: list[Product]
    documents: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def get(self, pid: str) -> Product:
        for p in self.products:
            if p.id == pid:
                return p
        raise LookupError(f"unknown financing product '{pid}'")


@lru_cache
def load_catalog(directory: str | None = None) -> Catalog:
    d = Path(directory) if directory else CONFIG_DIR / "financing"
    products: list[dict[str, Any]] = []
    documents: dict[str, dict[str, Any]] = {}
    for f in sorted(d.glob("*.y*ml")):
        with open(f, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        products += data.get("products", [])
        documents.update(data.get("documents", {}))
    cat = Catalog(products=products, documents=documents)
    ids = [p.id for p in cat.products]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate product ids in financing catalog")
    return cat
