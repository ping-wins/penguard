"""Gemini generateContent backend for the SOC agent."""

from __future__ import annotations

from typing import Any

import httpx

from app.ai.agent.backends.base import BackendError, Final, TextDelta, ToolCall
from app.ai.agent.registry import AgentTool


class GeminiBackend:
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com",
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
        body: dict[str, Any] = {
            "contents": _gemini_contents(history),
            "generationConfig": {"maxOutputTokens": max_output_tokens},
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        declarations = [_function_declaration(tool) for tool in tools]
        if declarations:
            body["tools"] = [{"functionDeclarations": declarations}]

        try:
            response = await self.http_client.post(
                f"{self.base_url}/v1beta/models/{self.model}:generateContent",
                headers={
                    "X-goog-api-key": self._api_key,
                    "Content-Type": "application/json",
                },
                json=body,
            )
            if response.status_code >= 400:
                yield _gemini_error(response.status_code, response.content)
                return
            try:
                payload = response.json()
            except ValueError:
                yield BackendError(
                    message="Gemini returned an invalid JSON response",
                    code="transport",
                    retryable=True,
                )
                return

            candidates = payload.get("candidates") or []
            candidate = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
            content = candidate.get("content") if isinstance(candidate, dict) else {}
            parts = content.get("parts") if isinstance(content, dict) else []
            emitted_tool = False

            if isinstance(parts, list):
                for index, part in enumerate(parts):
                    if not isinstance(part, dict):
                        continue
                    text = part.get("text")
                    if text:
                        yield TextDelta(text=str(text))
                    function_call = part.get("functionCall")
                    if isinstance(function_call, dict):
                        name = str(function_call.get("name") or "")
                        if not name:
                            continue
                        emitted_tool = True
                        args = function_call.get("args")
                        yield ToolCall(
                            call_id=str(function_call.get("id") or f"call_{index}"),
                            tool_name=name,
                            args=args if isinstance(args, dict) else {},
                            provider_metadata=_gemini_tool_call_metadata(part),
                        )

            usage = payload.get("usageMetadata") or {}
            yield Final(
                stop_reason=_normalize_stop_reason(
                    str(candidate.get("finishReason") or ""),
                    emitted_tool,
                ),
                tokens_in=int(usage.get("promptTokenCount") or 0),
                tokens_out=int(usage.get("candidatesTokenCount") or 0),
            )
        except httpx.HTTPError as exc:
            yield BackendError(
                message=f"Gemini transport error: {exc}"[:300],
                code="transport",
                retryable=True,
            )


def _gemini_contents(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for item in history:
        role = item.get("role")
        if role == "system":
            continue
        if role == "user":
            contents.append(
                {
                    "role": "user",
                    "parts": [{"text": str(item.get("content") or "")}],
                }
            )
        elif role == "assistant":
            parts: list[dict[str, Any]] = []
            text = str(item.get("content") or "")
            if text:
                parts.append({"text": text})
            for call in item.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function_call = {
                    "name": str(call.get("name") or ""),
                    "args": call.get("args") if isinstance(call.get("args"), dict) else {},
                }
                call_id = call.get("id")
                if call_id:
                    function_call["id"] = str(call_id)
                part: dict[str, Any] = {"functionCall": function_call}
                thought_signature = _stored_thought_signature(call)
                if thought_signature:
                    part["thoughtSignature"] = thought_signature
                parts.append(part)
            if parts:
                contents.append({"role": "model", "parts": parts})
        elif role == "tool":
            response = item.get("result")
            if not isinstance(response, dict):
                response = {"result": response}
            function_response: dict[str, Any] = {
                "name": str(item.get("tool_name") or ""),
                "response": response,
            }
            call_id = item.get("tool_call_id")
            if call_id:
                function_response["id"] = str(call_id)
            contents.append(
                {
                    "role": "user",
                    "parts": [{"functionResponse": function_response}],
                }
            )
    return contents


def _function_declaration(tool: AgentTool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "parameters": _gemini_schema(tool.input_schema),
    }


def _gemini_tool_call_metadata(part: dict[str, Any]) -> dict[str, Any]:
    thought_signature = part.get("thoughtSignature") or part.get("thought_signature")
    if not thought_signature:
        return {}
    return {"gemini": {"thoughtSignature": str(thought_signature)}}


def _stored_thought_signature(call: dict[str, Any]) -> str | None:
    metadata = call.get("providerMetadata") or call.get("provider_metadata") or {}
    if not isinstance(metadata, dict):
        return None
    gemini_metadata = metadata.get("gemini")
    if isinstance(gemini_metadata, dict):
        thought_signature = gemini_metadata.get("thoughtSignature") or gemini_metadata.get(
            "thought_signature"
        )
        if thought_signature:
            return str(thought_signature)
    thought_signature = metadata.get("thoughtSignature") or metadata.get("thought_signature")
    return str(thought_signature) if thought_signature else None


def _gemini_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "OBJECT"}

    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        raw_type = next((item for item in raw_type if item != "null"), None)
    if not raw_type:
        raw_type = "object" if isinstance(schema.get("properties"), dict) else "string"

    normalized_type = str(raw_type).upper()
    out: dict[str, Any] = {"type": normalized_type}
    if schema.get("description"):
        out["description"] = str(schema["description"])
    if isinstance(schema.get("enum"), list):
        out["enum"] = [str(item) for item in schema["enum"]]
    if isinstance(schema.get("required"), list):
        out["required"] = [str(item) for item in schema["required"]]
    if normalized_type == "OBJECT":
        properties = schema.get("properties")
        if isinstance(properties, dict):
            out["properties"] = {
                str(name): _gemini_schema(value) for name, value in properties.items()
            }
    if normalized_type == "ARRAY":
        out["items"] = _gemini_schema(schema.get("items") or {"type": "string"})
    return out


def _gemini_error(status_code: int, body: bytes) -> BackendError:
    text = body.decode("utf-8", errors="replace")[:200]
    if status_code == 429:
        return BackendError(message=text or "Gemini rate limit", code="rate_limit", retryable=True)
    if status_code in {401, 403}:
        return BackendError(message=text or "Gemini auth failed", code="auth", retryable=False)
    return BackendError(
        message=text or f"Gemini HTTP {status_code}",
        code="transport",
        retryable=500 <= status_code < 600,
    )


def _normalize_stop_reason(finish_reason: str, emitted_tool: bool) -> str:
    if emitted_tool:
        return "tool_use"
    normalized = finish_reason.upper()
    if normalized in {"MAX_TOKENS", "TOKEN_LIMIT"}:
        return "max_tokens"
    if normalized in {"STOP", ""}:
        return "end_turn"
    return "stop_sequence"
