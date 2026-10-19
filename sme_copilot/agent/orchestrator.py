"""The agent loop: language detection -> guardrails -> model/tool loop -> grounding -> audit.

    user text
      │  guardrails.check_request  (deterministic refusal, no model call)
      ▼
    router.chat(system + history + user, tools)   ← PII masked for external providers
      │ tool_calls?
      ├─ yes → executor.execute (validate → authorize → run/queue → audit) → tool messages → loop
      └─ no  → final text
      ▼
    numeric grounding check + disclaimer + traces + pending confirmations → AgentResult
"""
from __future__ import annotations

import json
import re
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from sme_copilot.llm_providers.base import ChatResponse, LLMProvider, Message, ProviderError, ToolCall
from sme_copilot.llm_providers.registry import ModelRouter, get_router
from sme_copilot.security import audit
from sme_copilot.security.guardrails import DISCLAIMER, check_request
from sme_copilot.security.injection import scan
from sme_copilot.security.pii import PIIVault, mask_text
from sme_copilot.config import get_settings

from .executor import ToolOutcome, execute
from .grounding import ungrounded_numbers
from .language import detect_language
from .prompts import build_system_prompt, build_user_turn
from .toolkit import REGISTRY, ToolContext, load_all_tools, specs_for

log = logging.getLogger(__name__)

MAX_STEPS = 6
MAX_HISTORY_MESSAGES = 8


# A reply that says something was done ("I have prepared a reminder", "the reminder is set") is only allowed when a
# tool in this turn actually did or queued it. The 2026-10-19 persona test caught the model claiming a reminder it never
# prepared, and inventing customers when it answered from memory in a long chat.
_VERBS = r"prepared|created|set up|sent|scheduled|drafted|saved|recorded|added|queued|paid|transferred"
_CLAIM = re.compile(r"\bI(?:'ve| have)?\s+(?:now\s+|already\s+|just\s+)?(?P<active>" + _VERBS + r")\b|"
                    r"\b(?P<noun>reminders?|payments?|transfers?|letters?|reports?|entries|entry|records?|drafts?|checklists?|bills?)\s+"
                    r"(?:is|are|has been|have been)\s+(?:now\s+)?(?P<passive>set|" + _VERBS + r")\b", re.I)
_NO_ACTION = ("I have not prepared or saved anything yet, so nothing will be sent. Ask me again with the details, for "
              "example \"Prepare a payment reminder for <customer>\", or open More, then Customers & suppliers.")
_NO_FACTS = ("I need to look at your records before I give numbers, and I could not do that for this answer. "
             "Please ask again, for example \"Who owes me money?\" or \"How much did I sell this month?\".")


def _supported_action(match, reply: str, outcomes: list[ToolOutcome]) -> bool:
    """Ground each action in its own tool and state, never in an unrelated write."""
    verb = (match.group("active") or match.group("passive")).lower()
    phrase = match.group("noun") or re.split(r"[.;!?\n]|\bbut\b", reply[match.end():], maxsplit=1, flags=re.I)[0]
    preparing = verb in ("prepared", "drafted", "set up")
    if preparing and re.fullmatch(r"\s*(?:this|the|a|your) request\s*", phrase, re.I):
        return sum(o.status == "pending_confirmation" for o in outcomes) == 1
    # No chat tool delivers real messages. A prepared request is not a sent message,
    # nor proof of a real payment; sandbox transfers must explicitly say sandbox.
    if verb == "sent":
        return False
    if verb in ("paid", "transferred"):
        return "sandbox" in reply.lower() and any(o.status == "ok" and o.tool in (
            "sandbox_transfer", "pay_supplier_invoice") and o.data.get("transfer_id") for o in outcomes)
    if re.search(r"\breminders?\b", phrase, re.I):
        allowed = {"create_payment_reminder": "reminder_id", "schedule_alert": "alert_id"}
    elif re.search(r"\bchecklists?\b", phrase, re.I):
        allowed = {"prepare_loan_checklist": "draft_id"}
    elif re.search(r"\breports?\b", phrase, re.I):
        allowed = {"generate_loan_report": "report_id"}
    elif re.search(r"\b(?:letters?|drafts?|follow[ -]?ups?)\b", phrase, re.I):
        allowed = {"draft_invoice_followup": "draft_id"}
    elif re.search(r"\b(?:payments?|transfers?)\b", phrase, re.I) and verb not in ("recorded", "added", "saved"):
        allowed = {"sandbox_transfer": "transfer_id", "pay_supplier_invoice": "transfer_id"}
    elif re.search(r"\b(?:obligations?|bills?)\b", phrase, re.I):
        allowed = {"add_obligation": "obligation_id"}
    elif verb in ("recorded", "added", "saved") or re.search(r"\b(?:entry|entries|records?|transactions?)\b", phrase, re.I):
        allowed = {"add_transaction": "recorded"}
    else:
        return False
    for o in outcomes:
        if o.tool not in allowed:
            continue
        if preparing and o.status == "pending_confirmation":
            return True
        if o.status == "ok" and o.data.get(allowed[o.tool]):
            return True
        if preparing and o.tool == "add_transaction" and o.status == "ok" and o.data.get("needs_confirm"):
            return True
    return False


