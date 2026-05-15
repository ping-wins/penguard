import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WidgetFirewallPolicies from '../../src/components/widgets/WidgetFirewallPolicies.vue'
import WidgetHealth from '../../src/components/widgets/WidgetHealth.vue'
import WidgetAnomalyHighlights from '../../src/components/widgets/WidgetAnomalyHighlights.vue'
import WidgetInterfaceHealth from '../../src/components/widgets/WidgetInterfaceHealth.vue'
import WidgetRecentEvents from '../../src/components/widgets/WidgetRecentEvents.vue'
import WidgetRiskPosture from '../../src/components/widgets/WidgetRiskPosture.vue'
import WidgetThreats from '../../src/components/widgets/WidgetThreats.vue'
import WidgetGenericData from '../../src/components/widgets/WidgetGenericData.vue'
import WidgetSoarPlaybookRunHistory from '../../src/components/widgets/soc/WidgetSoarPlaybookRunHistory.vue'
import TicketsPanel from '../../src/components/tickets/TicketsPanel.vue'
import { i18n, setLocale } from '../../src/i18n'
import { useAuthStore } from '../../src/stores/useAuthStore'
import { sourceBadgeFor } from '../../src/utils/sourceBadges'

let pinia: ReturnType<typeof createPinia>

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  setLocale('en-US')
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FortiGate widget renderers', () => {
  it('renders live FortiGate identity and health fields', () => {
    const wrapper = mount(WidgetHealth, {
      props: {
        data: {
          hostname: 'FGT-LIVE-01',
          model: 'FortiGate',
          version: 'v7.6.6',
          cpu: 1,
          memory: 45,
          sessions: 25,
          uptimeSeconds: 92420,
        },
      },
    })

    expect(wrapper.text()).toContain('FGT-LIVE-01')
    expect(wrapper.text()).toContain('FortiGate')
    expect(wrapper.text()).toContain('v7.6.6')
    expect(wrapper.text()).toContain('1%')
    expect(wrapper.text()).toContain('45%')
    expect(wrapper.text()).toContain('25')
    expect(wrapper.text()).toContain('Uptime')
    expect(wrapper.text()).toContain('1d 1h 40m')
  })

  it('renders generic SOC bar, feed and status-list preset payloads', () => {
    const bar = mount(WidgetGenericData, {
      props: {
        catalogId: 'soc-incidents-by-severity',
        data: {
          items: [
            { severity: 'high', count: 2 },
            { severity: 'medium', count: 1 },
          ],
          total: 3,
        },
      },
    })

    expect(bar.text()).toContain('Incidents by Severity')
    expect(bar.text()).toContain('high')
    expect(bar.text()).toContain('2')

    const feed = mount(WidgetGenericData, {
      props: {
        catalogId: 'soc-recent-incidents',
        data: {
          incidents: [{
            title: 'Possible port scan',
            severity: 'high',
            status: 'open',
            summary: 'Multiple denied connections',
          }],
        },
      },
    })

    expect(feed.text()).toContain('Recent Incidents')
    expect(feed.text()).toContain('Possible port scan')
    expect(feed.text()).toContain('open')

    const statusList = mount(WidgetGenericData, {
      props: {
        catalogId: 'xdr-endpoint-health',
        data: {
          endpoints: [{ hostname: 'win-lab-01', health: 'warning', os: 'Windows' }],
          summary: { warning: 1 },
          total: 1,
        },
      },
    })

    expect(statusList.text()).toContain('Endpoint Health')
    expect(statusList.text()).toContain('win-lab-01')
    expect(statusList.text()).toContain('warning')
  })

  it('renders provenance badges for generic SOC rows with existing metadata', () => {
    const feed = mount(WidgetGenericData, {
      props: {
        catalogId: 'soc-recent-incidents',
        data: {
          incidents: [
            {
              title: 'Seeded port scan',
              severity: 'high',
              status: 'open',
              summary: 'Demo replay event',
              source: 'kowalski',
              origin: { kind: 'demo.replay' },
              attributes: { source: 'demo.replay', demoRunId: 'demo_01' },
            },
            {
              title: 'Simulated endpoint beacon',
              severity: 'medium',
              status: 'open',
              summary: 'Simulator event',
              attributes: { source: 'simulator' },
            },
            {
              title: 'Live FortiGate deny',
              severity: 'high',
              status: 'open',
              summary: 'Forward traffic log',
              provider: 'fortigate',
            },
          ],
        },
      },
    })

    const rows = feed.findAll('[data-test="generic-feed-row"]')
    expect(rows[0].text()).toContain('Seeded demo')
    expect(rows[0].text()).toContain('open')
    expect(rows[1].text()).toContain('Simulator')
    expect(rows[2].text()).toContain('Live')
  })

  it('maps provenance fields to source badge labels without cluttering unknown rows', () => {
    expect(sourceBadgeFor({ attributes: { demoRunId: 'demo_01' } })?.label).toBe('Seeded demo')
    expect(sourceBadgeFor({ origin: { kind: 'demo.replay' } })?.label).toBe('Seeded demo')
    expect(sourceBadgeFor({ attributes: { source: 'demo.replay' } })?.label).toBe('Seeded demo')
    expect(sourceBadgeFor({ source: 'simulator' })?.label).toBe('Simulator')
    expect(sourceBadgeFor({ providerMode: 'scripted' })?.label).toBe('Scripted AI')
    expect(sourceBadgeFor({ rawOutput: 'scripted' })?.label).toBe('Scripted AI')
    expect(sourceBadgeFor({ raw_output: 'scripted' })?.label).toBe('Scripted AI')
    expect(sourceBadgeFor({ origin: { kind: 'fortigate' } })?.label).toBe('Live')
    expect(sourceBadgeFor({ source: 'manual' })).toBeNull()
    expect(sourceBadgeFor(null)).toBeNull()
  })

  it('renders a scripted AI badge when ticket analysis exposes scripted provider metadata', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') {
        return jsonResponse({
          items: [{
            id: 'inc_01',
            ruleId: 'port_scan',
            title: 'Possible port scan',
            severity: 'high',
            status: 'open',
            source: 'kowalski',
            entities: {},
            summary: 'Multiple denied connections',
            createdAt: '2026-05-12T10:00:00Z',
            timeline: [],
            eventIds: [],
            triageLevel: 'T1',
            ticketStatus: 'new',
            assigneeUserId: null,
            aiAnalysisId: null,
          }],
        })
      }
      if (url === '/api/soc/incidents/inc_01/analyze') {
        return jsonResponse({
          id: 'aian_01',
          incidentId: 'inc_01',
          headline: 'Scripted analysis',
          summary: 'Deterministic fallback analysis.',
          riskScore: 82,
          suggestedTriage: 'T1',
          suggestedTicketStatus: 'investigating',
          indicatorsOfCompromise: [],
          nextSteps: [],
          references: [],
          provider: 'scripted',
        })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(TicketsPanel, {
      global: {
        plugins: [pinia, i18n],
      },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_01"]').trigger('click')
    await wrapper.get('[data-test="ticket-ai-analyze"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="ticket-ai-analysis"]').text()).toContain('Scripted AI')
    wrapper.unmount()
  })

  it('renders detection explanation metadata in the ticket drawer', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') {
        return jsonResponse({
          items: [{
            id: 'inc_01',
            ruleId: 'denied_traffic_burst',
            title: 'Denied traffic burst',
            severity: 'high',
            status: 'open',
            source: 'kowalski',
            origin: { kind: 'demo.replay' },
            attributes: {
              attackType: 'port_scan',
              count: 42,
              detection: {
                ruleId: 'denied_traffic_burst',
                title: 'Denied traffic burst',
                summary: 'Denied network traffic exceeded the configured burst threshold.',
                matchedEventType: 'network.deny',
                observedCount: 42,
                thresholds: [{ path: 'attributes.count', operator: 'gte', value: 20 }],
              },
            },
            entities: { sourceIp: '203.0.113.77', destinationIp: '192.168.0.50' },
            summary: 'Multiple denied connections',
            createdAt: '2026-05-12T10:00:00Z',
            timeline: [],
            eventIds: ['evt_01'],
            triageLevel: 'T1',
            ticketStatus: 'new',
            assigneeUserId: null,
            aiAnalysisId: null,
          }],
        })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(TicketsPanel, {
      global: {
        plugins: [pinia, i18n],
      },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_01"]').trigger('click')
    await flushPromises()

    const explanation = wrapper.get('[data-test="ticket-detection-explanation"]').text()
    expect(explanation).toContain('Detection explanation')
    expect(explanation).toContain('denied_traffic_burst')
    expect(explanation).toContain('network.deny')
    expect(explanation).toContain('42')
    expect(explanation).toContain('attributes.count gte 20')
    expect(explanation).toContain('port_scan')
    wrapper.unmount()
  })

  it('renders deterministic MITRE triage context in the ticket drawer', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') {
        return jsonResponse({
          items: [{
            id: 'inc_01',
            ruleId: 'network_scan',
            title: 'Possible port scan',
            severity: 'high',
            status: 'open',
            source: 'kowalski',
            attributes: {
              attackType: 'allowed_port_scan',
              uniqueDestinationPortCount: 20,
            },
            entities: { sourceIp: '192.0.2.10', destinationIp: '198.51.100.20' },
            summary: 'Network scan telemetry was observed.',
            createdAt: '2026-05-12T10:00:00Z',
            timeline: [],
            eventIds: ['evt_01'],
            triageLevel: 'T1',
            ticketStatus: 'new',
            assigneeUserId: null,
            aiAnalysisId: null,
          }],
        })
      }
      if (url === '/api/soc/incidents/inc_01/triage-context') {
        return jsonResponse({
          incidentId: 'inc_01',
          ruleId: 'network_scan',
          alertFamily: 'network.scan',
          attackType: 'allowed_port_scan',
          severity: 'high',
          confidence: 'high',
          recommendedTriageLevel: 'T1',
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
              description: 'Create a FortiDashboard-owned temporary block scoped to the observed source and destination after approval.',
              riskLevel: 'high',
              requiresApproval: true,
              availableNow: true,
              providerRequired: 'fortigate',
              reason: 'FortiGate integration, source IP and destination IP are present.',
              parameters: {},
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
              parameters: {},
              requiresApproval: true,
            },
          ],
          missingData: [],
          generatedAt: '2026-05-15T12:00:00Z',
        })
      }
      if (url === '/api/soc/incidents/inc_01/playbook-recommendations/pb_network_scan_triage/instantiate') {
        return jsonResponse({
          ticketId: 'inc_01',
          playbook: {
            id: 'pb_tpl_01',
            name: 'Network scan triage — Possible port scan',
            enabled: false,
            nodes: [
              { id: 'trigger', type: 'trigger.incident_created' },
              { id: 'temporary_block', type: 'fortigate.temporary_block' },
            ],
            edges: [{ from: 'trigger', to: 'temporary_block' }],
          },
          simulation: {
            dryRun: true,
            valid: true,
            steps: [
              {
                nodeId: 'temporary_block',
                nodeType: 'fortigate.temporary_block',
                status: 'waiting_approval',
                sensitive: true,
              },
            ],
          },
          suggestion: {
            incidentId: 'inc_01',
            provider: 'deterministic',
            summary: 'Network scan evidence is present.',
            steps: [
              {
                title: 'Prepare FortiGate temporary block',
                description: 'Create policy review after approval.',
                playbookNodeType: 'fortigate.temporary_block',
                severity: 'high',
                requiresApproval: true,
              },
            ],
            playbookDraftId: 'pb_tpl_01',
          },
        })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(TicketsPanel, {
      global: {
        plugins: [pinia, i18n],
      },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_01"]').trigger('click')
    await flushPromises()

    const triageContext = wrapper.get('[data-test="ticket-triage-context"]').text()
    expect(triageContext).toContain('Deterministic triage')
    expect(triageContext).toContain('network.scan')
    expect(triageContext).toContain('T1046')
    expect(triageContext).toContain('Network Service Discovery')
    expect(triageContext).toContain('Unique destination ports')
    expect(triageContext).toContain('Temporarily block source to target')
    expect(triageContext).toContain('Network scan triage')

    await wrapper.get('[data-test="ticket-instantiate-template-pb_network_scan_triage"]').trigger('click')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith(
      '/api/soc/incidents/inc_01/playbook-recommendations/pb_network_scan_triage/instantiate',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(wrapper.get('[data-test="ticket-draft-playbook-result"]').text()).toContain('pb_tpl_01')
    wrapper.unmount()
  })

  it('approves a paused containment run from the ticket drawer', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/soc/tickets') {
        return jsonResponse({
          items: [{
            id: 'inc_01',
            ruleId: 'port_scan',
            title: 'Possible port scan',
            severity: 'high',
            status: 'open',
            source: 'kowalski',
            entities: {},
            summary: 'Multiple denied connections',
            createdAt: '2026-05-12T10:00:00Z',
            timeline: [],
            eventIds: [],
            triageLevel: 'T1',
            ticketStatus: 'investigating',
            assigneeUserId: null,
            aiAnalysisId: null,
          }],
        })
      }
      if (url === '/api/soc/incidents/inc_01/containment-suggestions') {
        return jsonResponse({
          incidentId: 'inc_01',
          summary: 'Contain the suspicious activity.',
          playbookDraftId: null,
          steps: [{
            title: 'Block outbound beacon',
            description: 'Draft a dry-run containment step.',
            playbookNodeType: 'firewall.block_ip',
            severity: 'high',
            requiresApproval: true,
          }],
        })
      }
      if (url === '/api/soc/tickets/inc_01/draft-playbook') {
        return jsonResponse({
          ticketId: 'inc_01',
          playbook: {
            id: 'pb_01',
            name: 'AI containment draft',
            enabled: false,
            nodes: [],
            edges: [],
          },
          simulation: {
            dryRun: true,
            valid: true,
            steps: [{ nodeId: 'approve_01', nodeType: 'approval.required', status: 'waiting', sensitive: true }],
          },
          suggestion: {
            incidentId: 'inc_01',
            summary: 'Contain the suspicious activity.',
            playbookDraftId: null,
            steps: [],
          },
        })
      }
      if (url === '/api/soc/tickets/inc_01/apply-containment') {
        return jsonResponse({
          ticketId: 'inc_01',
          playbookId: 'pb_01',
          ticket: null,
          ticketStatus: 'investigating',
          run: {
            id: 'run_01',
            incidentId: 'inc_01',
            playbookId: 'pb_01',
            dryRun: true,
            status: 'waiting_approval',
            steps: [],
            createdAt: '2026-05-12T10:00:00Z',
          },
        })
      }
      if (url === '/api/soc/playbook-runs/run_01/approve') {
        return jsonResponse({
          id: 'run_01',
          incidentId: 'inc_01',
          playbookId: 'pb_01',
          dryRun: true,
          status: 'completed',
          steps: [],
          ticketUpdate: {
            status: 'contained',
            incidentId: 'inc_01',
            ticket: {
              id: 'inc_01',
              ruleId: 'port_scan',
              title: 'Possible port scan',
              severity: 'high',
              status: 'open',
              source: 'kowalski',
              entities: {},
              summary: 'Multiple denied connections',
              createdAt: '2026-05-12T10:00:00Z',
              timeline: [],
              eventIds: [],
              triageLevel: 'T1',
              ticketStatus: 'contained',
              assigneeUserId: null,
              aiAnalysisId: null,
            },
          },
        })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(TicketsPanel, {
      global: {
        plugins: [pinia, i18n],
      },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_01"]').trigger('click')
    await wrapper.get('[data-test="ticket-ai-containment"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="ticket-draft-playbook"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="ticket-apply-playbook"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="ticket-approve-playbook"]').text()).toContain('Approve')

    await wrapper.get('[data-test="ticket-approve-playbook"]').trigger('click')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith(
      '/api/soc/playbook-runs/run_01/approve',
      expect.objectContaining({ method: 'POST', credentials: 'include' }),
    )
    expect(wrapper.get('[data-test="ticket-containment-result"]').text()).toContain('Threat contained')
    wrapper.unmount()
  })

  it('links a FortiGate policy review to a ticket containment run', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const containedTicket = {
      id: 'inc_01',
      ruleId: 'port_scan',
      title: 'Possible allowed port scan',
      severity: 'high',
      status: 'open',
      source: 'kowalski',
      attributes: {
        integrationId: 'int_fgt_lab',
        sourceIp: '192.0.2.50',
        destinationIp: '198.51.100.10',
        service: 'ALL',
      },
      entities: {},
      summary: 'Multiple accepted connections',
      createdAt: '2026-05-12T10:00:00Z',
      timeline: [],
      eventIds: [],
      triageLevel: 'T1',
      ticketStatus: 'contained',
      assigneeUserId: null,
      aiAnalysisId: null,
    }
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/soc/tickets') {
        return jsonResponse({
          items: [{
            ...containedTicket,
            ticketStatus: 'investigating',
          }],
        })
      }
      if (url === '/api/soc/incidents/inc_01/containment-suggestions') {
        return jsonResponse({
          incidentId: 'inc_01',
          summary: 'Block the scanner temporarily through FortiGate.',
          playbookDraftId: null,
          steps: [{
            title: 'Temporary FortiGate block',
            description: 'Create a governed FortiGate policy request.',
            playbookNodeType: 'fortigate.temporary_block',
            severity: 'high',
            requiresApproval: true,
          }],
        })
      }
      if (url === '/api/soc/tickets/inc_01/draft-playbook') {
        return jsonResponse({
          ticketId: 'inc_01',
          playbook: {
            id: 'pb_01',
            name: 'AI containment draft',
            enabled: false,
            nodes: [],
            edges: [],
          },
          simulation: {
            dryRun: true,
            valid: true,
            steps: [{ nodeId: 'block', nodeType: 'fortigate.temporary_block', status: 'waiting', sensitive: true }],
          },
          suggestion: {
            incidentId: 'inc_01',
            summary: 'Block the scanner temporarily through FortiGate.',
            playbookDraftId: null,
            steps: [],
          },
        })
      }
      if (url === '/api/soc/tickets/inc_01/apply-containment') {
        return jsonResponse({
          ticketId: 'inc_01',
          playbookId: 'pb_01',
          ticket: null,
          ticketStatus: 'investigating',
          run: {
            id: 'run_01',
            incidentId: 'inc_01',
            playbookId: 'pb_01',
            dryRun: true,
            status: 'waiting_approval',
            steps: [{ nodeId: 'block', nodeType: 'fortigate.temporary_block', status: 'waiting', sensitive: true }],
            createdAt: '2026-05-12T10:00:00Z',
          },
        })
      }
      if (url === '/api/soc/playbook-runs/run_01/approve') {
        return jsonResponse({
          id: 'run_01',
          incidentId: 'inc_01',
          playbookId: 'pb_01',
          dryRun: true,
          status: 'completed',
          policyReviewRequired: true,
          steps: [{ nodeId: 'block', nodeType: 'fortigate.temporary_block', status: 'completed', sensitive: true }],
        })
      }
      if (url === '/api/soc/playbook-runs/run_01/policy-review') {
        expect(init?.method).toBe('POST')
        expect(JSON.parse(String(init?.body))).toMatchObject({
          integrationId: 'int_fgt_lab',
          sourceIp: '192.0.2.50',
          destinationIp: '198.51.100.10',
          sourceInterface: 'port2',
          destinationInterface: 'port3',
          scope: 'source_destination',
          durationMinutes: 30,
        })
        return jsonResponse({
          request_id: 'fgpcr_01',
          status: 'pending_review',
          intent: 'temporary_block',
          scope: 'source_destination',
          integration_id: 'int_fgt_lab',
          existing_policy_count: 3,
          owned_policy_count: 1,
          proposed_policy_name: 'FD_TMP_BLOCK_192_0_2_50_TO_198_51_100_10',
          placement: 'before first FortiDashboard-owned lab allow/log policy',
          warnings: [],
          changes: [
            { operation: 'create', object_type: 'firewall.address', name: 'FD_ADDR_192_0_2_50', payload: {} },
            { operation: 'create', object_type: 'firewall.policy', name: 'FD_TMP_BLOCK_192_0_2_50_TO_198_51_100_10', payload: {} },
          ],
          review_hash: 'hash_01',
          runId: 'run_01',
          incidentId: 'inc_01',
        })
      }
      if (url === '/api/soc/playbook-runs/run_01/policy-apply') {
        expect(init?.method).toBe('POST')
        expect(JSON.parse(String(init?.body))).toMatchObject({
          integrationId: 'int_fgt_lab',
          requestId: 'fgpcr_01',
          reviewHash: 'hash_01',
        })
        return jsonResponse({
          runId: 'run_01',
          incidentId: 'inc_01',
          policy: {
            request_id: 'fgpcr_01',
            status: 'applied',
            applied_changes: [{ name: 'FD_TMP_BLOCK_192_0_2_50_TO_198_51_100_10' }],
          },
          ticketUpdate: {
            status: 'contained',
            incidentId: 'inc_01',
            ticket: containedTicket,
          },
        })
      }
      return jsonResponse({})
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(TicketsPanel, {
      global: {
        plugins: [pinia, i18n],
      },
    })

    await flushPromises()
    await wrapper.get('[data-test="ticket-card-inc_01"]').trigger('click')
    await wrapper.get('[data-test="ticket-ai-containment"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="ticket-draft-playbook"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="ticket-apply-playbook"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="ticket-approve-playbook"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="ticket-policy-review"]').text()).toContain('FortiGate policy review')

    await wrapper.get('[data-test="ticket-create-policy-review"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="ticket-policy-review"]').text()).toContain('FD_TMP_BLOCK_192_0_2_50_TO_198_51_100_10')

    await wrapper.get('[data-test="ticket-apply-policy-review"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="ticket-policy-review"]').text()).toContain('FortiGate policy applied')
    wrapper.unmount()
  })

  it('explains empty SOC preset states with first-setup next actions', () => {
    const incidents = mount(WidgetGenericData, {
      props: {
        catalogId: 'soc-incidents-by-severity',
        data: { items: [], total: 0 },
      },
    })
    const endpoints = mount(WidgetGenericData, {
      props: {
        catalogId: 'xdr-endpoint-health',
        data: { endpoints: [], summary: {}, total: 0 },
      },
    })

    expect(incidents.text()).toContain('No incidents yet')
    expect(incidents.text()).toContain('Connect a SIEM or FortiGate provider')
    expect(endpoints.text()).toContain('No endpoints yet')
    expect(endpoints.text()).toContain('run agent_private')
  })

  it('does not render missing FortiGate uptime as zero seconds', () => {
    const wrapper = mount(WidgetHealth, {
      props: {
        data: {
          hostname: 'FGT-LIVE-01',
          model: 'FortiGate',
          version: 'v7.6.6',
          cpu: 1,
          memory: 45,
          sessions: 25,
          uptimeSeconds: null,
        },
      },
    })

    expect(wrapper.text()).toContain('Uptime')
    expect(wrapper.text()).toContain('--')
    expect(wrapper.text()).not.toContain('0s')
  })

  it('renders normalized FortiGate threat fields from the API', () => {
    const wrapper = mount(WidgetThreats, {
      props: {
        data: {
          threats: [
            {
              message: 'IPS signature match',
              sourceIp: '10.0.0.5',
              destinationIp: '192.0.2.9',
              severity: 'high',
              action: 'blocked',
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('IPS signature match')
    expect(wrapper.text()).toContain('10.0.0.5')
    expect(wrapper.text()).toContain('192.0.2.9')
    expect(wrapper.text()).toContain('high')
    expect(wrapper.text()).toContain('blocked')
  })

  it('renders normalized FortiGate firewall policies', () => {
    const wrapper = mount(WidgetFirewallPolicies, {
      global: {
        plugins: [pinia, i18n],
      },
      props: {
        data: {
          policies: [
            {
              id: 1,
              name: 'FD_TMP_BLOCK_32FD0707AD9A',
              sourceInterfaces: ['port2'],
              destinationInterfaces: ['port3'],
              sourceAddresses: ['FD_ADDR_10_10_10_10'],
              destinationAddresses: ['FD_ADDR_10_10_20_10'],
              services: ['ALL'],
              schedule: 'always',
              logging: 'all',
              comments: 'FortiDashboard owned temporary block policy',
              policyKind: 'temporary_block',
              isBlocking: true,
              isFortiDashboardOwned: true,
              action: 'deny',
              status: 'enabled',
            },
            {
              id: 2,
              name: 'Allow SOC outbound',
              sourceInterfaces: ['port1'],
              destinationInterfaces: ['wan1'],
              sourceAddresses: ['all'],
              destinationAddresses: ['all'],
              services: ['HTTPS'],
              schedule: 'always',
              logging: 'all',
              policyKind: 'standard',
              action: 'accept',
              status: 'enabled',
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('FD_TMP_BLOCK_32FD0707AD9A')
    expect(wrapper.text()).toContain('Block')
    expect(wrapper.text()).toContain('Temporary block')
    expect(wrapper.text()).toContain('FortiDashboard')
    expect(wrapper.text()).toContain('port2 -> port3')
    expect(wrapper.text()).toContain('FD_ADDR_10_10_10_10')
    expect(wrapper.text()).toContain('FD_ADDR_10_10_20_10')
    expect(wrapper.text()).toContain('Log all')
    expect(wrapper.text()).toContain('ALL')
    expect(wrapper.text()).toContain('Allow SOC outbound')
    expect(wrapper.text()).toContain('port1')
    expect(wrapper.text()).toContain('wan1')
    expect(wrapper.text()).toContain('Allow/log')
    expect(wrapper.text()).toContain('enabled')
  })

  it('renders all SOAR playbook run history and approves pending runs', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/auth/csrf') return jsonResponse({ csrfToken: 'csrf_01' })
      if (url === '/api/soc/playbook-runs/run_waiting/approve') {
        return jsonResponse({
          id: 'run_waiting',
          incidentId: 'inc_01',
          playbookId: 'pb_block',
          status: 'completed',
          dryRun: true,
          steps: [{ nodeType: 'approval.required', status: 'completed' }],
        })
      }
      throw new Error(`unexpected url ${url}`)
    })
    vi.stubGlobal('fetch', fetcher)
    useAuthStore().csrfToken = 'csrf_01'

    const wrapper = mount(WidgetSoarPlaybookRunHistory, {
      global: {
        plugins: [pinia, i18n],
      },
      props: {
        instanceId: 'inst_runs',
        integrationId: 'int_soar',
        catalogId: 'soar-playbook-run-history',
        data: {
          count: 2,
          summary: {
            active: 1,
            completed: 1,
            failed: 0,
            running: 0,
            waitingApproval: 1,
          },
          runs: [
            {
              id: 'run_waiting',
              incidentId: 'inc_01',
              playbookId: 'pb_block',
              status: 'waiting_approval',
              dryRun: true,
              createdAt: '2026-05-15T16:17:29Z',
              steps: [{ nodeType: 'approval.required', status: 'waiting_approval' }],
            },
            {
              id: 'run_done',
              incidentId: 'inc_01',
              playbookId: 'pb_notes',
              status: 'completed',
              dryRun: true,
              createdAt: '2026-05-15T16:20:22Z',
              steps: [{ nodeType: 'case.note', status: 'completed' }],
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('Playbook Run History')
    expect(wrapper.text()).toContain('run_waiting')
    expect(wrapper.text()).toContain('pb_block')
    expect(wrapper.text()).toContain('inc_01')
    expect(wrapper.text()).toContain('waiting_approval')
    expect(wrapper.text()).toContain('run_done')
    expect(wrapper.text()).toContain('completed')

    await wrapper.get('[data-test="playbook-run-history-approve-run_waiting"]').trigger('click')
    await flushPromises()

    expect(fetcher).toHaveBeenCalledWith('/api/soc/playbook-runs/run_waiting/approve', expect.objectContaining({
      method: 'POST',
      credentials: 'include',
      headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf_01' }),
    }))
    expect(wrapper.text()).toContain('completed')
  })

  it('renders FortiGate risk posture signals and summary', () => {
    const wrapper = mount(WidgetRiskPosture, {
      props: {
        data: {
          score: 72,
          level: 'medium',
          signals: [
            {
              label: 'Interfaces down',
              severity: 'warning',
              value: 2,
              unit: 'count',
              description: 'One or more FortiGate interfaces report link down.',
            },
          ],
          summary: {
            critical: 1,
            warning: 2,
            healthy: 3,
          },
        },
      },
    })

    expect(wrapper.text()).toContain('Risk Posture')
    expect(wrapper.text()).toContain('72')
    expect(wrapper.text()).toContain('Medium')
    expect(wrapper.text()).toContain('Interfaces down')
    expect(wrapper.text()).toContain('2 count')
    expect(wrapper.text()).toContain('Critical')
    expect(wrapper.text()).toContain('1')
  })

  it('renders FortiGate interface health summary and rows', () => {
    const wrapper = mount(WidgetInterfaceHealth, {
      props: {
        data: {
          interfaces: [
            {
              id: 'port1',
              name: 'port1',
              alias: 'WAN',
              status: 'up',
              ip: '192.0.2.118',
              role: 'wan',
              rxBytes: 8304525,
              txBytes: 6185442,
            },
          ],
          summary: {
            total: 1,
            up: 1,
            down: 0,
            totalRxBytes: 8304525,
            totalTxBytes: 6185442,
          },
        },
      },
    })

    expect(wrapper.text()).toContain('Interface Health')
    expect(wrapper.text()).toContain('port1')
    expect(wrapper.text()).toContain('WAN')
    expect(wrapper.text()).toContain('192.0.2.118')
    expect(wrapper.text()).toContain('1 up')
    expect(wrapper.text()).toContain('0 down')
  })

  it('renders FortiGate recent events feed', () => {
    const wrapper = mount(WidgetRecentEvents, {
      props: {
        data: {
          events: [
            {
              timestamp: '2026-04-26T21:40:00Z',
              type: 'utm',
              subtype: 'ips',
              severity: 'high',
              sourceIp: '10.0.0.10',
              destinationIp: '203.0.113.10',
              action: 'blocked',
              message: 'IPS signature matched',
            },
          ],
          summary: {
            total: 1,
            blocked: 1,
            highSeverity: 1,
          },
        },
      },
    })

    expect(wrapper.text()).toContain('Recent Events')
    expect(wrapper.text()).toContain('IPS signature matched')
    expect(wrapper.text()).toContain('10.0.0.10')
    expect(wrapper.text()).toContain('203.0.113.10')
    expect(wrapper.text()).toContain('blocked')
    expect(wrapper.text()).toContain('high')
  })

  it('renders FortiGate anomaly highlights and handles empty state', () => {
    const emptyWrapper = mount(WidgetAnomalyHighlights, {
      props: {
        data: {
          anomalies: [],
          summary: {
            count: 0,
            highestSeverity: 'none',
          },
        },
      },
    })

    expect(emptyWrapper.text()).toContain('Anomaly Highlights')
    expect(emptyWrapper.text()).toContain('No active anomalies')

    const wrapper = mount(WidgetAnomalyHighlights, {
      props: {
        data: {
          anomalies: [
            {
              title: 'CPU pressure above normal SOC threshold',
              severity: 'critical',
              metric: 'system.cpu',
              value: 91,
              unit: 'percent',
              description: 'Sustained CPU pressure can delay inspection and logging.',
            },
          ],
          summary: {
            count: 1,
            highestSeverity: 'critical',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('CPU pressure above normal SOC threshold')
    expect(wrapper.text()).toContain('critical')
    expect(wrapper.text()).toContain('91%')
    expect(wrapper.text()).toContain('system.cpu')
  })

  it('renders SOC templates without array payloads', () => {
    const cases = [
      [WidgetRiskPosture, 'No risk signals returned.'],
      [WidgetInterfaceHealth, 'No interfaces returned.'],
      [WidgetRecentEvents, 'No recent events returned.'],
      [WidgetAnomalyHighlights, 'No active anomalies'],
    ] as const

    for (const [Component, emptyLabel] of cases) {
      const wrapper = mount(Component, {
        props: {
          data: {
            summary: {},
          },
        },
      })

      expect(wrapper.text()).toContain(emptyLabel)
    }
  })
})
