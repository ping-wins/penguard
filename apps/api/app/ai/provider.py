from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IncidentContext:
    """Sanitized incident snapshot fed to the AI provider.

    Secrets are scrubbed at the route layer before this struct is built; no
    Keycloak tokens, FortiGate API keys or session ids ever land here.
    """

    incident_id: str
    title: str
    severity: str
    triage_level: str
    ticket_status: str
    summary: str
    entities: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    rule_id: str | None = None
    event_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class IncidentAnalysis:
    """Structured AI output describing an incident.

    The cockpit treats this as a draft — nothing persists or executes until a
    human approves it. `risk_score` is 0-100, where 100 == immediate response
    required.
    """

    incident_id: str
    headline: str
    summary: str
    risk_score: int
    suggested_triage: str
    suggested_ticket_status: str
    indicators_of_compromise: list[str]
    next_steps: list[str]
    references: list[str]
    raw_output: str = ""


@dataclass(frozen=True)
class ContainmentStep:
    title: str
    description: str
    playbook_node_type: str
    severity: str
    requires_approval: bool


@dataclass(frozen=True)
class ContainmentSuggestion:
    incident_id: str
    summary: str
    steps: list[ContainmentStep]
    playbook_draft_id: str | None = None
    raw_output: str = ""


class AIProvider(Protocol):
    name: str

    def analyze_incident(self, context: IncidentContext) -> IncidentAnalysis:
        ...

    def suggest_containment(self, context: IncidentContext) -> ContainmentSuggestion:
        ...


# ---------------------------------------------------------------------------
# Scripted adapter (used in tests + offline demos)
# ---------------------------------------------------------------------------


class ScriptedAIProvider:
    name = "scripted"

    _IOC_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    def analyze_incident(self, context: IncidentContext) -> IncidentAnalysis:
        severity_normalized = (context.severity or "").lower()
        severity_score = {
            "critical": 95,
            "high": 80,
            "medium": 55,
            "low": 30,
            "informational": 15,
        }.get(severity_normalized, 50)
        suggested_triage = (
            "T1"
            if severity_normalized in {"critical", "high"}
            else "T2"
            if severity_normalized == "medium"
            else "T3"
        )
        iocs = self._extract_iocs(context)
        next_steps = [
            f"Validate scope of `{context.title}` against the affected hosts ({', '.join(iocs[:3]) or 'no IoCs extracted'}).",
            "Confirm the FortiGate policy that produced the deny and tighten if needed.",
            "Open a contained ticket and link any related endpoint timelines.",
        ]
        headline = f"{context.title} — {context.severity.upper()} severity"
        summary = (
            f"Incident {context.incident_id} matched rule {context.rule_id or 'unknown'}. "
            f"Triage suggestion: {suggested_triage}. "
            f"{context.summary or 'No summary recorded yet.'}"
        )
        return IncidentAnalysis(
            incident_id=context.incident_id,
            headline=headline,
            summary=summary,
            risk_score=severity_score,
            suggested_triage=suggested_triage,
            suggested_ticket_status="investigating",
            indicators_of_compromise=iocs,
            next_steps=next_steps,
            references=[
                "https://docs.fortinet.com/document/fortigate/latest",
                "https://attack.mitre.org/tactics/TA0043/",
            ],
            raw_output="scripted",
        )

    def suggest_containment(self, context: IncidentContext) -> ContainmentSuggestion:
        iocs = self._extract_iocs(context)
        steps = [
            ContainmentStep(
                title="Block attacker source IPs at the FortiGate",
                description=(
                    "Add a temporary deny entry for "
                    + (", ".join(iocs[:3]) if iocs else "the suspected source IPs")
                    + " on the LAN-to-WAN policy."
                ),
                playbook_node_type="firewall.block_ip",
                severity="high",
                requires_approval=True,
            ),
            ContainmentStep(
                title="Notify the SOC on-call channel",
                description="Post a Slack/Teams alert with the ticket id and AI summary.",
                playbook_node_type="notify.slack",
                severity="medium",
                requires_approval=False,
            ),
            ContainmentStep(
                title="Collect endpoint telemetry",
                description="Pull the last 30 minutes of process snapshots from the affected endpoint via xdr_rico.",
                playbook_node_type="endpoint.collect_telemetry",
                severity="low",
                requires_approval=False,
            ),
        ]
        summary = (
            f"Suggested 3-step containment plan for {context.incident_id}. "
            "Sensitive steps stay in draft until an analyst approves them."
        )
        return ContainmentSuggestion(
            incident_id=context.incident_id,
            summary=summary,
            steps=steps,
            raw_output="scripted",
        )

    def _extract_iocs(self, context: IncidentContext) -> list[str]:
        haystack = json.dumps(context.entities) + " " + " ".join(
            item.get("message", "") for item in context.timeline if isinstance(item, dict)
        )
        ips = sorted(set(self._IOC_PATTERN.findall(haystack)))
        return ips[:10]


