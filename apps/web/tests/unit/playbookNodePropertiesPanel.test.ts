import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import PlaybookNodePropertiesPanel from '../../src/components/playbooks/canvas/PlaybookNodePropertiesPanel.vue'
import { i18n, setLocale } from '../../src/i18n'
import { usePlaybooksStore } from '../../src/stores/usePlaybooksStore'
import type { PlaybookFlowNode } from '../../src/utils/playbookGraph'

describe('PlaybookNodePropertiesPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    setLocale('en-US')
    const store = usePlaybooksStore()
    store.webhookDestinations = [
      {
        id: 'pwd_discord_soc',
        name: 'SOC Discord',
        kind: 'discord',
        redactedUrl: 'https://discord.com/api/webhooks/123456789/...',
        status: 'active',
      },
    ]
    store.nodeTypes = [
      {
        id: 'notify.webhook',
        label: 'Notify Webhook',
        description: 'Sends a notification to a configured webhook destination.',
        effectSummary: 'Sends a real outbound notification through a configured webhook destination.',
        category: 'action',
        sensitive: false,
        dryRunOnly: false,
        executionMode: 'live',
        liveAvailable: true,
        boundary: 'notification_dry_run',
        configSchema: {
          type: 'object',
          required: ['destinationId', 'content'],
          properties: {
            destinationId: {
              type: 'string',
              title: 'Webhook destination',
              description: 'Configured Discord destination.',
            },
            content: {
              type: 'string',
              title: 'Message content',
              description: 'Message sent to Discord.',
            },
          },
        },
        exampleConfig: {
          destinationId: 'pwd_discord_soc',
          content: 'Critical incident {incident.id} from {entities.sourceIp}',
        },
        requiredInputs: [
          {
            key: 'destinationId',
            label: 'Webhook destination',
            description: 'A configured Discord destination.',
          },
          {
            key: 'content',
            label: 'Message content',
            description: 'Message body sent to Discord.',
          },
        ],
      },
    ]
  })

  it('renders guided schema fields, validates missing required inputs, and applies example config', async () => {
    const node: PlaybookFlowNode = {
      id: 'discord',
      type: 'playbookNode',
      position: { x: 0, y: 0 },
      data: {
        label: 'Notify Webhook',
        nodeType: 'notify.webhook',
        category: 'action',
        boundary: 'notification_dry_run',
        sensitive: false,
        liveAvailable: true,
        executionMode: 'live',
        config: {},
      },
    }

    const wrapper = mount(PlaybookNodePropertiesPanel, {
      props: { node },
      global: { plugins: [i18n] },
    })

    await flushPromises()

    expect(wrapper.text()).toContain('Sends a real outbound notification through a configured webhook destination.')
    expect(wrapper.text()).toContain('Missing: Webhook destination, Message content')
    expect(wrapper.get('[data-test="playbook-config-field-destinationId"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="playbook-config-field-content"]').exists()).toBe(true)

    await wrapper.get('[data-test="playbook-node-config-apply"]').trigger('click')
    expect(wrapper.emitted('updateConfig')).toBeUndefined()

    await wrapper.get('[data-test="playbook-node-config-apply-example"]').trigger('click')
    await flushPromises()

    expect(wrapper.emitted('updateConfig')?.[0]).toEqual([
      'discord',
      {
        destinationId: 'pwd_discord_soc',
        content: 'Critical incident {incident.id} from {entities.sourceIp}',
      },
    ])
  })
})
