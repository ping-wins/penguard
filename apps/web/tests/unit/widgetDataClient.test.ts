import { describe, expect, it, vi } from 'vitest'
import { fetchWidgetData } from '../../src/services/widgetDataClient'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('fetchWidgetData', () => {
  it('calls the widget data endpoint with credentials and returns ready data', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-kpi-sessions',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-26T23:45:00.000Z',
      status: 'ready',
      data: { sessions: 3812 },
      meta: { source: 'fortigate', cacheTtlSeconds: 2, refreshIntervalSeconds: 2 },
    }))

    const result = await fetchWidgetData({
      dataEndpoint: '/api/widgets/fortigate-kpi-sessions/data',
      integrationId: 'int_fgt_01',
      fetcher,
    })

    expect(fetcher).toHaveBeenCalledWith(
      '/api/widgets/fortigate-kpi-sessions/data?integrationId=int_fgt_01',
      { credentials: 'include' },
    )
    expect(result).toEqual({
      state: 'ready',
      data: { sessions: 3812 },
      response: expect.objectContaining({ status: 'ready' }),
    })
  })

  it('turns controlled backend widget errors into a renderable error state', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      widgetId: 'fortigate-top-threats',
      integrationId: 'int_fgt_01',
      refreshedAt: '2026-04-26T23:45:00.000Z',
      status: 'error',
      data: {},
      meta: {
        source: 'fortigate',
        cacheTtlSeconds: 5,
        refreshIntervalSeconds: 5,
        error: { message: 'FortiGate API request failed with HTTP 404' },
      },
    }))

    await expect(fetchWidgetData({
      dataEndpoint: '/api/widgets/fortigate-top-threats/data',
      integrationId: 'int_fgt_01',
      fetcher,
    })).resolves.toEqual({
      state: 'error',
      errorKind: 'widget_error',
      errorMessage: 'FortiGate API request failed with HTTP 404',
      response: expect.objectContaining({ status: 'error' }),
    })
  })

  it('returns an HTTP error state for non-2xx responses', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({ detail: 'Forbidden' }, { status: 403 }))

    await expect(fetchWidgetData({
      dataEndpoint: '/api/widgets/fortigate-system-status/data',
      integrationId: 'int_fgt_01',
      fetcher,
    })).resolves.toEqual({
      state: 'error',
      errorKind: 'invalid_connection',
      errorMessage: 'Widget connection is not authorized. Check the FortiDashboard session or FortiGate integration.',
    })
  })
})
