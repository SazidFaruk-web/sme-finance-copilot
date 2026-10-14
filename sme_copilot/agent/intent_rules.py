"""Offline rule-based intent engine (placeholder; full version arrives with the agent phase)."""
from __future__ import annotations

from typing import Any

from sme_copilot.llm_providers.base import ToolCall, ToolSpec


class RuleIntentEngine:
    def plan(self, user_text: str, tools: list[ToolSpec], context: dict[str, Any]) -> list[ToolCall] | str:
        return "I can help with sales, expenses, cash flow and financing questions."

    def compose(self, user_text: str, tool_results: list[tuple[str, dict[str, Any]]],
                context: dict[str, Any]) -> str:
        if not tool_results:
            return "I can help with sales, expenses, cash flow and financing questions."
        return "\n".join(f"{name}: {res}" for name, res in tool_results)
