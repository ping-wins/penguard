"""Anthropic Messages streaming backend for the SOC agent."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.ai.agent.backends.base import BackendError, Final, TextDelta, ToolCall
from app.ai.agent.registry import AgentTool


class AnthropicBackend:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
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
        body = {
            "model": self.model,
            "max_tokens": max_output_tokens,
            "stream": True,
            "system": system_prompt,
            "messages": _anthropic_messages(history),
            "tools": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            async with self.http_client.stream(
                "POST",
                f"{self.base_url}/v1/messages",
                headers=headers,
                json=body,
            ) as response:
                if response.status_code >= 400:
                    yield _anthropic_error(response.status_code, await response.aread())
                    return

                usage_in = 0
                usage_out = 0
                stop_reason = ""
                tool_blocks: dict[int, dict[str, Any]] = {}
                tool_json: dict[int, str] = {}
                emitted_tool = False

                async for line in response.aiter_lines():
                    payload = _sse_payload(line)
                    if payload is None:
                        continue
                    usage = payload.get("usage") or {}
                    usage_in = max(usage_in, int(usage.get("input_tokens") or 0))
                    usage_out = max(usage_out, int(usage.get("output_tokens") or 0))
                    event_type = payload.get("type")

                    if event_type == "message_start":
                        message = payload.get("message") or {}
                        usage = message.get("usage") or {}
                        usage_in = max(usage_in, int(usage.get("input_tokens") or 0))
                        usage_out = max(usage_out, int(usage.get("output_tokens") or 0))
                    elif event_type == "content_block_start":
                        index = int(payload.get("index") or 0)
                        block = payload.get("content_block") or {}
                        if block.get("type") == "tool_use":
                            tool_blocks[index] = {
                                "id": str(block.get("id") or ""),
                                "name": str(block.get("name") or ""),
                                "input": (
                                    block.get("input")
                                    if isinstance(block.get("input"), dict)
                                    else {}
                                ),
                            }
                            tool_json[index] = ""
                    elif event_type == "content_block_delta":
                        index = int(payload.get("index") or 0)
                        delta = payload.get("delta") or {}
                        if delta.get("type") == "text_delta":
                            yield TextDelta(text=str(delta.get("text") or ""))
                        elif delta.get("type") == "input_json_delta":
                            tool_json[index] = tool_json.get(index, "") + str(
                                delta.get("partial_json") or ""
                            )
                    elif event_type == "content_block_stop":
                        index = int(payload.get("index") or 0)
                        block = tool_blocks.get(index)
                        if block is not None:
                            args = block["input"] or _loads_object(tool_json.get(index, ""))
                            emitted_tool = True
                            yield ToolCall(
                                call_id=block["id"],
                                tool_name=block["name"],
                                args=args,
                            )
                    elif event_type == "message_delta":
                        delta = payload.get("delta") or {}
                        stop_reason = str(delta.get("stop_reason") or stop_reason)
                        usage = payload.get("usage") or {}
                        usage_out = max(usage_out, int(usage.get("output_tokens") or 0))
                    elif event_type == "message_stop":
                        yield Final(
                            stop_reason=stop_reason or ("tool_use" if emitted_tool else "end_turn"),
                            tokens_in=usage_in,
                            tokens_out=usage_out,
                        )
                        return
        except httpx.HTTPError as exc:
            yield BackendError(
                message=f"Anthropic transport error: {exc}"[:300],
                code="transport",
                retryable=True,
            )


def _anthropic_messages(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for item in history:
        role = item.get("role")
        if role == "system":
            continue
        if role == "user":
            messages.append({"role": "user", "content": str(item.get("content") or "")})
        elif role == "assistant":
            content: list[dict[str, Any]] = []
            text = str(item.get("content") or "")
            if text:
                content.append({"type": "text", "text": text})
            for call in item.get("tool_calls") or []:
                content.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id"),
                        "name": call.get("name"),
                        "input": call.get("args") or {},
                    }
                )
            messages.append({"role": "assistant", "content": content or text})
        elif role == "tool":
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": item.get("tool_call_id"),
                            "content": json.dumps(item.get("result"), ensure_ascii=False),
                        }
                    ],
                }
            )
    return messages


def _anthropic_error(status_code: int, body: bytes) -> BackendError:
    text = body.decode("utf-8", errors="replace")[:200]
    if status_code == 429:
        return BackendError(
            message=text or "Anthropic rate limit",
            code="rate_limit",
            retryable=True,
        )
    if status_code in {401, 403}:
        return BackendError(message=text or "Anthropic auth failed", code="auth", retryable=False)
    return BackendError(
        message=text or f"Anthropic HTTP {status_code}",
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
