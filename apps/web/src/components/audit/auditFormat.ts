import type { AuditEvent } from '../../services/auditClient'
import { i18n, getLocale } from '../../i18n'

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

const ACTION_KEYS: Record<string, string> = {
  register: 'audit.actions.register',
  logout: 'audit.actions.logout',
  'integration.fortigate.created': 'audit.actions.fortigateCreated',
  'integration.fortigate.deleted': 'audit.actions.fortigateDeleted',
  'integration.fortigate.health_checked': 'audit.actions.fortigateHealthCheck',
  'integration.fortiweb.created': 'audit.actions.fortiwebCreated',
  'integration.fortiweb.deleted': 'audit.actions.fortiwebDeleted',
  'integration.fortiweb.block_reviewed': 'audit.actions.fortiwebBlockReviewed',
  'integration.fortiweb.block_applied': 'audit.actions.fortiwebBlockApplied',
  'integration.fortiweb.block_removed': 'audit.actions.fortiwebBlockRemoved',
  'workspace.updated': 'audit.actions.workspaceUpdated',
  'workspace.imported': 'audit.actions.workspaceImported',
  'workspace.exported': 'audit.actions.workspaceExported',
  'workspace.presentation.updated': 'audit.actions.workspacePresentationUpdated',
  'workspace.widget.rebound': 'audit.actions.workspaceWidgetRebound',
  'soc.incident.analyzed': 'audit.actions.socIncidentAnalyzed',
  'soc.ticket.playbook_drafted': 'audit.actions.socTicketPlaybookDrafted',
  'soc.ticket.contained': 'audit.actions.socTicketContained',
  'audit.events.viewed': 'audit.actions.auditViewed',
}

function tr(key: string): string {
  return i18n.global.t(key)
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
    return event.outcome === 'success' ? tr('audit.actions.loginSuccess') : tr('audit.actions.loginFailed')
  }
  const key = ACTION_KEYS[event.action]
  return key ? tr(key) : event.action
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
  if (!createdAt) return tr('audit.fallbacks.timeUnavailable')
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) return createdAt
  return new Intl.DateTimeFormat(getLocale(), {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function formatAuditEvent(event: AuditEvent): FormattedAuditEvent {
  return {
    id: event.id,
    title: actionTitle(event),
    actorLabel: event.actor?.email || event.actor?.id || tr('audit.fallbacks.unknownActor'),
    outcomeLabel: outcomeLabel(event.outcome),
    outcomeTone: outcomeTone(event.outcome),
    createdAtLabel: createdAtLabel(event.createdAt),
    ipAddressLabel: event.ipAddress || tr('audit.fallbacks.ipUnavailable'),
    userAgentLabel: event.userAgent || tr('audit.fallbacks.userAgentUnavailable'),
    detailRows: collectDetailRows(event.details),
  }
}
