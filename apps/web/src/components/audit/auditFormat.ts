import type { AuditEvent } from '../../services/auditClient'

export type FormattedAuditEvent = {
  id: string
  title: string
  actorLabel: string
  outcomeLabel: string
  outcomeTone: 'success' | 'failed' | 'warning' | 'neutral'
  createdAtLabel: string
  ipAddressLabel: string
  userAgentLabel: string
  detailRows: Array<[string, string]>
}

const REDACTED = '[REDACTED]'
const SECRET_KEY_MARKERS = ['apikey', 'secret', 'token', 'password']

const ACTION_LABELS: Record<string, string> = {
  register: 'Registration',
  logout: 'Logout',
  'integration.fortigate.created': 'FortiGate integration created',
  'integration.fortigate.deleted': 'FortiGate integration removed',
  'integration.fortigate.health_checked': 'FortiGate health check',
  'workspace.updated': 'Workspace updated',
  'audit.events.viewed': 'Audit trail viewed',
}

function isSecretKey(key: string) {
  const normalized = key.replace(/[_-]/g, '').toLowerCase()
  return SECRET_KEY_MARKERS.some(marker => normalized.includes(marker))
}

function stringifyDetail(value: unknown): string {
  if (value === REDACTED) return REDACTED
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function collectDetailRows(
  value: unknown,
  prefix = '',
  rows: Array<[string, string]> = [],
) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    if (prefix) rows.push([prefix, stringifyDetail(value)])
    return rows
  }

  for (const [key, nestedValue] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key
    if (isSecretKey(key)) {
      rows.push([path, REDACTED])
    } else if (nestedValue && typeof nestedValue === 'object' && !Array.isArray(nestedValue)) {
      collectDetailRows(nestedValue, path, rows)
    } else {
      rows.push([path, stringifyDetail(nestedValue)])
    }
  }
  return rows
}

function actionTitle(event: AuditEvent) {
  if (event.action === 'login') {
    return event.outcome === 'success' ? 'Login succeeded' : 'Login failed'
  }
  return ACTION_LABELS[event.action] ?? event.action
}

function outcomeTone(outcome: string): FormattedAuditEvent['outcomeTone'] {
  if (outcome === 'success') return 'success'
  if (outcome === 'failed' || outcome === 'failure' || outcome.startsWith('provider_')) return 'failed'
  if (outcome === 'csrf_failed' || outcome === 'rate_limited') return 'warning'
  return 'neutral'
}

function outcomeLabel(outcome: string) {
  return outcome.replace(/_/g, ' ')
}

function createdAtLabel(createdAt: string | null) {
  if (!createdAt) return 'Time unavailable'
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return createdAt
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatAuditEvent(event: AuditEvent): FormattedAuditEvent {
  return {
    id: event.id,
    title: actionTitle(event),
    actorLabel: event.actor?.email || event.actor?.id || 'Unknown actor',
    outcomeLabel: outcomeLabel(event.outcome),
    outcomeTone: outcomeTone(event.outcome),
    createdAtLabel: createdAtLabel(event.createdAt),
    ipAddressLabel: event.ipAddress || 'IP unavailable',
    userAgentLabel: event.userAgent || 'User agent unavailable',
    detailRows: collectDetailRows(event.details),
  }
}
