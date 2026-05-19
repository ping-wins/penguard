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
        description: 'Adds a rendered note to the incident timeline.',
        effectSummary: 'Writes a real case note through the SIEM gateway.',
        category: 'action',
        sensitive: false,
        dryRunOnly: true,
        executionMode: 'dry_run',
        liveAvailable: false,
        boundary: 'case_note',
        configSchema: { required: ['template'] },
        exampleConfig: { template: 'Investigate {incident.id}.' },
        requiredInputs: [
          {
            key: 'template',
            label: 'Note template',
            description: 'Timeline note to write.',
          },
        ],
      },
    ]
    store.playbooks = [
      {
        id: 'pb_canvas',
        name: 'Canvas playbook',
        enabled: false,
        system: false,
        nodes: [{ id: 'trigger', type: 'trigger.incident_created', config: {} }],
        edges: [],
      },
      {
        id: 'pb_port_scan_triage',
        name: 'Port Scan Triage',
        enabled: false,
        system: true,
        nodes: [{ id: 'trigger', type: 'trigger.incident_created', config: {} }],
        edges: [],
      },
    ]
    useAuthStore().csrfToken = 'csrf_01'
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders an internal automation node drawer and emits drag payloads from the builder', async () => {
    vi.stubGlobal('fetch', vi.fn())

    const wrapper = mount(PlaybookCanvasLayer, {
      props: { surface: true },
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

    expect(wrapper.get('[data-test="playbook-node-drawer"]').text()).toContain('Automation nodes')
    expect(wrapper.get('[data-test="playbook-node-drawer"]').text()).toContain('Create Case Note')
    expect(wrapper.get('[data-test="playbook-node-drawer"]').text()).toContain('Writes a real case note through the SIEM gateway.')
    expect(wrapper.get('[data-test="playbook-node-drawer"]').text()).toContain('Note template')
    expect(wrapper.find('[data-test="playbook-node-drawer-node-trigger.incident_created"]').exists()).toBe(false)

    const dataTransfer = {
      setData: vi.fn(),
      effectAllowed: '',
    }

    await wrapper.get('[data-test="playbook-node-drawer-node-case.note"]').trigger('dragstart', {
      dataTransfer,
    })

    expect(dataTransfer.setData).toHaveBeenCalledWith(
      'application/x-penguard-playbook-node',
      expect.stringContaining('"nodeType":"case.note"'),
    )
    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', 'case.note')
    expect(dataTransfer.effectAllowed).toBe('copy')
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
      props: { surface: true },
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
          type === 'application/x-penguard-playbook-node'
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

  it('lists existing playbooks and deletes only custom playbooks', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/soc/playbooks/pb_canvas' && init?.method === 'DELETE') {
        return jsonResponse({ id: 'pb_canvas', deleted: true })
      }
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetcher)
    vi.stubGlobal('confirm', vi.fn(() => true))

    const wrapper = mount(PlaybookCanvasLayer, {
      props: { surface: true },
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

    expect(wrapper.get('[data-test="playbook-library-card-pb_canvas"]').text()).toContain('Canvas playbook')
    expect(wrapper.get('[data-test="playbook-library-card-pb_port_scan_triage"]').text()).toContain('System')
    expect(wrapper.find('[data-test="playbook-delete-pb_port_scan_triage"]').exists()).toBe(false)

    await wrapper.get('[data-test="playbook-delete-pb_canvas"]').trigger('click')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbooks/pb_canvas', expect.objectContaining({
      method: 'DELETE',
      headers: expect.objectContaining({
        'X-CSRF-Token': 'csrf_01',
      }),
    }))
    expect(usePlaybooksStore().playbooks.map((playbook) => playbook.id)).not.toContain('pb_canvas')
  })

  it('can expand the builder to fullscreen and restore it with Escape', async () => {
    vi.stubGlobal('fetch', vi.fn())
    const host = document.createElement('div')
    document.body.appendChild(host)

    const wrapper = mount(PlaybookCanvasLayer, {
      attachTo: host,
      props: { surface: true },
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

    const layerBefore = document.querySelector('[data-test="playbook-canvas-layer"]')
    expect(layerBefore?.className).toContain('relative')
    expect(layerBefore?.className).not.toContain('fixed')

    await wrapper.get('[data-test="playbook-canvas-fullscreen-toggle"]').trigger('click')
    await flushPromises()

    const fullscreenLayer = document.querySelector('[data-test="playbook-canvas-layer"]')
    const fullscreenToggle = document.querySelector<HTMLButtonElement>('[data-test="playbook-canvas-fullscreen-toggle"]')
    expect(fullscreenLayer?.className).toContain('fixed')
    expect(fullscreenLayer?.className).toContain('inset-4')
    expect(fullscreenToggle?.title).toBe('Exit fullscreen')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()

    const restoredLayer = document.querySelector('[data-test="playbook-canvas-layer"]')
    const restoredToggle = document.querySelector<HTMLButtonElement>('[data-test="playbook-canvas-fullscreen-toggle"]')
    expect(restoredLayer?.className).toContain('relative')
    expect(restoredLayer?.className).not.toContain('fixed')
    expect(restoredToggle?.title).toBe('Enter fullscreen')

    wrapper.unmount()
    host.remove()
  })

  it('renders as a main surface without a workspace move handle', async () => {
    vi.stubGlobal('fetch', vi.fn())

    const wrapper = mount(PlaybookCanvasLayer, {
      props: { surface: true },
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

    const layer = wrapper.get('[data-test="playbook-canvas-layer"]')
    expect(layer.classes()).toContain('relative')
    expect(layer.classes()).toContain('h-full')
    expect(layer.attributes('style')).toBeUndefined()
    expect(wrapper.find('[data-test="playbook-canvas-drag-handle"]').exists()).toBe(false)
  })
})
