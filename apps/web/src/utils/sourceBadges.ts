export type SourceBadge = {
  labelKey:
    | 'sourceBadges.seededDemo'
    | 'sourceBadges.simulator'
    | 'sourceBadges.scriptedAi'
    | 'sourceBadges.live'
  tone: 'demo' | 'simulator' | 'ai' | 'live'
}

const LIVE_VALUES = new Set([
  'fortigate',
  'siem',
  'siem_kowalski',
  'kowalski',
  'xdr',
  'xdr_rico',
  'rico',
  'soar',
  'soar_skipper',
  'skipper',
  'live',
])

export function sourceBadgeFor(value: unknown): SourceBadge | null {
  if (!isRecord(value)) return null

  const attributes = isRecord(value.attributes) ? value.attributes : {}
  const origin = isRecord(value.origin) ? value.origin : {}
  const source = normalized(value.source)
  const attributesSource = normalized(attributes.source)
  const originKind = normalized(origin.kind)

  if (
    source === 'demo.replay'
    || attributesSource === 'demo.replay'
    || originKind === 'demo.replay'
    || hasValue(value.demoRunId)
    || hasValue(attributes.demoRunId)
  ) {
    return { labelKey: 'sourceBadges.seededDemo', tone: 'demo' }
  }

  if (source === 'simulator' || attributesSource === 'simulator' || originKind === 'simulator') {
    return { labelKey: 'sourceBadges.simulator', tone: 'simulator' }
  }

  if (
    normalized(value.provider) === 'scripted'
    || normalized(value.providerMode) === 'scripted'
    || normalized(value.rawOutput) === 'scripted'
    || normalized(value.raw_output) === 'scripted'
  ) {
    return { labelKey: 'sourceBadges.scriptedAi', tone: 'ai' }
  }

  if (
    LIVE_VALUES.has(source)
    || LIVE_VALUES.has(attributesSource)
    || LIVE_VALUES.has(originKind)
    || LIVE_VALUES.has(normalized(value.provider))
    || LIVE_VALUES.has(normalized(value.providerMode))
  ) {
    return { labelKey: 'sourceBadges.live', tone: 'live' }
  }

  return null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalized(value: unknown) {
  return typeof value === 'string' ? value.trim().toLowerCase() : ''
}

function hasValue(value: unknown) {
  return value !== undefined && value !== null && value !== ''
}
