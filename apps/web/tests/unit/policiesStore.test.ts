import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../../src/stores/useAuthStore'
import { usePoliciesStore } from '../../src/stores/usePoliciesStore'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('usePoliciesStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('loads policy providers and inventory through the BFF', async () => {
    const fetcher = vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/policies/providers') {
        return Promise.resolve(jsonResponse({
          items: [{
            providerType: 'fortigate',
            integrationId: 'int_fgt_01',
            name: 'FortiGate Lab',
            capabilities: ['list', 'create', 'edit', 'enable', 'disable', 'delete'],
            policyKinds: ['firewall_policy'],
          }],
        }))
      }
      if (url === '/api/policies?providerType=fortigate') {
        return Promise.resolve(jsonResponse({
          items: [{
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
            managedByPenguard: false,
            isMutable: true,
            supports: ['edit', 'disable', 'delete'],
            risk: { level: 'medium', reasons: ['Allows traffic'] },
            summary: 'accept HTTPS from LAN_NET to WAN_NET',
            lastObservedAt: '2026-05-17T12:00:00.000Z',
          }],
          nextCursor: null,
        }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = usePoliciesStore()
    await store.loadProviders()
    await store.loadPolicies({ providerType: 'fortigate' })

    expect(store.providers[0].providerType).toBe('fortigate')
    expect(store.policies[0].name).toBe('LAN to WAN')
    expect(fetcher).toHaveBeenCalledWith('/api/policies/providers', {
      method: 'GET',
      credentials: 'include',
    })
    expect(fetcher).toHaveBeenCalledWith('/api/policies?providerType=fortigate', {
      method: 'GET',
      credentials: 'include',
    })
  })

  it('creates and applies policy reviews with CSRF credentials', async () => {
    const authStore = useAuthStore()
    authStore.csrfToken = 'csrf_01'
    const fetcher = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url === '/api/policies/reviews') {
        return Promise.resolve(jsonResponse({
          id: 'policy_review_01',
          providerType: 'fortigate',
          integrationId: 'int_fgt_01',
          policyId: 'fortigate:int_fgt_01:policy:10',
          action: 'disable',
          status: 'pending_review',
          title: 'Disable policy',
          before: { summary: 'enabled' },
          after: { summary: 'disabled' },
          diff: [{ field: 'status', before: 'enabled', after: 'disabled', risk: 'Stops traffic' }],
          warnings: [{ severity: 'high', message: 'External policy' }],
          rollback: ['Set status back to enabled'],
          reviewHash: 'hash_01',
        }))
      }
      if (url === '/api/policies/reviews/policy_review_01/apply') {
        return Promise.resolve(jsonResponse({
          id: 'policy_review_01',
          status: 'applied',
          providerType: 'fortigate',
          integrationId: 'int_fgt_01',
          appliedResult: { ok: true },
        }))
      }
      return Promise.resolve(jsonResponse({ detail: 'not found' }, { status: 404 }))
    })
    vi.stubGlobal('fetch', fetcher)

    const store = usePoliciesStore()
    await store.reviewPolicy({
      providerType: 'fortigate',
      integrationId: 'int_fgt_01',
      policyId: 'fortigate:int_fgt_01:policy:10',
      action: 'disable',
      payload: {},
    })
    await store.applyReview('policy_review_01', 'hash_01')

    expect(store.selectedReview?.id).toBe('policy_review_01')
    expect(store.lastApplyResult?.status).toBe('applied')
    expect(fetcher).toHaveBeenCalledWith('/api/policies/reviews', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      },
      credentials: 'include',
      body: JSON.stringify({
        providerType: 'fortigate',
        integrationId: 'int_fgt_01',
        policyId: 'fortigate:int_fgt_01:policy:10',
        action: 'disable',
        payload: {},
      }),
    })
    expect(fetcher).toHaveBeenCalledWith('/api/policies/reviews/policy_review_01/apply', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': 'csrf_01',
      },
      credentials: 'include',
      body: JSON.stringify({ reviewHash: 'hash_01', confirmed: true }),
    })
  })
})
