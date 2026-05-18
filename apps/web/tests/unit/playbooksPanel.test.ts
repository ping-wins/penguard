import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PlaybooksPanel from '../../src/components/playbooks/PlaybooksPanel.vue'
import { i18n, setLocale } from '../../src/i18n'
import { approvePlaybookRun, createPlaybook, getPlaybookRun, listPlaybookRuns, listPlaybooks, runPlaybook, simulatePlaybook } from '../../src/services/playbooksClient'
import { useAuthStore } from '../../src/stores/useAuthStore'
import { usePlaybooksStore } from '../../src/stores/usePlaybooksStore'

let pinia: ReturnType<typeof createPinia>

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const portScanPlaybook = {
  id: 'pb_port_scan_triage',
  name: 'Port scan triage',
  description: 'Investigate denied traffic burst.',
  enabled: false,
  nodes: [
    { id: 'trigger', type: 'trigger.incident_created', config: {} },
    { id: 'approval', type: 'approval.required', config: {} },
    { id: 'block', type: 'fortigate.recommend_block', config: {} },
  ],
  edges: [
    { from: 'trigger', to: 'approval' },
    { from: 'approval', to: 'block' },
  ],
}

const nodeTypesResponse = {
  items: [
    { id: 'enrich.ip', label: 'Enrich IP', category: 'enrichment', sensitive: false, dryRunOnly: true, executionMode: 'dry_run', liveAvailable: false, boundary: 'enrichment_read_only', configSchema: {} },
    { id: 'case.note', label: 'Create Case Note', category: 'action', sensitive: false, dryRunOnly: true, executionMode: 'dry_run', liveAvailable: false, boundary: 'case_note', configSchema: {} },
    { id: 'approval.required', label: 'Require Approval', category: 'control', sensitive: false, dryRunOnly: true, executionMode: 'dry_run', liveAvailable: false, boundary: 'approval_gate', configSchema: {} },
    { id: 'fortigate.recommend_block', label: 'Recommend FortiGate Block', category: 'action', sensitive: true, dryRunOnly: true, executionMode: 'dry_run', liveAvailable: false, boundary: 'recommendation_only', configSchema: {} },
    { id: 'webhook.dry_run', label: 'Webhook Dry Run', category: 'action', sensitive: false, dryRunOnly: true, executionMode: 'dry_run', liveAvailable: false, boundary: 'webhook_dry_run', configSchema: {} },
  ],
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setLocale('en-US')
  vi.stubGlobal('localStorage', {
    getItem: vi.fn().mockReturnValue(null),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('SOAR playbooks console', () => {
  it('calls playbook list, simulate, run lookup and approve endpoints with CSRF for mutations', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/soc/playbooks' && init?.method === 'POST') return jsonResponse({
        id: 'pb_custom_triage',
        name: 'Custom triage',
        enabled: false,
        nodes: [{ id: 'trigger', type: 'trigger.incident_created', config: {} }],
        edges: [],
      }, { status: 201 })
      if (url === '/api/soc/playbooks') return jsonResponse([portScanPlaybook])
      if (url === '/api/soc/playbook-runs') return jsonResponse({
        items: [
          { id: 'run_01', incidentId: 'inc_01', playbookId: 'pb_port_scan_triage', status: 'waiting_approval', steps: [] },
        ],
      })
      if (url === '/api/soc/playbook-node-types') return jsonResponse(nodeTypesResponse)
      if (url === '/api/auth/csrf') return jsonResponse({ csrfToken: 'csrf_01' })
      if (url === '/api/soc/playbooks/pb_port_scan_triage/simulate') {
        return jsonResponse({
          dryRun: true,
          valid: true,
          steps: [{ nodeId: 'approval', nodeType: 'approval.required', status: 'waiting_approval', sensitive: true }],
        })
      }
      if (url === '/api/soc/incidents/inc_01/playbooks/pb_port_scan_triage/run') {
        return jsonResponse({
          id: 'run_01',
          incidentId: 'inc_01',
          playbookId: 'pb_port_scan_triage',
          dryRun: true,
          status: 'waiting_approval',
          steps: [{ nodeId: 'approval', nodeType: 'approval.required', status: 'waiting_approval', sensitive: true }],
        })
      }
      if (url === '/api/soc/playbook-runs/run_01') {
        return jsonResponse({ id: 'run_01', status: 'waiting_approval', steps: [] })
      }
      if (url === '/api/soc/playbook-runs/run_01/approve') {
        return jsonResponse({ id: 'run_01', status: 'completed', ticketUpdate: { status: 'contained', incidentId: 'inc_01' }, steps: [] })
      }
      throw new Error(`unexpected url ${url}`)
    })
    vi.stubGlobal('fetch', fetcher)

    await expect(listPlaybooks()).resolves.toEqual([portScanPlaybook])
    fetcher.mockResolvedValueOnce(jsonResponse({ items: [portScanPlaybook] }))
    await expect(listPlaybooks()).resolves.toEqual([portScanPlaybook])
    await expect(listPlaybookRuns()).resolves.toEqual([
      { id: 'run_01', incidentId: 'inc_01', playbookId: 'pb_port_scan_triage', status: 'waiting_approval', steps: [] },
    ])
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    await expect(simulatePlaybook('pb_port_scan_triage')).resolves.toMatchObject({ dryRun: true, valid: true })
    await expect(runPlaybook('inc_01', 'pb_port_scan_triage')).resolves.toMatchObject({ id: 'run_01', status: 'waiting_approval' })
    await expect(getPlaybookRun('run_01')).resolves.toMatchObject({ id: 'run_01', status: 'waiting_approval' })
    await expect(approvePlaybookRun('run_01')).resolves.toMatchObject({ id: 'run_01', status: 'completed' })
    await expect(createPlaybook({
      id: 'pb_custom_triage',
      name: 'Custom triage',
      enabled: false,
      nodes: [{ id: 'trigger', type: 'trigger.incident_created', config: {} }],
      edges: [],
    })).resolves.toMatchObject({ id: 'pb_custom_triage' })

    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbooks', { credentials: 'include' })
    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbook-runs', { credentials: 'include' })
    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbooks/pb_port_scan_triage/simulate', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf_01' }),
    }))
    expect(fetcher).toHaveBeenCalledWith('/api/soc/incidents/inc_01/playbooks/pb_port_scan_triage/run', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf_01' }),
    }))
    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbook-runs/run_01', { credentials: 'include' })
    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbook-runs/run_01/approve', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf_01' }),
    }))
    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbooks', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      }),
      body: expect.stringContaining('pb_custom_triage'),
    }))
  })

  it('store exposes loading, empty, error, node catalog, simulation and run states', async () => {
    let playbookLoads = 0
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/playbook-node-types') return jsonResponse(nodeTypesResponse)
      if (url === '/api/soc/playbooks') {
        playbookLoads += 1
        if (playbookLoads === 1) return jsonResponse([])
        if (playbookLoads === 2) return jsonResponse({ detail: 'SOAR unavailable' }, { status: 503 })
        return jsonResponse([portScanPlaybook])
      }
      if (url === '/api/soc/playbook-runs') return jsonResponse({
        items: [
          { id: 'run_01', status: 'waiting_approval', playbookId: 'pb_port_scan_triage', incidentId: 'inc_01', steps: [] },
        ],
      })
      if (url === '/api/soc/playbooks/pb_port_scan_triage/simulate') return jsonResponse({ dryRun: true, valid: true, steps: [] })
      if (url === '/api/soc/incidents/inc_01/playbooks/pb_port_scan_triage/run') return jsonResponse({ id: 'run_01', status: 'waiting_approval', playbookId: 'pb_port_scan_triage', steps: [] })
      if (url === '/api/soc/playbook-runs/run_01/approve') return jsonResponse({ id: 'run_01', status: 'completed', playbookId: 'pb_port_scan_triage', steps: [] })
      throw new Error(`unexpected url ${url}`)
    })
    vi.stubGlobal('fetch', fetcher)
    useAuthStore().csrfToken = 'csrf_01'

    const store = usePlaybooksStore()
    await store.refresh()
    expect(store.playbooks).toEqual([])
    expect(store.isEmpty).toBe(true)

    await store.refresh()
    expect(store.error).toBe('SOAR unavailable')

    await store.refresh()
    expect(store.playbooks[0].id).toBe('pb_port_scan_triage')
    expect(store.runHistory[0].id).toBe('run_01')
    expect(store.nodeTypeById['fortigate.recommend_block'].boundary).toBe('recommendation_only')
    expect(store.safeActionNodeTypes.map((nodeType) => nodeType.id)).toContain('webhook.dry_run')
    await store.simulate('pb_port_scan_triage')
    expect(store.simulations.pb_port_scan_triage.valid).toBe(true)
    await store.run('inc_01', 'pb_port_scan_triage')
    expect(store.runs.run_01.status).toBe('waiting_approval')
    expect(store.latestRunByPlaybook.pb_port_scan_triage).toBe('run_01')
    await store.approve('run_01')
    expect(store.runs.run_01.status).toBe('completed')
  })

  it('renders playbooks, safety badges, flow details, simulation results and approval run controls', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/playbooks') return jsonResponse([portScanPlaybook])
      if (url === '/api/soc/playbook-node-types') return jsonResponse(nodeTypesResponse)
      if (url === '/api/soc/playbook-runs') return jsonResponse({
        items: [
          {
            id: 'run_older',
            incidentId: 'inc_01',
            playbookId: 'pb_old_waiting',
            dryRun: true,
            status: 'waiting_approval',
            steps: [{ nodeId: 'approval', nodeType: 'approval.required', status: 'waiting_approval', sensitive: true }],
          },
          {
            id: 'run_done',
            incidentId: 'inc_01',
            playbookId: 'pb_port_scan_triage',
            dryRun: true,
            status: 'completed',
            steps: [{ nodeId: 'approval', nodeType: 'approval.required', status: 'completed', sensitive: true }],
          },
        ],
      })
      if (url === '/api/soc/playbooks/pb_port_scan_triage/simulate') {
        return jsonResponse({
          dryRun: true,
          valid: true,
          steps: [
            { nodeId: 'trigger', nodeType: 'trigger.incident_created', status: 'completed', sensitive: false },
            { nodeId: 'approval', nodeType: 'approval.required', status: 'waiting_approval', sensitive: true },
          ],
        })
      }
      if (url === '/api/soc/incidents/inc_01/playbooks/pb_port_scan_triage/run') {
        return jsonResponse({
          id: 'run_01',
          incidentId: 'inc_01',
          playbookId: 'pb_port_scan_triage',
          dryRun: true,
          status: 'waiting_approval',
          steps: [{ nodeId: 'approval', nodeType: 'approval.required', status: 'waiting_approval', sensitive: true }],
        })
      }
      if (url === '/api/soc/playbook-runs/run_01/approve') {
        return jsonResponse({
          id: 'run_01',
          incidentId: 'inc_01',
          playbookId: 'pb_port_scan_triage',
          dryRun: true,
          status: 'completed',
          ticketUpdate: { status: 'contained', incidentId: 'inc_01' },
          steps: [{ nodeId: 'approval', nodeType: 'approval.required', status: 'completed', sensitive: true }],
        })
      }
      if (url === '/api/soc/playbook-runs/run_older/approve') {
        return jsonResponse({
          id: 'run_older',
          incidentId: 'inc_01',
          playbookId: 'pb_old_waiting',
          dryRun: true,
          status: 'completed',
          steps: [{ nodeId: 'approval', nodeType: 'approval.required', status: 'completed', sensitive: true }],
        })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetcher)
    useAuthStore().csrfToken = 'csrf_01'

    const wrapper = mount(PlaybooksPanel, { global: { plugins: [pinia, i18n] } })
    await flushPromises()

    expect(wrapper.text()).toContain('SOAR Playbooks')
    expect(wrapper.get('[data-test="playbook-card-pb_port_scan_triage"]').text()).toContain('Port scan triage')
    expect(wrapper.text()).toContain('Dry-run only')
    expect(wrapper.text()).toContain('Requires approval')
    expect(wrapper.text()).toContain('Sensitive steps')
    expect(wrapper.get('[data-test="playbook-run-history"]').text()).toContain('run_older')
    expect(wrapper.get('[data-test="playbook-run-history"]').text()).toContain('inc_01')
    expect(wrapper.get('[data-test="playbook-run-history"]').text()).toContain('waiting_approval')

    await wrapper.get('[data-test="playbook-card-pb_port_scan_triage"]').trigger('click')
    expect(wrapper.get('[data-test="playbook-detail"]').text()).toContain('trigger.incident_created')
    expect(wrapper.get('[data-test="playbook-detail"]').text()).toContain('trigger → approval')

    await wrapper.get('[data-test="playbook-simulate"]').trigger('click')
    await flushPromises()

    const simulation = wrapper.get('[data-test="playbook-simulation"]').text()
    expect(simulation).toContain('Simulation')
    expect(simulation).toContain('waiting_approval')
    expect(simulation).toContain('approval.required')

    await wrapper.get('[data-test="playbook-run-incident-id"]').setValue('inc_01')
    await wrapper.get('[data-test="playbook-run"]').trigger('click')
    await flushPromises()

    const run = wrapper.get('[data-test="playbook-run-detail"]').text()
    expect(run).toContain('Run run_01')
    expect(run).toContain('waiting_approval')
    expect(run).toContain('approval.required')

    await wrapper.get('[data-test="playbook-approve-run"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="playbook-run-detail"]').text()).toContain('completed')
    expect(wrapper.get('[data-test="playbook-run-detail"]').text()).toContain('Ticket contained')

    await wrapper.get('[data-test="playbook-run-history-approve-run_older"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="playbook-run-history"]').text()).toContain('completed')
    wrapper.unmount()
  })

  it('keeps the legacy panel read-only and points building to the dedicated surface', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/soc/playbooks' && init?.method === 'POST') {
        throw new Error('drawer should not create playbooks directly')
      }
      if (url === '/api/soc/playbooks') return jsonResponse([])
      if (url === '/api/soc/playbook-runs') return jsonResponse({ items: [] })
      if (url === '/api/soc/playbook-node-types') return jsonResponse(nodeTypesResponse)
      throw new Error(`unexpected url ${url}`)
    })
    vi.stubGlobal('fetch', fetcher)
    useAuthStore().csrfToken = 'csrf_01'

    const wrapper = mount(PlaybooksPanel, { global: { plugins: [pinia, i18n] } })
    await flushPromises()

    expect(wrapper.find('[data-test="playbook-builder-save"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="playbook-canvas-builder-hint"]').text()).toContain('dedicated SOAR Playbooks surface')
    wrapper.unmount()
  })
})
