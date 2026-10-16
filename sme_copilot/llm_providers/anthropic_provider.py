"""Anthropic (Claude) Messages API adapter."""
from __future__ import annotations

import json
import time
from typing import Any, Iterator

import httpx

from .base import (
    ChatResponse,
    LLMProvider,
    Message,
    ProviderError,
    StreamChunk,
    ToolCall,
    ToolSpec,
    Usage,
)

STRUCTURED_TOOL = "structured_output"


def to_anthropic(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Split out the system prompt and convert to Anthropic content blocks.

    Anthropic requires strictly alternating user/assistant turns, and tool results travel
    inside a *user* turn, so consecutive same-role blocks are merged.
    """
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []

    def push(role: str, blocks: list[dict[str, Any]]) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})

    for m in messages:
        if m.role == "system":
            system_parts.append(m.content)
        elif m.role == "tool":
            push("user", [{"type": "tool_result", "tool_use_id": m.tool_call_id or "", "content": m.content}])
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            for tc in m.tool_calls:
                blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
            push("assistant", blocks or [{"type": "text", "text": ""}])
        else:
            push("user", [{"type": "image", "source": {"type": "base64", "media_type": img.media_type, "data": img.data}}
                          for img in m.images] + [{"type": "text", "text": m.content}])
    return "\n\n".join(system_parts), out


class AnthropicProvider(LLMProvider):
    adapter = "anthropic"
    default_base_url = "https://api.anthropic.com"
    api_version = "2023-06-01"

    def __init__(self, model: str, **kw: Any):
        super().__init__(model, **kw)
        if not self.base_url:
            self.base_url = self.default_base_url

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError(f"{self.profile}: missing API key (set the env var named in providers.yaml)")
        return {"x-api-key": self.api_key, "anthropic-version": self.api_version,
                "content-type": "application/json"}

    def _payload(self, messages, tools, json_schema, temperature, max_tokens) -> dict[str, Any]:
        system, msgs = to_anthropic(messages)
        payload: dict[str, Any] = {"model": self.model, "max_tokens": max_tokens, "messages": msgs}
        if not self.extra.get("omit_temperature"):
            payload["temperature"] = temperature
        if system:
            payload["system"] = system
        tool_defs = [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                     for t in (tools or [])]
        if json_schema is not None:
            # Structured output via a forced tool call: robust and schema-shaped.
            tool_defs = [{"name": STRUCTURED_TOOL, "description": "Return the answer in this exact structure.",
                          "input_schema": json_schema}]
            payload["tool_choice"] = {"type": "tool", "name": STRUCTURED_TOOL}
        if tool_defs:
            payload["tools"] = tool_defs
        return payload

    def _chat(self, messages, *, tools, json_schema, temperature, max_tokens) -> ChatResponse:
        data = self._post(f"{self.base_url}/v1/messages",
                          self._payload(messages, tools, json_schema, temperature, max_tokens),
                          self._headers())
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in data.get("content") or []:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                if block.get("name") == STRUCTURED_TOOL and json_schema is not None:
                    text_parts.append(json.dumps(block.get("input") or {}, ensure_ascii=False))
                else:
                    calls.append(ToolCall(id=block.get("id", ""), name=block["name"],
                                          arguments=block.get("input") or {}))
        u = data.get("usage") or {}
        return ChatResponse(
            content="".join(text_parts), tool_calls=calls, provider=self.adapter,
            model=data.get("model", self.model),
            usage=Usage(u.get("input_tokens", 0) or 0, u.get("output_tokens", 0) or 0),
            finish_reason=data.get("stop_reason"), raw=data,
        )

    def stream(self, messages, *, temperature=0.2, max_tokens=1024) -> Iterator[StreamChunk]:
        payload = self._payload(messages, None, None, temperature, max_tokens)
        payload["stream"] = True
        start = time.perf_counter()
        ttft: float | None = None
        parts: list[str] = []
        usage = Usage()
        try:
            with self._client() as client, client.stream(
                "POST", f"{self.base_url}/v1/messages", json=payload, headers=self._headers()
            ) as r:
                if r.status_code >= 400:
                    r.read()
                    raise ProviderError(f"{self.profile}: HTTP {r.status_code}: {r.text[:300]}",
                                        retryable=r.status_code >= 500 or r.status_code == 429,
                                        status=r.status_code)
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        evt = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    et = evt.get("type")
                    if et == "message_start":
                        usage.input_tokens = (evt.get("message", {}).get("usage") or {}).get("input_tokens", 0)
                    elif et == "content_block_delta" and evt.get("delta", {}).get("type") == "text_delta":
                        delta = evt["delta"].get("text", "")
                        if delta:
                            if ttft is None:
                                ttft = (time.perf_counter() - start) * 1000
                            parts.append(delta)
                            yield StreamChunk(delta=delta)
                    elif et == "message_delta":
                        usage.output_tokens = (evt.get("usage") or {}).get("output_tokens", usage.output_tokens)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.profile}: stream error: {e}", retryable=True) from e
        yield StreamChunk(done=True, response=ChatResponse(
            content="".join(parts), tool_calls=[], provider=self.adapter, model=self.model, usage=usage,
            latency_ms=(time.perf_counter() - start) * 1000, ttft_ms=ttft))
