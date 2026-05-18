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


class AIConfigurationError(RuntimeError):
    """Raised when no production-safe AI provider is configured."""


class AIProviderResponseError(RuntimeError):
    """Raised when a configured AI provider returns unusable structured output."""


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
class MitreTechnique:
    """One MITRE ATT&CK reference extracted from the AI analysis.

    `id` follows the ATT&CK convention (e.g. "T1110.001"). `name` is the
    human-readable technique label. `url` always points at the canonical
    attack.mitre.org page so the cockpit can render a clickable anchor
    without having to derive the URL itself.
    """

    id: str
    name: str
    url: str


@dataclass(frozen=True)
class IncidentAnalysis:
    """Structured AI output describing an incident.

    The cockpit treats this as a draft — nothing persists or executes until a
    human approves it. `risk_score` is 0-100, where 100 == immediate response
    required. The CVSS fields back the risk score with a documented vector
    so an analyst can audit *why* the model picked that severity.
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
    cvss_score: float | None = None
    cvss_severity: str = ""  # "None"|"Low"|"Medium"|"High"|"Critical"
    cvss_vector: str = ""  # full v3.1 vector string, e.g. CVSS:3.1/AV:N/AC:L/...
    cvss_justification: str = ""
    mitre_techniques: list[MitreTechnique] = field(default_factory=list)
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
        cvss_score, cvss_severity, cvss_vector, cvss_justification = (
            self._scripted_cvss(context, severity_normalized, english=english)
        )
        mitre = self._scripted_mitre(context)
        references = [
            "https://attack.mitre.org/tactics/TA0043/",
            "https://attack.mitre.org/tactics/TA0001/",
            "https://docs.fortinet.com/document/fortigate/latest",
            "https://nvd.nist.gov/vuln/search/",
            "https://www.cisa.gov/news-events/cybersecurity-advisories",
        ]
        references.extend(t.url for t in mitre if t.url not in references)
        return IncidentAnalysis(
            incident_id=context.incident_id,
            headline=headline,
            summary=summary,
            risk_score=severity_score,
            suggested_triage=suggested_triage,
            suggested_ticket_status="investigating",
            indicators_of_compromise=iocs,
            next_steps=next_steps,
            references=references[:6],
            cvss_score=cvss_score,
            cvss_severity=cvss_severity,
            cvss_vector=cvss_vector,
            cvss_justification=cvss_justification,
            mitre_techniques=mitre,
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

    def _scripted_cvss(
        self,
        context: IncidentContext,
        severity_normalized: str,
        *,
        english: bool,
    ) -> tuple[float, str, str, str]:
        # Deterministic CVSS v3.1 base mapped from incident severity. Real
        # provider re-computes; scripted just keeps the cockpit demo coherent.
        mapping = {
            "critical": (
                9.5,
                "Critical",
                "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
            ),
            "high": (
                8.1,
                "High",
                "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
            ),
            "medium": (
                5.5,
                "Medium",
                "CVSS:3.1/AV:N/AC:L/PR:L/UI:R/S:U/C:L/I:L/A:L",
            ),
            "low": (
                3.1,
                "Low",
                "CVSS:3.1/AV:N/AC:H/PR:L/UI:R/S:U/C:L/I:N/A:N",
            ),
        }
        score, label, vector = mapping.get(severity_normalized, mapping["medium"])
        rule = context.rule_id or "rule"
        if english:
            justification = (
                f"AV:N (Network) — the event originated remotely; AC:L (Low) — no "
                f"specialised conditions seen; PR & UI reflect the {severity_normalized} "
                f"profile of {rule}. CIA values pivot from CIA-high for critical "
                f"denies to CIA-low for low-confidence noise so the score lines up "
                f"with the rule's published severity."
            )
        else:
            justification = (
                f"AV:N (Network) — evento originado remotamente; AC:L (Low) — sem "
                f"condições especiais observadas; PR e UI refletem o perfil "
                f"{severity_normalized} da regra {rule}. Os valores CIA variam de "
                f"CIA-high para denies críticos a CIA-low para ruído de baixa "
                f"confiança, mantendo o score coerente com a severidade publicada."
            )
        return score, label, vector, justification

    def _scripted_mitre(self, context: IncidentContext) -> list[MitreTechnique]:
        # Pick techniques based on the rule id / event type. Keeps the demo
        # references real (MITRE pages actually exist) without calling out.
        event_blob = " ".join(
            filter(
                None,
                [
                    (context.rule_id or "").lower(),
                    (context.title or "").lower(),
                    (context.summary or "").lower(),
                ],
            )
        )
        techniques: list[MitreTechnique] = []
        if any(token in event_blob for token in ("port_scan", "scan", "denied_traffic")):
            techniques.append(
                MitreTechnique(
                    id="T1046",
                    name="Network Service Discovery",
                    url="https://attack.mitre.org/techniques/T1046/",
                )
            )
        if any(token in event_blob for token in ("brute", "failed_login", "auth")):
            techniques.append(
                MitreTechnique(
                    id="T1110.001",
                    name="Brute Force: Password Guessing",
                    url="https://attack.mitre.org/techniques/T1110/001/",
                )
            )
        if any(token in event_blob for token in ("c2", "beacon", "suspicious_connection")):
            techniques.append(
                MitreTechnique(
                    id="T1071.001",
                    name="Application Layer Protocol: Web Protocols",
                    url="https://attack.mitre.org/techniques/T1071/001/",
                )
            )
        if not techniques:
            techniques.append(
                MitreTechnique(
                    id="T1078",
                    name="Valid Accounts",
                    url="https://attack.mitre.org/techniques/T1078/",
                )
            )
        return techniques[:3]

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
# Gemini native adapter — generateContent endpoint with X-goog-api-key
# ---------------------------------------------------------------------------


class GeminiAIProvider:
    """Native Google AI Studio adapter.

    Talks to `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
    using the `X-goog-api-key` header. Avoids the `/v1beta/openai` shim, which
    drops fields and silently turns missing keys into 404s.
    """

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://generativelanguage.googleapis.com",
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
        raw = self._generate(prompt, response_mime_type="application/json")
        return _parse_analysis(raw, context=context, locale=locale)

    def suggest_containment(
        self,
        context: IncidentContext,
        *,
        locale: str = "pt-BR",
    ) -> ContainmentSuggestion:
        prompt = _build_containment_prompt(context, locale=locale)
        raw = self._generate(prompt, response_mime_type="application/json")
        return _parse_containment(raw, context=context, locale=locale)

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        locale: str = "pt-BR",
    ) -> str:
        system_text = _chat_system_prompt(locale)
        contents: list[dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = str(message.get("content") or "")
            if not content:
                continue
            if role == "system":
                # Gemini accepts a system_instruction parameter; we fold legacy
                # system turns into it rather than the contents list.
                continue
            contents.append(
                {
                    "role": "model" if role == "assistant" else "user",
                    "parts": [{"text": content}],
                }
            )
        return self._generate_contents(
            contents=contents,
            system_instruction=system_text,
            response_mime_type=None,
        )

    def _generate(self, prompt: str, *, response_mime_type: str | None = None) -> str:
        return self._generate_contents(
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
            system_instruction=None,
            response_mime_type=response_mime_type,
        )

    def _generate_contents(
        self,
        *,
        contents: list[dict[str, Any]],
        system_instruction: str | None,
        response_mime_type: str | None,
    ) -> str:
        body: dict[str, Any] = {"contents": contents}
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}
        generation_config: dict[str, Any] = {"maxOutputTokens": 4096}
        if response_mime_type:
            generation_config["responseMimeType"] = response_mime_type
        body["generationConfig"] = generation_config

        response = self.http_client.post(
            f"{self.base_url}/v1beta/models/{self.model}:generateContent",
            headers={
                "X-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            },
            json=body,
        )
        if response.status_code >= 400:
            raise _RemoteAIError(
                f"Gemini API returned HTTP {response.status_code}: {response.text[:200]}"
            )
        payload = response.json()
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        parts = (candidates[0].get("content") or {}).get("parts") or []
        return "".join(part.get("text", "") for part in parts if isinstance(part, dict))


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
        # max_tokens=4096 covers Gemini 2.5 reasoning models (which spend a
        # chunk of the output budget on hidden thinking before the visible
        # JSON) and still fits well under every documented free-tier ceiling.
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 4096,
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
- risk_score: integer 0-100 (higher = more urgent). MUST align with cvss_score
  (multiply by 10 and round).
- cvss_score: number 0.0-10.0 using the CVSS v3.1 base metric (no environmental
  or temporal adjustments).
- cvss_severity: one of None, Low, Medium, High, Critical — following the
  official CVSS v3.1 thresholds (0.0=None, 0.1-3.9=Low, 4.0-6.9=Medium,
  7.0-8.9=High, 9.0-10.0=Critical).
- cvss_vector: full CVSS v3.1 base vector string starting with
  "CVSS:3.1/" (e.g. "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H").
- cvss_justification: 2-4 sentences explaining each metric in the vector
  (Attack Vector, Attack Complexity, Privileges Required, User Interaction,
  Scope, Confidentiality, Integrity, Availability) and why each value
  was chosen for THIS incident.
- suggested_triage: one of T1, T2, T3
- suggested_ticket_status: one of new, investigating, contained, closed
- indicators_of_compromise: array of strings (IPs, hostnames, usernames)
- next_steps: array of 3-5 concrete next actions for the analyst
- mitre_techniques: array of 1-4 objects, each with `id` (ATT&CK technique
  id like "T1110.001"), `name` (technique name as published by MITRE,
  e.g. "Brute Force: Password Guessing") and `url` (the canonical
  https://attack.mitre.org/techniques/<id>/ link, with sub-techniques
  written as Txxxx/yyy in the URL path). Only include techniques that
  are actually relevant to the incident.
- references: array of 3-6 authoritative URLs that an analyst can open
  to learn more. Include at minimum one MITRE ATT&CK tactic page
  (https://attack.mitre.org/tactics/TAxxxx/), one MITRE ATT&CK technique
  page, and one of: NIST CVE listing (https://nvd.nist.gov/vuln/detail/CVE-...),
  CISA advisory (https://www.cisa.gov/news-events/cybersecurity-advisories/...),
  Fortinet PSIRT (https://www.fortiguard.com/psirt/...) or Fortinet docs
  (https://docs.fortinet.com/...). Never invent URLs — only use slugs you
  are confident exist.
Write every string field in ENGLISH.
Do not include any keys other than the ones listed above.
"""


_ANALYZE_INSTRUCTIONS_PT = """Você é um assistente de analista SOC. Dada uma
descrição de incidente, responda com um objeto JSON estrito contendo os
seguintes campos e mais nada:
- headline: resumo curto de uma frase
- summary: 2-3 frases explicando o que aconteceu e por que importa
- risk_score: inteiro de 0 a 100 (quanto maior, mais urgente). DEVE ser
  coerente com cvss_score (multiplique por 10 e arredonde).
- cvss_score: número de 0.0 a 10.0 usando a métrica base CVSS v3.1 (sem
  ajustes ambientais ou temporais).
- cvss_severity: um de None, Low, Medium, High, Critical — seguindo os
  limites oficiais do CVSS v3.1 (0.0=None, 0.1-3.9=Low, 4.0-6.9=Medium,
  7.0-8.9=High, 9.0-10.0=Critical).
- cvss_vector: string completa do vetor base CVSS v3.1, começando com
  "CVSS:3.1/" (ex.: "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H").
- cvss_justification: 2-4 frases explicando cada métrica do vetor
  (Attack Vector, Attack Complexity, Privileges Required, User
  Interaction, Scope, Confidentiality, Integrity, Availability) e por
  que cada valor foi escolhido para ESTE incidente específico.
- suggested_triage: um de T1, T2, T3
- suggested_ticket_status: um de new, investigating, contained, closed
- indicators_of_compromise: array de strings (IPs, hostnames, usuários)
- next_steps: array com 3-5 ações concretas para o analista
- mitre_techniques: array com 1-4 objetos; cada objeto tem `id` (id de
  técnica ATT&CK como "T1110.001"), `name` (nome publicado pela MITRE,
  ex.: "Brute Force: Password Guessing") e `url` (link canônico
  https://attack.mitre.org/techniques/<id>/, com sub-técnicas escritas
  como Txxxx/yyy no path da URL). Inclua apenas técnicas que sejam
  realmente relevantes ao incidente.
- references: array com 3-6 URLs autoritativas que o analista pode
  abrir para aprofundar. Inclua no mínimo uma página de tática MITRE
  ATT&CK (https://attack.mitre.org/tactics/TAxxxx/), uma página de
  técnica MITRE ATT&CK, e uma de: listagem CVE do NIST
  (https://nvd.nist.gov/vuln/detail/CVE-...), advisory CISA
  (https://www.cisa.gov/news-events/cybersecurity-advisories/...),
  Fortinet PSIRT (https://www.fortiguard.com/psirt/...) ou docs
  Fortinet (https://docs.fortinet.com/...). Nunca invente URLs — use
  apenas slugs que você tem certeza que existem.
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
        raise AIProviderResponseError("AI analyze response was not a JSON object")
    cvss_score = _clamp_float(data.get("cvss_score"), low=0.0, high=10.0)
    cvss_vector = str(data.get("cvss_vector") or "").strip()[:200]
    if cvss_vector and not cvss_vector.upper().startswith("CVSS:3"):
        # Reject malformed vectors silently rather than ship them to the
        # cockpit pretending they were CVSS v3.1.
        cvss_vector = ""
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
        cvss_score=cvss_score,
        cvss_severity=_choice(
            data.get("cvss_severity"),
            {"None", "Low", "Medium", "High", "Critical"},
            default=_cvss_severity_for(cvss_score) if cvss_score is not None else "",
        ),
        cvss_vector=cvss_vector,
        cvss_justification=str(data.get("cvss_justification") or "")[:1500],
        mitre_techniques=_parse_mitre_techniques(data.get("mitre_techniques")),
        raw_output=raw,
    )


def _cvss_severity_for(score: float) -> str:
    if score <= 0.0:
        return "None"
    if score < 4.0:
        return "Low"
    if score < 7.0:
        return "Medium"
    if score < 9.0:
        return "High"
    return "Critical"


_MITRE_TECHNIQUE_PATTERN = re.compile(r"^T\d{4}(?:\.\d{3})?$")


def _parse_mitre_techniques(raw: Any) -> list[MitreTechnique]:
    if not isinstance(raw, list):
        return []
    out: list[MitreTechnique] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        technique_id = str(entry.get("id") or "").strip().upper()
        if not _MITRE_TECHNIQUE_PATTERN.match(technique_id):
            continue
        if technique_id in seen:
            continue
        seen.add(technique_id)
        url = str(entry.get("url") or "").strip()
        if not url.startswith("https://attack.mitre.org/"):
            slug = technique_id.replace(".", "/")
            url = f"https://attack.mitre.org/techniques/{slug}/"
        name = str(entry.get("name") or technique_id)[:160]
        out.append(MitreTechnique(id=technique_id, name=name, url=url[:300]))
        if len(out) >= 6:
            break
    return out


def _clamp_float(value: Any, *, low: float, high: float) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result < low:
        return low
    if result > high:
        return high
    return round(result, 1)


def _parse_containment(
    raw: str, *, context: IncidentContext, locale: str = "pt-BR"
) -> ContainmentSuggestion:
    data = _extract_json(raw)
    if not isinstance(data, dict):
        raise AIProviderResponseError("AI containment response was not a JSON object")
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
        raise AIProviderResponseError("AI containment response did not include any steps")
    return ContainmentSuggestion(
        incident_id=context.incident_id,
        summary=str(data.get("summary") or "")[:1000],
        steps=steps[:6],
        raw_output=raw,
    )


_FENCED_JSON_PATTERN = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```",
    flags=re.DOTALL | re.IGNORECASE,
)


