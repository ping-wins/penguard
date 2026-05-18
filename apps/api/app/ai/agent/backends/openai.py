"""OpenAI Chat Completions streaming backend for the SOC agent."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.agent.backends.base import BackendError, Final, TextDelta, ToolCall
from app.ai.agent.registry import AgentTool


class OpenAIBackend:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._owns_client = http_client is None
        self.http_client = http_client or httpx.AsyncClient(timeout=timeout_seconds)

    async def stream_decide(
        self,
        *,
        history: list[dict[str, Any]],
        tools: list[AgentTool],
        system_prompt: str,
        locale: str,
        max_output_tokens: int,
    ):
        del locale
        messages = _openai_messages(history, system_prompt=system_prompt)
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
                for tool in tools
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with self.http_client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=body,
            ) as response:
                if response.status_code >= 400:
                    yield _openai_error(response.status_code, await response.aread())
                    return

                tool_calls: dict[int, dict[str, str]] = {}
                tokens_in = 0
                tokens_out = 0
                stop_reason = ""

                async for line in response.aiter_lines():
                    payload = _sse_payload(line)
                    if payload is None:
                        continue
                    usage = payload.get("usage") or {}
                    tokens_in = max(tokens_in, int(usage.get("prompt_tokens") or 0))
                    tokens_out = max(tokens_out, int(usage.get("completion_tokens") or 0))

                    for choice in payload.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            yield TextDelta(text=str(delta.get("content") or ""))
                        for chunk in delta.get("tool_calls") or []:
                            index = int(chunk.get("index") or 0)
                            call = tool_calls.setdefault(
                                index,
                                {"id": "", "name": "", "arguments": ""},
                            )
                            if chunk.get("id"):
                                call["id"] += str(chunk.get("id") or "")
                            function = chunk.get("function") or {}
                            if function.get("name"):
                                call["name"] += str(function.get("name") or "")
                            if function.get("arguments"):
                                call["arguments"] += str(function.get("arguments") or "")
                        if choice.get("finish_reason"):
                            stop_reason = str(choice.get("finish_reason") or "")

                emitted_tool = False
                for index in sorted(tool_calls):
                    call = tool_calls[index]
                    if not call["name"]:
                        continue
                    emitted_tool = True
                    yield ToolCall(
                        call_id=call["id"] or f"call_{index}",
                        tool_name=call["name"],
                        args=_loads_object(call["arguments"]),
                    )
                yield Final(
                    stop_reason=_normalize_stop_reason(stop_reason, emitted_tool),
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                )
        except httpx.HTTPError as exc:
            yield BackendError(
                message=f"OpenAI transport error: {exc}"[:300],
                code="transport",
                retryable=True,
            )


def _openai_messages(
    history: list[dict[str, Any]],
    *,
    system_prompt: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for item in history:
        role = item.get("role")
        if role == "system":
            continue
        if role == "user":
            messages.append({"role": "user", "content": str(item.get("content") or "")})
        elif role == "assistant":
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": str(item.get("content") or ""),
            }
            tool_calls = []
            for call in item.get("tool_calls") or []:
                tool_calls.append(
                    {
                        "id": call.get("id"),
                        "type": "function",
                        "function": {
                            "name": call.get("name"),
                            "arguments": json.dumps(call.get("args") or {}),
                        },
                    }
                )
            if tool_calls:
                entry["tool_calls"] = tool_calls
            messages.append(entry)
        elif role == "tool":
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.get("tool_call_id"),
                    "content": json.dumps(item.get("result"), ensure_ascii=False),
                }
            )
    return messages


def _openai_error(status_code: int, body: bytes) -> BackendError:
    text = body.decode("utf-8", errors="replace")[:200]
    if status_code == 429:
        return BackendError(message=text or "OpenAI rate limit", code="rate_limit", retryable=True)
    if status_code in {401, 403}:
        return BackendError(message=text or "OpenAI auth failed", code="auth", retryable=False)
    return BackendError(
        message=text or f"OpenAI HTTP {status_code}",
        code="transport",
        retryable=500 <= status_code < 600,
    )


def _sse_payload(line: str) -> dict[str, Any] | None:
    if not line.startswith("data: "):
        return None
    data = line[len("data: ") :].strip()
    if not data or data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _loads_object(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _normalize_stop_reason(stop_reason: str, emitted_tool: bool) -> str:
    if emitted_tool:
        return "tool_use"
    if stop_reason == "length":
        return "max_tokens"
    if stop_reason == "tool_calls":
        return "tool_use"
    return "end_turn"
