<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { VueFlow, type Connection } from '@vue-flow/core'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { Plus, Save, Workflow } from 'lucide-vue-next'
import { usePlaybooksStore } from '../../../stores/usePlaybooksStore'
import { usePlaybookCanvasStore } from '../../../stores/usePlaybookCanvasStore'
import {
  PLAYBOOK_NODE_DRAG_MIME,
  parsePlaybookNodeDragPayload,
  type PlaybookCanvasNodeData,
} from '../../../utils/playbookGraph'
import PlaybookFlowNode from './PlaybookFlowNode.vue'
import PlaybookFlowEdge from './PlaybookFlowEdge.vue'
import PlaybookNodePropertiesPanel from './PlaybookNodePropertiesPanel.vue'
import PlaybookRunOverlay from './PlaybookRunOverlay.vue'

const { t } = useI18n()
const playbooksStore = usePlaybooksStore()
const canvasStore = usePlaybookCanvasStore()
const {
  selectedPlaybookId,
  draftId,
  draftName,
  nodes,
  edges,
  selectedNodeId,
  error,
  isSaving,
  selectedNode,
  graphTitle,
} = storeToRefs(canvasStore)

const selectedSimulation = computed(() => (
  selectedPlaybookId.value ? playbooksStore.simulations[selectedPlaybookId.value] ?? null : null
))
const selectedRun = computed(() => {
  if (!selectedPlaybookId.value) return null
  const runId = playbooksStore.latestRunByPlaybook[selectedPlaybookId.value]
  return runId ? playbooksStore.runs[runId] ?? null : null
})

onMounted(() => {
  canvasStore.loadFirstPlaybookIfNeeded()
})

watch(
  () => playbooksStore.playbooks.length,
  () => canvasStore.loadFirstPlaybookIfNeeded(),
)

function selectPlaybook(event: Event) {
  const id = (event.target as HTMLSelectElement).value
  const playbook = playbooksStore.playbooks.find((item) => item.id === id)
  canvasStore.loadPlaybook(playbook ?? null)
}

function handleConnect(connection: Connection) {
  canvasStore.connectNodes(connection)
}

function handleDrop(event: DragEvent) {
  const payload = parsePlaybookNodeDragPayload(event.dataTransfer)
  if (!payload) return
  event.preventDefault()
  const target = event.currentTarget instanceof HTMLElement ? event.currentTarget : null
  const rect = target?.getBoundingClientRect()
  canvasStore.addNodeFromCatalog(
    payload.nodeType,
    {
      x: Math.max(0, Math.round(event.clientX - (rect?.left ?? 0))),
      y: Math.max(0, Math.round(event.clientY - (rect?.top ?? 0))),
    },
    payload.config,
  )
}

function handleDragOver(event: DragEvent) {
  if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes(PLAYBOOK_NODE_DRAG_MIME)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
}

function selectNode(node: { id: string }) {
  selectedNodeId.value = node.id
}

async function saveGraph() {
  await canvasStore.save().catch(() => undefined)
}

async function simulateGraph() {
  if (!selectedPlaybookId.value) return
  await playbooksStore.simulate(selectedPlaybookId.value).catch(() => undefined)
}

function nodeColor(node: { data?: PlaybookCanvasNodeData }) {
  if (node.data?.sensitive) return '#ef4444'
  if (node.data?.category === 'control') return '#f59e0b'
  if (node.data?.category === 'trigger') return '#22c55e'
  return '#38bdf8'
}

function nodeListLabel(node: { id: string, data?: PlaybookCanvasNodeData }) {
  return node.data?.nodeType ?? node.id
}
</script>

