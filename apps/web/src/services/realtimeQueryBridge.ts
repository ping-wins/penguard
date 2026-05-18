import type { QueryClient } from '@tanstack/vue-query'
import type { RealtimeEvent, RealtimeWidgetSnapshot } from '../stores/useRealtimeStore'
import type { Ticket } from './ticketsClient'
import type { WidgetDataResponse } from '../types/dashboard'
import { socEventsKey, socIncidentsKey, socTicketsKey } from './queryKeys'

type ServerRecord = Record<string, any>
type ServerRecordWithId = ServerRecord & { id: string }

const BLOCKED_ACTIONS = new Set(['block', 'blocked', 'deny', 'dropped'])
const WAF_DOS_RULE_ID = 'fortiweb_dos_activity'
const WAF_HTTP_FLOW_PORTS = new Set(['80', '443', '8080', '8443'])
const WAF_HTTP_FLOW_SERVICES = new Set(['http', 'https'])

function asRecord(value: unknown): ServerRecord {
  return value && typeof value === 'object' ? value as ServerRecord : {}
}

function listWithUpsert<T extends { id: string }>(items: T[], item: T): T[] {
  const idx = items.findIndex((existing) => existing.id === item.id)
  if (idx >= 0) return items.map((existing) => existing.id === item.id ? item : existing)
  return [item, ...items]
}

function updateListCache<T extends { id: string }>(current: T[] | { items?: T[] } | undefined, item: T) {
  if (Array.isArray(current)) return listWithUpsert(current, item)
  if (current && typeof current === 'object') {
    return {
      ...current,
      items: listWithUpsert(Array.isArray(current.items) ? current.items : [], item),
    }
  }
  return [item]
}

function upsertTicketCaches(queryClient: QueryClient, ticket: Ticket) {
  queryClient.setQueryData(socTicketsKey(), (current: Ticket[] | undefined) =>
    updateListCache(current, ticket),
  )
  queryClient.setQueriesData({ queryKey: ['soc', 'tickets'] }, (current: Ticket[] | { items?: Ticket[] } | undefined) =>
    updateListCache(current, ticket),
  )
}

function upsertIncidentCaches(queryClient: QueryClient, ticket: Ticket) {
  queryClient.setQueryData(socIncidentsKey(), (current: Ticket[] | undefined) =>
    updateListCache(current, ticket),
  )
  queryClient.setQueriesData({ queryKey: ['soc', 'incidents'] }, (current: Ticket[] | { items?: Ticket[] } | undefined) =>
    updateListCache(current, ticket),
  )
}

function upsertSocEventCaches(queryClient: QueryClient, event: ServerRecord) {
  if (!event.id) return
  const eventWithId = event as ServerRecordWithId
  queryClient.setQueryData(socEventsKey(), (current: ServerRecord[] | undefined) =>
    updateListCache(current as ServerRecordWithId[] | undefined, eventWithId),
  )
  queryClient.setQueriesData({ queryKey: ['soc', 'events'] }, (current: unknown) =>
    updateListCache(
      current as ServerRecordWithId[] | { items?: ServerRecordWithId[] } | undefined,
      eventWithId,
    ),
  )
}

function widgetResponseFromSnapshot(snapshot: RealtimeWidgetSnapshot): WidgetDataResponse | null {
  if (!snapshot.widgetId || !snapshot.integrationId || !snapshot.data) return null
  return {
    widgetId: snapshot.widgetId,
    integrationId: snapshot.integrationId,
    refreshedAt: snapshot.refreshedAt || new Date().toISOString(),
    status: snapshot.status === 'error' ? 'error' : 'ready',
    data: snapshot.data,
    meta: snapshot.meta,
  }
}

function upsertWidgetSnapshotCaches(queryClient: QueryClient, snapshot: RealtimeWidgetSnapshot) {
  const response = widgetResponseFromSnapshot(snapshot)
  if (!response) return
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', response.widgetId] },
    (current: WidgetDataResponse | undefined) => current ? response : current,
  )
}

function ticketSeverity(ticket: Ticket) {
  return String(ticket.severity || 'informational').toLowerCase()
}

