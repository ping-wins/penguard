import { describe, expect, it } from 'vitest'
import {
  createWidgetInstance,
  normalizeWidgetLayout,
  normalizeWorkspaceWidgets,
} from '../../src/utils/widgetLayout'

describe('widget layout normalization', () => {
  it('converts backend grid-unit layouts into visible pixel dimensions', () => {
    expect(normalizeWidgetLayout({ x: 0, y: 0, w: 3, h: 2, z: 10 })).toEqual({
      x: 0,
      y: 0,
      w: 320,
      h: 200,
      z: 10,
    })
  })

  it('keeps already-pixel-sized layouts unchanged', () => {
    expect(normalizeWidgetLayout({ x: 50, y: 50, w: 320, h: 200, z: 10 })).toEqual({
      x: 50,
      y: 50,
      w: 320,
      h: 200,
      z: 10,
    })
  })

  it('uses catalog defaultSize grid units when creating a widget instance', () => {
    expect(createWidgetInstance({
      catalogId: 'fortigate-firewall-policies',
      integrationId: 'int_fgt_01',
      defaultSize: { w: 5, h: 4 },
      instanceId: 'w_policy',
      zIndex: 105,
    })).toEqual({
      instanceId: 'w_policy',
      catalogId: 'fortigate-firewall-policies',
      integrationId: 'int_fgt_01',
      layout: { x: 50, y: 50, w: 520, h: 380, z: 105 },
    })
  })

  it('normalizes all widgets from a workspace response', () => {
    const widgets = normalizeWorkspaceWidgets([
      {
        instanceId: 'w_01',
        catalogId: 'fortigate-system-status',
        integrationId: 'int_fgt_01',
        layout: { x: 0, y: 0, w: 3, h: 2, z: 10 },
      },
    ])

    expect(widgets[0].layout).toEqual({ x: 0, y: 0, w: 320, h: 200, z: 10 })
  })
})
