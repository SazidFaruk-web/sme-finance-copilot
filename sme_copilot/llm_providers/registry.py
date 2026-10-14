"""Build providers from config/providers.yaml and route requests with automatic fallback."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from sme_copilot.config import Settings, env_or_none, get_settings, load_yaml

from .anthropic_provider import AnthropicProvider
from .base import ChatResponse, LLMProvider, Message, ProviderBlockedError, ProviderError, ToolSpec
from .gemini_provider import GeminiProvider
from .openai_provider import OllamaProvider, OpenAICompatibleProvider, OpenAIProvider
from .rules_provider import RulesProvider
from .structured import emulated_tool_chat

log = logging.getLogger(__name__)

ADAPTERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "ollama": OllamaProvider,
    "rules": RulesProvider,
}

# Adapters that need an API key to work at all.
KEY_REQUIRED = {"anthropic", "openai", "gemini"}


@dataclass
class ProfileInfo:
    name: str
    adapter: str
    model: str
    label: str
    external: bool
    available: bool
    reason: str = ""


class ProviderRegistry:
    def __init__(self, config: dict[str, Any] | None = None, settings: Settings | None = None,
                 transport: httpx.BaseTransport | None = None):
        self.settings = settings or get_settings()
        self.config = config if config is not None else load_yaml(self.settings.providers_file)
        self.profiles: dict[str, dict[str, Any]] = self.config.get("profiles", {})
        self.routing: dict[str, Any] = self.config.get("routing", {}) or {}
        self._transport = transport
        self._cache: dict[str, LLMProvider] = {}

    @property
    def default_profile(self) -> str:
        return self.settings.llm_profile or self.config.get("default_profile", "rules-offline")

    def info(self, name: str) -> ProfileInfo:
        p = self.profiles[name]
        external = bool(p.get("external", True))
        available, reason = True, ""
        if external and self.settings.local_only_mode:
            available, reason = False, "blocked: LOCAL_ONLY_MODE is on"
        elif p.get("adapter") in KEY_REQUIRED or (p.get("api_key_env") and external):
            if not env_or_none(p.get("api_key_env")):
                available, reason = False, f"missing env var {p.get('api_key_env')}"
        return ProfileInfo(name=name, adapter=p.get("adapter", "?"), model=p.get("model", "?"),
                           label=p.get("label", name), external=external, available=available, reason=reason)

    def list_profiles(self) -> list[ProfileInfo]:
        return [self.info(n) for n in self.profiles]

    def get(self, name: str) -> LLMProvider:
        if name not in self.profiles:
            raise ProviderError(f"unknown provider profile '{name}'")
        info = self.info(name)
        if info.external and self.settings.local_only_mode:
            raise ProviderBlockedError(f"profile '{name}' sends data off-machine; LOCAL_ONLY_MODE is on")
        if name in self._cache:
            return self._cache[name]
        p = self.profiles[name]
        cls = ADAPTERS.get(p.get("adapter", ""))
        if cls is None:
            raise ProviderError(f"profile '{name}': unknown adapter '{p.get('adapter')}'")
        extra = dict(p.get("extra") or {})
        base_url = p.get("base_url")
        if p.get("adapter") == "ollama" and env_or_none("OLLAMA_BASE_URL"):
            base_url = env_or_none("OLLAMA_BASE_URL")  # e.g. http://ollama:11434/v1 inside docker-compose
        if p.get("tools") == "emulated":
            extra["supports_tools"] = False
        provider = cls(
            p.get("model", ""), profile=name, api_key=env_or_none(p.get("api_key_env")),
            base_url=base_url, timeout=float(p.get("timeout", self.settings.llm_timeout_seconds)),
            max_retries=int(p.get("max_retries", self.settings.llm_max_retries)),
            external=bool(p.get("external", True)), pricing=p.get("pricing"),
            transport=self._transport, extra=extra,
        )
        if p.get("tools") == "emulated":
            provider.supports_tools = False
        self._cache[name] = provider
        return provider


@dataclass
class Attempt:
    profile: str
    ok: bool
    error: str = ""
    latency_ms: float = 0.0


@dataclass
class RoutedResponse:
    response: ChatResponse
    profile: str
    attempts: list[Attempt] = field(default_factory=list)


class ModelRouter:
    """Chooses a provider per task and falls back down the chain on failure.

    Tasks: ``advisory`` (default, the main agent), ``classification``, ``extraction``,
    ``categorization``. Rules live in providers.yaml -> routing.
    """

    def __init__(self, registry: ProviderRegistry):
        self.registry = registry

    def chain(self, task: str = "advisory", override: str | None = None, fallback: bool = True) -> list[str]:
        r = self.registry.routing
        if override:
            primary = override
        elif r.get("enabled"):
            primary = (r.get("task_profiles") or {}).get(task) or self.registry.default_profile
        else:
            primary = self.registry.default_profile
        if not fallback:  # benchmarks: measure exactly one model, never silently substitute another
            return [primary]
        # Fallback is on for users: a failing provider must never leave them without an answer.
        names = [primary] + [n for n in (r.get("fallback_chain") or []) if n != primary]
        if "rules-offline" in self.registry.profiles and "rules-offline" not in names:
            names.append("rules-offline")
        return names

    def chat(self, messages: list[Message], *, task: str = "advisory", override: str | None = None,
             tools: list[ToolSpec] | None = None, json_schema: dict[str, Any] | None = None,
             max_tokens: int = 1024, temperature: float = 0.2,
             transform: Any = None, fallback: bool = True) -> RoutedResponse:
        """Try each profile in the chain. ``transform(provider, messages) -> (messages, restore)``
        lets the caller mask PII for external providers and restore it in the reply."""
        attempts: list[Attempt] = []
        for name in self.chain(task, override, fallback):
            info = self.registry.info(name)
            if not info.available:
                attempts.append(Attempt(name, False, info.reason))
                continue
            try:
                provider = self.registry.get(name)
                msgs, restore = (transform(provider, messages) if transform else (messages, None))
                if tools and not provider.supports_tools:
                    resp = emulated_tool_chat(provider, msgs, tools, max_tokens=max_tokens)
                else:
                    resp = provider.chat(msgs, tools=tools, json_schema=json_schema,
                                         temperature=temperature, max_tokens=max_tokens)
                if restore:
                    resp = restore(resp)
                attempts.append(Attempt(name, True, latency_ms=resp.latency_ms))
                return RoutedResponse(resp, name, attempts)
            except ProviderError as e:
                log.warning("provider %s failed: %s", name, e)
                attempts.append(Attempt(name, False, str(e)[:300]))
        raise ProviderError("all providers failed: " + "; ".join(f"{a.profile}: {a.error}" for a in attempts))


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry


def get_router() -> ModelRouter:
    return ModelRouter(get_registry())


def reset_registry() -> None:
    global _registry
    _registry = None
