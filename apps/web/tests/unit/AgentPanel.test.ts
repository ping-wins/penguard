import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AgentPanel from '../../src/components/ai/AgentPanel.vue'
import { i18n, setLocale } from '../../src/i18n'
import { useAiAgentStore } from '../../src/stores/useAiAgentStore'

describe('AgentPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('pt-BR')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [] }), {
        headers: { 'Content-Type': 'application/json' },
      }),
    ))
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

  it('labels execute approvals separately from writes', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAiAgentStore()
    store.tools = [
      {
        name: 'run_playbook',
        description: 'Run an approved response playbook.',
        inputSchema: { type: 'object' },
        category: 'execute',
        requiresApproval: true,
        requiredPermissions: ['playbooks.execute'],
        timeoutSeconds: 5,
      },
    ]
    store.pendingApproval = {
      callId: 'call_2',
      toolName: 'run_playbook',
      args: { playbookId: 'pb_1' },
      reason: 'execute tool requires approval',
    }

    const wrapper = mount(AgentPanel, {
      global: { plugins: [pinia, i18n] },
    })

    expect(wrapper.text()).toContain('Execução aprovada')
    expect(wrapper.text()).toContain('playbooks.execute')
    expect(wrapper.text()).toContain('execute tool requires approval')
  })

  it('renders assistant markdown without executing raw html', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const store = useAiAgentStore()
    store.trace = [
      {
        kind: 'text',
        step: 1,
        text: '## Incidentes recentes\n- **critical** em `inc_1`\n<script>alert(1)</script>',
      },
    ]

    const wrapper = mount(AgentPanel, {
      global: { plugins: [pinia, i18n] },
    })

    const markdown = wrapper.get('[data-test="agent-markdown"]')
    expect(markdown.find('h2').text()).toBe('Incidentes recentes')
    expect(markdown.find('strong').text()).toBe('critical')
    expect(markdown.find('code').text()).toBe('inc_1')
    expect(markdown.html()).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(markdown.find('script').exists()).toBe(false)
  })
})
