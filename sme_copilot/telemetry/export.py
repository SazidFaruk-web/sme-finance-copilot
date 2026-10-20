"""Export the interaction log as datasets for fine-tuning / evaluating a local model.

    python -m sme_copilot.cli export-finetune [--out data/finetune] [--include-unrated]

Outputs (all PII-masked at logging time):
  sft_openai.jsonl        chat-format trajectories incl. tool calls and tool results
                          (OpenAI / most open-source SFT trainers accept this "messages" format)
  preference_pairs.jsonl  {prompt, chosen, rejected} from thumbs-down + user correction (DPO/ORPO)
  stats.json              counts and exclusion reasons

Selection rules: thumbs-up -> kept; thumbs-down WITH correction -> kept with the correction as the
target answer (and a preference pair); thumbs-down without correction -> excluded; unrated -> only
with --include-unrated and only when the turn had no error and no ungrounded numbers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sme_copilot.config import ROOT_DIR

from .interactions import read_all

SYSTEM = ("You are Ascent Copilot for Bangladesh small businesses. Use tools for every number, reply in the "
          "user's language (English, Bangla or Banglish), be brief, show uncertainty, never move money without the "
          "owner's confirmation, and refuse fraud or tax evasion.")


def trajectory(rec: dict[str, Any], final: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": rec["user"]}]
    for i, tr in enumerate(rec.get("tool_results") or []):
        cid = f"call_{i}"
        msgs.append({"role": "assistant", "content": None, "tool_calls": [{
            "id": cid, "type": "function",
            "function": {"name": tr.get("tool"), "arguments": json.dumps(tr.get("arguments") or {}, ensure_ascii=False)}}]})
        msgs.append({"role": "tool", "tool_call_id": cid, "content": tr.get("output", "")})
    msgs.append({"role": "assistant", "content": final})
    return msgs


def build(include_unrated: bool = False, path: Path | None = None) -> tuple[list, list, dict[str, int]]:
    inter, fb = read_all(path)
    sft, prefs = [], []
    stats = {"interactions": len(inter), "feedback": len(fb), "kept_up": 0, "kept_corrected": 0, "kept_unrated": 0,
             "excluded_down_no_correction": 0, "excluded_unrated": 0, "excluded_error_or_ungrounded": 0}
    for iid, rec in inter.items():
        f = fb.get(iid)
        meta = {"id": iid, "language": rec.get("language"), "profile": rec.get("profile"), "model": rec.get("model")}
        if f and f.get("rating") == "down":
            if f.get("correction"):
                sft.append({"messages": trajectory(rec, f["correction"]), "meta": {**meta, "source": "correction"}})
                prefs.append({"prompt": rec["user"], "chosen": f["correction"], "rejected": rec["reply"], "meta": meta})
                stats["kept_corrected"] += 1
            else:
                stats["excluded_down_no_correction"] += 1
            continue
        if f and f.get("rating") == "up":
            sft.append({"messages": trajectory(rec, rec["reply"]), "meta": {**meta, "source": "thumbs_up"}})
            stats["kept_up"] += 1
            continue
        if not include_unrated:
            stats["excluded_unrated"] += 1
            continue
        if rec.get("error") or rec.get("ungrounded_numbers"):
            stats["excluded_error_or_ungrounded"] += 1
            continue
        sft.append({"messages": trajectory(rec, rec["reply"]), "meta": {**meta, "source": "unrated"}})
        stats["kept_unrated"] += 1
    return sft, prefs, stats


def export(out_dir: Path, include_unrated: bool = False, path: Path | None = None) -> dict[str, int]:
    sft, prefs, stats = build(include_unrated, path)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "sft_openai.jsonl", "w", encoding="utf-8") as fh:
        for ex in sft:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with open(out_dir / "preference_pairs.jsonl", "w", encoding="utf-8") as fh:
        for ex in prefs:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")
    (out_dir / "stats.json").write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return stats


def export_cli(out: str, include_unrated: bool = False) -> int:
    out_dir = Path(out) if Path(out).is_absolute() else ROOT_DIR / out
    stats = export(out_dir, include_unrated)
    print(json.dumps(stats, indent=1))
    print(f"Wrote {out_dir / 'sft_openai.jsonl'} and {out_dir / 'preference_pairs.jsonl'}")
    return 0
