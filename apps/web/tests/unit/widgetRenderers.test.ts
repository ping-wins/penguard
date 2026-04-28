import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WidgetFirewallPolicies from '../../src/components/widgets/WidgetFirewallPolicies.vue'
import WidgetHealth from '../../src/components/widgets/WidgetHealth.vue'
import WidgetThreats from '../../src/components/widgets/WidgetThreats.vue'

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
        },
      },
    })

    expect(wrapper.text()).toContain('FGT-LIVE-01')
    expect(wrapper.text()).toContain('FortiGate')
    expect(wrapper.text()).toContain('v7.6.6')
    expect(wrapper.text()).toContain('1%')
    expect(wrapper.text()).toContain('45%')
    expect(wrapper.text()).toContain('25')
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
      props: {
        data: {
          policies: [
            {
              id: 1,
              name: 'Allow SOC outbound',
              srcIntf: 'port1',
              dstIntf: 'wan1',
              action: 'accept',
              status: 'enabled',
            },
          ],
        },
      },
    })

    expect(wrapper.text()).toContain('Allow SOC outbound')
    expect(wrapper.text()).toContain('port1')
    expect(wrapper.text()).toContain('wan1')
    expect(wrapper.text()).toContain('accept')
    expect(wrapper.text()).toContain('enabled')
  })
})
