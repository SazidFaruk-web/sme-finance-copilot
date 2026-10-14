"""Explainability: every number a tool returns carries the steps and data rows behind it."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

MAX_ROW_IDS = 60


class Step(BaseModel):
    label: str
    value: float | str | None
    expression: str = ""  # e.g. "312,000 - 198,500"


class Trace(BaseModel):
    formula: str = ""
    steps: list[Step] = Field(default_factory=list)
    row_ids: list[int] = Field(default_factory=list)  # transaction / invoice ids (truncated)
    row_count: int = 0
    row_table: str = "transactions"
    period: str = ""
    sources: list[str] = Field(default_factory=list)  # e.g. "csv:sales_2026.csv rows 2-118"
    assumptions: list[str] = Field(default_factory=list)

    def step(self, label: str, value: Any, expression: str = "") -> "Trace":
        if isinstance(value, float):
            value = round(value, 4)
        self.steps.append(Step(label=label, value=value, expression=expression))
        return self

    def rows(self, ids: list[int], table: str = "transactions") -> "Trace":
        self.row_count = len(ids)
        self.row_ids = [int(i) for i in ids[:MAX_ROW_IDS]]
        self.row_table = table
        return self


def fmt(n: float) -> str:
    """Compact number for expressions inside traces."""
    return f"{n:,.2f}".rstrip("0").rstrip(".") if n != int(n) else f"{int(n):,}"
