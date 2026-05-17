import type { Connection, Edge } from '@vue-flow/core'
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import type { Playbook, PlaybookNodeType } from '../services/playbooksClient'
import { usePlaybooksStore } from './usePlaybooksStore'
import {
  defaultNodeConfig,
  edgeId,
  flowToPlaybookDraft,
  playbookToFlow,
  type PlaybookFlowNode,
} from '../utils/playbookGraph'

type NodeInsertPosition = {
  x: number
  y: number
}

export const usePlaybookCanvasStore = defineStore('playbookCanvas', () => {
  const selectedPlaybookId = ref<string>('')
  const draftId = ref('pb_canvas_draft')
  const draftName = ref('Canvas playbook draft')
  const nodes = shallowRef<PlaybookFlowNode[]>([])
  const edges = shallowRef<Edge[]>([])
  const selectedNodeId = ref<string | null>(null)
  const error = ref<string | null>(null)
  const isSaving = ref(false)

  const playbooksStore = usePlaybooksStore()
  const selectedPlaybook = computed(() => (
    playbooksStore.playbooks.find((playbook) => playbook.id === selectedPlaybookId.value) ?? null
  ))
  const selectedNode = computed<PlaybookFlowNode | null>(() => (
    nodes.value.find((node) => node.id === selectedNodeId.value) ?? null
  ))
  const graphTitle = computed(() => selectedPlaybook.value?.name || draftName.value)

  function loadPlaybook(playbook: Playbook | null) {
    if (!playbook) {
      selectedPlaybookId.value = ''
      nodes.value = []
      edges.value = []
      return
    }
    selectedPlaybookId.value = playbook.id
    draftId.value = playbook.id
    draftName.value = playbook.name
    const graph = playbookToFlow(playbook, playbooksStore.nodeTypes)
    nodes.value = graph.nodes
    edges.value = graph.edges
    selectedNodeId.value = graph.nodes[0]?.id ?? null
  }

  function loadFirstPlaybookIfNeeded() {
    if (nodes.value.length > 0 || selectedPlaybookId.value) return
    loadPlaybook(playbooksStore.playbooks[0] ?? null)
  }

  function startNewDraft() {
    selectedPlaybookId.value = ''
    draftId.value = uniquePlaybookId()
    draftName.value = 'Canvas playbook draft'
    nodes.value = [
      nodeFromType(
        'trigger.incident_created',
        { x: 40, y: 160 },
        playbooksStore.nodeTypes,
        {},
        'trigger',
      ),
    ]
    edges.value = []
    selectedNodeId.value = 'trigger'
  }

  function addNodeFromCatalog(
    nodeType: string,
    position: NodeInsertPosition = { x: 260, y: 180 },
    config: Record<string, unknown> = defaultNodeConfig(nodeType),
  ) {
    const id = uniqueNodeId(nodeType)
    nodes.value = [
      ...nodes.value,
      nodeFromType(nodeType, position, playbooksStore.nodeTypes, config, id),
    ]
    selectedNodeId.value = id
  }

  function connectNodes(connection: Connection) {
    if (!connection.source || !connection.target) return
    const id = edgeId(connection.source, connection.target)
    if (edges.value.some((edge) => edge.id === id)) return
    edges.value = [
      ...edges.value,
      {
        id,
        source: connection.source,
        target: connection.target,
        type: 'playbookEdge',
        data: { condition: 'success' },
      },
    ]
  }

  function updateNodeConfig(nodeId: string, config: Record<string, unknown>) {
    nodes.value = nodes.value.map((node): PlaybookFlowNode => (
      node.id === nodeId
        ? { ...node, data: { ...node.data, config } }
        : node
    ))
  }

  async function save() {
    const base = {
      id: selectedPlaybook.value?.id || draftId.value.trim(),
      name: selectedPlaybook.value?.name || draftName.value.trim(),
      enabled: selectedPlaybook.value?.enabled ?? false,
    }
    if (!base.id || !base.name) {
      error.value = 'Playbook id and name are required'
      return null
    }
    isSaving.value = true
    error.value = null
    try {
      const payload = flowToPlaybookDraft(base, nodes.value, edges.value)
      const result = selectedPlaybook.value
        ? await playbooksStore.update(base.id, payload)
        : await playbooksStore.create(payload)
      loadPlaybook(result)
      return result
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to save playbook graph'
      throw err
    } finally {
      isSaving.value = false
    }
  }

  return {
    selectedPlaybookId,
    draftId,
    draftName,
    nodes,
    edges,
    selectedNodeId,
    error,
    isSaving,
    selectedPlaybook,
    selectedNode,
    graphTitle,
    loadPlaybook,
    loadFirstPlaybookIfNeeded,
    startNewDraft,
    addNodeFromCatalog,
    connectNodes,
    updateNodeConfig,
    save,
  }
})

function nodeFromType(
  nodeType: string,
  position: NodeInsertPosition,
  nodeTypes: PlaybookNodeType[],
  config: Record<string, unknown>,
  id: string,
): PlaybookFlowNode {
  const definition = nodeTypes.find((item) => item.id === nodeType)
  return {
    id,
    type: 'playbookNode',
    position,
    data: {
      label: definition?.label ?? nodeType,
      nodeType,
      category: definition?.category ?? 'action',
      boundary: definition?.boundary ?? 'unknown',
      sensitive: Boolean(definition?.sensitive),
      liveAvailable: Boolean(definition?.liveAvailable),
      executionMode: definition?.executionMode ?? 'dry_run',
      config,
    },
  }
}

function uniqueNodeId(nodeType: string) {
  const safeType = nodeType.replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return `${safeType || 'node'}_${Date.now().toString(36)}`
}

function uniquePlaybookId() {
  return `pb_canvas_${Date.now().toString(36)}`
}
