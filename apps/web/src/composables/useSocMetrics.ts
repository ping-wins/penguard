export type SlaBucket = 'green' | 'amber' | 'red'

export interface SlaThresholds {
  amberMs: number
  redMs: number
}

export const DEFAULT_SLA_THRESHOLDS: SlaThresholds = {
  amberMs: 15 * 60 * 1000,
  redMs: 60 * 60 * 1000,
}

export function ageMs(iso: string | null | undefined, nowMs: number = Date.now()): number | null {
  if (!iso) return null
  const parsed = Date.parse(iso)
  if (!Number.isFinite(parsed)) return null
  const delta = nowMs - parsed
  return delta < 0 ? 0 : delta
}

export function formatAge(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms) || ms < 0) return '--'
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remMinutes = minutes % 60
  if (hours < 24) return remMinutes > 0 ? `${hours}h ${remMinutes}m` : `${hours}h`
  const days = Math.floor(hours / 24)
  const remHours = hours % 24
  return remHours > 0 ? `${days}d ${remHours}h` : `${days}d`
}

export function slaBucket(ageValue: number | null | undefined, thresholds: SlaThresholds = DEFAULT_SLA_THRESHOLDS): SlaBucket {
  if (ageValue === null || ageValue === undefined || !Number.isFinite(ageValue)) return 'green'
  if (ageValue >= thresholds.redMs) return 'red'
  if (ageValue >= thresholds.amberMs) return 'amber'
  return 'green'
}

export interface IncidentLike {
  createdAt?: string | null
  updatedAt?: string | null
  ticketStatus?: string | null
  timeline?: Array<{ at?: string | null, type?: string | null, note?: string | null }> | null
}

export function mttdEstimate(incident: IncidentLike | null | undefined): number | null {
  if (!incident) return null
  const created = incident.createdAt ? Date.parse(incident.createdAt) : NaN
  if (!Number.isFinite(created)) return null
  const timeline = Array.isArray(incident.timeline) ? incident.timeline : []
  const firstChange = timeline
    .map((entry) => entry?.at ? Date.parse(entry.at) : NaN)
    .filter((value) => Number.isFinite(value) && value > created)
    .sort((a, b) => a - b)[0]
  if (Number.isFinite(firstChange)) return firstChange - created
  const updated = incident.updatedAt ? Date.parse(incident.updatedAt) : NaN
  if (Number.isFinite(updated) && updated > created) return updated - created
  return null
}

export function mttrEstimate(incident: IncidentLike | null | undefined): number | null {
  if (!incident) return null
  const created = incident.createdAt ? Date.parse(incident.createdAt) : NaN
  if (!Number.isFinite(created)) return null
  const timeline = Array.isArray(incident.timeline) ? incident.timeline : []
  const resolvedEntry = timeline
    .filter((entry) => {
      const type = String(entry?.type || '').toLowerCase()
      return type.includes('contained') || type.includes('closed') || type.includes('resolved')
    })
    .map((entry) => entry?.at ? Date.parse(entry.at) : NaN)
    .filter((value) => Number.isFinite(value))
    .sort((a, b) => b - a)[0]
  if (Number.isFinite(resolvedEntry)) return resolvedEntry - created
  const status = String(incident.ticketStatus || '').toLowerCase()
  if ((status === 'contained' || status === 'closed') && incident.updatedAt) {
    const updated = Date.parse(incident.updatedAt)
    if (Number.isFinite(updated) && updated >= created) return updated - created
  }
  return null
}

export function topByCount<T>(items: T[], keyFn: (item: T) => string | null | undefined, limit: number): Array<{ key: string, count: number }> {
  if (!Array.isArray(items) || items.length === 0 || limit <= 0) return []
  const counts = new Map<string, number>()
  for (const item of items) {
    const key = keyFn(item)
    if (key === null || key === undefined || key === '') continue
    const k = String(key)
    counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  return Array.from(counts.entries())
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
    .slice(0, limit)
}
