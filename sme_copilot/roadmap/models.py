"""Stored goal roadmaps. One row per goal the owner is planning for."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from sme_copilot.db import Base
from sme_copilot.models import utcnow
from sme_copilot.security.crypto import EncryptedString


class GoalPlan(Base):
    """A roadmap towards one purchase or savings goal.

    ``plan`` holds the full rendered roadmap (deterministic figures plus the reviewed wording) so an
    owner always reopens exactly what they saw. ``facts_stamp`` records the records the plan was built
    from; when the records move on, the plan is shown as out of date rather than silently recalculated.
    """

    __tablename__ = "goal_plans"
    __table_args__ = (UniqueConstraint("business_id", "request_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | saved | achieved | dropped
    language: Mapped[str] = mapped_column(String(2), default="en")

    goal_text: Mapped[str] = mapped_column(EncryptedString())  # the owner's own words
    item: Mapped[str] = mapped_column(EncryptedString(), default="")
    specification: Mapped[str] = mapped_column(EncryptedString(), default="")
    category: Mapped[str] = mapped_column(String(24), default="other")

    target_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_source: Mapped[str] = mapped_column(String(16), default="unknown")  # owner | catalog | web | unknown
    price_detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    horizon_months: Mapped[int | None] = mapped_column(Integer, nullable=True)  # owner's own deadline, if given
    monthly_override: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    start_month: Mapped[date | None] = mapped_column(Date, nullable=True)

    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    facts_stamp: Mapped[str] = mapped_column(String(64), default="")
    progress: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # {"done": [phase index, ...]}

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
