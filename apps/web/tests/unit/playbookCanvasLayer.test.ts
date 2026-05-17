import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PlaybookCanvasLayer from '../../src/components/playbooks/canvas/PlaybookCanvasLayer.vue'
import { i18n, setLocale } from '../../src/i18n'
import { useAuthStore } from '../../src/stores/useAuthStore'
import { usePlaybooksStore } from '../../src/stores/usePlaybooksStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('PlaybookCanvasLayer', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('en-US')
    const store = usePlaybooksStore()
    store.nodeTypes = [
      {
        id: 'trigger.incident_created',
        label: 'Incident Created',
        category: 'trigger',
        sensitive: false,
        dryRunOnly: true,
        executionMode: 'dry_run',
        liveAvailable: false,
        boundary: 'trigger_only',
        configSchema: {},
      },
      {
        id: 'case.note',
        label: 'Create Case Note',
        category: 'action',
        sensitive: false,
        dryRunOnly: true,
        executionMode: 'dry_run',
        liveAvailable: false,
        boundary: 'case_note',
        configSchema: {},
      },
    ]
    store.playbooks = [
      {
        id: 'pb_canvas',
        name: 'Canvas playbook',
        enabled: false,
        nodes: [{ id: 'trigger', type: 'trigger.incident_created', config: {} }],
        edges: [],
      },
    ]
    useAuthStore().csrfToken = 'csrf_01'
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('adds an automation node from drag payload and saves the visual graph', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/soc/playbooks/pb_canvas' && init?.method === 'PUT') {
        const payload = JSON.parse(String(init.body))
        expect(payload.nodes).toEqual([
          expect.objectContaining({ id: 'trigger', type: 'trigger.incident_created' }),
          expect.objectContaining({
            type: 'case.note',
            config: { template: 'Review incident.' },
            position: { x: 240, y: 180 },
          }),
        ])
        return jsonResponse(payload)
      }
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(PlaybookCanvasLayer, {
      global: {
        plugins: [i18n],
        stubs: {
          VueFlow: {
            props: ['nodes', 'edges'],
            template: '<div data-test="vue-flow-stub"><slot /></div>',
          },
          Background: { template: '<div />' },
          Controls: { template: '<div />' },
          MiniMap: { template: '<div />' },
        },
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Canvas playbook')
    expect(wrapper.text()).toContain('trigger.incident_created')

    await wrapper.get('[data-test="playbook-canvas-drop-zone"]').trigger('drop', {
      clientX: 240,
      clientY: 180,
      preventDefault: vi.fn(),
      dataTransfer: {
        getData: vi.fn((type: string) => (
          type === 'application/x-fortidashboard-playbook-node'
            ? JSON.stringify({
                nodeType: 'case.note',
                config: { template: 'Review incident.' },
              })
            : ''
        )),
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('case.note')

    await wrapper.get('[data-test="playbook-canvas-save"]').trigger('click')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbooks/pb_canvas', expect.objectContaining({
      method: 'PUT',
      headers: expect.objectContaining({
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      }),
    }))
  })
})
