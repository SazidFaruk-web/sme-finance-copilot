"""Provider adapters tested against mocked HTTP (no network, no keys)."""
from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel

from sme_copilot.config import Settings
from sme_copilot.llm_providers.anthropic_provider import AnthropicProvider, to_anthropic
from sme_copilot.llm_providers.base import Message, ProviderError, ToolCall, ToolSpec, estimate_tokens
from sme_copilot.llm_providers.gemini_provider import GeminiProvider
from sme_copilot.llm_providers.openai_provider import OllamaProvider, OpenAICompatibleProvider, OpenAIProvider
from sme_copilot.llm_providers.registry import ModelRouter, ProviderRegistry
from sme_copilot.llm_providers.schema_utils import inline_schema
from sme_copilot.llm_providers.structured import emulated_tool_chat, extract_json, structured_chat

TOOL = ToolSpec("get_summary", "Income/expense summary", {
    "type": "object", "properties": {"months": {"type": "integer"}}, "required": ["months"]})


def mock(handler):
    return httpx.MockTransport(handler)


# ----------------------------------------------------------------------------- OpenAI
def test_openai_tool_call_roundtrip():
    seen = {}

    def handler(req: httpx.Request):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={
            "model": "gpt-x",
            "choices": [{"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "get_summary", "arguments": "{\"months\": 3}"}}]}}],
            "usage": {"prompt_tokens": 50, "completion_tokens": 7}})

    p = OpenAIProvider("gpt-x", api_key="sk-test", transport=mock(handler), max_retries=0)
    r = p.chat([Message("system", "s"), Message("user", "summary please")], tools=[TOOL])
    assert r.tool_calls[0].name == "get_summary" and r.tool_calls[0].arguments == {"months": 3}
    assert r.usage.input_tokens == 50 and r.usage.output_tokens == 7
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["tools"][0]["function"]["name"] == "get_summary"
    assert "max_completion_tokens" in seen["body"]


def test_openai_tool_result_message_format():
    from sme_copilot.llm_providers.openai_provider import to_openai_messages
    msgs = to_openai_messages([
        Message("assistant", "", tool_calls=[ToolCall("get_summary", {"months": 1}, id="c9")]),
        Message("tool", '{"ok": true}', tool_call_id="c9", name="get_summary")])
    assert msgs[0]["tool_calls"][0]["id"] == "c9"
    assert msgs[1] == {"role": "tool", "tool_call_id": "c9", "content": '{"ok": true}'}


def test_openai_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    p = OpenAIProvider("m", api_key="k", transport=mock(handler), max_retries=2)
    assert p.chat([Message("user", "hi")]).content == "ok"
    assert calls["n"] == 2


def test_openai_does_not_retry_on_401():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(401, text="bad key")

    p = OpenAIProvider("m", api_key="k", transport=mock(handler), max_retries=3)
    with pytest.raises(ProviderError) as ei:
        p.chat([Message("user", "hi")])
    assert ei.value.status == 401 and calls["n"] == 1


def test_openai_streaming_ttft_and_usage():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":5,"completion_tokens":2}}\n\n'
        "data: [DONE]\n\n")
    p = OpenAIProvider("m", api_key="k", transport=mock(lambda r: httpx.Response(200, text=sse)))
    chunks = list(p.stream([Message("user", "hi")]))
    assert "".join(c.delta for c in chunks) == "Hello"
    final = chunks[-1].response
    assert final.content == "Hello" and final.ttft_ms is not None and final.usage.output_tokens == 2


def test_compatible_and_ollama_defaults():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{\"a\": 1}"}}]})

    p = OpenAICompatibleProvider("llama", base_url="https://api.groq.com/openai/v1", api_key="k",
                                 transport=mock(handler))
    p.chat([Message("user", "x")], json_schema={"type": "object"})
    assert seen["url"].startswith("https://api.groq.com/openai/v1/chat/completions")
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert "max_tokens" in seen["body"]

    o = OllamaProvider("qwen2.5:7b-instruct", transport=mock(handler))
    o.chat([Message("user", "x")])
    assert seen["url"].startswith("http://localhost:11434/v1/") and o.external is False


