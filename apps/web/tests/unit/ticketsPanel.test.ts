import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import TicketsPanel from '../../src/components/tickets/TicketsPanel.vue'
import { i18n, setLocale } from '../../src/i18n'
import { queryClient } from '../../src/services/queryClient'
import { useAuthStore } from '../../src/stores/useAuthStore'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null

  constructor(public url: string, public init?: EventSourceInit) {
    FakeEventSource.instances.push(this)
  }

  addEventListener() {}
  close() {}
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

const portScanTicket = {
  id: 'inc_port_scan',
  ruleId: 'network_scan',
  title: 'Possible port scan',
  severity: 'high',
  status: 'open',
  source: 'kowalski',
  origin: { kind: 'fortigate.syslog' },
  attributes: {
    source: 'fortigate.syslog',
    detection: {
      ruleId: 'network_scan',
      title: 'Possible port scan',
      summary: 'Network scan telemetry was observed.',
      matchedEventType: 'network.scan',
      observedCount: 1,
      thresholds: [],
    },
    attackType: 'allowed_port_scan',
    sourceIp: '198.51.100.10',
    destinationIp: '192.0.2.20',
    destinationPorts: [22, 23, 25, 53, 80, 443, 445, 3389, 5900, 8080, 10001, 10002, 10003, 10004, 10005, 10006, 10007, 10008, 10009, 10010],
    uniqueDestinationPortCount: 20,
    scanWindowSeconds: 60,
    integrationId: 'int_fgt_test',
    policyId: '1',
    service: 'tcp/10010',
    relatedEventIds: ['evt_a', 'evt_b'],
  },
  entities: {
    sourceIp: '198.51.100.10',
    destinationIp: '192.0.2.20',
    integrationId: 'int_fgt_test',
    deviceName: 'FortiGate Test',
  },
  summary: 'Network scan telemetry was observed.',
  createdAt: '2026-05-20T03:28:38.088203Z',
  timeline: [
    {
      id: 'tl_created',
      type: 'created',
      status: null,
      message: 'Incident created from event evt_a.',
      occurredAt: '2026-05-20T03:28:38.088216Z',
    },
  ],
  eventIds: ['evt_a'],
  triageLevel: 'T3',
  ticketStatus: 'new',
  assigneeUserId: null,
  aiAnalysisId: null,
}

const triageContext = {
  incidentId: 'inc_port_scan',
  ruleId: 'network_scan',
  alertFamily: 'network.scan',
  attackType: 'allowed_port_scan',
  severity: 'high',
  confidence: 'high',
  recommendedTriageLevel: 'T3',
  recommendedTicketStatus: 'investigating',
  summary: 'Network scan telemetry was observed.',
  evidence: [
    {
      id: 'ev_unique_destination_ports',
      type: 'threshold',
      label: 'Unique destination ports',
      value: 20,
      threshold: { operator: 'gte', value: 20, windowSeconds: 60 },
      severity: 'high',
      source: 'siem_kowalski',
    },
  ],
  entities: [],
  impactedAssets: [],
  mitreMappings: [
    {
      tacticId: 'TA0007',
      tacticName: 'Discovery',
      techniqueId: 'T1046',
      techniqueName: 'Network Service Discovery',
      subtechniqueId: null,
      subtechniqueName: null,
      confidence: 'high',
      reason: 'Unique destination port evidence crossed the scan threshold.',
      evidenceIds: ['ev_unique_destination_ports'],
    },
  ],
  responseCandidates: [
    {
      id: 'fortigate.temporary_source_destination_block',
      type: 'fortigate',
      label: 'Temporarily block source to target',
      description: 'Create a Penguard-owned temporary block scoped to the observed source and destination after approval.',
      riskLevel: 'high',
      requiresApproval: true,
      availableNow: true,
      providerRequired: 'fortigate',
      reason: 'FortiGate integration, source IP and destination IP are present.',
      parameters: {
        integrationId: 'int_fgt_test',
        sourceIp: '198.51.100.10',
        destinationIp: '192.0.2.20',
      },
      mappedMitreTechniqueIds: ['T1046'],
      playbookTemplateIds: ['pb_network_scan_triage'],
    },
  ],
  playbookTemplates: [
    {
      templateId: 'pb_network_scan_triage',
      label: 'Network scan triage',
      reason: 'Network scan evidence is present and maps to service discovery.',
      confidence: 'high',
      requiredCandidateIds: ['fortigate.temporary_source_destination_block'],
      parameters: {
        sourceIp: '198.51.100.10',
        destinationIp: '192.0.2.20',
        integrationId: 'int_fgt_test',
      },
      requiresApproval: true,
    },
  ],
  missingData: [],
  generatedAt: '2026-05-20T03:28:39.000Z',
}

