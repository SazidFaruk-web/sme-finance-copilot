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
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from sme_copilot.llm_providers.base import ChatResponse, LLMProvider, Message, ProviderError, ToolCall
from sme_copilot.llm_providers.registry import ModelRouter, get_router
from sme_copilot.security import audit
from sme_copilot.security.guardrails import DISCLAIMER, check_request
from sme_copilot.security.pii import PIIVault, mask_text
from sme_copilot.config import get_settings

from .executor import ToolOutcome, execute
from .grounding import ungrounded_numbers
from .language import detect_language
from .prompts import build_system_prompt
from .toolkit import REGISTRY, ToolContext, load_all_tools, specs_for

MAX_STEPS = 6
MAX_HISTORY_MESSAGES = 8


@dataclass
class AgentResult:
    request_id: str
    reply: str
    language: str
    profile: str = ""
    model: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    traces: list[dict[str, Any]] = field(default_factory=list)
    pending_actions: list[dict[str, Any]] = field(default_factory=list)
    ungrounded_numbers: list[float] = field(default_factory=list)
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

        system = build_system_prompt(language=lang, business_name=ctx.business.name, sector=ctx.business.sector,
                                     today=ctx.as_of, style=ctx.style, user_role=ctx.user.role)
        messages: list[Message] = [Message("system", system)]
        messages += (history or [])[-MAX_HISTORY_MESSAGES:]
        messages.append(Message("user", user_text))
        tools = specs_for(ctx.user)
        vault = PIIVault()
        transform = _pii_transform(vault)
        outcomes: list[ToolOutcome] = []
        final = ""

        for step in range(MAX_STEPS):
            result.steps = step + 1
            try:
                routed = self.router.chat(messages, task="advisory", override=profile, tools=tools,
                                          transform=transform, max_tokens=1200, fallback=allow_fallback)
            except ProviderError as e:
                result.error = str(e)[:300]
                final = _fallback_text(lang)
                break
            resp = routed.response
            result.profile, result.model = routed.profile, resp.model
            result.attempts += [a.__dict__ for a in routed.attempts]
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
        result.ungrounded_numbers = ungrounded_numbers(result.reply, ok_data, user_text) if outcomes else \
            ungrounded_numbers(result.reply, [], user_text)
        if any(REGISTRY[o.tool].advisory for o in outcomes if o.tool in REGISTRY and o.status == "ok"):
            result.disclaimer = DISCLAIMER.get(lang, DISCLAIMER["en"])
        result.latency_ms = (time.perf_counter() - start) * 1000

        audit.record(ctx.session, actor=ctx.user.username, actor_role=ctx.user.role, business_id=ctx.business.id,
                     event_type="agent_decision", action="answer",
                     inputs={"text": user_text[:500], "language": lang, "profile": result.profile},
                     result={"tools": [f"{o.tool}:{o.status}" for o in outcomes], "reply": mask_text(result.reply[:400]),
                             "ungrounded_numbers": result.ungrounded_numbers[:10],
                             "pending_actions": [p["id"] for p in result.pending_actions]},
                     request_id=rid)
        return result


def _fallback_text(lang: str) -> str:
    return {"bn": "দুঃখিত, এই মুহূর্তে উত্তর তৈরি করতে পারছি না। একটু পরে আবার চেষ্টা করুন।",
            "banglish": "Dukkhito, ekhon uttor dite parchi na. Ektu pore abar chesta korun."}.get(
        lang, "Sorry, I couldn't complete that right now. Please try again.")