# ----------------------------------------------------------------------------- Anthropic
def test_anthropic_message_conversion_merges_tool_results():
    system, msgs = to_anthropic([
        Message("system", "be helpful"), Message("user", "q"),
        Message("assistant", "", tool_calls=[ToolCall("a", {}, id="t1"), ToolCall("b", {}, id="t2")]),
        Message("tool", "r1", tool_call_id="t1", name="a"), Message("tool", "r2", tool_call_id="t2", name="b")])
    assert system == "be helpful"
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in msgs[2]["content"]] == ["t1", "t2"]


def test_anthropic_tool_use_and_structured_output():
    seen = {}

    def handler(req):
        body = json.loads(req.content)
        seen.setdefault("bodies", []).append(body)
        assert req.headers["x-api-key"] == "ak" and req.headers["anthropic-version"]
        if body.get("tool_choice", {}).get("name") == "structured_output":
            return httpx.Response(200, json={"content": [
                {"type": "tool_use", "id": "x", "name": "structured_output", "input": {"category": "rent"}}],
                "usage": {"input_tokens": 9, "output_tokens": 4}, "stop_reason": "tool_use"})
        return httpx.Response(200, json={"content": [
            {"type": "text", "text": "Let me check."},
            {"type": "tool_use", "id": "tu1", "name": "get_summary", "input": {"months": 6}}],
            "usage": {"input_tokens": 30, "output_tokens": 12}, "stop_reason": "tool_use"})

    p = AnthropicProvider("claude-sonnet-5-5", api_key="ak", transport=mock(handler))
    r = p.chat([Message("system", "sys"), Message("user", "how am I doing")], tools=[TOOL])
    assert r.tool_calls[0].arguments == {"months": 6} and r.content == "Let me check."
    assert seen["bodies"][0]["system"] == "sys"
    assert seen["bodies"][0]["tools"][0]["input_schema"]["required"] == ["months"]

    r2 = p.chat([Message("user", "categorize")], json_schema={"type": "object"})
    assert json.loads(r2.content) == {"category": "rent"}


def test_anthropic_missing_key_is_clear_error():
    p = AnthropicProvider("m", api_key=None, transport=mock(lambda r: httpx.Response(200, json={})))
    with pytest.raises(ProviderError, match="missing API key"):
        p.chat([Message("user", "x")])


def test_anthropic_streaming():
    sse = (
        'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":11}}}\n\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"আপনার "}}\n\n'
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"লাভ"}}\n\n'
        'data: {"type":"message_delta","usage":{"output_tokens":3}}\n\n')
    p = AnthropicProvider("m", api_key="ak", transport=mock(lambda r: httpx.Response(200, text=sse)))
    chunks = list(p.stream([Message("user", "লাভ কত?")]))
    assert chunks[-1].response.content == "আপনার লাভ"
    assert chunks[-1].response.usage.input_tokens == 11 and chunks[-1].response.usage.output_tokens == 3


# ----------------------------------------------------------------------------- Gemini
def test_gemini_function_call_and_schema_inlining():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"functionCall": {"name": "get_summary", "args": {"months": 2}}}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 5}})

    class Inner(BaseModel):
        x: int

    class Outer(BaseModel):
        inner: Inner
        note: str | None = None

    tool = ToolSpec("t", "d", Outer.model_json_schema())
    p = GeminiProvider("gemini-2.5-flash", api_key="g", transport=mock(handler))
    r = p.chat([Message("system", "s"), Message("user", "u")], tools=[tool])
    assert r.tool_calls[0].name == "get_summary" and r.usage.input_tokens == 20
    params = seen["body"]["tools"][0]["functionDeclarations"][0]["parameters"]
    assert "$defs" not in json.dumps(params) and params["properties"]["inner"]["properties"]["x"]["type"] == "integer"
    assert params["properties"]["note"]["nullable"] is True
    assert seen["body"]["systemInstruction"]["parts"][0]["text"] == "s"
    assert ":generateContent" in seen["url"]


def test_gemini_blocked_response_raises():
    p = GeminiProvider("g", api_key="g", transport=mock(lambda r: httpx.Response(200, json={"candidates": []})))
    with pytest.raises(ProviderError):
        p.chat([Message("user", "x")])