function updateRecentIncidents(current: WidgetDataResponse | undefined, ticket: Ticket): WidgetDataResponse | undefined {
  if (!current) return current
  const data = asRecord(current.data)
  const incidents = Array.isArray(data.incidents) ? data.incidents : []
  const alreadyPresent = incidents.some((incident: any) => incident?.id === ticket.id)
  const nextIncidents = alreadyPresent
    ? incidents.map((incident: any) => incident?.id === ticket.id ? ticket : incident)
    : [ticket, ...incidents]
  return {
    ...current,
    refreshedAt: new Date().toISOString(),
    data: {
      ...data,
      incidents: nextIncidents.slice(0, 10),
      count: (Number(data.count) || incidents.length) + (alreadyPresent ? 0 : 1),
    },
  }
}

function updateIncidentsBySeverity(current: WidgetDataResponse | undefined, ticket: Ticket): WidgetDataResponse | undefined {
  if (!current) return current
  const data = asRecord(current.data)
  const severity = ticketSeverity(ticket)
  const items = Array.isArray(data.items) ? [...data.items] : []
  const idx = items.findIndex((item: any) => String(item?.severity || '').toLowerCase() === severity)
  if (idx >= 0) {
    items[idx] = { ...items[idx], count: (Number(items[idx].count) || 0) + 1 }
  } else {
    items.push({ severity, count: 1 })
  }
  return {
    ...current,
    refreshedAt: new Date().toISOString(),
    data: {
      ...data,
      items,
      total: (Number(data.total) || 0) + 1,
    },
  }
}

function upsertSocWidgetCaches(queryClient: QueryClient, ticket: Ticket) {
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'soc-recent-incidents'] },
    (current: WidgetDataResponse | undefined) => updateRecentIncidents(current, ticket),
  )
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'soc-incidents-by-severity'] },
    (current: WidgetDataResponse | undefined) => updateIncidentsBySeverity(current, ticket),
  )
}

function eventAttributes(event: ServerRecord | null | undefined, ticket?: Ticket): ServerRecord {
  return {
    ...asRecord(ticket?.attributes),
    ...asRecord(event?.attributes),
  }
}

function eventEntities(event: ServerRecord | null | undefined, ticket?: Ticket): ServerRecord {
  return {
    ...asRecord(ticket?.entities),
    ...asRecord(event?.entities),
  }
}

function isBlockedAction(action: unknown): boolean {
  return BLOCKED_ACTIONS.has(String(action || '').toLowerCase())
}

function isLiveHttpFlowPayload(event: ServerRecord | null | undefined): boolean {
  if (event?.eventType !== 'network.event') return false
  const attributes = asRecord(event.attributes)
  const entities = asRecord(event.entities)
  const sourceIp = attributes.sourceIp || entities.sourceIp
  const destinationIp = attributes.destinationIp || entities.destinationIp
  if (!sourceIp || !destinationIp) return false
  const service = String(attributes.service || attributes.application || '').toLowerCase()
  const destinationPort = String(
    attributes.destinationPort
      || attributes.dstPort
      || attributes.destPort
      || '',
  )
  return WAF_HTTP_FLOW_SERVICES.has(service) || WAF_HTTP_FLOW_PORTS.has(destinationPort)
}

function isWafDosPayload(event: ServerRecord | null | undefined, ticket?: Ticket): boolean {
  return event?.eventType === 'waf.dos'
    || ticket?.ruleId === WAF_DOS_RULE_ID
    || isLiveHttpFlowPayload(event)
}

function payloadCount(attributes: ServerRecord): number {
  const raw = attributes.count ?? attributes.requestCount ?? attributes.observedCount
  const count = Number(raw)
  return Number.isFinite(count) && count > 0 ? count : 1
}

function eventTs(event: ServerRecord | null | undefined, ticket: Ticket | undefined, realtimeEvent: RealtimeEvent): string {
  return String(event?.occurredAt || ticket?.createdAt || realtimeEvent.receivedAt || new Date().toISOString())
}

function minuteBucketTs(ts: string): string {
  const date = new Date(ts)
  if (Number.isNaN(date.getTime())) return ts
  date.setSeconds(0, 0)
  return date.toISOString()
}

