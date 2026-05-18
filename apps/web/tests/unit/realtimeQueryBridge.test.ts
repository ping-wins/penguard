import { QueryClient } from '@tanstack/vue-query'
import { describe, expect, it, vi } from 'vitest'
import { applyRealtimeQueryEvent, resyncRealtimeQueries } from '../../src/services/realtimeQueryBridge'
import { socEventsKey, socTicketsKey, widgetDataKey } from '../../src/services/queryKeys'
import type { WidgetDataResponse } from '../../src/types/dashboard'

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchInterval: false,
        refetchOnWindowFocus: false,
      },
    },
  })
}

function widgetResponse(widgetId: string, data: Record<string, unknown>): WidgetDataResponse {
  return {
    widgetId,
    integrationId: 'int_siem_01',
    refreshedAt: '2026-05-18T03:29:00.000Z',
    status: 'ready',
    data,
    meta: { source: 'siem_kowalski', cacheTtlSeconds: 5, refreshIntervalSeconds: 0 },
  }
}

describe('realtimeQueryBridge', () => {
  it('upserts created tickets into SOC ticket cache without a fetch', () => {
    const queryClient = makeClient()
    queryClient.setQueryData(socTicketsKey(), [])

    applyRealtimeQueryEvent(queryClient, {
      type: 'soc.incident.created',
      integrationId: 'int_fgt_01',
      ticket: {
        id: 'inc_waf_dos_01',
        ruleId: 'fortiweb_dos_activity',
        title: 'FortiWeb DoS activity detected',
        severity: 'critical',
        status: 'open',
        source: 'kowalski',
        entities: {},
        summary: 'HTTP flood observed.',
        createdAt: '2026-05-18T03:30:00.000Z',
        timeline: [],
        eventIds: ['evt_waf_dos_01'],
        triageLevel: 'T1',
        ticketStatus: 'new',
        assigneeUserId: null,
        aiAnalysisId: null,
      },
    })

    expect(queryClient.getQueryData<any[]>(socTicketsKey())?.map((ticket) => ticket.id)).toEqual([
      'inc_waf_dos_01',
    ])
  })

  it('updates WAF DoS widget caches from observed close actions as allowed traffic', () => {
    const queryClient = makeClient()
    queryClient.setQueryData(
      widgetDataKey('waf-dos-rate', { integrationId: 'int_siem_01', source: 'siem' }),
      widgetResponse('waf-dos-rate', { source: 'siem', buckets: [] }),
    )
    queryClient.setQueryData(
      widgetDataKey('waf-dos-top-ips', { integrationId: 'int_siem_01', source: 'siem' }),
      widgetResponse('waf-dos-top-ips', { source: 'siem', rows: [] }),
    )
    queryClient.setQueryData(
      widgetDataKey('waf-dos-feed', { integrationId: 'int_siem_01', source: 'siem' }),
      widgetResponse('waf-dos-feed', { source: 'siem', items: [] }),
    )

    applyRealtimeQueryEvent(queryClient, {
      type: 'soc.event.created',
      integrationId: 'int_fgt_01',
      eventId: 'evt_waf_dos_01',
      receivedAt: '2026-05-18T03:30:05.000Z',
      event: {
        id: 'evt_waf_dos_01',
        eventType: 'waf.dos',
        severity: 'critical',
        occurredAt: '2026-05-18T03:30:05.000Z',
        entities: { sourceIp: '10.10.10.10' },
        attributes: {
          action: 'close',
          count: 100,
          attackType: 'http_flood',
          ingestionMode: 'fortigate_flow_inference',
          policyId: '2',
        },
      },
    })

    const rate = queryClient.getQueryData<WidgetDataResponse>(
      widgetDataKey('waf-dos-rate', { integrationId: 'int_siem_01', source: 'siem' }),
    )
    const topIps = queryClient.getQueryData<WidgetDataResponse>(
      widgetDataKey('waf-dos-top-ips', { integrationId: 'int_siem_01', source: 'siem' }),
    )
    const feed = queryClient.getQueryData<WidgetDataResponse>(
      widgetDataKey('waf-dos-feed', { integrationId: 'int_siem_01', source: 'siem' }),
    )

    expect(rate?.data.buckets).toEqual([
      { ts: '2026-05-18T03:30:00.000Z', blocked: 0, allowed: 100 },
    ])
    expect(topIps?.data.rows).toEqual([
      { ip: '10.10.10.10', count: 100, lastSeen: '2026-05-18T03:30:05.000Z', blocked: false },
    ])
    expect(feed?.data.items).toEqual([
      expect.objectContaining({
        id: 'evt_waf_dos_01',
        sourceIp: '10.10.10.10',
        action: 'close',
        severity: 'critical',
      }),
    ])
  })

  it('clears SOC and WAF widget caches on incident reset without fetching', () => {
    const queryClient = makeClient()
    queryClient.setQueryData(socTicketsKey(), [{ id: 'inc_01' }])
    queryClient.setQueryData(
      widgetDataKey('waf-dos-feed', { integrationId: 'int_siem_01' }),
      widgetResponse('waf-dos-feed', { items: [{ id: 'evt_01' }] }),
    )

    applyRealtimeQueryEvent(queryClient, { type: 'soc.incidents.reset' })

    expect(queryClient.getQueryData(socTicketsKey())).toEqual([])
    expect(queryClient.getQueryData<WidgetDataResponse>(
      widgetDataKey('waf-dos-feed', { integrationId: 'int_siem_01' }),
    )?.data.items).toEqual([])
  })

  it('invalidates active SOC and widget queries once during SSE resync', () => {
    const queryClient = makeClient()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    resyncRealtimeQueries(queryClient)

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['soc'], refetchType: 'active' })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['widgets', 'data'], refetchType: 'active' })
  })

  it('upserts SIEM events into event caches', () => {
    const queryClient = makeClient()
    queryClient.setQueryData(socEventsKey(), [])

    applyRealtimeQueryEvent(queryClient, {
      type: 'soc.event.created',
      event: {
        id: 'evt_network_01',
        eventType: 'network.event',
        severity: 'medium',
        occurredAt: '2026-05-18T03:30:00.000Z',
      },
    })

    expect(queryClient.getQueryData<any[]>(socEventsKey())?.map((event) => event.id)).toEqual([
      'evt_network_01',
    ])
  })
})
