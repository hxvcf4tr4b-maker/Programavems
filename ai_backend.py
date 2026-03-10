"""
ai_backend.py — Unified AI backend supporting multiple providers.

Supported providers
───────────────────
  anthropic   → Claude (claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5)
  openai      → GPT-4o, GPT-4-turbo, o1, o3-mini  (needs OPENAI_API_KEY)
  groq        → llama-3.3-70b, mixtral-8x7b        (needs GROQ_API_KEY)
  openrouter  → any model proxied by openrouter.ai  (needs OPENROUTER_API_KEY)
  ollama      → any local Ollama model (no key needed, Ollama must be running)
  gemini      → Gemini 2.0 Flash, 1.5 Pro           (needs GOOGLE_API_KEY)
  mistral     → Mistral Large, Codestral            (needs MISTRAL_API_KEY)

Specifying a model
──────────────────
  Pass  "provider:model_id"  e.g.  "openai:gpt-4o"  or  "ollama:llama3"
  Omit the provider to use the default: "claude-opus-4-6" → Anthropic.

All backends emit the same StreamEvent types so main.py stays provider-agnostic.
Messages are passed in Anthropic format; conversion is handled internally.
"""

from __future__ import annotations

import json
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator

# ─── Stream event types ───────────────────────────────────────────────────────


@dataclass
class TextDeltaEvent:
    text: str


@dataclass
class ThinkingDeltaEvent:
    text: str


@dataclass
class ToolStartEvent:
    tool_id: str
    tool_name: str


@dataclass
class ToolInputDeltaEvent:
    chunk: str


@dataclass
class ToolCompleteEvent:
    tool_id: str
    tool_name: str
    tool_input: dict


@dataclass
class StreamEndEvent:
    stop_reason: str  # "end_turn" | "tool_use" | "max_tokens"


StreamEvent = (
    TextDeltaEvent
    | ThinkingDeltaEvent
    | ToolStartEvent
    | ToolInputDeltaEvent
    | ToolCompleteEvent
    | StreamEndEvent
)

# ─── Tool / message format converters ────────────────────────────────────────