function wafPayload(event: ServerRecord | null | undefined, ticket: Ticket | undefined, realtimeEvent: RealtimeEvent) {
  const attributes = eventAttributes(event, ticket)
  const entities = eventEntities(event, ticket)
  const action = String(attributes.action || '')
  const ts = eventTs(event, ticket, realtimeEvent)
  const count = payloadCount(attributes)
  const sourceIp = String(attributes.sourceIp || entities.sourceIp || '')
  const policy = String(attributes.policy || attributes.policyName || attributes.policyId || '')
  const severity = String(event?.severity || ticket?.severity || 'medium')
  const liveHttpFlow = isLiveHttpFlowPayload(event)
  const message = String(
    attributes.message
      || attributes.summary
      || ticket?.title
      || (liveHttpFlow ? 'HTTP flow observed' : '')
      || (attributes.attackType === 'http_flood' ? 'HTTP flood detected' : 'WAF DoS event detected'),
  )
  return {
    id: String(event?.id || ticket?.id || realtimeEvent.eventId || `${sourceIp}:${ts}`),
    ts,
    count,
    sourceIp,
    action,
    blocked: isBlockedAction(action),
    severity,
    message,
    policy,
  }
}

function updateWafDosRate(
  current: WidgetDataResponse | undefined,
  event: ServerRecord | null | undefined,
  ticket: Ticket | undefined,
  realtimeEvent: RealtimeEvent,
): WidgetDataResponse | undefined {
  if (!current || !isWafDosPayload(event, ticket)) return current
  const payload = wafPayload(event, ticket, realtimeEvent)
  const data = asRecord(current.data)
  const bucketTs = minuteBucketTs(payload.ts)
  const buckets = Array.isArray(data.buckets) ? [...data.buckets] : []
  const idx = buckets.findIndex((bucket: any) => bucket?.ts === bucketTs)
  const previous = idx >= 0 ? asRecord(buckets[idx]) : { ts: bucketTs, blocked: 0, allowed: 0 }
  const nextBucket = {
    ...previous,
    ts: bucketTs,
    blocked: (Number(previous.blocked) || 0) + (payload.blocked ? payload.count : 0),
    allowed: (Number(previous.allowed) || 0) + (payload.blocked ? 0 : payload.count),
  }
  if (idx >= 0) buckets[idx] = nextBucket
  else buckets.push(nextBucket)
  return {
    ...current,
    refreshedAt: payload.ts,
    data: {
      ...data,
      source: data.source || 'siem',
      buckets: buckets.slice(-1440),
    },
  }
}

function updateWafTopIps(
  current: WidgetDataResponse | undefined,
  event: ServerRecord | null | undefined,
  ticket: Ticket | undefined,
  realtimeEvent: RealtimeEvent,
): WidgetDataResponse | undefined {
  if (!current || !isWafDosPayload(event, ticket)) return current
  const payload = wafPayload(event, ticket, realtimeEvent)
  if (!payload.sourceIp) return current
  const data = asRecord(current.data)
  const rows = Array.isArray(data.rows) ? [...data.rows] : []
  const idx = rows.findIndex((row: any) => row?.ip === payload.sourceIp)
  const previous = idx >= 0 ? asRecord(rows[idx]) : {}
  const nextRow = {
    ...previous,
    ip: payload.sourceIp,
    count: (Number(previous.count) || 0) + payload.count,
    lastSeen: payload.ts,
    blocked: Boolean(previous.blocked) || payload.blocked,
  }
  if (idx >= 0) rows[idx] = nextRow
  else rows.push(nextRow)
  rows.sort((left: any, right: any) => (Number(right.count) || 0) - (Number(left.count) || 0))
  return {
    ...current,
    refreshedAt: payload.ts,
    data: {
      ...data,
      source: data.source || 'siem',
      rows: rows.slice(0, 25),
    },
  }
}

