"""Persistent owner reminders. Run as a supervised service; never start from a browser.

Provider contract: https://ismsplus.sslwireless.com/api-documentation (2026-10-17).
An accepted API request is not proof of handset delivery. Ambiguous sends require
operator reconciliation; only connections that never opened are retried automatically.
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from sme_copilot.config import get_settings
from sme_copilot.db import SessionLocal, init_db
from sme_copilot.models import Alert, Invoice, User, utcnow
from sme_copilot.security import audit
from .knowledge import check_sources, sources
from .models import GuidedCase, NotificationDelivery, NotificationPreference, ReminderJob

LOG = logging.getLogger(__name__)
DHAKA = timezone(timedelta(hours=6))


class SSLWireless:
    def send(self, phone, message, reference):
        s = get_settings()
        if not (s.pilot_sms_enabled and s.pilot_sms_api_token and s.pilot_sms_sid):
            return "blocked", "", "provider_not_configured"
        try:
            r = httpx.post("https://smsplus.sslwireless.com/api/v3/send-sms", timeout=20,
                json={"api_token": s.pilot_sms_api_token, "sid": s.pilot_sms_sid,
                      "msisdn": phone.lstrip("+"), "sms": message, "csms_id": reference})
            r.raise_for_status()
            data = r.json()
            info = data.get("smsinfo", [{}])[0] if data.get("smsinfo") else {}
            ref = str(info.get("reference_id", ""))[:150]
            if data.get("status") == "SUCCESS" and info.get("sms_status") == "SUCCESS":
                return "accepted", ref, ""
            if info.get("sms_status") == "DUPLICATE":
                return "unknown", ref, "provider_duplicate_reconcile"
            if data.get("status") in ("FAILED", "INVALID"):
                return "failed", ref, "provider_rejected"
            return "unknown", ref, "unexpected_response"
        except (httpx.ConnectError, httpx.ConnectTimeout):
            return "retry", "", "connection_failed"
        except (httpx.HTTPError, ValueError, TypeError, IndexError):
            return "unknown", "", "delivery_uncertain"


def due_jobs(db, today):
    eligible = {}
    # Old user-created reminders participate too, with no invented renewal period.
    known = set(db.scalars(select(ReminderJob.alert_id)))
    for alert in db.scalars(select(Alert).where(Alert.kind == "custom", Alert.due_date.is_not(None),
                                               Alert.status.in_(["open", "scheduled"]))):
        if alert.id not in known:
            db.add(ReminderJob(business_id=alert.business_id, alert_id=alert.id, due_date=alert.due_date, kind="reminder"))
    db.flush()
    for job in db.scalars(select(ReminderJob).where(ReminderJob.active.is_(True))):
        alert = db.get(Alert, job.alert_id)
        invoice = db.get(Invoice, job.invoice_id) if job.invoice_id else None
        if not alert or alert.status in ("acknowledged", "dismissed") or invoice and (
                invoice.status in ("paid", "written_off") or invoice.amount_paid >= invoice.amount):
            job.active = False
            if alert:
                alert.status = "acknowledged"
            continue
        if alert.due_date != job.due_date:
            job.due_date = alert.due_date
        days = (job.due_date - today).days
        if days <= 0:
            alert.status = "open"
        offsets = (30, 7, 1, 0) if job.kind == "renewal" else (3, 1, 0) if job.kind == "payment" else (0,)
        if days in offsets and job.kind != "review":  # strategic reviews are in-app, not urgent owner SMS
            eligible.setdefault(job.business_id, []).append(job.id)
    return eligible


def tick(db, now=None, provider=None):
    now = now or utcnow()
    local = now.replace(tzinfo=timezone.utc).astimezone(DHAKA)
    eligible = due_jobs(db, local.date())
    # A crash after sending must not produce a second SMS on restart.
    db.execute(update(NotificationDelivery).where(NotificationDelivery.status == "sending",
        NotificationDelivery.claimed_at < now - timedelta(minutes=5)).values(status="unknown", error="worker_interrupted"))
    db.commit()
    if not get_settings().pilot_sms_enabled:
        return
    for pref in db.scalars(select(NotificationPreference).where(NotificationPreference.consent.is_(True),
                                                               NotificationPreference.verified.is_(True))):
        owner = db.get(User, pref.user_id)
        if not owner or not owner.is_active or owner.role != "owner" or local.hour < pref.send_hour or pref.business_id not in eligible:
            continue
        delivery = db.scalar(select(NotificationDelivery).where(NotificationDelivery.user_id == pref.user_id,
                                                               NotificationDelivery.send_date == local.date()))
        if delivery is None:
            delivery = NotificationDelivery(business_id=pref.business_id, user_id=pref.user_id, send_date=local.date(),
                status="missed" if local.hour > pref.send_hour else "queued",
                error="selected_hour_missed" if local.hour > pref.send_hour else "")
            db.add(delivery)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                continue
        if local.hour > pref.send_hour and delivery.status in ("queued", "retry"):
            delivery.status, delivery.error = "missed", "selected_hour_missed"
            db.commit()
        if delivery.status not in ("queued", "retry") or delivery.next_attempt_at and delivery.next_attempt_at > now:
            continue
        claimed = db.execute(update(NotificationDelivery).where(NotificationDelivery.id == delivery.id,
            NotificationDelivery.status.in_(["queued", "retry"]), NotificationDelivery.attempts == delivery.attempts)
            .values(status="sending", attempts=NotificationDelivery.attempts + 1, claimed_at=now))
        db.commit()
        if claimed.rowcount != 1:
            continue
        db.refresh(pref)  # honour opt-out or number changes immediately before delivery
        if not pref.consent or not pref.verified:
            delivery.status = "cancelled"; db.commit(); continue
        text = ("Ascent Copilot: You have an important reminder. Open Tasks in the app. Turn off SMS in Reminder settings."
                if pref.language == "en" else "এসএমই কোপাইলট: জরুরি কাজ মনে করিয়ে দিচ্ছি। অ্যাপে কাজ দেখুন। রিমাইন্ডার সেটিংসে এসএমএস বন্ধ করতে পারেন।")
        status, ref, error = (provider or SSLWireless()).send(pref.phone, text, f"SME{delivery.id:017d}")
        delivery.status = "failed" if status == "retry" and delivery.attempts >= 3 else status
        delivery.provider_id, delivery.error = ref, error
        delivery.next_attempt_at = now + timedelta(minutes=5 * delivery.attempts)
        db.commit()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true")
    p.add_argument("--verify-owner", type=int, help="User ID; only after checking ownership of their saved phone")
    p.add_argument("--delivery", type=int, help="Reconcile a provider delivery report by delivery ID")
    p.add_argument("--status", choices=["delivered", "failed"])
    p.add_argument("--review-case", type=int)
    p.add_argument("--reviewer", help="Accountable operator name")
    p.add_argument("--note", help="Verification evidence or review result, no secrets")
    p.add_argument("--report", action="store_true")
    args = p.parse_args()
    init_db()
    with SessionLocal() as db:
        if args.verify_owner or args.delivery or args.review_case:
            if not args.reviewer or not args.note:
                p.error("--reviewer and --note are required")
            row = db.get(NotificationPreference, args.verify_owner) if args.verify_owner else db.get(NotificationDelivery, args.delivery) if args.delivery else db.get(GuidedCase, args.review_case)
            if not row:
                p.error("No matching record")
            if args.verify_owner:
                if not row.consent or not row.phone:
                    p.error("Owner must save their phone and opt in first")
                row.verified = True
            elif args.delivery:
                if not args.status or row.status not in ("accepted", "unknown"):
                    p.error("Only reconcile accepted/unknown deliveries using a provider report")
                row.status = args.status
            else:
                if row.status != "completed" or row.kind not in ("loan", "paperwork", "strategy"):
                    p.error("Only completed loan/paperwork/strategy cases require this review")
                row.result = {**row.result, "human_review": "reviewed", "reviewer": args.reviewer,
                              "review_note": args.note, "reviewed_at": utcnow().isoformat()}
            audit.record(db, actor=args.reviewer, actor_role="operator", business_id=row.business_id,
                         event_type="operation", action="pilot_operator_review", inputs={"note": args.note,
                         "user_id": args.verify_owner, "delivery_id": args.delivery, "case_id": args.review_case}, commit=False)
            db.commit()
            return
        if args.report:
            import json
            print(json.dumps({"sources": sources(db, datetime.now(DHAKA).date()),
                "deliveries": [{"id": r.id, "business_id": r.business_id, "status": r.status, "error": r.error}
                    for r in db.scalars(select(NotificationDelivery).where(NotificationDelivery.status != "delivered"))],
                "overdue_jobs": [{"id": r.id, "business_id": r.business_id, "due_date": r.due_date} for r in db.scalars(
                    select(ReminderJob).where(ReminderJob.active.is_(True), ReminderJob.due_date < datetime.now(DHAKA).date()))],
                "cases_to_review": [r.id for r in db.scalars(select(GuidedCase)) if r.result.get("human_review") == "pending"]}, default=str))
            return
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            with SessionLocal() as db:
                tick(db)
                if get_settings().pilot_source_checks:
                    check_sources(db)
        except Exception:
            LOG.exception("Pilot worker cycle failed")
        if args.once:
            return
        time.sleep(30)


if __name__ == "__main__":
    main()
