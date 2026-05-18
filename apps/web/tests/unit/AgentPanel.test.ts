import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import AgentPanel from '../../src/components/ai/AgentPanel.vue'
import { i18n, setLocale } from '../../src/i18n'
import { useAiAgentStore } from '../../src/stores/useAiAgentStore'

describe('AgentPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('pt-BR')
  })

  it('renders approval context with risk, permissions, reason and payload', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAiAgentStore()
    store.tools = [
      {
        name: 'write_policy',
        description: 'Apply a governed policy change.',
        inputSchema: { type: 'object' },
        category: 'write',
        requiresApproval: true,
        requiredPermissions: ['policies.manage'],
        timeoutSeconds: 5,
      },
    ]
    store.pendingApproval = {
      callId: 'call_1',
      toolName: 'write_policy',
      args: { policyId: 'policy_42' },
      reason: 'write tool requires approval',
    }

    const wrapper = mount(AgentPanel, {
      global: { plugins: [pinia, i18n] },
    })

    expect(wrapper.text()).toContain('Risco')
    expect(wrapper.text()).toContain('Escrita aprovada')
    expect(wrapper.text()).toContain('policies.manage')
    expect(wrapper.text()).toContain('write tool requires approval')
    expect(wrapper.text()).toContain('policy_42')
  })
})
