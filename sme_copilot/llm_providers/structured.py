"""Structured output and tool-call emulation with validation + retry.

Two helpers:

* ``structured_chat`` - get a pydantic-validated object from any provider. Uses native JSON
  mode when available, otherwise prompt-instructed JSON; on parse/validation failure the error
  is fed back to the model and it retries.
* ``emulated_tool_chat`` - for models without reliable native tool calling (many small local
  models). The tool list is described in the prompt and the model must answer with a strict
  JSON envelope, which is validated and converted to ``ToolCall`` objects.
"""
from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .base import ChatResponse, LLMProvider, Message, ProviderError, ToolCall, ToolSpec
from .schema_utils import inline_schema, strip_nullable

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str) -> Any:
    """Pull the first JSON object/array out of model text (handles code fences and chatter)."""
    text = (text or "").strip()
    m = _FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # find first balanced {...}
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except ValueError:
                        break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object found in model output")


def structured_chat(provider: LLMProvider, messages: list[Message], model: type[T], *,
                    retries: int = 2, max_tokens: int = 800) -> tuple[T, ChatResponse]:
    schema = strip_nullable(inline_schema(model.model_json_schema()))
    msgs = list(messages)
    if not provider.supports_json_mode:
        msgs = msgs + [Message("system", "Respond ONLY with a JSON object matching this JSON schema, "
                                         f"no prose:\n{json.dumps(schema, ensure_ascii=False)}")]
    last_err = ""
    for _ in range(retries + 1):
        resp = provider.chat(msgs, json_schema=schema if provider.supports_json_mode else None,
                             temperature=0.0, max_tokens=max_tokens)
        try:
            obj = model.model_validate(extract_json(resp.content))
            return obj, resp
        except (ValueError, ValidationError) as e:
            last_err = str(e)[:500]
            msgs = msgs + [Message("assistant", resp.content),
                           Message("user", f"That output was invalid: {last_err}\n"
                                           "Return ONLY corrected JSON matching the schema.")]
    raise ProviderError(f"structured output failed after {retries + 1} attempts: {last_err}")


class _Envelope(BaseModel):
    action: str  # "call_tool" | "final"
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    content: str | None = None


def tool_prompt(tools: list[ToolSpec]) -> str:
    lines = ["You can call tools. Reply with EXACTLY ONE JSON object and nothing else:",
             '  {"action": "call_tool", "tool": "<name>", "arguments": {...}}',
             '  or {"action": "final", "content": "<answer for the user>"}',
             "Available tools:"]
    for t in tools:
        params = strip_nullable(inline_schema(t.parameters))
        lines.append(f"- {t.name}: {t.description}\n  arguments schema: {json.dumps(params, ensure_ascii=False)}")
    return "\n".join(lines)


def emulated_tool_chat(provider: LLMProvider, messages: list[Message], tools: list[ToolSpec], *,
                       retries: int = 2, max_tokens: int = 1024) -> ChatResponse:
    """Tool calling via strict JSON for providers that lack native tools."""
    names = {t.name for t in tools}
    # Tool results are rendered as plain text, since the model has no native tool role.
    msgs: list[Message] = [Message("system", tool_prompt(tools))]
    for m in messages:
        if m.role == "tool":
            msgs.append(Message("user", f"[tool result: {m.name}]\n{m.content}"))
        elif m.role == "assistant" and m.tool_calls:
            tc = m.tool_calls[0]
            msgs.append(Message("assistant", json.dumps({"action": "call_tool", "tool": tc.name,
                                                         "arguments": tc.arguments}, ensure_ascii=False)))
        else:
            msgs.append(m)
    last_err = ""
    for _ in range(retries + 1):
        resp = provider.chat(msgs, temperature=0.0, max_tokens=max_tokens)
        try:
            env = _Envelope.model_validate(extract_json(resp.content))
            if env.action == "call_tool":
                if env.tool not in names:
                    raise ValueError(f"unknown tool '{env.tool}'. Valid: {sorted(names)}")
                resp.tool_calls = [ToolCall(name=env.tool, arguments=env.arguments or {})]
                resp.content = ""
            elif env.action == "final":
                resp.content = env.content or ""
                resp.tool_calls = []
            else:
                raise ValueError("action must be 'call_tool' or 'final'")
            return resp
        except (ValueError, ValidationError) as e:
            # Small models sometimes answer in prose: accept it as a final answer if it has no braces.
            if "{" not in (resp.content or "") and resp.content.strip():
                resp.tool_calls = []
                return resp
            last_err = str(e)[:400]
            msgs = msgs + [Message("assistant", resp.content),
                           Message("user", f"Invalid reply: {last_err}. Reply with ONE valid JSON object only.")]
    raise ProviderError(f"tool-call emulation failed: {last_err}")