function updateWafFeed(
  current: WidgetDataResponse | undefined,
  event: ServerRecord | null | undefined,
  ticket: Ticket | undefined,
  realtimeEvent: RealtimeEvent,
): WidgetDataResponse | undefined {
  if (!current || !isWafDosPayload(event, ticket)) return current
  const payload = wafPayload(event, ticket, realtimeEvent)
  const data = asRecord(current.data)
  const items = Array.isArray(data.items) ? data.items : []
  const nextItem = {
    id: payload.id,
    ts: payload.ts,
    sourceIp: payload.sourceIp,
    action: payload.action,
    severity: payload.severity,
    message: payload.message,
    policy: payload.policy,
  }
  return {
    ...current,
    refreshedAt: payload.ts,
    data: {
      ...data,
      source: data.source || 'siem',
      items: [nextItem, ...items.filter((item: any) => item?.id !== nextItem.id)].slice(0, 100),
    },
  }
}

function upsertWafWidgetCaches(
  queryClient: QueryClient,
  event: ServerRecord | null | undefined,
  ticket: Ticket | undefined,
  realtimeEvent: RealtimeEvent,
) {
  if (!isWafDosPayload(event, ticket)) return
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'waf-dos-rate'] },
    (current: WidgetDataResponse | undefined) => updateWafDosRate(current, event, ticket, realtimeEvent),
  )
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'waf-dos-top-ips'] },
    (current: WidgetDataResponse | undefined) => updateWafTopIps(current, event, ticket, realtimeEvent),
  )
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'waf-dos-feed'] },
    (current: WidgetDataResponse | undefined) => updateWafFeed(current, event, ticket, realtimeEvent),
  )
}

function clearSocCaches(queryClient: QueryClient) {
  queryClient.setQueriesData({ queryKey: ['soc', 'tickets'] }, () => [])
  queryClient.setQueriesData({ queryKey: ['soc', 'incidents'] }, () => [])
  queryClient.setQueriesData({ queryKey: ['soc', 'events'] }, () => [])
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'soc-recent-incidents'] },
    (current: WidgetDataResponse | undefined) => current ? { ...current, data: { ...asRecord(current.data), incidents: [], count: 0 } } : current,
  )
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'soc-incidents-by-severity'] },
    (current: WidgetDataResponse | undefined) => current ? { ...current, data: { ...asRecord(current.data), items: [], total: 0 } } : current,
  )
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'waf-dos-rate'] },
    (current: WidgetDataResponse | undefined) => current ? { ...current, data: { ...asRecord(current.data), buckets: [] } } : current,
  )
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'waf-dos-top-ips'] },
    (current: WidgetDataResponse | undefined) => current ? { ...current, data: { ...asRecord(current.data), rows: [] } } : current,
  )
  queryClient.setQueriesData(
    { queryKey: ['widgets', 'data', 'waf-dos-feed'] },
    (current: WidgetDataResponse | undefined) => current ? { ...current, data: { ...asRecord(current.data), items: [] } } : current,
  )
}

export function resyncRealtimeQueries(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: ['soc'], refetchType: 'active' })
  void queryClient.invalidateQueries({ queryKey: ['widgets', 'data'], refetchType: 'active' })
}

export function applyRealtimeQueryEvent(queryClient: QueryClient, realtimeEvent: RealtimeEvent) {
  if (realtimeEvent.type === 'soc.incidents.reset') {
    clearSocCaches(queryClient)
    return
  }

  if (Array.isArray(realtimeEvent.widgets)) {
    for (const snapshot of realtimeEvent.widgets) upsertWidgetSnapshotCaches(queryClient, snapshot)
  }

  const event = asRecord(realtimeEvent.event)
  const hasEvent = Boolean(realtimeEvent.event && typeof realtimeEvent.event === 'object')
  const ticket = realtimeEvent.ticket

  if (hasEvent && realtimeEvent.type === 'soc.event.created') {
    upsertSocEventCaches(queryClient, event)
    upsertWafWidgetCaches(queryClient, event, undefined, realtimeEvent)
  }

  if (ticket) {
    upsertTicketCaches(queryClient, ticket)
    upsertIncidentCaches(queryClient, ticket)
    upsertSocWidgetCaches(queryClient, ticket)
    if (!hasEvent) upsertWafWidgetCaches(queryClient, null, ticket, realtimeEvent)
  }
}
