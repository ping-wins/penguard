import type { Edge, Node } from '@vue-flow/core'
import type {
  Playbook,
  PlaybookDraft,
  PlaybookEdge,
  PlaybookNode,
  PlaybookNodeType,
} from '../services/playbooksClient'

export const PLAYBOOK_NODE_DRAG_MIME = 'application/x-fortidashboard-playbook-node'

export type PlaybookCanvasNodeData = {
  label: string
  nodeType: string
  category: string
  boundary: string
  sensitive: boolean
  liveAvailable: boolean
  executionMode: string
  config: Record<string, unknown>
  runStatus?: string | null
}

export type PlaybookFlowNode = Node<PlaybookCanvasNodeData> & {
  data: PlaybookCanvasNodeData
}

export type PlaybookNodeDragPayload = {
  nodeType: string
  config?: Record<string, unknown>
}

type PlaybookFlowGraph = {
  nodes: PlaybookFlowNode[]
  edges: Edge[]
}

const DEFAULT_NODE_WIDTH = 260
const DEFAULT_NODE_GAP = 120

export function playbookToFlow(
  playbook: Playbook,
  nodeTypes: PlaybookNodeType[],
): PlaybookFlowGraph {
  const definitions = new Map(nodeTypes.map((nodeType) => [nodeType.id, nodeType]))
  return {
    nodes: playbook.nodes.map((node, index) => {
      const definition = definitions.get(node.type)
      return {
        id: node.id,
        type: 'playbookNode',
        position: normalizePosition(node.position, index),
        data: {
          label: definition?.label ?? node.type,
          nodeType: node.type,
          category: definition?.category ?? 'action',
          boundary: definition?.boundary ?? 'unknown',
          sensitive: Boolean(definition?.sensitive ?? node.sensitive),
          liveAvailable: Boolean(definition?.liveAvailable),
          executionMode: definition?.executionMode ?? 'dry_run',
          config: node.config ?? {},
        },
      }
    }),
    edges: playbook.edges.map((edge) => ({
      id: edge.id || edgeId(edge.from, edge.to, edge.condition ?? 'success'),
      source: edge.from,
      target: edge.to,
      type: 'playbookEdge',
      animated: edge.condition === 'approved' || edge.condition === 'true',
      data: {
        condition: edge.condition ?? 'success',
      },
    })),
  }
}

export function flowToPlaybookDraft(
  base: Pick<Playbook, 'id' | 'name' | 'enabled'>,
  nodes: Node[],
  edges: Edge[],
): PlaybookDraft {
  return {
    id: base.id,
    name: base.name,
    enabled: base.enabled,
    nodes: nodes.map((node): PlaybookNode => {
      const data = node.data as Partial<PlaybookCanvasNodeData> | undefined
      return {
        id: node.id,
        type: String(data?.nodeType || node.type || 'case.note'),
        config: isRecord(data?.config) ? data.config : {},
        position: {
          x: Math.round(Number(node.position?.x) || 0),
          y: Math.round(Number(node.position?.y) || 0),
        },
      }
    }),
    edges: edges.map((edge): PlaybookEdge => ({
      id: edge.id,
      from: edge.source,
      to: edge.target,
      condition: edgeCondition(edge),
    })),
  }
}

export function edgeId(source: string, target: string, condition = 'success') {
  return `edge_${source}_${target}_${condition}`.replace(/[^a-zA-Z0-9_-]/g, '_')
}

export function defaultNodeConfig(nodeType: string): Record<string, unknown> {
  switch (nodeType) {
    case 'condition.severity':
      return { severity: ['high', 'critical'] }
    case 'enrich.ip':
      return { field: 'entities.sourceIp' }
    case 'case.note':
      return { template: 'Review incident.' }
    case 'audit.note':
      return { message: 'SOC playbook note.' }
    case 'approval.required':
      return { role: 'admin' }
    case 'notify.webhook':
      return { mode: 'dry_run', channel: 'soc' }
    case 'fortigate.recommend_block':
      return { mode: 'dry_run', field: 'entities.sourceIp' }
    case 'fortiweb.recommend_block':
      return { sourceIp: '203.0.113.10', durationMinutes: 60 }
    case 'fortigate.temporary_block':
      return {
        scope: 'source_only',
        durationMinutes: 30,
        sourceField: 'entities.sourceIp',
      }
    case 'webhook.dry_run':
      return { url: 'https://example.invalid/webhook', method: 'POST' }
    default:
      return {}
  }
}

export function parsePlaybookNodeDragPayload(
  dataTransfer: DataTransfer | null,
): PlaybookNodeDragPayload | null {
  if (!dataTransfer) return null
  const raw = dataTransfer.getData(PLAYBOOK_NODE_DRAG_MIME)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    if (typeof parsed.nodeType !== 'string') return null
    return {
      nodeType: parsed.nodeType,
      config: isRecord(parsed.config) ? parsed.config : defaultNodeConfig(parsed.nodeType),
    }
  } catch {
    return null
  }
}

export function serializePlaybookNodeDragPayload(payload: PlaybookNodeDragPayload) {
  return JSON.stringify({
    nodeType: payload.nodeType,
    config: payload.config ?? defaultNodeConfig(payload.nodeType),
  })
}

function normalizePosition(
  position: PlaybookNode['position'] | undefined,
  index: number,
) {
  if (position && Number.isFinite(position.x) && Number.isFinite(position.y)) {
    return {
      x: Number(position.x),
      y: Number(position.y),
    }
  }
  return {
    x: index * (DEFAULT_NODE_WIDTH + DEFAULT_NODE_GAP),
    y: 120 + (index % 2) * 120,
  }
}

function edgeCondition(edge: Edge) {
  const data = edge.data as { condition?: unknown } | undefined
  return typeof data?.condition === 'string' && data.condition ? data.condition : 'success'
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value))
}
