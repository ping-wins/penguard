<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import { VueFlow, type Connection } from '@vue-flow/core'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'
import { GripHorizontal, Maximize2, Minimize2, Plus, Save, ShieldCheck, Trash2, Workflow } from 'lucide-vue-next'
import { useDashboardStore } from '../../../stores/useDashboardStore'
import { usePlaybooksStore } from '../../../stores/usePlaybooksStore'
import { usePlaybookCanvasStore } from '../../../stores/usePlaybookCanvasStore'
import {
  defaultNodeConfig,
  PLAYBOOK_NODE_DRAG_MIME,
  parsePlaybookNodeDragPayload,
  serializePlaybookNodeDragPayload,
  type PlaybookCanvasNodeData,
} from '../../../utils/playbookGraph'
import type { PlaybookNodeType } from '../../../services/playbooksClient'
import PlaybookFlowNode from './PlaybookFlowNode.vue'
import PlaybookFlowEdge from './PlaybookFlowEdge.vue'
import PlaybookNodePropertiesPanel from './PlaybookNodePropertiesPanel.vue'
import PlaybookRunOverlay from './PlaybookRunOverlay.vue'

const props = withDefaults(defineProps<{
  embedded?: boolean
  surface?: boolean
}>(), {
  embedded: false,
  surface: false,
})

const { t } = useI18n()
const dashboardStore = useDashboardStore()
const playbooksStore = usePlaybooksStore()
const canvasStore = usePlaybookCanvasStore()
const isFullscreen = ref(false)
const isMoving = ref(false)
const layerPosition = ref({ x: 840, y: 120 })
const {
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
} = storeToRefs(canvasStore)

const selectedSimulation = computed(() => (
  selectedPlaybookId.value ? playbooksStore.simulations[selectedPlaybookId.value] ?? null : null
))
const selectedRun = computed(() => {
  if (!selectedPlaybookId.value) return null
  const runId = playbooksStore.latestRunByPlaybook[selectedPlaybookId.value]
  return runId ? playbooksStore.runs[runId] ?? null : null
})
const automationNodeTypes = computed(() => playbooksStore.nodeTypes.filter((nodeType) => nodeType.category !== 'trigger'))
const isAnchored = computed(() => props.embedded || props.surface)
const selectedIsSystem = computed(() => Boolean(selectedPlaybook.value?.system))
const layerClass = computed(() => (
  isFullscreen.value
    ? 'fixed inset-4 z-[900] h-auto w-auto rounded-lg'
    : props.surface
      ? 'relative h-full w-full rounded-none border-0 shadow-none'
    : props.embedded
      ? 'relative h-full w-full rounded-none'
    : 'absolute z-[160] h-[680px] w-[1180px] rounded'
))
const layerStyle = computed(() => (
  isFullscreen.value || isAnchored.value
    ? undefined
    : { transform: `translate(${Math.round(layerPosition.value.x)}px, ${Math.round(layerPosition.value.y)}px)` }
))
const bodyGridClass = computed(() => (
  isFullscreen.value
    ? 'playbook-builder-body playbook-builder-body--fullscreen'
    : props.surface
      ? 'playbook-builder-body playbook-builder-body--surface'
    : props.embedded
      ? 'playbook-builder-body playbook-builder-body--embedded'
      : 'playbook-builder-body playbook-builder-body--floating'
))
const fullscreenLabel = computed(() => (
  isFullscreen.value ? t('playbooks.canvas.exitFullscreen') : t('playbooks.canvas.enterFullscreen')
))
const moveLabel = computed(() => t('playbooks.canvas.moveBuilder'))

let moveStartClientX = 0
let moveStartClientY = 0
let moveStartLayerX = 0
let moveStartLayerY = 0

