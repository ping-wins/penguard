import { afterEach, describe, expect, it, vi } from 'vitest'
import { listPlaybookNodeTypes } from '../../src/services/playbooksClient'

function mockFetch(response: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    json: vi.fn().mockResolvedValue(response),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('playbooksClient', () => {
  it('loads SOAR node catalog with dry-run and boundary metadata', async () => {
    const fetchMock = mockFetch({
      items: [
        {
          id: 'case.note',
          label: 'Create Case Note',
          category: 'action',
          sensitive: false,
          dryRunOnly: true,
          executionMode: 'dry_run',
          liveAvailable: false,
          boundary: 'case_note',
          configSchema: { type: 'object' },
        },
      ],
    })

    const items = await listPlaybookNodeTypes()

    expect(fetchMock).toHaveBeenCalledWith('/api/soc/playbook-node-types', { credentials: 'include' })
    expect(items).toEqual([
      expect.objectContaining({
        id: 'case.note',
        executionMode: 'dry_run',
        liveAvailable: false,
        boundary: 'case_note',
      }),
    ])
  })
})
