"""Multi-backend LLM client abstraction for benchmarking.

Supports Anthropic (direct API) and Vertex AI (via LiteLLM) behind a common
interface. The factory function create_client() selects the right backend based
on the model_id prefix.

Usage:
    client = create_client("claude-sonnet-4-20250514")
    client = create_client("vertex_ai/gemini-2.0-flash-001", vertex_project="...", vertex_region="...")
"""

from __future__ import annotations

import ast
import json
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Normalized response from any LLM backend."""

    content: list
    stop_reason: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: int
    raw_response: Any = field(default=None, repr=False)

    @property
    def usage(self):
        """Compatibility shim: allows response.usage.input_tokens like the native Anthropic SDK."""
        return self


class BaseLLMClient(ABC):
    """Abstract base for LLM clients."""

    model_id: str

    @abstractmethod
    def create_message(
        self,
        system: str,
        messages: list,
        tools: list,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        ...


class AnthropicClient(BaseLLMClient):
    """Direct Anthropic API client (production path)."""

    def __init__(
        self,
        model_id: str = "claude-sonnet-4-20250514",
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        seed: Optional[int] = None,
    ):
        import anthropic

        resolved_key = api_key
        if not resolved_key:
            try:
                from api.agent.secret_manager import get_anthropic_api_key
                resolved_key = get_anthropic_api_key()
            except ImportError:
                pass  # Fall back to ANTHROPIC_API_KEY env var via SDK default

        self.model_id = model_id
        self.client = anthropic.Anthropic(api_key=resolved_key)
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._seed = seed

    def create_message(self, system, messages, tools, max_tokens=2048):
        t0 = time.time()
        sampling_kwargs = {k: v for k, v in {
            "temperature": self._temperature,
            "top_p": self._top_p,
            "top_k": self._top_k,
            "seed": self._seed,
        }.items() if v is not None}
        response = self.client.messages.create(
            model=self.model_id,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
            **sampling_kwargs,
        )
        latency = int((time.time() - t0) * 1000)
        return LLMResponse(
            content=response.content,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=self.model_id,
            latency_ms=latency,
            raw_response=response,
        )


class LiteLLMClient(BaseLLMClient):
    """Vertex AI client via LiteLLM (Gemini Flash, Pro, Claude on Vertex)."""

    def __init__(
        self,
        model_id: str,
        vertex_project: str = "",
        vertex_region: str = "",
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        seed: Optional[int] = None,
    ):
        import litellm

        self.model_id = model_id
        self._litellm = litellm
        self._vertex_project = vertex_project
        self._vertex_region = vertex_region
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._seed = seed

    @property
    def _is_model_garden_maas(self) -> bool:
        """Model Garden MaaS models use the OpenAI-compatible endpoint, not the publisher endpoint."""
        maas_publishers = ("/meta/", "/deepseek-ai/", "/openai/", "/zai-org/", "/mistralai/", "/qwen/", "/kimi/", "/minimax/", "/ai21/")
        return any(p in self.model_id for p in maas_publishers)

    def _get_maas_kwargs(self) -> dict:
        """Build kwargs for Model Garden MaaS models (OpenAI-compatible endpoint + ADC)."""
        import google.auth
        import google.auth.transport.requests

        creds, _ = google.auth.default()
        creds.refresh(google.auth.transport.requests.Request())

        region = self._vertex_region or "us-east5"
        project = self._vertex_project
        if region == "global":
            api_base = (
                f"https://aiplatform.googleapis.com/v1/"
                f"projects/{project}/locations/global/endpoints/openapi"
            )
        else:
            api_base = (
                f"https://{region}-aiplatform.googleapis.com/v1/"
                f"projects/{project}/locations/{region}/endpoints/openapi"
            )
        model_name = self.model_id.removeprefix("vertex_ai/")
        return {
            "model": f"openai/{model_name}",
            "api_base": api_base,
            "api_key": creds.token,
        }

    def create_message(self, system, messages, tools, max_tokens=2048):
        t0 = time.time()

        openai_tools = self._convert_tools(tools)
        openai_messages = [{"role": "system", "content": system}] + self._convert_messages(messages)

        sampling_kwargs = {k: v for k, v in {
            "temperature": self._temperature,
            "top_p": self._top_p,
            "top_k": self._top_k,
            "seed": self._seed,
        }.items() if v is not None}

        response = self._call_with_retry(
            openai_messages, openai_tools, max_tokens, sampling_kwargs,
        )

        latency = int((time.time() - t0) * 1000)
        return self._normalize_response(response, latency)

    def _call_with_retry(self, messages, tools, max_tokens, sampling_kwargs,
                         max_retries=5, base_delay=10):
        """Wrap _call_with_timeout with exponential backoff on rate-limit (429) errors."""
        for attempt in range(max_retries + 1):
            try:
                return self._call_with_timeout(messages, tools, max_tokens, sampling_kwargs)
            except Exception as exc:
                is_rate_limit = "429" in str(exc) or "RateLimitError" in type(exc).__name__
                if not is_rate_limit or attempt >= max_retries:
                    raise
                delay = base_delay * (2 ** attempt)
                logger.warning("Rate limited (attempt %d/%d), retrying in %ds: %s",
                               attempt + 1, max_retries, delay, str(exc)[:120])
                time.sleep(delay)

    def _call_with_timeout(self, messages, tools, max_tokens, sampling_kwargs, timeout_sec=300):
        """Call litellm.completion with a hard timeout (5 min).

        Uses a daemon thread so the hung HTTP call doesn't block shutdown.
        """
        import concurrent.futures
        import threading

        result_holder = [None]
        error_holder = [None]

        def _do_call():
            try:
                if self._is_model_garden_maas:
                    maas_kwargs = self._get_maas_kwargs()
                    result_holder[0] = self._litellm.completion(
                        messages=messages,
                        tools=tools if tools else None,
                        max_tokens=max_tokens,
                        timeout=timeout_sec,
                        **maas_kwargs,
                        **sampling_kwargs,
                    )
                else:
                    vertex_kwargs = {}
                    if self._vertex_project:
                        vertex_kwargs["vertex_project"] = self._vertex_project
                    if self._vertex_region:
                        vertex_kwargs["vertex_location"] = self._vertex_region
                    result_holder[0] = self._litellm.completion(
                        model=self.model_id,
                        messages=messages,
                        tools=tools if tools else None,
                        max_tokens=max_tokens,
                        timeout=timeout_sec,
                        **vertex_kwargs,
                        **sampling_kwargs,
                    )
            except Exception as exc:
                error_holder[0] = exc

        thread = threading.Thread(target=_do_call, daemon=True)
        thread.start()
        thread.join(timeout=timeout_sec)

        if thread.is_alive():
            # Thread still running — API hung. Daemon thread will die on process exit.
            raise TimeoutError(
                f"LLM API call timed out after {timeout_sec}s — "
                f"MaaS endpoint not responding for model {self.model_id}"
            )
        if error_holder[0] is not None:
            raise error_holder[0]
        return result_holder[0]

    def _convert_tools(self, anthropic_tools: list) -> list:
        """Convert Anthropic tool format to OpenAI function calling format."""
        openai_tools = []
        for tool in anthropic_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {}),
                },
            })
        return openai_tools

    def _convert_messages(self, messages: list) -> list:
        """Convert Anthropic message format to OpenAI format.

        Handles both dict blocks (from agent code) and _TextBlock/_ToolUseBlock
        objects (from _normalize_response round-trip).
        """
        converted = []
        for msg in messages:
            if isinstance(msg.get("content"), str):
                converted.append(msg)
            elif isinstance(msg.get("content"), list):
                text_parts = []
                tool_calls = []
                tool_results = []
                for block in msg["content"]:
                    btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                    if btype == "text":
                        text_parts.append(block["text"] if isinstance(block, dict) else block.text)
                    elif btype == "tool_use":
                        tool_calls.append(block)
                    elif btype == "tool_result":
                        tool_results.append(block)
                    else:
                        text_parts.append(str(block))

                if tool_results:
                    for tr in tool_results:
                        converted.append({
                            "role": "tool",
                            "tool_call_id": tr.get("tool_use_id", "") if isinstance(tr, dict) else getattr(tr, "tool_use_id", ""),
                            "content": tr.get("content", "") if isinstance(tr, dict) else getattr(tr, "content", ""),
                        })
                elif tool_calls:
                    out = {
                        "role": "assistant",
                        "content": " ".join(text_parts) if text_parts else None,
                        "tool_calls": [
                            {
                                "id": tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", ""),
                                "type": "function",
                                "function": {
                                    "name": tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", ""),
                                    "arguments": json.dumps(tc.get("input", {}) if isinstance(tc, dict) else getattr(tc, "input", {})),
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                    converted.append(out)
                else:
                    converted.append({
                        "role": msg["role"],
                        "content": " ".join(text_parts) if text_parts else "",
                    })
            else:
                converted.append(msg)
        return converted

    @staticmethod
    def _parse_python_tool_calls(text: str) -> list[dict]:
        """Parse tool calls from <|python_start|>func(k=v, ...)<|python_end|> format.

        Some models (e.g. Llama-4-Maverick) emit tool invocations as
        Python-style function calls wrapped in special tokens instead of
        structured tool_calls. This extracts them so the benchmark can
        execute the tools normally.
        """
        pattern = r"<\|python_start\|>\s*(.+?)\s*<\|python_end\|>"
        matches = re.findall(pattern, text, re.DOTALL)
        parsed = []
        for match in matches:
            # e.g. "query_erosion_stats(query_type='timeseries', municipality='X')"
            call_match = re.match(r"(\w+)\s*\((.+)\)\s*$", match.strip(), re.DOTALL)
            if not call_match:
                continue
            func_name = call_match.group(1)
            args_str = call_match.group(2)
            try:
                # Parse as a function call AST node, then extract keyword args
                tree = ast.parse(f"_f({args_str})", mode="eval")
                call_node = tree.body
                args = {kw.arg: ast.literal_eval(kw.value) for kw in call_node.keywords}
            except Exception:
                args = {}
            parsed.append({"name": func_name, "input": args})
        return parsed

    def _normalize_response(self, response, latency_ms: int) -> LLMResponse:
        """Convert LiteLLM response to normalized LLMResponse."""
        import json as _json

        choice = response.choices[0]
        content = []
        stop_reason = "end_turn"

        if choice.message.content:
            content.append(_TextBlock(text=choice.message.content))

        if choice.message.tool_calls:
            stop_reason = "tool_use"
            for tc in choice.message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    args = _json.loads(args)
                content.append(_ToolUseBlock(
                    id=tc.id,
                    name=tc.function.name,
                    input=args,
                ))
        elif choice.message.content and "<|python_start|>" in choice.message.content:
            # Fallback: parse tool calls from models that emit Python-style
            # invocations (e.g. Llama-4-Maverick) instead of structured tool_calls.
            parsed_calls = self._parse_python_tool_calls(choice.message.content)
            if parsed_calls:
                stop_reason = "tool_use"
                for pc in parsed_calls:
                    content.append(_ToolUseBlock(
                        id=f"call_{uuid.uuid4().hex[:12]}",
                        name=pc["name"],
                        input=pc["input"],
                    ))

        usage = response.usage
        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            input_tokens=usage.prompt_tokens or 0,
            output_tokens=usage.completion_tokens or 0,
            model=self.model_id,
            latency_ms=latency_ms,
            raw_response=response,
        )


class _TextBlock:
    """Mimics anthropic.types.TextBlock for normalized responses."""

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _ToolUseBlock:
    """Mimics anthropic.types.ToolUseBlock for normalized responses."""

    def __init__(self, id: str, name: str, input: dict):
        self.type = "tool_use"
        self.id = id
        self.name = name
        self.input = input


def create_client(model_id: str, **kwargs) -> BaseLLMClient:
    """Factory: pick the right client based on model_id prefix.

    Args:
        model_id: Model identifier. Prefix 'vertex_ai/' routes to LiteLLM.
        **kwargs: Passed to the client constructor (api_key, vertex_project, vertex_region).
    """
    if model_id.startswith(("vertex_ai/", "gemini/")):
        return LiteLLMClient(model_id, **kwargs)
    return AnthropicClient(model_id, **kwargs)