onMounted(() => {
  canvasStore.loadFirstPlaybookIfNeeded()
  playbooksStore.loadWebhookDestinations()
  window.addEventListener('keydown', handleFullscreenKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleFullscreenKeydown)
  stopMove()
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

function handleNodeDrawerDragStart(event: DragEvent, nodeType: PlaybookNodeType) {
  if (!event.dataTransfer) return
  event.dataTransfer.setData(
    PLAYBOOK_NODE_DRAG_MIME,
    serializePlaybookNodeDragPayload({
      nodeType: nodeType.id,
      config: defaultNodeConfig(nodeType.id),
    }),
  )
  event.dataTransfer.setData('text/plain', nodeType.id)
  event.dataTransfer.effectAllowed = 'copy'
}

function selectNode(node: { id: string }) {
  selectedNodeId.value = node.id
}

async function saveGraph() {
  if (selectedIsSystem.value) {
    error.value = t('playbooks.canvas.systemReadOnly')
    return
  }
  await canvasStore.save().catch(() => undefined)
}

async function deletePlaybook(playbookId: string) {
  const playbook = playbooksStore.playbooks.find((item) => item.id === playbookId)
  if (!playbook || playbook.system) return
  if (!window.confirm(t('playbooks.canvas.deleteConfirm', { name: playbook.name }))) return
  await playbooksStore.remove(playbookId).catch(() => undefined)
  if (selectedPlaybookId.value === playbookId) {
    const nextPlaybook = playbooksStore.playbooks[0] ?? null
    if (nextPlaybook) {
      canvasStore.loadPlaybook(nextPlaybook)
    } else {
      canvasStore.startNewDraft()
    }
  }
}

async function simulateGraph() {
  if (!selectedPlaybookId.value) return
  await playbooksStore.simulate(selectedPlaybookId.value).catch(() => undefined)
}

function toggleFullscreen() {
  stopMove()
  isFullscreen.value = !isFullscreen.value
}

function handleFullscreenKeydown(event: KeyboardEvent) {
  if (!isFullscreen.value || event.key !== 'Escape') return
  event.preventDefault()
  isFullscreen.value = false
}

function startMove(event: PointerEvent) {
  if (isFullscreen.value || isAnchored.value) return
  isMoving.value = true
  moveStartClientX = event.clientX
  moveStartClientY = event.clientY
  moveStartLayerX = layerPosition.value.x
  moveStartLayerY = layerPosition.value.y
  window.addEventListener('pointermove', handleMove)
  window.addEventListener('pointerup', stopMove)
  event.preventDefault()
  event.stopPropagation()
}

function handleMove(event: PointerEvent) {
  if (!isMoving.value) return
  const zoom = dashboardStore.zoom || 1
  layerPosition.value = {
    x: moveStartLayerX + (event.clientX - moveStartClientX) / zoom,
    y: moveStartLayerY + (event.clientY - moveStartClientY) / zoom,
  }
}

function stopMove() {
  if (!isMoving.value) return
  isMoving.value = false
  window.removeEventListener('pointermove', handleMove)
  window.removeEventListener('pointerup', stopMove)
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
  <Teleport to="body" :disabled="!isFullscreen">
    <section
      data-test="playbook-canvas-layer"
      class="playbook-builder-shell flex flex-col overflow-hidden border border-theme-border bg-theme-panel/95 shadow-2xl"
      :class="[layerClass, isAnchored && !isFullscreen ? 'shadow-none' : '', isMoving ? 'ring-2 ring-theme-primary/50 shadow-theme-primary/10' : '']"
      :style="layerStyle"
    >
      <header class="flex items-center justify-between gap-3 border-b border-theme-border px-3 py-2">
        <div class="flex min-w-0 items-center gap-2">
          <button
            v-if="!isAnchored"
            type="button"
            data-test="playbook-canvas-drag-handle"
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded border border-theme-border bg-theme-bg text-theme-text-muted hover:text-theme-text disabled:cursor-default disabled:opacity-50"
            :class="isMoving ? 'cursor-grabbing' : 'cursor-grab'"
            :disabled="isFullscreen"
            :title="moveLabel"
            :aria-label="moveLabel"
            @pointerdown="startMove"
          >
            <GripHorizontal :size="14" />
          </button>
          <Workflow :size="16" class="shrink-0 text-theme-primary" />
          <div class="min-w-0">
            <div class="flex min-w-0 items-center gap-2">
              <div class="truncate text-sm font-semibold text-theme-text">{{ graphTitle }}</div>
              <span
                v-if="selectedIsSystem"
                class="inline-flex shrink-0 items-center gap-1 rounded border border-amber-400/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-100"
              >
                <ShieldCheck :size="11" />
                {{ t('playbooks.canvas.systemTemplate') }}
              </span>
            </div>
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
            :disabled="isSaving || nodes.length === 0 || selectedIsSystem"
            :title="selectedIsSystem ? t('playbooks.canvas.systemReadOnly') : t('playbooks.canvas.saveGraph')"
            @click="saveGraph"
          >
            <Save :size="13" />
            {{ isSaving ? t('playbooks.saving') : t('playbooks.canvas.saveGraph') }}
          </button>
          <button
            type="button"
            data-test="playbook-canvas-fullscreen-toggle"
            class="inline-flex h-8 w-8 items-center justify-center rounded border border-theme-border bg-theme-bg text-theme-text-muted hover:text-theme-text"
            :title="fullscreenLabel"
            :aria-label="fullscreenLabel"
            @click="toggleFullscreen"
          >
            <Minimize2 v-if="isFullscreen" :size="14" />
            <Maximize2 v-else :size="14" />
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

      <div :class="bodyGridClass">
        <aside
          data-test="playbook-node-drawer"
          class="playbook-builder-node-drawer flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-theme-border bg-theme-panel/80"
        >
          <section data-test="playbook-library" class="border-b border-theme-border">
            <div class="border-b border-theme-border px-3 py-2">
              <div class="flex items-center justify-between gap-2">
                <h3 class="truncate text-[11px] font-semibold uppercase tracking-wide text-theme-text">
                  {{ t('playbooks.canvas.playbookLibrary') }}
                </h3>
                <button
                  type="button"
                  data-test="playbook-library-new"
                  class="inline-flex h-6 shrink-0 items-center gap-1 rounded border border-theme-border bg-theme-bg px-1.5 text-[10px] text-theme-text-muted hover:text-theme-text"
                  @click="canvasStore.startNewDraft"
                >
                  <Plus :size="11" />
                  {{ t('playbooks.canvas.newGraph') }}
                </button>
              </div>
            </div>
            <div class="max-h-48 overflow-y-auto p-2">
              <div v-if="playbooksStore.playbooks.length === 0" class="rounded border border-theme-border bg-theme-bg p-2 text-[11px] text-theme-text-muted">
                {{ t('playbooks.empty') }}
              </div>
              <div v-else class="grid grid-cols-1 gap-1.5">
                <div
                  v-for="playbook in playbooksStore.playbooks"
                  :key="playbook.id"
                  role="button"
                  tabindex="0"
                  class="group grid min-w-0 cursor-pointer grid-cols-[minmax(0,1fr)_auto] gap-2 rounded border p-2 text-left transition-colors"
                  :class="selectedPlaybookId === playbook.id ? 'border-theme-primary/60 bg-theme-primary/10' : 'border-theme-border bg-theme-bg hover:border-theme-primary/40'"
                  :data-test="`playbook-library-card-${playbook.id}`"
                  @click="canvasStore.loadPlaybook(playbook)"
                  @keydown.enter.prevent="canvasStore.loadPlaybook(playbook)"
                  @keydown.space.prevent="canvasStore.loadPlaybook(playbook)"
                >
                  <span class="min-w-0">
                    <span class="block truncate text-xs font-semibold text-theme-text">{{ playbook.name }}</span>
                    <span class="mt-1 flex min-w-0 items-center gap-1">
                      <span
                        class="rounded border px-1 py-0.5 text-[9px]"
                        :class="playbook.system ? 'border-amber-400/40 text-amber-100' : 'border-theme-border text-theme-text-muted'"
                      >
                        {{ playbook.system ? t('playbooks.canvas.systemTemplate') : t('playbooks.canvas.customPlaybook') }}
                      </span>
                      <span class="truncate font-mono text-[9px] text-theme-text-muted">{{ playbook.id }}</span>
                    </span>
                  </span>
                  <span class="flex shrink-0 items-center gap-1">
                    <button
                      v-if="!playbook.system"
                      type="button"
                      class="inline-flex h-7 w-7 items-center justify-center rounded border border-red-400/30 text-red-200 opacity-80 hover:bg-red-500/10 hover:opacity-100 disabled:opacity-40"
                      :data-test="`playbook-delete-${playbook.id}`"
                      :disabled="playbooksStore.isDeleting[playbook.id]"
                      :title="t('playbooks.canvas.deletePlaybook')"
                      @click.stop="deletePlaybook(playbook.id)"
                    >
                      <Trash2 :size="12" />
                    </button>
                  </span>
                </div>
              </div>
            </div>
          </section>

          <div class="border-b border-theme-border px-3 py-2">
            <div class="flex items-center justify-between gap-2">
              <h3 class="truncate text-[11px] font-semibold uppercase tracking-wide text-theme-text">
                {{ t('playbooks.canvas.automationNodes') }}
              </h3>
              <span class="shrink-0 rounded border border-theme-border bg-theme-bg px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                {{ playbooksStore.isLoading ? t('common.loading') : t('playbooks.canvas.nodeCount', { count: automationNodeTypes.length }) }}
              </span>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto p-2">
            <div v-if="playbooksStore.error" class="rounded border border-red-500/30 bg-red-500/10 p-2 text-[11px] text-red-200">
              {{ playbooksStore.error }}
            </div>
            <div v-else-if="playbooksStore.isLoading" class="rounded border border-theme-border bg-theme-bg p-2 text-[11px] text-theme-text-muted">
              {{ t('playbooks.canvas.loadingNodes') }}
            </div>
            <div v-else-if="automationNodeTypes.length === 0" class="rounded border border-theme-border bg-theme-bg p-2 text-[11px] text-theme-text-muted">
              {{ t('playbooks.canvas.emptyNodes') }}
            </div>
            <div v-else class="grid grid-cols-1 gap-2">
              <div
                v-for="nodeType in automationNodeTypes"
                :key="nodeType.id"
                draggable="true"
                class="cursor-grab rounded border border-theme-border bg-theme-bg p-2 text-left transition-colors hover:border-theme-primary/50 hover:bg-theme-border/50 active:cursor-grabbing"
                :class="nodeType.sensitive ? 'border-red-400/30 bg-red-500/5' : ''"
                :data-test="`playbook-node-drawer-node-${nodeType.id}`"
                :title="nodeType.boundary"
                @dragstart="handleNodeDrawerDragStart($event, nodeType)"
              >
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <div class="truncate text-xs font-semibold text-theme-text">{{ nodeType.label }}</div>
                    <div class="mt-0.5 truncate font-mono text-[10px] text-theme-text-muted">{{ nodeType.id }}</div>
                  </div>
                  <span
                    class="shrink-0 rounded border px-1 py-0.5 text-[9px]"
                    :class="nodeType.liveAvailable ? 'border-amber-400/40 text-amber-100' : 'border-sky-400/30 text-sky-100'"
                  >
                    {{ nodeType.liveAvailable ? t('playbooks.liveCapable') : t('playbooks.dryRunOnly') }}
                  </span>
                </div>
                <div class="mt-2 flex flex-wrap gap-1">
                  <span class="rounded border border-theme-border bg-theme-panel/70 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                    {{ nodeType.category }}
                  </span>
                  <span class="max-w-full truncate rounded border border-theme-border bg-theme-panel/70 px-1.5 py-0.5 text-[10px] text-theme-text-muted">
                    {{ nodeType.boundary }}
                  </span>
                </div>
                <p v-if="nodeType.effectSummary" class="mt-2 line-clamp-2 text-[10px] leading-snug text-theme-text-muted">
                  {{ nodeType.effectSummary }}
                </p>
                <div v-if="nodeType.requiredInputs?.length" class="mt-2 flex flex-col gap-1">
                  <div
                    v-for="input in nodeType.requiredInputs"
                    :key="input.key"
                    class="rounded border border-theme-border bg-theme-panel/70 px-1.5 py-1 text-[10px] text-theme-text-muted"
                  >
                    <span class="font-semibold text-theme-text">{{ input.label }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div
          data-test="playbook-canvas-drop-zone"
          class="relative min-h-0 min-w-0"
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

        <div class="playbook-builder-properties flex min-h-0 min-w-0 flex-col gap-3 overflow-y-auto border-l border-theme-border bg-theme-panel/80 p-3">
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
  </Teleport>
</template>

<style>
@import '@vue-flow/core/dist/style.css';
@import '@vue-flow/core/dist/theme-default.css';
@import '@vue-flow/controls/dist/style.css';
@import '@vue-flow/minimap/dist/style.css';

.playbook-builder-shell {
  container-type: inline-size;
}

.playbook-builder-body {
  display: grid;
  min-height: 0;
  flex: 1 1 0%;
}

.playbook-builder-body--fullscreen {
  grid-template-columns: 240px minmax(0, 1fr) 320px;
}

.playbook-builder-body--surface {
  grid-template-columns: 280px minmax(0, 1fr) 340px;
}

.playbook-builder-body--floating {
  grid-template-columns: 220px minmax(0, 1fr) 260px;
}

.playbook-builder-body--embedded {
  grid-template-columns: minmax(190px, 220px) minmax(360px, 1fr) minmax(240px, 280px);
}

@container (max-width: 920px) {
  .playbook-builder-body--surface {
    grid-template-columns: minmax(220px, 260px) minmax(0, 1fr);
  }

  .playbook-builder-body--surface .playbook-builder-properties {
    grid-column: 1 / -1;
    min-height: 260px;
    border-left: 0;
    border-top: 1px solid var(--theme-border);
  }

  .playbook-builder-body--embedded {
    grid-template-columns: minmax(170px, 200px) minmax(0, 1fr);
  }

  .playbook-builder-body--embedded .playbook-builder-properties {
    grid-column: 1 / -1;
    min-height: 230px;
    border-left: 0;
    border-top: 1px solid var(--theme-border);
  }
}

@container (max-width: 760px) {
  .playbook-builder-body--surface {
    grid-template-columns: 1fr;
  }

  .playbook-builder-body--surface .playbook-builder-node-drawer {
    max-height: 300px;
    border-right: 0;
    border-bottom: 1px solid var(--theme-border);
  }

  .playbook-builder-body--embedded {
    grid-template-columns: 1fr;
  }

  .playbook-builder-body--embedded .playbook-builder-node-drawer {
    max-height: 220px;
    border-right: 0;
    border-bottom: 1px solid var(--theme-border);
  }
}
</style>
