from datetime import date, timedelta
import hashlib

import httpx

from sme_copilot.config import load_yaml
from sme_copilot.models import utcnow
from .models import SourceCheck


def sources(db, today: date):
    result = []
    for spec in load_yaml("pilot_sources.yaml")["sources"]:
        check = db.get(SourceCheck, spec["id"])
        try:
            reviewed = date.fromisoformat(str(spec["reviewed_on"]))
            valid = (spec.get("reviewed_by") and date.fromisoformat(str(spec["effective_from"])) <= today
                     <= date.fromisoformat(str(spec["valid_until"])) and reviewed <= today
                     and (today - reviewed).days <= 7)
        except (KeyError, ValueError):
            valid = False
        valid = valid and check is not None and check.digest == spec.get("reviewed_digest") and 0 <= (today - check.checked_at.date()).days <= 1
        status = "reviewed" if valid else "needs_review"
        if check and check.status in ("changed", "unavailable"):
            status = check.status
        result.append({"reviewed_by": None, "reviewed_on": None, "effective_from": None, "valid_until": None,
                       "documents": None, "destination": None, "audience": None,
                       **spec, "status": status, "checked_at": check.checked_at.isoformat() if check else None,
                       "checked_digest": check.digest if check else None})
    return result


def check_sources(db, now=None, client=None):
    """Fetch only operator-configured official URLs. Changes NEVER auto-publish a rule."""
    now = now or utcnow()
    with httpx.Client(timeout=15, follow_redirects=False) if client is None else client as http:
        for spec in load_yaml("pilot_sources.yaml")["sources"]:
            old = db.get(SourceCheck, spec["id"])
            if old and now - old.checked_at < timedelta(days=1):
                continue
            row = old or SourceCheck(source_id=spec["id"], digest="")
            try:
                with http.stream("GET", spec["url"]) as response:
                    response.raise_for_status()
                    digest, size = hashlib.sha256(), 0
                    for block in response.iter_bytes():
                        size += len(block)
                        if size > 15_000_000:
                            raise ValueError("too_large")
                        digest.update(block)
                new = digest.hexdigest()
                # A changed page stays flagged until the configured reviewed digest matches it.
                row.status = "unreviewed" if not row.digest else "changed" if row.digest != new else row.status
                if spec.get("reviewed_digest") == new:
                    row.status = "unchanged"
                row.digest, row.error = new, ""
            except (httpx.HTTPError, ValueError):
                row.status, row.error = "unavailable", "source_check_failed"
            row.checked_at = now
            db.add(row)
        db.commit()
