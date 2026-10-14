"""Google Gemini (Generative Language API, generateContent) adapter."""
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
    Usage,
)
from .schema_utils import inline_schema


def to_gemini(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    system: list[str] = []
    contents: list[dict[str, Any]] = []

    def push(role: str, parts: list[dict[str, Any]]) -> None:
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"].extend(parts)
        else:
            contents.append({"role": role, "parts": parts})

    for m in messages:
        if m.role == "system":
            system.append(m.content)
        elif m.role == "tool":
            try:
                payload = json.loads(m.content)
                if not isinstance(payload, dict):
                    payload = {"result": payload}
            except ValueError:
                payload = {"result": m.content}
            push("user", [{"functionResponse": {"name": m.name or "tool", "response": payload}}])
        elif m.role == "assistant":
            parts: list[dict[str, Any]] = []
            if m.content:
                parts.append({"text": m.content})
            for tc in m.tool_calls:
                parts.append({"functionCall": {"name": tc.name, "args": tc.arguments}})
            push("model", parts or [{"text": ""}])
        else:
            push("user", [{"text": m.content}])
    return "\n\n".join(system), contents


class GeminiProvider(LLMProvider):
    adapter = "gemini"
    default_base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, model: str, **kw: Any):
        super().__init__(model, **kw)
        if not self.base_url:
            self.base_url = self.default_base_url

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise ProviderError(f"{self.profile}: missing API key")
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def _payload(self, messages, tools, json_schema, temperature, max_tokens) -> dict[str, Any]:
        system, contents = to_gemini(messages)
        gen: dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_tokens}
        payload: dict[str, Any] = {"contents": contents, "generationConfig": gen}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description, "parameters": inline_schema(t.parameters)}
                for t in tools]}]
        if json_schema is not None:
            gen["responseMimeType"] = "application/json"
            gen["responseSchema"] = inline_schema(json_schema)
        return payload

    def _parse(self, data: dict[str, Any]) -> ChatResponse:
        cands = data.get("candidates") or []
        if not cands:
            raise ProviderError(f"{self.profile}: no candidates (blocked or empty): {str(data)[:200]}")
        parts = (cands[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        calls = [ToolCall(name=p["functionCall"]["name"], arguments=p["functionCall"].get("args") or {})
                 for p in parts if "functionCall" in p]
        um = data.get("usageMetadata") or {}
        return ChatResponse(content=text, tool_calls=calls, provider=self.adapter, model=self.model,
                            usage=Usage(um.get("promptTokenCount", 0) or 0, um.get("candidatesTokenCount", 0) or 0),
                            finish_reason=cands[0].get("finishReason"), raw=data)

    def _chat(self, messages, *, tools, json_schema, temperature, max_tokens) -> ChatResponse:
        data = self._post(f"{self.base_url}/models/{self.model}:generateContent",
                          self._payload(messages, tools, json_schema, temperature, max_tokens),
                          self._headers())
        return self._parse(data)

    def stream(self, messages, *, temperature=0.2, max_tokens=1024) -> Iterator[StreamChunk]:
        payload = self._payload(messages, None, None, temperature, max_tokens)
        start = time.perf_counter()
        ttft: float | None = None
        parts: list[str] = []
        usage = Usage()
        try:
            with self._client() as client, client.stream(
                "POST", f"{self.base_url}/models/{self.model}:streamGenerateContent?alt=sse",
                json=payload, headers=self._headers()
            ) as r:
                if r.status_code >= 400:
                    r.read()
                    raise ProviderError(f"{self.profile}: HTTP {r.status_code}: {r.text[:300]}",
                                        retryable=r.status_code >= 500, status=r.status_code)
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    try:
                        evt = json.loads(line[5:].strip())
                    except ValueError:
                        continue
                    um = evt.get("usageMetadata")
                    if um:
                        usage = Usage(um.get("promptTokenCount", 0) or 0, um.get("candidatesTokenCount", 0) or 0)
                    for c in evt.get("candidates") or []:
                        for p in (c.get("content") or {}).get("parts") or []:
                            delta = p.get("text")
                            if delta:
                                if ttft is None:
                                    ttft = (time.perf_counter() - start) * 1000
                                parts.append(delta)
                                yield StreamChunk(delta=delta)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.profile}: stream error: {e}", retryable=True) from e
        yield StreamChunk(done=True, response=ChatResponse(
            content="".join(parts), tool_calls=[], provider=self.adapter, model=self.model, usage=usage,
            latency_ms=(time.perf_counter() - start) * 1000, ttft_ms=ttft))
