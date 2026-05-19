export type SeriesSample = Record<string, number>

type SamplerFn = (data: unknown) => SeriesSample

function num(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function items(data: unknown, key: string): unknown[] {
  if (!data || typeof data !== 'object') return []
  const value = (data as Record<string, unknown>)[key]
  return Array.isArray(value) ? value : []
}

function findCount(data: unknown, severityKey: string): number {
  const list = items(data, 'items')
  const match = list.find((entry) => {
    if (!entry || typeof entry !== 'object') return false
    return String((entry as Record<string, unknown>).severity ?? '').toLowerCase() === severityKey
  })
  if (!match || typeof match !== 'object') return 0
  return num((match as Record<string, unknown>).count)
}

const SAMPLERS: Record<string, SamplerFn> = {
  'fortigate-system-status': (data) => ({
    cpu: num((data as Record<string, unknown> | null)?.cpu),
    memory: num((data as Record<string, unknown> | null)?.memory),
    sessions: num((data as Record<string, unknown> | null)?.sessions),
  }),
  'fortigate-kpi-sessions': (data) => ({
    sessions: num((data as Record<string, unknown> | null)?.sessions),
  }),
  'fortigate-top-threats': (data) => {
    const threats = items(data, 'threats')
    let critHigh = 0
    for (const t of threats) {
      if (!t || typeof t !== 'object') continue
      const sev = String((t as Record<string, unknown>).severity ?? '').toLowerCase()
      if (sev === 'critical' || sev === 'high') critHigh += 1
    }
    return { count: threats.length, criticalHigh: critHigh }
  },
  'fortigate-network-traffic': (data) => {
    const ifaces = items(data, 'interfaces')
    let totalRx = 0
    let totalTx = 0
    for (const iface of ifaces) {
      if (!iface || typeof iface !== 'object') continue
      totalRx += num((iface as Record<string, unknown>).rxBytes)
      totalTx += num((iface as Record<string, unknown>).txBytes)
    }
    return { totalRxMb: Math.round(totalRx / 1024 / 1024), totalTxMb: Math.round(totalTx / 1024 / 1024) }
  },
  'fortigate-firewall-policies': (data) => {
    const policies = items(data, 'policies')
    let accept = 0
    let deny = 0
    for (const p of policies) {
      if (!p || typeof p !== 'object') continue
      const action = String((p as Record<string, unknown>).action ?? '').toLowerCase()
      if (action === 'accept' || action === 'allow') accept += 1
      else if (action === 'deny' || action === 'drop' || action === 'block') deny += 1
    }
    return { total: policies.length, accept, deny }
  },
  'fortigate-risk-posture': (data) => ({
    score: num((data as Record<string, unknown> | null)?.score),
    critical: num(((data as any)?.summary?.critical)),
    warning: num(((data as any)?.summary?.warning)),
  }),
  'fortigate-interface-health': (data) => {
    const ifaces = items(data, 'interfaces')
    let up = 0
    let down = 0
    for (const iface of ifaces) {
      if (!iface || typeof iface !== 'object') continue
      const status = String((iface as Record<string, unknown>).status ?? '').toLowerCase()
      if (status === 'up') up += 1
      else down += 1
    }
    return { total: ifaces.length, up, down }
  },
  'fortigate-recent-events': (data) => {
    const summary = ((data as any)?.summary) ?? {}
    return {
      total: num(summary.total) || items(data, 'events').length,
      highSeverity: num(summary.highSeverity),
      blocked: num(summary.blocked),
    }
  },
  'fortigate-anomaly-highlights': (data) => ({
    count: num(((data as any)?.summary?.count)) || items(data, 'anomalies').length,
  }),
  'fortigate-top-source-ips': (data) => {
    const events = items(data, 'events')
    const uniqueIps = new Set<string>()
    let denied = 0
    for (const event of events) {
      if (!event || typeof event !== 'object') continue
      const rec = event as Record<string, unknown>
      const ip = String(rec.sourceIp ?? rec.srcIp ?? '').trim()
      if (ip) uniqueIps.add(ip)
      const action = String(rec.action ?? '').toLowerCase()
      if (action === 'deny' || action === 'drop' || action === 'block') denied += 1
    }
    return { uniqueIps: uniqueIps.size, denied, events: events.length }
  },
  'soc-incidents-by-severity': (data) => ({
    total: num((data as Record<string, unknown> | null)?.total),
    critical: findCount(data, 'critical'),
    high: findCount(data, 'high'),
    medium: findCount(data, 'medium'),
    low: findCount(data, 'low'),
  }),
  'soc-recent-incidents': (data) => ({
    count: num((data as Record<string, unknown> | null)?.count) || items(data, 'incidents').length,
  }),
  'soc-top-entities': (data) => ({
    uniqueEntities: items(data, 'entities').length,
  }),
  'soc-sla-breach': (data) => {
    if (data && typeof data === 'object') {
      const rec = data as Record<string, unknown>
      if ('red' in rec || 'amber' in rec || 'open' in rec) {
        return {
          red: num(rec.red),
          amber: num(rec.amber),
          open: num(rec.open),
        }
      }
    }
    const incidents = items(data, 'incidents')
    let red = 0
    let amber = 0
    let openCount = 0
    for (const inc of incidents) {
      if (!inc || typeof inc !== 'object') continue
      const rec = inc as Record<string, unknown>
      const status = String(rec.ticketStatus ?? rec.status ?? '').toLowerCase()
      if (status === 'closed' || status === 'contained') continue
      openCount += 1
      const createdAt = rec.createdAt
      const createdMs = typeof createdAt === 'string' ? Date.parse(createdAt) : NaN
      if (!Number.isFinite(createdMs)) continue
      const ageMs = Date.now() - createdMs
      const oneHour = 60 * 60 * 1000
      if (ageMs >= 4 * oneHour) red += 1
      else if (ageMs >= oneHour) amber += 1
    }
    return { red, amber, open: openCount }
  },
  'soc-mttd-mttr': (data) => {
    if (data && typeof data === 'object') {
      const rec = data as Record<string, unknown>
      if ('mttdAvgMs' in rec || 'mttrAvgMs' in rec) {
        return {
          count: num(rec.mttdSampleSize) + num(rec.mttrSampleSize),
          mttdAvgMs: num(rec.mttdAvgMs),
          mttrAvgMs: num(rec.mttrAvgMs),
        }
      }
    }
    const incidents = items(data, 'incidents')
    const mttd: number[] = []
    const mttr: number[] = []
    for (const inc of incidents) {
      if (!inc || typeof inc !== 'object') continue
      const rec = inc as Record<string, unknown>
      const created = typeof rec.createdAt === 'string' ? Date.parse(rec.createdAt) : NaN
      const detected = typeof rec.detectedAt === 'string' ? Date.parse(rec.detectedAt) : NaN
      const resolved = typeof rec.resolvedAt === 'string' ? Date.parse(rec.resolvedAt) : NaN
      if (Number.isFinite(created) && Number.isFinite(detected)) mttd.push(detected - created)
      if (Number.isFinite(created) && Number.isFinite(resolved)) mttr.push(resolved - created)
    }
    const avg = (arr: number[]) => arr.length === 0 ? 0 : arr.reduce((s, v) => s + v, 0) / arr.length
    return {
      count: incidents.length,
      mttdAvgMs: Math.round(avg(mttd)),
      mttrAvgMs: Math.round(avg(mttr)),
    }
  },
  'xdr-endpoint-health': (data) => {
    const summary = (data as Record<string, unknown> | null)?.summary
    const summaryObj = summary && typeof summary === 'object' ? summary as Record<string, unknown> : {}
    const unhealthy = num(summaryObj.unhealthy) + num(summaryObj.offline) + num(summaryObj.degraded)
    return {
      total: num((data as Record<string, unknown> | null)?.total) || items(data, 'endpoints').length,
      unhealthy,
      healthy: num(summaryObj.healthy) + num(summaryObj.online),
    }
  },
  'soar-active-playbook-runs': (data) => {
    const runs = items(data, 'runs')
    let running = 0
    let waitingApproval = 0
    for (const run of runs) {
      if (!run || typeof run !== 'object') continue
      const status = String((run as Record<string, unknown>).status ?? '').toLowerCase()
      if (status === 'running') running += 1
      else if (status === 'waiting_approval' || status === 'pending_approval') waitingApproval += 1
    }
    return {
      count: num((data as Record<string, unknown> | null)?.count) || runs.length,
      running,
      waitingApproval,
    }
  },
  'soar-playbook-run-history': (data) => {
    const runs = items(data, 'runs')
    let completed = 0
    let failed = 0
    let waitingApproval = 0
    for (const run of runs) {
      if (!run || typeof run !== 'object') continue
      const status = String((run as Record<string, unknown>).status ?? '').toLowerCase()
      if (status === 'completed' || status === 'succeeded') completed += 1
      else if (status === 'failed' || status === 'error') failed += 1
      else if (status === 'waiting_approval' || status === 'pending_approval') waitingApproval += 1
    }
    return {
      count: num((data as Record<string, unknown> | null)?.count) || runs.length,
      completed,
      failed,
      waitingApproval,
    }
  },
  'waf-dos-rate': (data) => {
    const buckets = items(data, 'buckets')
    const blocked = buckets.reduce<number>((s, b) => {
      if (!b || typeof b !== 'object') return s
      return s + num((b as Record<string, unknown>).blocked)
    }, 0)
    const allowed = buckets.reduce<number>((s, b) => {
      if (!b || typeof b !== 'object') return s
      return s + num((b as Record<string, unknown>).allowed)
    }, 0)
    return { blocked, allowed, total: blocked + allowed }
  },
  'waf-dos-top-ips': (data) => ({
    topCount: num((data as any)?.rows?.[0]?.count ?? 0),
    uniqueIps: items(data, 'rows').length,
  }),
  'waf-dos-feed': (data) => ({
    events: items(data, 'items').length,
  }),
}

export function extractSeriesSample(widgetId: string, data: unknown): SeriesSample | null {
  const sampler = SAMPLERS[widgetId]
  if (!sampler) return null
  try {
    return sampler(data ?? null)
  } catch {
    return null
  }
}

export const SERIES_CAPACITY = 30
