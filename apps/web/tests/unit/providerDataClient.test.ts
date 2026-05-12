import { describe, expect, it, vi } from 'vitest'
import { fetchFortigateDataFields, fetchProviderDataFields } from '../../src/services/providerDataClient'

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

  it('loads and normalizes data fields for multiple connected integration categories', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/fortigate/data-fields')) {
        return Promise.resolve(jsonResponse({
          provider: 'fortigate',
          groups: [{
            id: 'system',
            name: 'System Data',
            category: 'Network / FortiGate',
            fields: [{
              id: 'system.cpu',
              label: 'CPU Usage',
              type: 'number',
              source: 'fortigate-system-status',
            }],
          }],
        }))
      }
      return Promise.resolve(jsonResponse({
        provider: 'siem_kowalski',
        groups: [{
          id: 'incidents',
          name: 'Incident Data',
          category: 'SIEM / Incidents',
          fields: [{
            id: 'total',
            label: 'Open Incidents',
            type: 'number',
            unit: 'count',
            source: 'soc-incidents-by-severity',
          }],
        }],
      }))
    })

    await expect(fetchProviderDataFields({
      integrationTypes: ['fortigate', 'siem_kowalski'],
      fetcher,
    })).resolves.toEqual({
      provider: 'soc',
      groups: [
        expect.objectContaining({
          id: 'fortigate.system',
          category: 'Network / FortiGate',
          fields: [expect.objectContaining({
            id: 'system.cpu',
            provider: 'fortigate',
            integrationType: 'fortigate',
          })],
        }),
        expect.objectContaining({
          id: 'siem_kowalski.incidents',
          category: 'SIEM / Incidents',
          fields: [expect.objectContaining({
            id: 'total',
            provider: 'siem_kowalski',
            integrationType: 'siem_kowalski',
          })],
        }),
      ],
    })

    expect(fetcher).toHaveBeenCalledWith('/api/providers/fortigate/data-fields', {
      credentials: 'include',
    })
    expect(fetcher).toHaveBeenCalledWith('/api/providers/siem_kowalski/data-fields', {
      credentials: 'include',
    })
  })
})
