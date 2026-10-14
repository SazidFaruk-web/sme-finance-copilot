"""Deterministic offline "model".

It implements the same LLMProvider interface as the real adapters, so the full agent loop
(tool selection -> permission check -> execution -> answer) runs with zero network and zero
GPU. It is used for: (1) the offline demo, (2) deterministic end-to-end tests, and (3) the
baseline row in the model benchmark.

Behaviour:
* If the conversation has no tool results after the latest user turn, it asks the intent
  engine which tool(s) to call.
* Otherwise it asks the intent engine to compose a templated answer from the tool results.
"""
from __future__ import annotations

import json
from typing import Any, Protocol

from .base import ChatResponse, LLMProvider, Message, ToolCall, ToolSpec, Usage, estimate_tokens


class IntentEngine(Protocol):
    def plan(self, user_text: str, tools: list[ToolSpec], context: dict[str, Any]) -> list[ToolCall] | str: ...

    def compose(self, user_text: str, tool_results: list[tuple[str, dict[str, Any]]],
                context: dict[str, Any]) -> str: ...


class RulesProvider(LLMProvider):
    adapter = "rules"
    supports_tools = True
    supports_json_mode = False

    def __init__(self, model: str = "rules-v1", *, engine: IntentEngine | None = None, **kw: Any):
        kw.setdefault("external", False)
        super().__init__(model, **kw)
        self._engine = engine

    @property
    def engine(self) -> IntentEngine:
        if self._engine is None:
            from sme_copilot.agent.intent_rules import RuleIntentEngine  # lazy: avoid import cycle
            self._engine = RuleIntentEngine()
        return self._engine

    def _chat(self, messages: list[Message], *, tools: list[ToolSpec] | None, json_schema, temperature,
              max_tokens) -> ChatResponse:
        last_user = max((i for i, m in enumerate(messages) if m.role == "user"), default=-1)
        user_text = messages[last_user].content if last_user >= 0 else ""
        context = _context_from_system(messages)
        results: list[tuple[str, dict[str, Any]]] = []
        for m in messages[last_user + 1:]:
            if m.role == "tool":
                try:
                    payload = json.loads(m.content)
                except ValueError:
                    payload = {"raw": m.content}
                results.append((m.name or "", payload if isinstance(payload, dict) else {"value": payload}))

        if results or not tools:
            text = self.engine.compose(user_text, results, context)
            return ChatResponse(content=text, tool_calls=[], provider=self.adapter, model=self.model,
                                usage=Usage(0, estimate_tokens(text)), finish_reason="stop")
        plan = self.engine.plan(user_text, tools, context)
        if isinstance(plan, str):
            return ChatResponse(content=plan, tool_calls=[], provider=self.adapter, model=self.model,
                                finish_reason="stop")
        return ChatResponse(content="", tool_calls=plan, provider=self.adapter, model=self.model,
                            finish_reason="tool_use")


def _context_from_system(messages: list[Message]) -> dict[str, Any]:
    """The agent embeds a small JSON context block (language, today) in the system prompt."""
    for m in messages:
        if m.role == "system" and "<context>" in m.content:
            try:
                raw = m.content.split("<context>", 1)[1].split("</context>", 1)[0]
                return json.loads(raw)
            except (IndexError, ValueError):
                return {}
    return {}
