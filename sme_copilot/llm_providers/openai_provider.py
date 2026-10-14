"""OpenAI Chat Completions adapter, plus the generic OpenAI-compatible adapter.

The OpenAI-compatible adapter covers OpenRouter, Groq, DeepSeek, Together, and local servers
(Ollama ``/v1``, llama.cpp ``server``, vLLM) since they all speak the same wire format.
"""
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
    parse_json_arguments,
)


def to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append({
                "role": "assistant",
                "content": m.content or None,
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.name, "arguments": json.dumps(tc.arguments, ensure_ascii=False)}}
                    for tc in m.tool_calls
                ],
            })
        else:
            out.append({"role": m.role, "content": m.content})
    return out


def to_openai_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [{"type": "function",
             "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tools]


class OpenAIProvider(LLMProvider):
    adapter = "openai"
    default_base_url = "https://api.openai.com/v1"
    max_tokens_field = "max_completion_tokens"
    json_mode = "json_schema"  # json_schema | json_object | none

    def __init__(self, model: str, **kw: Any):
        super().__init__(model, **kw)
        if not self.base_url:
            self.base_url = self.default_base_url
        self.json_mode = self.extra.get("json_mode", self.json_mode)
        self.supports_tools = bool(self.extra.get("supports_tools", self.supports_tools))
        self.max_tokens_field = self.extra.get("max_tokens_field", self.max_tokens_field)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        h.update(self.extra.get("headers", {}))
        return h

    def _payload(self, messages: list[Message], tools: list[ToolSpec] | None,
                 json_schema: dict[str, Any] | None, temperature: float, max_tokens: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(messages),
            "temperature": temperature,
            self.max_tokens_field: max_tokens,
        }
        if tools and self.supports_tools:
            payload["tools"] = to_openai_tools(tools)
            payload["tool_choice"] = "auto"
        if json_schema is not None and self.json_mode != "none":
            if self.json_mode == "json_schema":
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "structured_output", "schema": json_schema, "strict": False},
                }
            else:
                payload["response_format"] = {"type": "json_object"}
        payload.update(self.extra.get("request_params") or {})  # e.g. top_p/top_k for a local server
        return payload

    def _chat(self, messages, *, tools, json_schema, temperature, max_tokens) -> ChatResponse:
        data = self._post(f"{self.base_url}/chat/completions",
                          self._payload(messages, tools, json_schema, temperature, max_tokens),
                          self._headers())
        return self._parse(data)

    def _parse(self, data: dict[str, Any]) -> ChatResponse:
        try:
            choice = data["choices"][0]
            msg = choice.get("message") or {}
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"{self.profile}: unexpected response shape") from e
        calls = [
            ToolCall(id=tc.get("id") or f"call_{i}", name=tc["function"]["name"],
                     arguments=parse_json_arguments(tc["function"].get("arguments")))
            for i, tc in enumerate(msg.get("tool_calls") or [])
            if tc.get("function")
        ]
        u = data.get("usage") or {}
        return ChatResponse(
            content=msg.get("content") or "",
            tool_calls=calls,
            provider=self.adapter,
            model=data.get("model", self.model),
            usage=Usage(u.get("prompt_tokens", 0) or 0, u.get("completion_tokens", 0) or 0),
            finish_reason=choice.get("finish_reason"),
            raw=data,
        )

    def stream(self, messages, *, temperature=0.2, max_tokens=1024) -> Iterator[StreamChunk]:
        payload = self._payload(messages, None, None, temperature, max_tokens)
        payload["stream"] = True
        if self.extra.get("stream_usage", True):
            payload["stream_options"] = {"include_usage": True}
        start = time.perf_counter()
        ttft: float | None = None
        parts: list[str] = []
        usage = Usage()
        try:
            with self._client() as client, client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=self._headers()
            ) as r:
                if r.status_code >= 400:
                    r.read()
                    raise ProviderError(f"{self.profile}: HTTP {r.status_code}: {r.text[:300]}",
                                        retryable=r.status_code >= 500, status=r.status_code)
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if body == "[DONE]":
                        break
                    try:
                        evt = json.loads(body)
                    except ValueError:
                        continue
                    if evt.get("usage"):
                        usage = Usage(evt["usage"].get("prompt_tokens", 0) or 0,
                                      evt["usage"].get("completion_tokens", 0) or 0)
                    for ch in evt.get("choices") or []:
                        delta = (ch.get("delta") or {}).get("content")
                        if delta:
                            if ttft is None:
                                ttft = (time.perf_counter() - start) * 1000
                            parts.append(delta)
                            yield StreamChunk(delta=delta)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.profile}: stream error: {e}", retryable=True) from e
        text = "".join(parts)
        resp = ChatResponse(content=text, tool_calls=[], provider=self.adapter, model=self.model,
                            usage=usage, latency_ms=(time.perf_counter() - start) * 1000, ttft_ms=ttft)
        if not resp.usage.output_tokens:
            from .base import estimate_tokens, messages_token_estimate
            resp.usage = Usage(messages_token_estimate(messages), estimate_tokens(text))
        yield StreamChunk(done=True, response=resp)


class OpenAICompatibleProvider(OpenAIProvider):
    """Any server exposing ``/chat/completions`` (OpenRouter, Groq, DeepSeek, Together, vLLM,
    llama.cpp, Ollama). Uses the classic ``max_tokens`` field and ``json_object`` mode, which
    have the widest support."""

    adapter = "openai_compatible"
    default_base_url = "http://localhost:8000/v1"
    max_tokens_field = "max_tokens"
    json_mode = "json_object"


class OllamaProvider(OpenAICompatibleProvider):
    """Ollama via its OpenAI-compatible endpoint. Local by default: no data leaves the machine."""

    adapter = "ollama"
    default_base_url = "http://localhost:11434/v1"

    def __init__(self, model: str, **kw: Any):
        kw.setdefault("external", False)
        super().__init__(model, **kw)
