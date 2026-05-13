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


ChatMessage = dict[str, str]  # {"role": "user"|"assistant"|"system", "content": str}


class AIProvider(Protocol):
    name: str

    def analyze_incident(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> IncidentAnalysis: ...

    def suggest_containment(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> ContainmentSuggestion: ...

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        locale: str = "pt-BR",
    ) -> str: ...


def _is_english(locale: str | None) -> bool:
    return (locale or "").lower().startswith("en")


def _chat_system_prompt(locale: str | None) -> str:
    if _is_english(locale):
        return (
            "You are an embedded SOC assistant inside the FortiDashboard "
            "cockpit. Answer concisely (1-3 short paragraphs) and stay on "
            "topic for incident response, FortiGate operations, detection "
            "engineering and SOC workflows. If the analyst asks about a "
            "dashboard widget, mention it by name. Never make up incident "
            "IDs, credentials, IPs or audit-trail entries — say you don't "
            "have that information instead. Do not produce shell commands "
            "that change firewall state; only describe them at a high level."
        )
    return (
        "Você é um assistente SOC embarcado na cockpit do FortiDashboard. "
        "Responda de forma concisa (1-3 parágrafos curtos), mantendo o foco "
        "em resposta a incidentes, operações de FortiGate, engenharia de "
        "detecção e workflows de SOC. Se o analista perguntar sobre um "
        "widget, cite-o pelo nome. Nunca invente IDs de incidente, "
        "credenciais, IPs ou entradas de audit trail — diga que você não "
        "tem essa informação. Não produza comandos shell que mudem o "
        "estado do firewall; apenas descreva-os em alto nível."
    )


# ---------------------------------------------------------------------------
# Scripted adapter (used in tests + offline demos)
# ---------------------------------------------------------------------------


class ScriptedAIProvider:
    name = "scripted"

    _IOC_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

    def analyze_incident(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> IncidentAnalysis:
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
        english = _is_english(locale)
        if english:
            hosts_label = ", ".join(iocs[:3]) or "no IoCs extracted"
            next_steps = [
                (
                    f"Validate the scope of `{context.title}` against the affected "
                    f"hosts ({hosts_label})."
                ),
                "Confirm the FortiGate policy that produced the deny and tighten it if needed.",
                "Open a contained ticket and link any related endpoint timelines.",
            ]
            headline = f"{context.title} — {context.severity.upper()} severity"
            summary = (
                f"Incident {context.incident_id} matched rule {context.rule_id or 'unknown'}. "
                f"Triage suggestion: {suggested_triage}. "
                f"{context.summary or 'No summary recorded yet.'}"
            )
        else:
            hosts_label = ", ".join(iocs[:3]) or "nenhum IoC extraído"
            next_steps = [
                f"Validar o escopo de `{context.title}` contra os hosts afetados ({hosts_label}).",
                "Conferir a policy do FortiGate que produziu o deny e endurecê-la se necessário.",
                "Abrir um ticket de contenção e linkar timelines de endpoint relacionados.",
            ]
            headline = f"{context.title} — severidade {context.severity.upper()}"
            summary = (
                f"Incidente {context.incident_id} disparou a regra "
                f"{context.rule_id or 'desconhecida'}. "
                f"Sugestão de triagem: {suggested_triage}. "
                f"{context.summary or 'Sem resumo registrado ainda.'}"
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

    def suggest_containment(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> ContainmentSuggestion:
        iocs = self._extract_iocs(context)
        english = _is_english(locale)
        if english:
            steps = [
                ContainmentStep(
                    title="Block attacker source IPs on the FortiGate",
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
                    title="Notify the on-call SOC channel",
                    description="Post a Slack/Teams alert with the ticket id and the AI summary.",
                    playbook_node_type="notify.slack",
                    severity="medium",
                    requires_approval=False,
                ),
                ContainmentStep(
                    title="Collect endpoint telemetry",
                    description=(
                        "Pull the last 30 minutes of process snapshots from the "
                        "affected endpoint via xdr_rico."
                    ),
                    playbook_node_type="endpoint.collect_telemetry",
                    severity="low",
                    requires_approval=False,
                ),
            ]
            summary = (
                f"Suggested 3-step containment plan for {context.incident_id}. "
                "Sensitive steps stay as drafts until an analyst approves them."
            )
        else:
            steps = [
                ContainmentStep(
                    title="Bloquear IPs de origem do atacante no FortiGate",
                    description=(
                        "Adicionar entrada temporária de deny para "
                        + (", ".join(iocs[:3]) if iocs else "os IPs de origem suspeitos")
                        + " na policy LAN-to-WAN."
                    ),
                    playbook_node_type="firewall.block_ip",
                    severity="high",
                    requires_approval=True,
                ),
                ContainmentStep(
                    title="Avisar o canal SOC on-call",
                    description="Postar alerta no Slack/Teams com o id do ticket e o resumo da IA.",
                    playbook_node_type="notify.slack",
                    severity="medium",
                    requires_approval=False,
                ),
                ContainmentStep(
                    title="Coletar telemetria do endpoint",
                    description=(
                        "Puxar os últimos 30 minutos de snapshots de processos do "
                        "endpoint afetado via xdr_rico."
                    ),
                    playbook_node_type="endpoint.collect_telemetry",
                    severity="low",
                    requires_approval=False,
                ),
            ]
            summary = (
                f"Plano de contenção sugerido em 3 etapas para {context.incident_id}. "
                "Etapas sensíveis ficam como rascunho até aprovação do analista."
            )
        return ContainmentSuggestion(
            incident_id=context.incident_id,
            summary=summary,
            steps=steps,
            raw_output="scripted",
        )

    def _extract_iocs(self, context: IncidentContext) -> list[str]:
        haystack = (
            json.dumps(context.entities)
            + " "
            + " ".join(
                item.get("message", "") for item in context.timeline if isinstance(item, dict)
            )
        )
        ips = sorted(set(self._IOC_PATTERN.findall(haystack)))
        return ips[:10]

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        locale: str = "pt-BR",
    ) -> str:
        user_message = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_message = message.get("content", "")
                break
        if _is_english(locale):
            return (
                "Scripted assistant: I cannot reach a live model in this "
                "environment. Configure FORTIDASHBOARD_AI_PROVIDER + "
                "FORTIDASHBOARD_AI_API_KEY to enable a real backend. "
                f"You asked: \"{user_message[:200]}\"."
            )
        return (
            "Assistente scripted: não consigo alcançar um modelo real neste "
            "ambiente. Configure FORTIDASHBOARD_AI_PROVIDER + "
            "FORTIDASHBOARD_AI_API_KEY para habilitar um backend de verdade. "
            f"Sua pergunta: \"{user_message[:200]}\"."
        )


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

    def analyze_incident(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> IncidentAnalysis:
        prompt = _build_analyze_prompt(context, locale=locale)
        raw = self._completion(prompt)
        return _parse_analysis(raw, context=context, locale=locale)

    def suggest_containment(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> ContainmentSuggestion:
        prompt = _build_containment_prompt(context, locale=locale)
        raw = self._completion(prompt)
        return _parse_containment(raw, context=context, locale=locale)

    def _completion(self, prompt: str) -> str:
        return self._messages_call(
            messages=[{"role": "user", "content": prompt}],
            system=None,
        )

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        locale: str = "pt-BR",
    ) -> str:
        system_prompt = _chat_system_prompt(locale)
        normalized: list[ChatMessage] = []
        for message in messages:
            role = message.get("role", "user")
            if role == "system":
                continue
            normalized.append(
                {
                    "role": "assistant" if role == "assistant" else "user",
                    "content": message.get("content", ""),
                }
            )
        if not normalized:
            return ""
        return self._messages_call(messages=normalized, system=system_prompt)

    def _messages_call(
        self,
        *,
        messages: list[ChatMessage],
        system: str | None,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": messages,
        }
        if system:
            body["system"] = system
        response = self.http_client.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
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

    def analyze_incident(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> IncidentAnalysis:
        prompt = _build_analyze_prompt(context, locale=locale)
        return _parse_analysis(self._completion(prompt), context=context, locale=locale)

    def suggest_containment(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> ContainmentSuggestion:
        prompt = _build_containment_prompt(context, locale=locale)
        return _parse_containment(self._completion(prompt), context=context, locale=locale)

    def _completion(self, prompt: str) -> str:
        return self._chat_call(
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        locale: str = "pt-BR",
    ) -> str:
        full_messages: list[ChatMessage] = [
            {"role": "system", "content": _chat_system_prompt(locale)}
        ]
        for message in messages:
            role = message.get("role", "user")
            if role not in {"user", "assistant", "system"}:
                role = "user"
            full_messages.append({"role": role, "content": message.get("content", "")})
        return self._chat_call(messages=full_messages, temperature=0.7)

    def _chat_call(
        self,
        *,
        messages: list[ChatMessage],
        response_format: dict[str, Any] | None = None,
        temperature: float = 0.2,
    ) -> str:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": temperature,
        }
        if response_format is not None:
            body["response_format"] = response_format
        response = self.http_client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
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


_ANALYZE_INSTRUCTIONS_EN = """You are a SOC analyst assistant. Given an incident
description, respond with a strict JSON object containing the following
fields and nothing else:
- headline: short single-sentence summary
- summary: 2-3 sentences explaining what happened and why it matters
- risk_score: integer 0-100 (higher = more urgent)
- suggested_triage: one of T1, T2, T3
- suggested_ticket_status: one of new, investigating, contained, closed
- indicators_of_compromise: array of strings (IPs, hostnames, usernames)
- next_steps: array of 3-5 concrete next actions for the analyst
- references: array of helpful URLs (MITRE ATT&CK technique pages,
  Fortinet docs, CVE entries, vendor advisories)
Write every string field in ENGLISH.
Do not include any keys other than the ones listed above.
"""


_ANALYZE_INSTRUCTIONS_PT = """Você é um assistente de analista SOC. Dada uma
descrição de incidente, responda com um objeto JSON estrito contendo os
seguintes campos e mais nada:
- headline: resumo curto de uma frase
- summary: 2-3 frases explicando o que aconteceu e por que importa
- risk_score: inteiro de 0 a 100 (quanto maior, mais urgente)
- suggested_triage: um de T1, T2, T3
- suggested_ticket_status: um de new, investigating, contained, closed
- indicators_of_compromise: array de strings (IPs, hostnames, usuários)
- next_steps: array com 3-5 ações concretas para o analista
- references: array de URLs úteis (páginas de técnicas MITRE ATT&CK,
  documentação Fortinet, CVEs, advisories de fornecedor)
Escreva todos os campos de texto em PORTUGUÊS DO BRASIL.
Não inclua chaves diferentes das listadas acima.
"""


_CONTAINMENT_INSTRUCTIONS_EN = """You are a SOC SOAR planner. Suggest a safe,
read-only-or-reversible containment plan for the incident. Reply with a
strict JSON object containing:
- summary: 1-2 sentence overview
- steps: array of 2-5 steps; each step has title, description,
  playbook_node_type, severity (low|medium|high), requires_approval (boolean).
Write every string field in ENGLISH.
The plan must avoid destructive operations. Sensitive steps must set
requires_approval to true.
"""


_CONTAINMENT_INSTRUCTIONS_PT = """Você é um planejador SOAR de SOC. Sugira um
plano de contenção seguro, somente leitura ou reversível, para o incidente.
Responda com um objeto JSON estrito contendo:
- summary: visão geral em 1-2 frases
- steps: array com 2-5 etapas; cada etapa tem title, description,
  playbook_node_type, severity (low|medium|high), requires_approval (boolean).
Escreva todos os campos de texto em PORTUGUÊS DO BRASIL.
O plano deve evitar operações destrutivas. Etapas sensíveis precisam ter
requires_approval=true.
"""


def _build_analyze_prompt(context: IncidentContext, *, locale: str = "pt-BR") -> str:
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
    instructions = _ANALYZE_INSTRUCTIONS_EN if _is_english(locale) else _ANALYZE_INSTRUCTIONS_PT
    header = "Incident:" if _is_english(locale) else "Incidente:"
    return instructions + "\n\n" + header + "\n" + json.dumps(body, indent=2)


def _build_containment_prompt(context: IncidentContext, *, locale: str = "pt-BR") -> str:
    body = {
        "id": context.incident_id,
        "title": context.title,
        "severity": context.severity,
        "triageLevel": context.triage_level,
        "summary": context.summary,
        "entities": context.entities,
    }
    instructions = (
        _CONTAINMENT_INSTRUCTIONS_EN if _is_english(locale) else _CONTAINMENT_INSTRUCTIONS_PT
    )
    header = "Incident:" if _is_english(locale) else "Incidente:"
    return instructions + "\n\n" + header + "\n" + json.dumps(body, indent=2)


def _parse_analysis(
    raw: str, *, context: IncidentContext, locale: str = "pt-BR"
) -> IncidentAnalysis:
    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.warning("AI analyze response was not a JSON object; falling back to scripted")
        return ScriptedAIProvider().analyze_incident(context, locale=locale)
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


def _parse_containment(
    raw: str, *, context: IncidentContext, locale: str = "pt-BR"
) -> ContainmentSuggestion:
    data = _extract_json(raw)
    if not isinstance(data, dict):
        logger.warning("AI containment response was not a JSON object; falling back to scripted")
        return ScriptedAIProvider().suggest_containment(context, locale=locale)
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
        return ScriptedAIProvider().suggest_containment(context, locale=locale)
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
