"""Unified LLM provider interface.

Every adapter (Anthropic, OpenAI, Gemini, OpenAI-compatible, Ollama, offline rules) converts
between these provider-neutral types and its own wire format, so the agent never touches a
vendor-specific payload.
"""
from __future__ import annotations

import json
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Literal

import httpx

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    id: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")


@dataclass
class Message:
    role: Role
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None  # for role == "tool"
    name: str | None = None  # tool name for role == "tool"


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema (object)


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[ToolCall]
    provider: str
    model: str
    usage: Usage = field(default_factory=Usage)
    latency_ms: float = 0.0
    ttft_ms: float | None = None
    finish_reason: str | None = None
    raw: Any = None

    @property
    def tokens_per_second(self) -> float | None:
        if not self.usage.output_tokens or not self.latency_ms:
            return None
        gen_ms = self.latency_ms - (self.ttft_ms or 0)
        return self.usage.output_tokens / max(gen_ms / 1000, 1e-3)


@dataclass
class StreamChunk:
    delta: str = ""
    done: bool = False
    response: ChatResponse | None = None  # populated on the final chunk


class ProviderError(Exception):
    """Any failure talking to a provider (network, auth, bad response)."""

    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class ProviderBlockedError(ProviderError):
    """Provider refused by policy (e.g. local-only mode forbids external APIs)."""


def estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate.

    ~4 chars/token for Latin text; Bangla script tokenizes much worse (often 1-2 chars/token),
    so we count non-ASCII characters more heavily. Used for budgeting and cost estimates when
    the provider does not report usage.
    """
    if not text:
        return 0
    ascii_chars = sum(1 for c in text if ord(c) < 128)
    other = len(text) - ascii_chars
    return max(1, int(ascii_chars / 4 + other / 1.5))


def messages_token_estimate(messages: list[Message]) -> int:
    total = 0
    for m in messages:
        total += 4 + estimate_tokens(m.content)
        for tc in m.tool_calls:
            total += estimate_tokens(tc.name + json.dumps(tc.arguments, ensure_ascii=False))
    return total


class LLMProvider(ABC):
    """Abstract provider. Subclasses implement ``_chat`` and optionally ``_stream``."""

    adapter: str = "base"
    supports_tools: bool = True
    supports_json_mode: bool = True

    def __init__(
        self,
        model: str,
        *,
        profile: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 2,
        external: bool = True,
        pricing: dict[str, float] | None = None,
        transport: httpx.BaseTransport | None = None,
        extra: dict[str, Any] | None = None,
    ):
        self.model = model
        self.profile = profile or f"{self.adapter}:{model}"
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.external = external  # True if data leaves this machine
        self.pricing = pricing or {}
        self.extra = extra or {}
        self._transport = transport  # injectable for tests

    # ------------------------------------------------------------------ public API
    def chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> ChatResponse:
        """Single non-streaming completion, with retries on transient errors."""
        start = time.perf_counter()
        resp = self._with_retries(
            lambda: self._chat(messages, tools=tools, json_schema=json_schema,
                               temperature=temperature, max_tokens=max_tokens)
        )
        resp.latency_ms = (time.perf_counter() - start) * 1000
        if not resp.usage.input_tokens:
            resp.usage.input_tokens = messages_token_estimate(messages)
        if not resp.usage.output_tokens:
            resp.usage.output_tokens = estimate_tokens(resp.content)
        return resp

    def stream(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> Iterator[StreamChunk]:
        """Stream text deltas. Final chunk has ``done=True`` and the full ChatResponse.

        Default implementation falls back to a single chat call (one big chunk) for
        adapters without native streaming.
        """
        start = time.perf_counter()
        resp = self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        resp.ttft_ms = (time.perf_counter() - start) * 1000
        yield StreamChunk(delta=resp.content)
        yield StreamChunk(done=True, response=resp)

    def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        on_delta: Callable[[str], None],
    ) -> ChatResponse:
        """Like ``chat`` (tool calls included) but reports answer text through ``on_delta`` as it is
        generated. Adapters without incremental output just return the full response."""
        return self.chat(messages, tools=tools, temperature=temperature, max_tokens=max_tokens)

    def count_tokens(self, messages: list[Message]) -> int:
        return messages_token_estimate(messages)

    def estimate_cost(self, usage: Usage) -> float:
        """USD estimate using pricing from providers.yaml (illustrative; verify)."""
        pin = float(self.pricing.get("input_per_mtok", 0))
        pout = float(self.pricing.get("output_per_mtok", 0))
        return usage.input_tokens / 1e6 * pin + usage.output_tokens / 1e6 * pout

    # ------------------------------------------------------------------ for subclasses
    @abstractmethod
    def _chat(
        self,
        messages: list[Message],
        *,
        tools: list[ToolSpec] | None,
        json_schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> ChatResponse: ...

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self._transport)

    def _post(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        try:
            with self._client() as client:
                r = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ProviderError(f"{self.profile}: timeout: {e}", retryable=True) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.profile}: network error: {e}", retryable=True) from e
        if r.status_code >= 400:
            retryable = r.status_code in (408, 409, 429) or r.status_code >= 500
            raise ProviderError(
                f"{self.profile}: HTTP {r.status_code}: {r.text[:300]}",
                retryable=retryable, status=r.status_code,
            )
        try:
            return r.json()
        except ValueError as e:
            raise ProviderError(f"{self.profile}: invalid JSON response") from e

    def _with_retries(self, fn: Callable[[], ChatResponse]) -> ChatResponse:
        last: ProviderError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return fn()
            except ProviderError as e:
                last = e
                if not e.retryable or attempt == self.max_retries:
                    raise
                time.sleep(min(0.5 * 2**attempt, 4.0))
        assert last is not None
        raise last


def parse_json_arguments(raw: Any) -> dict[str, Any]:
    """Tool-call arguments arrive as dict or JSON string depending on the vendor."""
    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw)
    except (TypeError, ValueError):
        return {"__unparseable__": str(raw)}
    return val if isinstance(val, dict) else {"__value__": val}