def _enforce_honesty(result: "AgentResult", outcomes: list[ToolOutcome]) -> None:
    claims = list(_CLAIM.finditer(result.reply or ""))
    if any(not _supported_action(m, result.reply, outcomes) for m in claims):
        result.reply = (_NO_ACTION if not outcomes else "I could not confirm that action was completed. Please check the action status below before relying on it.")
        result.blocked_claim = "action"
    elif not outcomes and result.ungrounded_numbers:  # numbers from nowhere: no tool ran and none were said before
        result.reply, result.blocked_claim = _NO_FACTS, "numbers"
    if result.blocked_claim:
        result.ungrounded_numbers = []
        log.warning("request %s: blocked an unsupported %s claim", result.request_id, result.blocked_claim)


@dataclass
class AgentResult:
    request_id: str
    reply: str
    language: str
    profile: str = ""
    model: str = ""
    requested_profile: str = ""
    fallback: bool = False  # True when a profile other than the requested one produced (part of) the answer
    fallback_reason: str = ""
    streamed: bool = False  # answer text was already sent to the caller as live `delta` events
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    traces: list[dict[str, Any]] = field(default_factory=list)
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    ungrounded_numbers: list[float] = field(default_factory=list)
    blocked_claim: str = ""  # "action" | "numbers" when an unsupported reply was replaced
    refused: bool = False
    disclaimer: str = ""
    attempts: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    ttft_ms: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    steps: int = 0
    error: str = ""
    tool_outputs: list[dict[str, Any]] = field(default_factory=list)  # compact, as the model saw them

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def _pii_transform(vault: PIIVault):
    """Mask PII for external providers; restore it in replies and tool arguments."""
    def transform(provider: LLMProvider, messages: list[Message]):
        if not (provider.external and get_settings().mask_pii):
            return messages, None
        masked = []
        for m in messages:
            masked.append(Message(m.role, vault.mask(m.content),
                                  tool_calls=[ToolCall(tc.name, json.loads(vault.mask(json.dumps(tc.arguments,
                                                                                                  ensure_ascii=False))),
                                                       id=tc.id) for tc in m.tool_calls],
                                  tool_call_id=m.tool_call_id, name=m.name))

        def restore(resp: ChatResponse) -> ChatResponse:
            resp.content = vault.unmask(resp.content)
            for tc in resp.tool_calls:
                tc.arguments = vault.unmask_obj(tc.arguments)
            return resp
        return masked, restore
    return transform


