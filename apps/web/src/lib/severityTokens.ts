export type SeverityToken =
  | 'critical'
  | 'high'
  | 'warning'
  | 'medium'
  | 'low'
  | 'healthy'
  | 'informational'
  | 'unknown'

const NORMALIZED: Record<string, SeverityToken> = {
  critical: 'critical',
  crit: 'critical',
  high: 'high',
  warning: 'warning',
  warn: 'warning',
  medium: 'medium',
  med: 'medium',
  low: 'low',
  healthy: 'healthy',
  ok: 'healthy',
  online: 'healthy',
  informational: 'informational',
  info: 'informational',
}

export function normalizeSeverity(value: unknown): SeverityToken {
  if (value === null || value === undefined) return 'unknown'
  const key = String(value).trim().toLowerCase()
  if (!key) return 'unknown'
  return NORMALIZED[key] ?? 'unknown'
}

export function severityRank(value: unknown): number {
  const token = normalizeSeverity(value)
  switch (token) {
    case 'critical': return 5
    case 'high': return 4
    case 'warning':
    case 'medium': return 3
    case 'low': return 2
    case 'informational': return 1
    case 'healthy': return 0
    default: return -1
  }
}

export interface SeverityVisualTokens {
  dot: string
  border: string
  background: string
  text: string
  badge: string
}

const TOKENS: Record<SeverityToken, SeverityVisualTokens> = {
  critical: {
    dot: 'bg-red-400',
    border: 'border-red-400/40',
    background: 'bg-red-950/30',
    text: 'text-red-200',
    badge: 'bg-red-500/15 text-red-300 border-red-400/30',
  },
  high: {
    dot: 'bg-orange-400',
    border: 'border-orange-400/40',
    background: 'bg-orange-950/30',
    text: 'text-orange-200',
    badge: 'bg-orange-500/15 text-orange-300 border-orange-400/30',
  },
  warning: {
    dot: 'bg-amber-400',
    border: 'border-amber-400/40',
    background: 'bg-amber-950/30',
    text: 'text-amber-100',
    badge: 'bg-amber-500/15 text-amber-200 border-amber-400/30',
  },
  medium: {
    dot: 'bg-amber-400',
    border: 'border-amber-400/30',
    background: 'bg-amber-950/20',
    text: 'text-amber-100',
    badge: 'bg-amber-500/10 text-amber-200 border-amber-400/30',
  },
  low: {
    dot: 'bg-blue-400',
    border: 'border-blue-400/30',
    background: 'bg-blue-950/20',
    text: 'text-blue-100',
    badge: 'bg-blue-500/10 text-blue-200 border-blue-400/30',
  },
  healthy: {
    dot: 'bg-emerald-400',
    border: 'border-emerald-400/30',
    background: 'bg-emerald-950/20',
    text: 'text-emerald-100',
    badge: 'bg-emerald-500/15 text-emerald-300 border-emerald-400/30',
  },
  informational: {
    dot: 'bg-sky-400',
    border: 'border-sky-400/30',
    background: 'bg-sky-950/20',
    text: 'text-sky-100',
    badge: 'bg-sky-500/10 text-sky-200 border-sky-400/30',
  },
  unknown: {
    dot: 'bg-theme-text-muted',
    border: 'border-theme-border',
    background: 'bg-theme-text/5',
    text: 'text-theme-text',
    badge: 'bg-theme-text/10 text-theme-text-muted border-theme-border',
  },
}

export function severityTokens(value: unknown): SeverityVisualTokens {
  return TOKENS[normalizeSeverity(value)]
}
