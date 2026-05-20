import type { Ticket, TriageContext } from '../../services/ticketsClient'

export type IncidentDrawerStep = 'summary' | 'analysis' | 'containment'

export type IncidentFacts = {
  title: string
  attackType: string
  source: string
  target: string
  observedPortCount: string
  scanWindow: string
  provider: string
  recommendedResponse: string
}

function stringValue(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
    if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  }
  return ''
}

function numberValue(...values: unknown[]): number | null {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
    if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) {
      return Number(value)
    }
  }
  return null
}

export function buildIncidentFacts(ticket: Ticket, context?: TriageContext | null): IncidentFacts {
  const attributes = ticket.attributes ?? {}
  const entities = ticket.entities ?? {}
  const detection = attributes.detection && typeof attributes.detection === 'object'
    ? attributes.detection as Record<string, unknown>
    : {}
  const destinationPorts = Array.isArray(attributes.destinationPorts)
    ? attributes.destinationPorts
    : []
  const observedPortCount = numberValue(
    attributes.uniqueDestinationPortCount,
    destinationPorts.length || undefined,
    detection.observedCount,
    attributes.count,
  )
  const scanWindowSeconds = numberValue(attributes.scanWindowSeconds)
  const recommendedResponse = context?.responseCandidates.find(candidate => (
    candidate.availableNow && candidate.type === 'fortigate'
  ))?.label ?? context?.responseCandidates.find(candidate => candidate.availableNow)?.label ?? ''

  return {
    title: ticket.title || stringValue(detection.title) || 'Incident',
    attackType: stringValue(context?.attackType, attributes.attackType, detection.matchedEventType, ticket.ruleId),
    source: stringValue(attributes.sourceIp, attributes.source_ip, attributes.srcip, entities.sourceIp, entities.source_ip, entities.srcip),
    target: stringValue(attributes.destinationIp, attributes.destination_ip, attributes.dstip, entities.destinationIp, entities.destination_ip, entities.dstip),
    observedPortCount: observedPortCount === null ? '' : String(observedPortCount),
    scanWindow: scanWindowSeconds === null ? '' : `${scanWindowSeconds}s`,
    provider: stringValue(attributes.source, ticket.origin?.kind, ticket.source),
    recommendedResponse,
  }
}

export function defaultIncidentDrawerStep(ticket: Ticket): IncidentDrawerStep {
  return ticket.ticketStatus === 'contained' ? 'containment' : 'summary'
}

export function hasDeterministicContainment(context?: TriageContext | null): boolean {
  return Boolean(
    context?.playbookTemplates?.length
      || context?.responseCandidates?.some(candidate => candidate.availableNow && candidate.requiresApproval),
  )
}

export function isFortiWebPrimary(ticket: Ticket, context?: TriageContext | null): boolean {
  const source = `${ticket.source} ${ticket.origin?.kind ?? ''} ${ticket.ruleId ?? ''} ${context?.alertFamily ?? ''} ${context?.attackType ?? ''}`.toLowerCase()
  return source.includes('fortiweb') || source.includes('waf')
}