def _tools_to_openai(tools: list[dict]) -> list[dict]:
    """Convert Anthropic-style tool defs to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _messages_to_openai(messages: list[dict], system: str) -> list[dict]:
    """Convert Anthropic-format messages to OpenAI format."""
    result: list[dict] = []
    if system:
        result.append({"role": "system", "content": system})

    for msg in messages:
        role = msg["role"]
        content = msg["content"]

        if isinstance(content, str):
            result.append({"role": role, "content": content})
            continue

        if not isinstance(content, list):
            continue

        if role == "assistant":
            text_parts: list[str] = []
            tool_calls: list[dict] = []
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    text_parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    tool_calls.append(
                        {
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block.get("input", {})),
                            },
                        }
                    )
                # skip "thinking" blocks
            oai: dict = {"role": "assistant"}
            joined = " ".join(text_parts).strip()
            oai["content"] = joined or None
            if tool_calls:
                oai["tool_calls"] = tool_calls
            result.append(oai)

        elif role == "user":
            tool_results: list[dict] = []
            plain_texts: list[str] = []
            for block in content:
                btype = block.get("type", "")
                if btype == "tool_result":
                    raw = block.get("content", "")
                    tool_results.append(
                        {
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": raw if isinstance(raw, str) else json.dumps(raw),
                        }
                    )
                elif btype == "text":
                    plain_texts.append(block.get("text", ""))
            for tr in tool_results:
                result.append(tr)
            if plain_texts:
                result.append({"role": "user", "content": " ".join(plain_texts)})

    return result


def _messages_to_gemini(messages: list[dict]) -> list[dict]:
    """Convert Anthropic-format messages to Gemini history format (dicts)."""
    history: list[dict] = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        content = msg["content"]
        if isinstance(content, str):
            history.append({"role": role, "parts": [{"text": content}]})
        elif isinstance(content, list):
            parts: list[dict] = []
            fn_responses: list[dict] = []
            for block in content:
                btype = block.get("type", "")
                if btype == "text":
                    parts.append({"text": block.get("text", "")})
                elif btype == "tool_use":
                    parts.append(
                        {
                            "function_call": {
                                "name": block["name"],
                                "args": block.get("input", {}),
                            }
                        }
                    )
                elif btype == "tool_result":
                    raw = block.get("content", "")
                    fn_responses.append(
                        {
                            "function_response": {
                                "name": block.get("name", "tool"),
                                "response": {"result": raw if isinstance(raw, str) else json.dumps(raw)},
                            }
                        }
                    )
            if parts:
                history.append({"role": role, "parts": parts})
            if fn_responses:
                history.append({"role": "user", "parts": fn_responses})
    return history


# ─── Base class ───────────────────────────────────────────────────────────────


class AIBackend(ABC):
    """Abstract base for all AI providers."""

    def __init__(self, model: str) -> None:
        self.model = model
        self._last_content: list = []  # Anthropic-format content blocks

    @property
    @abstractmethod
    def provider(self) -> str: ...

    @property
    def supports_tools(self) -> bool:
        return True

    @abstractmethod
    def stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> Iterator[StreamEvent]: ...

    def last_response_for_history(self) -> list:
        """Return the last streamed response as Anthropic-format content blocks."""
        return self._last_content

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


# ─── Anthropic backend ────────────────────────────────────────────────────────


class AnthropicBackend(AIBackend):
    def __init__(self, model: str = "claude-opus-4-6", api_key: str | None = None) -> None:
        super().__init__(model)
        import anthropic as _anthropic

        self._client = _anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])

    @property
    def provider(self) -> str:
        return "anthropic"

    def stream(self, messages, system, tools) -> Iterator[StreamEvent]:
        import anthropic as _anthropic

        current_tool: dict | None = None
        current_json = ""

        with self._client.messages.stream(
            model=self.model,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            system=system,
            tools=tools,
            messages=messages,
        ) as s:
            for event in s:
                etype = event.type

                if etype == "content_block_start":
                    blk = event.content_block
                    if blk.type == "tool_use":
                        current_tool = {"id": blk.id, "name": blk.name}
                        current_json = ""
                        yield ToolStartEvent(tool_id=blk.id, tool_name=blk.name)

                elif etype == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta":
                        yield TextDeltaEvent(text=delta.text)
                    elif delta.type == "thinking_delta":
                        yield ThinkingDeltaEvent(text=delta.thinking)
                    elif delta.type == "input_json_delta":
                        current_json += delta.partial_json
                        yield ToolInputDeltaEvent(chunk=delta.partial_json)

                elif etype == "content_block_stop":
                    if current_tool and current_json:
                        try:
                            inp = json.loads(current_json)
                        except json.JSONDecodeError:
                            inp = {}
                        yield ToolCompleteEvent(
                            tool_id=current_tool["id"],
                            tool_name=current_tool["name"],
                            tool_input=inp,
                        )
                        current_tool = None
                        current_json = ""

                elif etype == "message_delta":
                    reason = getattr(event.delta, "stop_reason", "end_turn") or "end_turn"
                    yield StreamEndEvent(stop_reason=reason)

            self._last_content = list(s.get_final_message().content)


# ─── OpenAI-compatible backend ────────────────────────────────────────────────


class OpenAICompatibleBackend(AIBackend):
    """
    Covers: OpenAI, Groq, OpenRouter, Mistral, Ollama and any OpenAI-compatible API.
    """

    PROVIDER_BASES = {
        "groq": "https://api.groq.com/openai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "mistral": "https://api.mistral.ai/v1",
        "ollama": "http://localhost:11434/v1",
        "together": "https://api.together.xyz/v1",
        "fireworks": "https://api.fireworks.ai/inference/v1",
        "perplexity": "https://api.perplexity.ai",
        "deepinfra": "https://api.deepinfra.com/v1/openai",
    }
    PROVIDER_ENV = {
        "openai": "OPENAI_API_KEY",
        "groq": "GROQ_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "mistral": "MISTRAL_API_KEY",
        "together": "TOGETHER_API_KEY",
        "fireworks": "FIREWORKS_API_KEY",
        "perplexity": "PERPLEXITY_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY",
        "ollama": None,  # no key required
    }

    def __init__(
        self,
        model: str,
        provider: str = "openai",
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        super().__init__(model)
        self._provider = provider
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("pip install openai") from e

        key_env = self.PROVIDER_ENV.get(provider, "OPENAI_API_KEY")
        key = api_key or (os.environ.get(key_env) if key_env else "ollama")
        url = base_url or self.PROVIDER_BASES.get(provider)
        kwargs: dict = {"api_key": key or "no-key"}
        if url:
            kwargs["base_url"] = url
        self._client = OpenAI(**kwargs)

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def supports_tools(self) -> bool:
        # Ollama only supports tools on some models; we attempt it anyway
        return True

    def stream(self, messages, system, tools) -> Iterator[StreamEvent]:
        oai_messages = _messages_to_openai(messages, system)
        oai_tools = _tools_to_openai(tools) if tools else None

        kwargs: dict = {
            "model": self.model,
            "messages": oai_messages,
            "stream": True,
            "max_tokens": 8192,
        }
        if oai_tools:
            kwargs["tools"] = oai_tools
            kwargs["tool_choice"] = "auto"

        # Accumulated content for history
        acc_text = ""
        acc_tools: dict[int, dict] = {}   # index → {id, name, arguments}
        announced: set[int] = set()

        try:
            stream = self._client.chat.completions.create(**kwargs)
        except Exception as exc:
            yield TextDeltaEvent(text=f"[Backend error: {exc}]")
            yield StreamEndEvent(stop_reason="end_turn")
            return

        finish_reason = "stop"
        for chunk in stream:
            choice = chunk.choices[0]
            delta = choice.delta
            if choice.finish_reason:
                finish_reason = choice.finish_reason

            if delta.content:
                acc_text += delta.content
                yield TextDeltaEvent(text=delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in acc_tools:
                        acc_tools[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        acc_tools[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            acc_tools[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            acc_tools[idx]["arguments"] += tc.function.arguments
                            if idx not in announced:
                                announced.add(idx)
                                yield ToolStartEvent(
                                    tool_id=acc_tools[idx]["id"],
                                    tool_name=acc_tools[idx]["name"],
                                )
                            yield ToolInputDeltaEvent(chunk=tc.function.arguments)

        # Emit tool complete events
        for idx, tc in acc_tools.items():
            try:
                inp = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                inp = {}
            yield ToolCompleteEvent(
                tool_id=tc["id"] or str(uuid.uuid4()),
                tool_name=tc["name"],
                tool_input=inp,
            )

        stop = "tool_use" if finish_reason == "tool_calls" else "end_turn"
        yield StreamEndEvent(stop_reason=stop)

        # Build Anthropic-format content for history
        content: list = []
        if acc_text:
            content.append({"type": "text", "text": acc_text})
        for tc in acc_tools.values():
            try:
                inp = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                inp = {}
            content.append(
                {
                    "type": "tool_use",
                    "id": tc["id"] or str(uuid.uuid4()),
                    "name": tc["name"],
                    "input": inp,
                }
            )
        self._last_content = content


# ─── Gemini backend ───────────────────────────────────────────────────────────


class GeminiBackend(AIBackend):
    def __init__(self, model: str = "gemini-2.0-flash-exp", api_key: str | None = None) -> None:
        super().__init__(model)
        try:
            import google.generativeai as genai
        except ImportError as e:
            raise ImportError("pip install google-generativeai") from e
        key = api_key or os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY", "")
        genai.configure(api_key=key)
        self._genai = genai

    @property
    def provider(self) -> str:
        return "gemini"

    def stream(self, messages, system, tools) -> Iterator[StreamEvent]:
        genai = self._genai

        # Build Gemini tool declarations
        gemini_tools = None
        if tools:
            fns = []
            for t in tools:
                schema = t.get("input_schema", {})
                # Gemini requires properties to be FunctionDeclaration-compatible
                fns.append(
                    genai.protos.FunctionDeclaration(
                        name=t["name"],
                        description=t.get("description", ""),
                        parameters=genai.protos.Schema(
                            type=genai.protos.Type.OBJECT,
                            properties={
                                k: genai.protos.Schema(type=genai.protos.Type.STRING)
                                for k in schema.get("properties", {})
                            },
                            required=schema.get("required", []),
                        ),
                    )
                )
            gemini_tools = [genai.protos.Tool(function_declarations=fns)]

        history = _messages_to_gemini(messages[:-1]) if len(messages) > 1 else []
        last_msg = messages[-1]["content"] if messages else ""
        if isinstance(last_msg, list):
            last_msg = " ".join(b.get("text", "") for b in last_msg if b.get("type") == "text")

        try:
            model_obj = genai.GenerativeModel(
                model_name=self.model,
                tools=gemini_tools,
                system_instruction=system,
            )
            chat = model_obj.start_chat(history=history)
            response = chat.send_message(last_msg, stream=True)
        except Exception as exc:
            yield TextDeltaEvent(text=f"[Gemini error: {exc}]")
            yield StreamEndEvent(stop_reason="end_turn")
            return

        acc_text = ""
        tool_events: list[ToolCompleteEvent] = []

        for chunk in response:
            for part in chunk.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    acc_text += part.text
                    yield TextDeltaEvent(text=part.text)
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_id = f"gemini_{fc.name}_{len(tool_events)}"
                    inp = dict(fc.args) if fc.args else {}
                    yield ToolStartEvent(tool_id=tool_id, tool_name=fc.name)
                    yield ToolCompleteEvent(tool_id=tool_id, tool_name=fc.name, tool_input=inp)
                    tool_events.append(
                        ToolCompleteEvent(tool_id=tool_id, tool_name=fc.name, tool_input=inp)
                    )

        stop = "tool_use" if tool_events else "end_turn"
        yield StreamEndEvent(stop_reason=stop)

        # Build history content
        content: list = []
        if acc_text:
            content.append({"type": "text", "text": acc_text})
        for te in tool_events:
            content.append(
                {"type": "tool_use", "id": te.tool_id, "name": te.tool_name, "input": te.tool_input}
            )
        self._last_content = content


# ─── Factory ──────────────────────────────────────────────────────────────────

_PROVIDER_ALIASES = {
    # short aliases users might type
    "claude": "anthropic",
    "gpt": "openai",
    "gpt4": "openai",
    "chatgpt": "openai",
    "local": "ollama",
    "google": "gemini",
    "flash": "gemini",
}

_DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-6",
    "openai": "gpt-4o",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3",
    "openrouter": "openai/gpt-4o",
    "gemini": "gemini-2.0-flash-exp",
    "mistral": "mistral-large-latest",
    "together": "mistralai/Mixtral-8x7B-Instruct-v0.1",
    "fireworks": "accounts/fireworks/models/firefunction-v2",
    "perplexity": "llama-3.1-sonar-large-128k-online",
    "deepinfra": "meta-llama/Meta-Llama-3.1-70B-Instruct",
}

_OPENAI_COMPATIBLE = {
    "groq", "openrouter", "mistral", "ollama", "together",
    "fireworks", "perplexity", "deepinfra",
}


def create_backend(spec: str, api_key: str | None = None) -> AIBackend:
    """
    Create a backend from a spec string like "anthropic:claude-opus-4-6"
    or just a model name like "claude-opus-4-6" (auto-detects anthropic).
    """
    if ":" in spec:
        provider, model = spec.split(":", 1)
    else:
        # Auto-detect provider from model name
        s = spec.lower()
        if "claude" in s:
            provider, model = "anthropic", spec
        elif any(x in s for x in ("gpt", "o1", "o3", "o4")):
            provider, model = "openai", spec
        elif "gemini" in s or "flash" in s:
            provider, model = "gemini", spec
        elif "llama" in s or "mixtral" in s or "mistral" in s:
            # Could be groq or ollama — prefer groq if key set
            if os.environ.get("GROQ_API_KEY"):
                provider, model = "groq", spec
            else:
                provider, model = "ollama", spec
        else:
            provider, model = "anthropic", spec

    provider = _PROVIDER_ALIASES.get(provider.lower(), provider.lower())
    if not model:
        model = _DEFAULT_MODELS.get(provider, "")

    if provider == "anthropic":
        return AnthropicBackend(model=model, api_key=api_key)
    elif provider == "gemini":
        return GeminiBackend(model=model, api_key=api_key)
    elif provider in _OPENAI_COMPATIBLE or provider == "openai":
        return OpenAICompatibleBackend(model=model, provider=provider, api_key=api_key)
    else:
        # Try as OpenAI-compatible with the given provider name
        return OpenAICompatibleBackend(model=model, provider=provider, api_key=api_key)


def list_providers() -> list[dict]:
    """Return info about all providers and whether they appear configured."""
    checks = [
        ("anthropic", "ANTHROPIC_API_KEY", "claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5"),
        ("openai", "OPENAI_API_KEY", "gpt-4o, gpt-4o-mini, gpt-4-turbo, o1, o3-mini"),
        ("groq", "GROQ_API_KEY", "llama-3.3-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it"),
        ("gemini", "GOOGLE_API_KEY", "gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash"),
        ("openrouter", "OPENROUTER_API_KEY", "any model via openrouter.ai"),
        ("mistral", "MISTRAL_API_KEY", "mistral-large-latest, codestral-latest"),
        ("together", "TOGETHER_API_KEY", "Mixtral-8x7B, Llama-3.1-70B, ..."),
        ("ollama", None, "llama3, codellama, deepseek-r1, phi3 (local)"),
    ]
    result = []
    for name, env_var, models in checks:
        configured = (env_var is None) or bool(os.environ.get(env_var, ""))
        result.append(
            {"provider": name, "env_var": env_var, "models": models, "configured": configured}
        )
    return result
