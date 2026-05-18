import { describe, expect, it } from 'vitest'
import { normalizeQueryParams, socEventsKey, socIncidentsKey, socTicketsKey, widgetDataKey } from '../../src/services/queryKeys'

describe('queryKeys', () => {
  it('normalizes widget data keys with stable parameter order', () => {
    expect(widgetDataKey('waf-dos-rate', {
      window: '1h',
      integrationId: 'int_siem_01',
      source: 'siem',
      limit: undefined,
    })).toEqual([
      'widgets',
      'data',
      'waf-dos-rate',
      {
        integrationId: 'int_siem_01',
        limit: null,
        source: 'siem',
        window: '1h',
      },
    ])
  })

  it('builds SOC cache keys from normalized filters', () => {
    expect(socTicketsKey({ severity: 'high', status: 'new' })).toEqual([
      'soc',
      'tickets',
      { severity: 'high', status: 'new' },
    ])
    expect(socIncidentsKey({ status: 'open' })).toEqual([
      'soc',
      'incidents',
      { status: 'open' },
    ])
    expect(socEventsKey({ limit: 25, eventType: 'waf.dos' })).toEqual([
      'soc',
      'events',
      { eventType: 'waf.dos', limit: 25 },
    ])
  })

  it('normalizes empty values to null without dropping identity fields', () => {
    expect(normalizeQueryParams({ integrationId: '', source: undefined })).toEqual({
      integrationId: null,
      source: null,
    })
  })
})