class Agent:
    def __init__(self, router: ModelRouter | None = None):
        self.router = router or get_router()
        load_all_tools()

    def run(self, ctx: ToolContext, user_text: str, *, history: list[Message] | None = None,
            profile: str | None = None, language: str | None = None,
            on_event: Callable[[str, dict[str, Any]], None] | None = None,
            allow_fallback: bool = True) -> AgentResult:
        """Run one turn. ``on_event(kind, payload)`` streams progress (tool results) to the UI."""
        start = time.perf_counter()
        rid = ctx.request_id or uuid.uuid4().hex[:16]
        ctx.request_id = rid
        lang = language or detect_language(user_text)
        enabled = get_settings().languages  # Bangla script and Banglish both need Bangla switched on
        if ("bn" if lang == "banglish" else lang) not in enabled:
            lang = "en"
        ctx.language = lang
        result = AgentResult(request_id=rid, reply="", language=lang)

        guard = check_request(user_text, lang)
        if guard.refused:
            result.reply, result.refused = guard.message, True
            audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                         event_type="agent_decision", action="refuse_request", inputs={"text": user_text[:300]},
                         result={"category": guard.category}, request_id=rid)
            result.latency_ms = (time.perf_counter() - start) * 1000
            return result

        sus = scan(user_text)
        if sus.suspicious:
            ctx.suspicious_input = True
            audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                         event_type="security", action="suspicious_user_input", inputs={"text": user_text[:300]},
                         result={"rules": sus.rules}, request_id=rid)

        messages: list[Message] = [Message("system", build_system_prompt())]
        messages += (history or [])[-MAX_HISTORY_MESSAGES:]
        messages.append(Message("user", build_user_turn(
            user_text, language=lang, business_name=ctx.business.name, sector=ctx.business.sector,
            today=ctx.as_of, style=ctx.style, user_role=ctx.user.role)))
        tools = specs_for(ctx.user)
        vault = PIIVault()
        transform = _pii_transform(vault)
        outcomes: list[ToolOutcome] = []
        final = ""
        result.requested_profile = self.router.chain("advisory", profile, fallback=False)[0]

        def on_delta(text: str) -> None:
            result.streamed = True
            on_event("delta", {"text": text})

        for step in range(MAX_STEPS):
            result.steps = step + 1
            try:
                routed = self.router.chat(messages, task="advisory", override=profile, tools=tools,
                                          transform=transform, max_tokens=1200, fallback=allow_fallback,
                                          on_delta=on_delta if on_event else None)
            except ProviderError as e:
                result.error = str(e)[:300]
                result.fallback, result.fallback_reason = True, result.error
                log.error("request %s: no provider could answer: %s", rid, e)
                final = _fallback_text(lang)
                break
            resp = routed.response
            result.profile, result.model = routed.profile, resp.model
            result.attempts += [a.__dict__ for a in routed.attempts]
            if routed.profile != result.requested_profile and not result.fallback:
                failed = next((a for a in routed.attempts if a.profile == result.requested_profile and not a.ok),
                              None)
                result.fallback = True
                result.fallback_reason = (failed.error if failed else "requested profile unavailable")[:300]
                log.error("request %s: %s failed, answered by %s instead: %s", rid, result.requested_profile,
                          routed.profile, result.fallback_reason)
            result.input_tokens += resp.usage.input_tokens
            result.output_tokens += resp.usage.output_tokens
            if result.ttft_ms is None and resp.ttft_ms is not None:
                result.ttft_ms = resp.ttft_ms
            if not resp.tool_calls:
                final = resp.content
                break
            messages.append(Message("assistant", resp.content, tool_calls=resp.tool_calls))
            for tc in resp.tool_calls[:4]:  # cap fan-out per step
                out = execute(ctx, tc.name, tc.arguments)
                outcomes.append(out)
                result.tool_outputs.append({"tool": tc.name, "arguments": tc.arguments, "output": out.for_model()[:3000]})
                if on_event:
                    on_event("tool", {"tool": out.tool, "status": out.status, "tier": out.tier,
                                      "message": out.message})
                messages.append(Message("tool", out.for_model(), tool_call_id=tc.id, name=tc.name))
        else:
            final = final or _fallback_text(lang)

        result.reply = (final or "").strip() or _fallback_text(lang)
        result.tool_calls = [{"tool": o.tool, "status": o.status, "tier": o.tier, "args": o.args,
                              "message": o.message, "duration_ms": round(o.duration_ms, 1)} for o in outcomes]
        result.traces = [{"tool": o.tool, **o.data["trace"]} for o in outcomes
                         if o.status == "ok" and isinstance(o.data.get("trace"), dict)]
        result.pending_actions = [{"id": o.pending_action_id, "tool": o.tool, **o.data} for o in outcomes
                                  if o.status == "pending_confirmation"]
        ok_data = [o.data for o in outcomes if o.status in ("ok", "pending_confirmation")] + \
            [o.message for o in outcomes if o.message]
        # Earlier replies in this conversation were checked when they were given, so their numbers count too.
        earlier = [m.content for m in (history or [])[-MAX_HISTORY_MESSAGES:] if m.role in ("assistant", "tool") and m.content]
        result.ungrounded_numbers = ungrounded_numbers(result.reply, ok_data + earlier, user_text)
        _enforce_honesty(result, outcomes)
        if any(REGISTRY[o.tool].advisory for o in outcomes if o.tool in REGISTRY and o.status == "ok"):
            result.disclaimer = DISCLAIMER.get(lang, DISCLAIMER["en"])
        result.latency_ms = (time.perf_counter() - start) * 1000

        audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                     event_type="agent_decision", action="answer",
                     inputs={"text": user_text[:500], "language": lang, "profile": result.profile,
                             "requested_profile": result.requested_profile},
                     result={"tools": [f"{o.tool}:{o.status}" for o in outcomes], "reply": mask_text(result.reply[:400]),
                             "fallback": result.fallback, "fallback_reason": result.fallback_reason,
                             "ungrounded_numbers": result.ungrounded_numbers[:10],
                             "pending_actions": [p["id"] for p in result.pending_actions]},
                     request_id=rid)
        return result


def _fallback_text(lang: str) -> str:
    return {"bn": "দুঃখিত, এই মুহূর্তে উত্তর তৈরি করতে পারছি না। একটু পরে আবার চেষ্টা করুন।",
            "banglish": "Dukkhito, ekhon uttor dite parchi na. Ektu pore abar chesta korun.",
            "zh": "抱歉，现在无法完成。请稍后再试。"}.get(
        lang, "Sorry, I couldn't complete that right now. Please try again.")
