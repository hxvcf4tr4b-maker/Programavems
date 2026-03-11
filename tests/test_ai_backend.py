"""Tests for ai_backend.py — provider detection, message conversion, list_providers."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ai_backend import (
    AnthropicBackend,
    GeminiBackend,
    OpenAICompatibleBackend,
    StreamEndEvent,
    TextDeltaEvent,
    ToolCompleteEvent,
    ToolStartEvent,
    _messages_to_openai,
    _tools_to_openai,
    create_backend,
    list_providers,
)


# ── create_backend: provider detection ────────────────────────────────────────

def _make_backend_mocks():
    """Return three patch objects that replace backend constructors with simple mocks."""
    def make_anthropic(model, api_key=None):
        inst = MagicMock()
        inst.model = model
        inst.api_key = api_key
        inst._backend_type = "anthropic"
        return inst

    def make_openai(model, provider="openai", api_key=None, base_url=None):
        inst = MagicMock()
        inst.model = model
        inst.provider = provider
        inst.api_key = api_key
        inst._backend_type = "openai"
        return inst

    def make_gemini(model, api_key=None):
        inst = MagicMock()
        inst.model = model
        inst.api_key = api_key
        inst._backend_type = "gemini"
        return inst

    return (
        patch("ai_backend.AnthropicBackend", side_effect=make_anthropic),
        patch("ai_backend.OpenAICompatibleBackend", side_effect=make_openai),
        patch("ai_backend.GeminiBackend", side_effect=make_gemini),
    )


class TestCreateBackend:
    def _run(self, spec, **kw):
        p1, p2, p3 = _make_backend_mocks()
        with p1, p2, p3:
            return create_backend(spec, **kw)

    def test_explicit_anthropic(self):
        b = self._run("anthropic:claude-opus-4-6")
        assert b.model == "claude-opus-4-6"
        assert b._backend_type == "anthropic"

    def test_explicit_openai(self):
        b = self._run("openai:gpt-4o")
        assert b.model == "gpt-4o"
        assert b.provider == "openai"

    def test_explicit_groq(self):
        b = self._run("groq:llama-3.3-70b-versatile")
        assert b.provider == "groq"

    def test_explicit_gemini(self):
        b = self._run("gemini:gemini-2.0-flash-exp")
        assert b.model == "gemini-2.0-flash-exp"
        assert b._backend_type == "gemini"

    def test_explicit_ollama(self):
        b = self._run("ollama:llama3")
        assert b.provider == "ollama"

    def test_explicit_mistral(self):
        b = self._run("mistral:mistral-large-latest")
        assert b.provider == "mistral"

    def test_explicit_openrouter(self):
        b = self._run("openrouter:anthropic/claude-3.5-sonnet")
        assert b.provider == "openrouter"

    def test_alias_claude(self):
        b = self._run("claude:claude-opus-4-6")
        assert b._backend_type == "anthropic"

    def test_alias_gpt(self):
        b = self._run("gpt:gpt-4o")
        assert b.provider == "openai"

    def test_alias_local(self):
        b = self._run("local:llama3")
        assert b.provider == "ollama"

    def test_alias_google(self):
        b = self._run("google:gemini-1.5-pro")
        assert b._backend_type == "gemini"

    def test_auto_detect_claude(self):
        b = self._run("claude-opus-4-6")
        assert b._backend_type == "anthropic"

    def test_auto_detect_gpt(self):
        b = self._run("gpt-4o")
        assert b.provider == "openai"

    def test_auto_detect_gemini(self):
        b = self._run("gemini-2.0-flash-exp")
        assert b._backend_type == "gemini"

    def test_auto_detect_llama_groq_key(self):
        p1, p2, p3 = _make_backend_mocks()
        with p1, p2, p3, patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            b = create_backend("llama-3.3-70b-versatile")
        assert b.provider == "groq"

    def test_auto_detect_llama_no_key(self):
        env = {k: v for k, v in os.environ.items() if k != "GROQ_API_KEY"}
        p1, p2, p3 = _make_backend_mocks()
        with p1, p2, p3, patch.dict(os.environ, env, clear=True):
            b = create_backend("llama3")
        assert b.provider == "ollama"

    def test_unknown_provider_falls_back_to_openai_compat(self):
        b = self._run("mycloud:my-model")
        assert b.provider == "mycloud"

    def test_api_key_passed_through(self):
        b = self._run("anthropic:claude-opus-4-6", api_key="sk-test")
        assert b.api_key == "sk-test"


# ── _messages_to_openai ────────────────────────────────────────────────────────

class TestMessagesToOpenAI:
    def test_string_content_round_trips(self):
        messages = [{"role": "user", "content": "Hello"}]
        result = _messages_to_openai(messages, system="")
        assert result == [{"role": "user", "content": "Hello"}]

    def test_system_prompt_prepended(self):
        messages = [{"role": "user", "content": "Hi"}]
        result = _messages_to_openai(messages, system="You are helpful.")
        assert result[0] == {"role": "system", "content": "You are helpful."}
        assert result[1]["role"] == "user"

    def test_assistant_text_block(self):
        messages = [
            {"role": "assistant", "content": [{"type": "text", "text": "Hello!"}]}
        ]
        result = _messages_to_openai(messages, system="")
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Hello!"

    def test_assistant_tool_use_block(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu_1",
                        "name": "generate_script",
                        "input": {"feature": "leaderboard"},
                    }
                ],
            }
        ]
        result = _messages_to_openai(messages, system="")
        assert result[0]["role"] == "assistant"
        assert "tool_calls" in result[0]
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "tu_1"
        assert tc["function"]["name"] == "generate_script"
        parsed = json.loads(tc["function"]["arguments"])
        assert parsed["feature"] == "leaderboard"

    def test_user_tool_result_becomes_tool_message(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tu_1",
                        "content": "Script generated successfully.",
                    }
                ],
            }
        ]
        result = _messages_to_openai(messages, system="")
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "tu_1"
        assert result[0]["content"] == "Script generated successfully."

    def test_thinking_blocks_skipped(self):
        messages = [
            {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Let me think…"},
                    {"type": "text", "text": "Answer."},
                ],
            }
        ]
        result = _messages_to_openai(messages, system="")
        assert result[0]["content"] == "Answer."
        assert "thinking" not in str(result)

    def test_empty_messages(self):
        result = _messages_to_openai([], system="")
        assert result == []


# ── _tools_to_openai ──────────────────────────────────────────────────────────

class TestToolsToOpenAI:
    def test_basic_conversion(self):
        tools = [
            {
                "name": "generate_script",
                "description": "Generate a Luau script",
                "input_schema": {
                    "type": "object",
                    "properties": {"feature": {"type": "string"}},
                },
            }
        ]
        result = _tools_to_openai(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        fn = result[0]["function"]
        assert fn["name"] == "generate_script"
        assert fn["description"] == "Generate a Luau script"
        assert fn["parameters"]["properties"]["feature"]["type"] == "string"

    def test_empty_tools(self):
        assert _tools_to_openai([]) == []

    def test_missing_description_defaults_to_empty(self):
        tools = [{"name": "foo", "input_schema": {"type": "object", "properties": {}}}]
        result = _tools_to_openai(tools)
        assert result[0]["function"]["description"] == ""


# ── list_providers ────────────────────────────────────────────────────────────

class TestListProviders:
    def test_returns_list_of_dicts(self):
        providers = list_providers()
        assert isinstance(providers, list)
        assert all(isinstance(p, dict) for p in providers)

    def test_expected_providers_present(self):
        names = {p["provider"] for p in list_providers()}
        for expected in ("anthropic", "openai", "groq", "gemini", "mistral", "ollama"):
            assert expected in names

    def test_ollama_always_configured(self):
        """Ollama has no API key requirement so it's always 'configured'."""
        providers = {p["provider"]: p for p in list_providers()}
        assert providers["ollama"]["configured"] is True

    def test_env_var_controls_configured(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}, clear=False):
            providers = {p["provider"]: p for p in list_providers()}
            assert providers["anthropic"]["configured"] is False

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            providers = {p["provider"]: p for p in list_providers()}
            assert providers["anthropic"]["configured"] is True

    def test_each_entry_has_required_keys(self):
        for p in list_providers():
            assert "provider" in p
            assert "models" in p
            assert "configured" in p
