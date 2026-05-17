import { describe, expect, it } from 'vitest'
import type { Edge, Node } from '@vue-flow/core'
import type { Playbook, PlaybookNodeType } from '../../src/services/playbooksClient'
import { flowToPlaybookDraft, playbookToFlow } from '../../src/utils/playbookGraph'

const nodeTypes: PlaybookNodeType[] = [
  {
    id: 'trigger.incident_created',
    label: 'Incident Created',
    category: 'trigger',
    sensitive: false,
    dryRunOnly: true,
    executionMode: 'dry_run',
    liveAvailable: false,
    boundary: 'trigger_only',
    configSchema: {},
  },
  {
    id: 'case.note',
    label: 'Create Case Note',
    category: 'action',
    sensitive: false,
    dryRunOnly: true,
    executionMode: 'dry_run',
    liveAvailable: false,
    boundary: 'case_note',
    configSchema: {},
  },
]

const playbook: Playbook = {
  id: 'pb_canvas',
  name: 'Canvas playbook',
  enabled: false,
  nodes: [
    {
      id: 'trigger',
      type: 'trigger.incident_created',
      config: {},
      position: { x: 40, y: 120 },
    },
    {
      id: 'note',
      type: 'case.note',
      config: { template: 'Review incident.' },
      position: { x: 340, y: 120 },
    },
  ],
  edges: [
    {
      id: 'edge_trigger_note',
      from: 'trigger',
      to: 'note',
      condition: 'success',
    },
  ],
}

describe('playbook graph helpers', () => {
  it('maps persisted playbooks to Vue Flow nodes and edges with metadata', () => {
    const graph = playbookToFlow(playbook, nodeTypes)

    expect(graph.nodes).toEqual([
      expect.objectContaining({
        id: 'trigger',
        type: 'playbookNode',
        position: { x: 40, y: 120 },
        data: expect.objectContaining({
          label: 'Incident Created',
          nodeType: 'trigger.incident_created',
          boundary: 'trigger_only',
        }),
      }),
      expect.objectContaining({
        id: 'note',
        type: 'playbookNode',
        position: { x: 340, y: 120 },
        data: expect.objectContaining({
          label: 'Create Case Note',
          nodeType: 'case.note',
          config: { template: 'Review incident.' },
        }),
      }),
    ])
    expect(graph.edges).toEqual([
      expect.objectContaining({
        id: 'edge_trigger_note',
        source: 'trigger',
        target: 'note',
        type: 'playbookEdge',
        data: { condition: 'success' },
      }),
    ])
  })

  it('maps Vue Flow edits back to the SOAR playbook payload', () => {
    const nodes: Node[] = [
      {
        id: 'trigger',
        type: 'playbookNode',
        position: { x: 80, y: 140 },
        data: {
          nodeType: 'trigger.incident_created',
          config: {},
        },
      },
      {
        id: 'note',
        type: 'playbookNode',
        position: { x: 380, y: 140 },
        data: {
          nodeType: 'case.note',
          config: { template: 'Escalate to L2.' },
        },
      },
    ]
    const edges: Edge[] = [
      {
        id: 'edge_trigger_note',
        source: 'trigger',
        target: 'note',
        type: 'playbookEdge',
        data: { condition: 'success' },
      },
    ]

    expect(flowToPlaybookDraft(playbook, nodes, edges)).toMatchObject({
      id: 'pb_canvas',
      name: 'Canvas playbook',
      enabled: false,
      nodes: [
        {
          id: 'trigger',
          type: 'trigger.incident_created',
          config: {},
          position: { x: 80, y: 140 },
        },
        {
          id: 'note',
          type: 'case.note',
          config: { template: 'Escalate to L2.' },
          position: { x: 380, y: 140 },
        },
      ],
      edges: [
        {
          id: 'edge_trigger_note',
          from: 'trigger',
          to: 'note',
          condition: 'success',
        },
      ],
    })
  })
})
