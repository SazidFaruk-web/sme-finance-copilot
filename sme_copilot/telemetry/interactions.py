"""Interaction dataset: one JSONL line per agent turn, PII-masked, for evaluation/fine-tuning.

Record types:
  {"type": "interaction", "id", "ts", "profile", "model", "language", "user", "reply", "tool_calls",
   "latency_ms", "ttft_ms", "input_tokens", "output_tokens", "ungrounded_numbers", "refused", ...}
  {"type": "feedback", "id", "ts", "rating": "up"|"down", "correction": str|None}

Feedback is appended as its own line (the file is append-only); the exporter joins them.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sme_copilot.config import get_settings
from sme_copilot.security.pii import mask_obj, mask_text

_lock = threading.Lock()


def _path() -> Path:
    return get_settings().interaction_log_path


def _append(rec: dict[str, Any]) -> None:
    if not get_settings().interaction_log_enabled:
        return
    line = json.dumps(rec, ensure_ascii=False, default=str)
    with _lock:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def log_interaction(result: Any, user_text: str, *, business_id: int, system_prompt_version: str = "v1",
                    tool_results: list[dict[str, Any]] | None = None) -> None:
    d = result.as_dict() if hasattr(result, "as_dict") else dict(result)
    _append({
        "type": "interaction", "id": d["request_id"], "ts": datetime.now(timezone.utc).isoformat(),
        "business_ref": f"b{business_id}", "profile": d.get("profile"), "model": d.get("model"),
        "language": d.get("language"), "prompt_version": system_prompt_version,
        "user": mask_text(user_text), "reply": mask_text(d.get("reply", "")),
        "tool_calls": mask_obj([{k: tc.get(k) for k in ("tool", "status", "tier", "args")}
                                for tc in d.get("tool_calls", [])]),
        "tool_results": mask_obj(tool_results or []),
        "latency_ms": round(d.get("latency_ms") or 0, 1), "ttft_ms": d.get("ttft_ms"),
        "input_tokens": d.get("input_tokens"), "output_tokens": d.get("output_tokens"),
        "ungrounded_numbers": d.get("ungrounded_numbers", []), "refused": d.get("refused", False),
        "error": d.get("error", ""),
    })


def log_feedback(interaction_id: str, rating: str, correction: str | None = None) -> None:
    if rating not in ("up", "down"):
        raise ValueError("rating must be 'up' or 'down'")
    _append({"type": "feedback", "id": interaction_id, "ts": datetime.now(timezone.utc).isoformat(),
             "rating": rating, "correction": mask_text(correction) if correction else None})


def read_all(path: Path | None = None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Return (interactions by id, latest feedback by id)."""
    p = path or _path()
    inter: dict[str, dict[str, Any]] = {}
    fb: dict[str, dict[str, Any]] = {}
    if not p.exists():
        return inter, fb
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") == "interaction":
                inter[rec["id"]] = rec
            elif rec.get("type") == "feedback":
                fb[rec["id"]] = rec
    return inter, fb


def purge_business(business_id: int) -> int:
    """Right to erasure for the dataset: rewrite the JSONL without this business's interactions
    (and the feedback attached to them). Returns the number of lines removed."""
    p = _path()
    if not p.exists():
        return 0
    ref = f"b{business_id}"
    with _lock:
        lines = p.read_text(encoding="utf-8").splitlines()
        drop_ids: set[str] = set()
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") == "interaction" and rec.get("business_ref") == ref:
                drop_ids.add(rec["id"])
        keep = []
        for line in lines:
            try:
                rec = json.loads(line)
            except ValueError:
                keep.append(line)
                continue
            if rec.get("id") in drop_ids:
                continue
            keep.append(line)
        p.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    return len(lines) - len(keep)
