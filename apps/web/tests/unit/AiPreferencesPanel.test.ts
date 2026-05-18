import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AiPreferencesPanel from '../../src/components/settings/AiPreferencesPanel.vue'
import { i18n, setLocale } from '../../src/i18n'

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('AiPreferencesPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('en-US')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('preserves unsaved edits while testing saved settings', async () => {
    const savedSettings = {
      provider: 'anthropic',
      model: 'claude-sonnet-4-6',
      apiKeySet: true,
      configured: true,
      lastTestedAt: null,
      lastTestStatus: null,
      lastTestError: null,
      updatedBy: 'admin@example.com',
      updatedAt: '2026-05-18T12:01:00.000Z',
    }
    let resolveTest: (response: Response) => void = () => {}
    const testResponse = new Promise<Response>((resolve) => {
      resolveTest = resolve
    })
    const fetcher = vi.fn((url: string, init?: RequestInit) => {
      if (url === '/api/ai/agent/settings' && (!init?.method || init.method === 'GET')) {
        return Promise.resolve(jsonResponse(savedSettings))
      }
      if (url === '/api/auth/csrf') {
        return Promise.resolve(jsonResponse({ csrfToken: 'csrf_z' }))
      }
      if (url === '/api/ai/agent/settings/test') {
        return testResponse
      }
      return Promise.reject(new Error(`unexpected fetch ${url}`))
    })
    vi.stubGlobal('fetch', fetcher)

    const wrapper = mount(AiPreferencesPanel, {
      global: {
        plugins: [i18n],
      },
    })
    await flushPromises()

    await wrapper.get('[data-test="soc-assistant-model"]').setValue('claude-custom')
    await wrapper.get('[data-test="soc-assistant-api-key"]').setValue('sk-unsaved')
    await wrapper.get('[data-test="soc-assistant-test"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test="soc-assistant-save"]').attributes('disabled')).toBeDefined()

    resolveTest(jsonResponse({ ok: true, status: 'success', error: null }))
    await flushPromises()

    expect((wrapper.get('[data-test="soc-assistant-model"]').element as HTMLInputElement).value).toBe('claude-custom')
    expect((wrapper.get('[data-test="soc-assistant-api-key"]').element as HTMLInputElement).value).toBe('sk-unsaved')
  })
})

async function flushPromises() {
  await new Promise(resolve => setTimeout(resolve, 0))
}