def _extract_json(raw: str) -> Any:
    raw = (raw or "").strip()
    if not raw:
        return None
    # Gemini and some OpenAI-compat shims wrap JSON in ```json ... ``` fences
    # despite the response_format hint. Peel them off before parsing.
    fenced = _FENCED_JSON_PATTERN.search(raw)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
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
    provider_name = (
        (getattr(settings, "ai_provider", None) or "").lower().strip().replace("-", "_")
    )
    api_key = getattr(settings, "ai_api_key", "") or ""
    model = getattr(settings, "ai_model", "") or ""
    base_url = getattr(settings, "ai_base_url", "") or ""

    if not provider_name:
        raise AIConfigurationError(
            "AI provider is not configured. Set FORTIDASHBOARD_AI_PROVIDER to "
            "anthropic, gemini or openai-compatible and provide FORTIDASHBOARD_AI_API_KEY."
        )

    if provider_name == "scripted":
        if getattr(settings, "enable_lab_demo_tools", False):
            return ScriptedAIProvider()
        raise AIConfigurationError(
            "The scripted AI provider is lab-only. Set "
            "FORTIDASHBOARD_ENABLE_LAB_DEMO_TOOLS=true for isolated lab runs, "
            "or configure a real AI provider."
        )

    if provider_name == "anthropic":
        if not api_key:
            raise AIConfigurationError(
                "FORTIDASHBOARD_AI_API_KEY is required when FORTIDASHBOARD_AI_PROVIDER=anthropic."
            )
        return AnthropicAIProvider(
            api_key=api_key,
            model=model or "claude-3-5-haiku-latest",
            base_url=base_url or "https://api.anthropic.com",
        )
    if provider_name in {"gemini", "google", "google_ai", "google_gemini"}:
        if not api_key:
            raise AIConfigurationError(
                "FORTIDASHBOARD_AI_API_KEY is required when FORTIDASHBOARD_AI_PROVIDER=gemini."
            )
        return GeminiAIProvider(
            api_key=api_key,
            model=model or "gemini-flash-latest",
            base_url=base_url or "https://generativelanguage.googleapis.com",
        )
    if provider_name in {"openai", "openai_compat", "openai_compatible"}:
        if not api_key:
            raise AIConfigurationError(
                "FORTIDASHBOARD_AI_API_KEY is required when "
                "FORTIDASHBOARD_AI_PROVIDER is OpenAI-compatible."
            )
        return OpenAICompatibleAIProvider(
            api_key=api_key,
            model=model or "gpt-4o-mini",
            base_url=base_url or "https://api.openai.com/v1",
        )
    raise AIConfigurationError(
        f"Unsupported AI provider '{provider_name}'. Configure anthropic, "
        "gemini or openai-compatible."
    )