<template>
  <section
    data-test="playbook-canvas-layer"
    class="absolute left-[840px] top-[120px] z-[160] flex h-[620px] w-[980px] flex-col overflow-hidden rounded border border-theme-border bg-theme-panel/95 shadow-2xl"
  >
    <header class="flex items-center justify-between gap-3 border-b border-theme-border px-3 py-2">
      <div class="flex min-w-0 items-center gap-2">
        <Workflow :size="16" class="shrink-0 text-theme-primary" />
        <div class="min-w-0">
          <div class="truncate text-sm font-semibold text-theme-text">{{ graphTitle }}</div>
          <div class="truncate text-[11px] text-theme-text-muted">{{ t('playbooks.canvas.subtitle') }}</div>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <select
          :value="selectedPlaybookId"
          data-test="playbook-canvas-select"
          class="h-8 max-w-[180px] rounded border border-theme-border bg-theme-bg px-2 text-xs text-theme-text"
          @change="selectPlaybook"
        >
          <option value="">{{ t('playbooks.canvas.newDraft') }}</option>
          <option v-for="playbook in playbooksStore.playbooks" :key="playbook.id" :value="playbook.id">
            {{ playbook.name }}
          </option>
        </select>
        <button
          type="button"
          data-test="playbook-canvas-new"
          class="inline-flex h-8 items-center gap-1 rounded border border-theme-border bg-theme-bg px-2 text-xs text-theme-text-muted hover:text-theme-text"
          @click="canvasStore.startNewDraft"
        >
          <Plus :size="13" />
          {{ t('playbooks.canvas.newGraph') }}
        </button>
        <button
          type="button"
          data-test="playbook-canvas-save"
          class="inline-flex h-8 items-center gap-1 rounded border border-theme-primary/40 bg-theme-primary/10 px-2 text-xs font-semibold text-theme-primary hover:bg-theme-primary/20 disabled:opacity-50"
          :disabled="isSaving || nodes.length === 0"
          @click="saveGraph"
        >
          <Save :size="13" />
          {{ isSaving ? t('playbooks.saving') : t('playbooks.canvas.saveGraph') }}
        </button>
        <button
          type="button"
          data-test="playbook-canvas-simulate"
          class="h-8 rounded border border-emerald-400/40 bg-emerald-500/10 px-2 text-xs font-semibold text-emerald-200 disabled:opacity-50"
          :disabled="!selectedPlaybookId"
          @click="simulateGraph"
        >
          {{ t('playbooks.simulate') }}
        </button>
      </div>
    </header>

    <div v-if="error || playbooksStore.error" class="border-b border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
      {{ error || playbooksStore.error }}
    </div>

    <div class="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_260px]">
      <div
        data-test="playbook-canvas-drop-zone"
        class="relative min-h-0"
        @drop="handleDrop"
        @dragover="handleDragOver"
      >
        <VueFlow
          v-model:nodes="nodes"
          v-model:edges="edges"
          class="h-full w-full bg-theme-bg"
          fit-view-on-init
          @connect="handleConnect"
          @node-click="selectNode($event.node)"
        >
          <template #node-playbookNode="nodeProps">
            <PlaybookFlowNode v-bind="nodeProps" />
          </template>
          <template #edge-playbookEdge="edgeProps">
            <PlaybookFlowEdge v-bind="edgeProps" />
          </template>
          <Background />
          <Controls />
          <MiniMap :node-color="nodeColor" pannable zoomable />
        </VueFlow>
      </div>

      <div class="flex min-h-0 flex-col gap-3 border-l border-theme-border bg-theme-panel/80 p-3">
        <div v-if="!selectedPlaybookId" class="grid grid-cols-1 gap-2">
          <input
            v-model="draftId"
            data-test="playbook-canvas-draft-id"
            class="h-8 rounded border border-theme-border bg-theme-bg px-2 text-xs text-theme-text"
            :placeholder="t('playbooks.builderIdPlaceholder')"
          />
          <input
            v-model="draftName"
            data-test="playbook-canvas-draft-name"
            class="h-8 rounded border border-theme-border bg-theme-bg px-2 text-xs text-theme-text"
            :placeholder="t('playbooks.builderNamePlaceholder')"
          />
        </div>
        <PlaybookRunOverlay :simulation="selectedSimulation" :run="selectedRun" />
        <div class="rounded border border-theme-border bg-theme-bg/70 p-2">
          <div class="mb-1 text-[10px] font-semibold uppercase tracking-wide text-theme-text-muted">
            {{ t('playbooks.canvas.nodesInGraph') }}
          </div>
          <button
            v-for="node in nodes"
            :key="node.id"
            type="button"
            class="mb-1 block w-full truncate rounded px-2 py-1 text-left font-mono text-[11px]"
            :class="selectedNodeId === node.id ? 'bg-theme-primary/15 text-theme-primary' : 'text-theme-text-muted hover:bg-theme-border/60 hover:text-theme-text'"
            :data-test="`playbook-canvas-node-list-${node.id}`"
            @click="selectedNodeId = node.id"
          >
            {{ nodeListLabel(node) }}
          </button>
        </div>
        <PlaybookNodePropertiesPanel
          class="min-h-0 flex-1"
          :node="selectedNode"
          @update-config="canvasStore.updateNodeConfig"
        />
      </div>
    </div>
  </section>
</template>

<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
@import '@vue-flow/controls/dist/style.css';
@import '@vue-flow/minimap/dist/style.css';
</style>
