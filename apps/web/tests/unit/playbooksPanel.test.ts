import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PlaybooksPanel from '../../src/components/playbooks/PlaybooksPanel.vue'
import { i18n, setLocale } from '../../src/i18n'
import { approvePlaybookRun, createPlaybook, getPlaybookRun, listPlaybooks, runPlaybook, simulatePlaybook } from '../../src/services/playbooksClient'
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

  it('store exposes loading, empty, error, simulation and run states', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(jsonResponse([]))
      .mockResolvedValueOnce(jsonResponse({ detail: 'SOAR unavailable' }, { status: 503 }))
      .mockResolvedValueOnce(jsonResponse([portScanPlaybook]))
      .mockResolvedValueOnce(jsonResponse({ dryRun: true, valid: true, steps: [] }))
      .mockResolvedValueOnce(jsonResponse({ id: 'run_01', status: 'waiting_approval', steps: [] }))
      .mockResolvedValueOnce(jsonResponse({ id: 'run_01', status: 'completed', steps: [] }))
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
    wrapper.unmount()
  })

  it('builds and saves a linear dry-run playbook from the console', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/soc/playbooks' && init?.method === 'POST') {
        const payload = JSON.parse(String(init.body))
        expect(payload).toMatchObject({
          id: 'pb_custom_triage',
          name: 'Custom triage',
          enabled: false,
          nodes: [
            { id: 'trigger', type: 'trigger.incident_created' },
            { id: 'step_1', type: 'enrich.ip', config: { field: 'entities.sourceIp' } },
            { id: 'step_2', type: 'case.note', config: { template: 'Review source IP.' } },
          ],
          edges: [
            { from: 'trigger', to: 'step_1' },
            { from: 'step_1', to: 'step_2' },
          ],
        })
        return jsonResponse(payload, { status: 201 })
      }
      if (url === '/api/soc/playbooks') return jsonResponse([])
      throw new Error(`unexpected url ${url}`)
    })
    vi.stubGlobal('fetch', fetcher)
    useAuthStore().csrfToken = 'csrf_01'

    const wrapper = mount(PlaybooksPanel, { global: { plugins: [pinia, i18n] } })
    await flushPromises()

    await wrapper.get('[data-test="playbook-builder-id"]').setValue('pb_custom_triage')
    await wrapper.get('[data-test="playbook-builder-name"]').setValue('Custom triage')
    await wrapper.get('[data-test="playbook-builder-step-type"]').setValue('enrich.ip')
    await wrapper.get('[data-test="playbook-builder-step-config"]').setValue('{"field":"entities.sourceIp"}')
    await wrapper.get('[data-test="playbook-builder-add-step"]').trigger('click')
    await wrapper.get('[data-test="playbook-builder-step-type"]').setValue('case.note')
    await wrapper.get('[data-test="playbook-builder-step-config"]').setValue('{"template":"Review source IP."}')
    await wrapper.get('[data-test="playbook-builder-add-step"]').trigger('click')

    expect(wrapper.get('[data-test="playbook-builder-preview"]').text()).toContain('trigger.incident_created → enrich.ip → case.note')
    await wrapper.get('[data-test="playbook-builder-save"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Custom triage')
    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbooks', expect.objectContaining({
      method: 'POST',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf_01' }),
    }))
    wrapper.unmount()
  })
})