# ---------------------------------------------------------------------------
# Anthropic adapter
# ---------------------------------------------------------------------------


class _RemoteAIError(RuntimeError):
    pass


class AnthropicAIProvider:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
        timeout_seconds: float = 20.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def analyze_incident(self, context: IncidentContext) -> IncidentAnalysis:
        prompt = _build_analyze_prompt(context)
        raw = self._completion(prompt)
        return _parse_analysis(raw, context=context)

    def suggest_containment(self, context: IncidentContext) -> ContainmentSuggestion:
        prompt = _build_containment_prompt(context)
        raw = self._completion(prompt)
        return _parse_containment(raw, context=context)

    def _completion(self, prompt: str) -> str:
        response = self.http_client.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        if response.status_code >= 400:
            raise _RemoteAIError(
                f"Anthropic API returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        chunks = payload.get("content") or []
        text_chunks = [chunk.get("text", "") for chunk in chunks if chunk.get("type") == "text"]
        return "".join(text_chunks)


# ---------------------------------------------------------------------------
# OpenAI-compatible adapter (works for OpenAI, Groq, Ollama OpenAI shim, etc.)
# ---------------------------------------------------------------------------


class OpenAICompatibleAIProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)

    def analyze_incident(self, context: IncidentContext) -> IncidentAnalysis:
        prompt = _build_analyze_prompt(context)
        return _parse_analysis(self._completion(prompt), context=context)

    def suggest_containment(self, context: IncidentContext) -> ContainmentSuggestion:
        prompt = _build_containment_prompt(context)
        return _parse_containment(self._completion(prompt), context=context)

    def _completion(self, prompt: str) -> str:
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )
        if response.status_code >= 400:
            raise _RemoteAIError(
                f"OpenAI-compatible API returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            return ""
        message = choices[0].get("message") or {}
        return str(message.get("content") or "")


# ---------------------------------------------------------------------------
# Prompt + parser helpers
# ---------------------------------------------------------------------------


_ANALYZE_INSTRUCTIONS = """You are a SOC analyst assistant. Given an incident
description, respond with a strict JSON object containing the following
fields and nothing else:
- headline: short single-sentence summary
- summary: 2-3 sentences explaining what happened and why it matters
- risk_score: integer 0-100 (higher = more urgent)
- suggested_triage: one of T1, T2, T3
- suggested_ticket_status: one of new, investigating, contained, closed
- indicators_of_compromise: array of strings (IPs, hostnames, usernames)
- next_steps: array of 3-5 concrete next actions for the analyst
- references: array of helpful URLs
Do not include any keys other than the ones listed above.
"""


_CONTAINMENT_INSTRUCTIONS = """You are a SOC SOAR planner. Suggest a safe,
read-only-or-reversible containment plan for the incident. Reply with a
strict JSON object containing:
- summary: 1-2 sentence overview
- steps: array of 2-5 steps; each step has title, description,
  playbook_node_type, severity (low|medium|high), requires_approval (boolean).
The plan must avoid destructive operations. Sensitive steps must set
requires_approval to true.
"""


def _build_analyze_prompt(context: IncidentContext) -> str:
    body = {
        "id": context.incident_id,
        "title": context.title,
        "severity": context.severity,
        "triageLevel": context.triage_level,
        "ticketStatus": context.ticket_status,
        "ruleId": context.rule_id,
        "summary": context.summary,
        "entities": context.entities,
        "timeline": context.timeline,
        "eventIds": context.event_ids,
    }
    return _ANALYZE_INSTRUCTIONS + "\n\nIncident:\n" + json.dumps(body, indent=2)


def _build_containment_prompt(context: IncidentContext) -> str:
    body = {
        "id": context.incident_id,
        "title": context.title,
        "severity": context.severity,
        "triageLevel": context.triage_level,
        "summary": context.summary,
        "entities": context.entities,
    }
    return _CONTAINMENT_INSTRUCTIONS + "\n\nIncident:\n" + json.dumps(body, indent=2)


def _parse_analysis(raw: str, *, context: IncidentContext) -> IncidentAnalysis:
    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.warning("AI analyze response was not a JSON object; falling back to scripted")
        return ScriptedAIProvider().analyze_incident(context)
    return IncidentAnalysis(
        incident_id=context.incident_id,
        headline=str(data.get("headline") or context.title)[:200],
        summary=str(data.get("summary") or context.summary or "")[:2000],
        risk_score=_clamp_int(data.get("risk_score"), low=0, high=100, default=50),
        suggested_triage=_choice(data.get("suggested_triage"), {"T1", "T2", "T3"}, default="T2"),
        suggested_ticket_status=_choice(
            data.get("suggested_ticket_status"),
            {"new", "investigating", "contained", "closed"},
            default="investigating",
        ),
        indicators_of_compromise=_string_list(data.get("indicators_of_compromise")),
        next_steps=_string_list(data.get("next_steps"))[:8],
        references=_string_list(data.get("references"))[:8],
        raw_output=raw,
    )


def _parse_containment(raw: str, *, context: IncidentContext) -> ContainmentSuggestion:
    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.warning("AI containment response was not a JSON object; falling back to scripted")
        return ScriptedAIProvider().suggest_containment(context)
    raw_steps = data.get("steps") or []
    steps: list[ContainmentStep] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        steps.append(
            ContainmentStep(
                title=str(step.get("title") or "Step"),
                description=str(step.get("description") or ""),
                playbook_node_type=str(step.get("playbook_node_type") or "notify.slack"),
                severity=_choice(step.get("severity"), {"low", "medium", "high"}, default="medium"),
                requires_approval=bool(step.get("requires_approval", True)),
            )
        )
    if not steps:
        return ScriptedAIProvider().suggest_containment(context)
    return ContainmentSuggestion(
        incident_id=context.incident_id,
        summary=str(data.get("summary") or "")[:1000],
        steps=steps[:6],
        raw_output=raw,
    )


def _extract_json(raw: str) -> Any:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None


def _clamp_int(value: Any, *, low: int, high: int, default: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if result < low:
        return low
    if result > high:
        return high
    return result


def _choice(value: Any, allowed: set[str], *, default: str) -> str:
    if isinstance(value, str) and value in allowed:
        return value
    return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, (str, int, float))][:10]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache
def get_ai_provider() -> AIProvider:
    settings = get_settings()
    provider_name = (getattr(settings, "ai_provider", None) or "scripted").lower()
    api_key = getattr(settings, "ai_api_key", "") or ""
    model = getattr(settings, "ai_model", "") or ""
    base_url = getattr(settings, "ai_base_url", "") or ""

    if provider_name == "anthropic":
        if not api_key:
            logger.warning("Anthropic AI provider selected without ai_api_key; using scripted")
            return ScriptedAIProvider()
        return AnthropicAIProvider(
            api_key=api_key,
            model=model or "claude-3-5-haiku-latest",
            base_url=base_url or "https://api.anthropic.com",
        )
    if provider_name in {"openai", "openai_compat", "openai-compatible"}:
        if not api_key:
            logger.warning("OpenAI-compatible provider selected without ai_api_key; using scripted")
            return ScriptedAIProvider()
        return OpenAICompatibleAIProvider(
            api_key=api_key,
            model=model or "gpt-4o-mini",
            base_url=base_url or "https://api.openai.com/v1",
        )
    return ScriptedAIProvider()
