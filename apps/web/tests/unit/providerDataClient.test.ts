import { describe, expect, it, vi } from 'vitest'
import { fetchFortigateDataFields } from '../../src/services/providerDataClient'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('providerDataClient', () => {
  it('loads FortiGate data fields through the backend API with browser credentials', async () => {
    const fetcher = vi.fn().mockResolvedValue(jsonResponse({
      provider: 'fortigate',
      groups: [
        {
          id: 'system',
          name: 'System Data',
          fields: [
            {
              id: 'system.cpu',
              label: 'CPU Usage',
              type: 'number',
              unit: 'percent',
              source: 'fortigate-system-status',
              recommendedVisuals: ['kpi'],
            },
          ],
        },
      ],
    }))

    await expect(fetchFortigateDataFields({ fetcher })).resolves.toEqual({
      provider: 'fortigate',
      groups: [
        {
          id: 'system',
          name: 'System Data',
          fields: [
            {
              id: 'system.cpu',
              label: 'CPU Usage',
              type: 'number',
              unit: 'percent',
              source: 'fortigate-system-status',
              recommendedVisuals: ['kpi'],
            },
          ],
        },
      ],
    })

    expect(fetcher).toHaveBeenCalledWith('/api/providers/fortigate/data-fields', {
      credentials: 'include',
    })
  })
})
