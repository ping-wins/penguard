import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WidgetSocPolicyManager from '../../src/components/widgets/policies/WidgetSocPolicyManager.vue'
import { i18n, setLocale } from '../../src/i18n'
import { useAuthStore } from '../../src/stores/useAuthStore'

let pinia: ReturnType<typeof createPinia>

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('WidgetSocPolicyManager', () => {
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    setLocale('en-US')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows policies from every provider and applies a reviewed action', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/policies/providers') {
        return Promise.resolve(jsonResponse({
          items: [
            {
              providerType: 'fortigate',
              integrationId: 'int_fgt_01',
              name: 'FortiGate Lab',
              capabilities: ['list', 'create', 'edit', 'enable', 'disable', 'delete'],
              policyKinds: ['firewall_policy'],
            },
            {
              providerType: 'fortiweb',
              integrationId: 'int_fwb_01',
              name: 'FortiWeb Lab',
              capabilities: ['list', 'create', 'edit', 'enable', 'disable', 'delete'],
              policyKinds: ['ip_blocklist'],
            },
          ],
        }))
      }
      if (url === '/api/policies') {
        return Promise.resolve(jsonResponse({
          items: [
            {
              id: 'fortigate:int_fgt_01:policy:10',
              providerType: 'fortigate',
              integrationId: 'int_fgt_01',
              nativeId: '10',
              name: 'LAN to WAN',
              kind: 'firewall_policy',
              status: 'enabled',
              action: 'accept',
              direction: { source: ['port2'], destination: ['port3'] },
              scope: { source: ['LAN_NET'], destination: ['WAN_NET'], service: ['HTTPS'] },
              ownership: 'external',
              managedByFortiDashboard: false,
              isMutable: true,
              supports: ['edit', 'disable', 'delete'],
              risk: { level: 'medium' },
              summary: 'accept HTTPS from LAN_NET to WAN_NET',
            },
            {
              id: 'fortiweb:int_fwb_01:block:203.0.113.10',
              providerType: 'fortiweb',
              integrationId: 'int_fwb_01',
              nativeId: '203.0.113.10',
              name: 'Block 203.0.113.10',
              kind: 'ip_blocklist',
              status: 'enabled',
              action: 'block',
              direction: {},
              scope: { source: ['203.0.113.10'] },
              ownership: 'external',
              managedByFortiDashboard: false,
              isMutable: true,
              supports: ['edit', 'disable', 'delete'],
              risk: { level: 'high' },
              summary: 'FortiWeb IP block policy',
            },
          ],
          nextCursor: null,
        }))
      }
      if (url === '/api/policies/reviews') {
        const body = JSON.parse(String(init?.body))
        expect(body).toMatchObject({
          providerType: 'fortigate',
          integrationId: 'int_fgt_01',
          policyId: 'fortigate:int_fgt_01:policy:10',
          action: 'disable',
        })
        return Promise.resolve(jsonResponse({
          id: 'fortigate:review_01',
          providerType: 'fortigate',
          integrationId: 'int_fgt_01',
          policyId: 'fortigate:int_fgt_01:policy:10',
          action: 'disable',
          status: 'pending_review',
          title: 'disable FortiGate policy',
          before: { summary: 'enabled' },
          after: { summary: 'disabled' },
          diff: [{ field: 'status', before: 'enabled', after: 'disabled' }],
          warnings: [{ severity: 'high', message: 'External policy' }],
          rollback: ['Enable the policy again.'],
          reviewHash: 'hash_01',
        }))
      }
      if (url === '/api/policies/reviews/fortigate%3Areview_01/apply') {
        return Promise.resolve(jsonResponse({
          id: 'fortigate:review_01',
          status: 'applied',
          providerType: 'fortigate',
          integrationId: 'int_fgt_01',
          appliedResult: { ok: true },
        }))
      }
      return Promise.resolve(jsonResponse({ detail: `unexpected ${url}` }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)
    useAuthStore().csrfToken = 'csrf_01'

    const wrapper = mount(WidgetSocPolicyManager, {
      global: { plugins: [pinia, i18n] },
      props: {
        data: {},
        instanceId: 'inst_policy_manager',
        integrationId: 'int_fgt_01',
        catalogId: 'soc-policy-manager',
      },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('LAN to WAN')
    expect(wrapper.text()).toContain('Block 203.0.113.10')

    await wrapper.find('[data-test="policy-action-disable"]').trigger('click')
    await wrapper.find('[data-test="policy-review"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('External policy')

    await wrapper.find('[data-test="policy-apply"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('Policy change applied')
  })
})
