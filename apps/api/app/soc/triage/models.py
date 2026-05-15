from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Confidence = Literal["low", "medium", "high"]
TriageLevel = Literal["T1", "T2", "T3"]
TicketStatus = Literal["new", "investigating", "contained", "closed"]
EvidenceType = Literal[
    "threshold",
    "entity",
    "event",
    "timeline",
    "correlation",
    "provider_state",
]
EvidenceSeverity = Literal["informational", "low", "medium", "high", "critical"]
RiskLevel = Literal["low", "medium", "high"]


class EvidenceItem(BaseModel):
    id: str
    type: EvidenceType
    label: str
    value: str | int | float | list[Any] | dict[str, Any]
    threshold: str | int | float | dict[str, Any] | None = None
    severity: EvidenceSeverity = "informational"
    source: str


class TriageEntity(BaseModel):
    id: str
    kind: str
    label: str
    value: str
    source: str


class ImpactedAsset(BaseModel):
    id: str
    kind: str
    label: str
    value: str


class MitreMapping(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tactic_id: str = Field(alias="tacticId")
    tactic_name: str = Field(alias="tacticName")
    technique_id: str = Field(alias="techniqueId")
    technique_name: str = Field(alias="techniqueName")
    subtechnique_id: str | None = Field(default=None, alias="subtechniqueId")
    subtechnique_name: str | None = Field(default=None, alias="subtechniqueName")
    confidence: Confidence
    reason: str
    evidence_ids: list[str] = Field(default_factory=list, alias="evidenceIds")


class ResponseCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    type: str
    label: str
    description: str
    risk_level: RiskLevel = Field(alias="riskLevel")
    requires_approval: bool = Field(alias="requiresApproval")
    available_now: bool = Field(alias="availableNow")
    provider_required: str | None = Field(default=None, alias="providerRequired")
    reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    mapped_mitre_technique_ids: list[str] = Field(
        default_factory=list,
        alias="mappedMitreTechniqueIds",
    )
    playbook_template_ids: list[str] = Field(default_factory=list, alias="playbookTemplateIds")


class PlaybookTemplateRecommendation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    template_id: str = Field(alias="templateId")
    label: str
    reason: str
    confidence: Confidence
    required_candidate_ids: list[str] = Field(default_factory=list, alias="requiredCandidateIds")
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = Field(alias="requiresApproval")


class MissingDataItem(BaseModel):
    id: str
    label: str
    reason: str


class TriageContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    incident_id: str = Field(alias="incidentId")
    rule_id: str | None = Field(default=None, alias="ruleId")
    alert_family: str = Field(alias="alertFamily")
    attack_type: str = Field(alias="attackType")
    severity: str
    confidence: Confidence
    recommended_triage_level: TriageLevel = Field(alias="recommendedTriageLevel")
    recommended_ticket_status: TicketStatus = Field(alias="recommendedTicketStatus")
    summary: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    entities: list[TriageEntity] = Field(default_factory=list)
    impacted_assets: list[ImpactedAsset] = Field(default_factory=list, alias="impactedAssets")
    mitre_mappings: list[MitreMapping] = Field(default_factory=list, alias="mitreMappings")
    response_candidates: list[ResponseCandidate] = Field(
        default_factory=list,
        alias="responseCandidates",
    )
    playbook_templates: list[PlaybookTemplateRecommendation] = Field(
        default_factory=list,
        alias="playbookTemplates",
    )
    missing_data: list[MissingDataItem] = Field(default_factory=list, alias="missingData")
    generated_at: str = Field(alias="generatedAt")