describe('TicketsPanel incident drawer', () => {
  beforeEach(() => {
    const pinia = createPinia()
    setActivePinia(pinia)
    queryClient.clear()
    setLocale('en-US')
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('localStorage', {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    })
    const authStore = useAuthStore()
    authStore.isAuthenticated = true
    authStore.csrfToken = 'csrf_01'
    authStore.user = {
      id: 'usr_admin',
      email: 'admin@example.com',
      displayName: 'SOC Admin',
      roles: ['admin'],
      isAdmin: true,
      permissions: ['*'],
    }
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens a port-scan incident on a concise guided summary instead of raw operational blocks', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') return jsonResponse({ items: [portScanTicket] })
      if (url === '/api/integrations') return jsonResponse({ items: [] })
      if (url === '/api/soc/incidents/inc_port_scan/triage-context') return jsonResponse(triageContext)
      throw new Error(`unexpected url ${url}`)
    }))

    const wrapper = mount(TicketsPanel, {
      global: { plugins: [i18n] },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_port_scan"]').trigger('click')
    await flushPromises()

    const drawer = wrapper.get('[data-test="ticket-incident-drawer"]')
    expect(drawer.get('[data-test="ticket-drawer-step-summary"]').classes()).toContain('bg-theme-primary/15')
    expect(drawer.get('[data-test="ticket-drawer-summary-step"]').text()).toContain('Possible port scan')
    expect(drawer.get('[data-test="ticket-drawer-summary-step"]').text()).toContain('198.51.100.10')
    expect(drawer.get('[data-test="ticket-drawer-summary-step"]').text()).toContain('192.0.2.20')
    expect(drawer.get('[data-test="ticket-drawer-summary-step"]').text()).toContain('20')
    expect(drawer.get('[data-test="ticket-drawer-summary-step"]').text()).toContain('60s')

    expect(drawer.find('[data-test="ticket-policy-integration"]').exists()).toBe(false)
    expect(drawer.find('[data-test="ticket-create-fortiweb-block-review"]').exists()).toBe(false)
    expect(drawer.find('[data-test="ticket-raw-entities"]').exists()).toBe(false)
    expect(drawer.find('[data-test="ticket-raw-timeline"]').exists()).toBe(false)
  })

  it('keeps analysis focused on evidence and hides containment provider actions', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') return jsonResponse({ items: [portScanTicket] })
      if (url === '/api/integrations') return jsonResponse({ items: [] })
      if (url === '/api/soc/incidents/inc_port_scan/triage-context') return jsonResponse(triageContext)
      throw new Error(`unexpected url ${url}`)
    }))

    const wrapper = mount(TicketsPanel, {
      global: { plugins: [i18n] },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_port_scan"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="ticket-drawer-step-analysis"]').trigger('click')
    await flushPromises()

    const drawer = wrapper.get('[data-test="ticket-incident-drawer"]')
    expect(drawer.get('[data-test="ticket-drawer-analysis-step"]').text()).toContain('Unique destination ports')
    expect(drawer.get('[data-test="ticket-drawer-analysis-step"]').text()).toContain('T1046')
    expect(drawer.find('[data-test="ticket-create-fortiweb-block-review"]').exists()).toBe(false)
    expect(drawer.find('[data-test="ticket-policy-integration"]').exists()).toBe(false)
  })

  it('shows recommended playbook containment separately from evidence and raw details', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') return jsonResponse({ items: [portScanTicket] })
      if (url === '/api/integrations') return jsonResponse({ items: [] })
      if (url === '/api/soc/incidents/inc_port_scan/triage-context') return jsonResponse(triageContext)
      throw new Error(`unexpected url ${url}`)
    }))

    const wrapper = mount(TicketsPanel, {
      global: { plugins: [i18n] },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_port_scan"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="ticket-drawer-step-containment"]').trigger('click')
    await flushPromises()

    const drawer = wrapper.get('[data-test="ticket-incident-drawer"]')
    expect(drawer.get('[data-test="ticket-drawer-containment-step"]').text()).toContain('Network scan triage')
    expect(drawer.get('[data-test="ticket-drawer-containment-step"]').text()).toContain('FortiGate')
    expect(drawer.get('[data-test="ticket-drawer-containment-step"]').text()).not.toContain('Unique destination ports')
    expect(drawer.find('[data-test="ticket-raw-entities"]').exists()).toBe(false)
  })

  it('reveals raw entities and timeline only when the analyst asks for raw details', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') return jsonResponse({ items: [portScanTicket] })
      if (url === '/api/integrations') return jsonResponse({ items: [] })
      if (url === '/api/soc/incidents/inc_port_scan/triage-context') return jsonResponse(triageContext)
      throw new Error(`unexpected url ${url}`)
    }))

    const wrapper = mount(TicketsPanel, {
      global: { plugins: [i18n] },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_port_scan"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-test="ticket-raw-entities"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="ticket-raw-timeline"]').exists()).toBe(false)

    await wrapper.get('[data-test="ticket-toggle-raw-details"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="ticket-raw-entities"]').text()).toContain('sourceIp')
    expect(wrapper.get('[data-test="ticket-raw-timeline"]').text()).toContain('Incident created from event')
  })
})