# ----------------------------------------------------------------------------- structured / emulated tools
class Cat(BaseModel):
    category: str
    confidence: float


def test_extract_json_variants():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is: {"a": {"b": "}"}} hope that helps') == {"a": {"b": "}"}}
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_structured_chat_retries_after_invalid_output():
    replies = iter(['{"category": "rent"}', '{"category": "rent", "confidence": 0.9}'])

    def handler(req):
        return httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})

    p = OpenAICompatibleProvider("small", transport=mock(handler))
    obj, _ = structured_chat(p, [Message("user", "paid shop rent")], Cat)
    assert obj.category == "rent" and obj.confidence == 0.9


def test_emulated_tool_calling_for_weak_models():
    replies = iter(['I think I should call {"action": "call_tool", "tool": "nope"}',
                    '{"action": "call_tool", "tool": "get_summary", "arguments": {"months": 3}}'])

    def handler(req):
        body = json.loads(req.content)
        assert "tools" not in body  # emulated: no native tools in payload
        return httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})

    p = OpenAICompatibleProvider("tiny", transport=mock(handler), extra={"supports_tools": False})
    r = emulated_tool_chat(p, [Message("user", "summary")], [TOOL])
    assert r.tool_calls[0].name == "get_summary" and r.tool_calls[0].arguments == {"months": 3}


def test_inline_schema_resolves_refs():
    class A(BaseModel):
        v: int

    class B(BaseModel):
        a: A
        items: list[A]

    s = inline_schema(B.model_json_schema())
    assert s["properties"]["items"]["items"]["properties"]["v"]["type"] == "integer"


def test_token_estimate_counts_bangla_heavier():
    assert estimate_tokens("আমার দোকানের ভাড়া") > estimate_tokens("my shop rent")


# ----------------------------------------------------------------------------- registry / router
CFG = {
    "default_profile": "primary",
    "profiles": {
        "primary": {"adapter": "openai_compatible", "model": "m1", "base_url": "http://fail.local/v1",
                    "external": False, "max_retries": 0},
        "cloud": {"adapter": "anthropic", "model": "c", "api_key_env": "ANTHROPIC_API_KEY", "external": True},
        "rules-offline": {"adapter": "rules", "model": "rules-v1", "external": False},
    },
    "routing": {"enabled": True, "task_profiles": {"categorization": "primary"},
                "fallback_chain": ["cloud", "rules-offline"]},
}


def test_router_falls_back_and_records_attempts():
    def handler(req):
        return httpx.Response(500, text="boom")

    reg = ProviderRegistry(CFG, Settings(), transport=mock(handler))
    router = ModelRouter(reg)
    assert router.chain("categorization") == ["primary", "cloud", "rules-offline"]
    res = router.chat([Message("user", "hello")], task="categorization")
    assert res.profile == "rules-offline"
    assert [a.ok for a in res.attempts] == [False, False, True]
    assert "missing env var" in res.attempts[1].error


def test_local_only_mode_blocks_external_profiles():
    s = Settings(local_only_mode=True)
    reg = ProviderRegistry(CFG, s)
    info = {p.name: p for p in reg.list_profiles()}
    assert info["cloud"].available is False and "LOCAL_ONLY" in info["cloud"].reason
    assert info["primary"].available is True
    from sme_copilot.llm_providers.base import ProviderBlockedError
    with pytest.raises(ProviderBlockedError):
        reg.get("cloud")


def test_per_request_override_goes_first():
    reg = ProviderRegistry(CFG, Settings())
    assert ModelRouter(reg).chain(override="rules-offline")[0] == "rules-offline"


def test_shipped_providers_yaml_is_valid():
    reg = ProviderRegistry(settings=Settings())
    names = {p.name for p in reg.list_profiles()}
    assert {"rules-offline", "claude-sonnet", "openai-mini", "gemini-flash", "local-qwen7b",
            "groq-llama70b", "local-llamacpp", "local-vllm"} <= names
    for n in names:
        assert reg.profiles[n]["adapter"] in {"anthropic", "openai", "gemini", "openai_compatible", "ollama", "rules"}
    assert reg.get("local-llama8b").supports_tools is False  # emulated tool mode honoured
