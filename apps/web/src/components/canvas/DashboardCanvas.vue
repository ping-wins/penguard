<script setup lang="ts">
import { computed, nextTick, ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { useIntegrationsStore } from '../../stores/useIntegrationsStore'
import { useProviderDataStore } from '../../stores/useProviderDataStore'
import { useWidgetCompactStore } from '../../stores/useWidgetCompactStore'
import { useWidgetSeriesStore } from '../../stores/useWidgetSeriesStore'
import {
  useCockpitLayoutStore,
  BUILD_PANE_MAX_WIDTH,
  BUILD_PANE_MIN_WIDTH,
} from '../../stores/useCockpitLayoutStore'
import { useDraggableEdge } from '../../composables/useDraggableEdge'
import { storeToRefs } from 'pinia'
import {
  PanelRightClose,
  PanelRightOpen,
  Minimize2,
  Maximize2,
  Filter,
  BarChart2,
  Database,
  Folder,
  FolderOpen,
  Table,
  Activity,
  Network,
  RefreshCcw,
  AlertTriangle,
  Layers3,
  Pencil,
  Check,
  X,
  ChevronDown,
  ChevronRight,
} from 'lucide-vue-next'
import DraggableWidget from './DraggableWidget.vue'
import WidgetHealth from '../widgets/WidgetHealth.vue'
import WidgetThreats from '../widgets/WidgetThreats.vue'
import WidgetNetwork from '../widgets/WidgetNetwork.vue'
import WidgetKpiCard from '../widgets/WidgetKpiCard.vue'
import WidgetFirewallPolicies from '../widgets/WidgetFirewallPolicies.vue'
import WidgetRiskPosture from '../widgets/WidgetRiskPosture.vue'
import WidgetInterfaceHealth from '../widgets/WidgetInterfaceHealth.vue'
import WidgetRecentEvents from '../widgets/WidgetRecentEvents.vue'
import WidgetAnomalyHighlights from '../widgets/WidgetAnomalyHighlights.vue'
import WidgetEmptyVisual from '../widgets/WidgetEmptyVisual.vue'
import WidgetGenericData from '../widgets/WidgetGenericData.vue'
import WidgetSocIncidentsBySeverity from '../widgets/soc/WidgetSocIncidentsBySeverity.vue'
import WidgetSocRecentIncidents from '../widgets/soc/WidgetSocRecentIncidents.vue'
import WidgetSocTopEntities from '../widgets/soc/WidgetSocTopEntities.vue'
import WidgetXdrEndpointHealth from '../widgets/soc/WidgetXdrEndpointHealth.vue'
import WidgetSoarPlaybookRuns from '../widgets/soc/WidgetSoarPlaybookRuns.vue'
import WidgetSocSlaBreach from '../widgets/soc/WidgetSocSlaBreach.vue'
import WidgetSocMttdMttr from '../widgets/soc/WidgetSocMttdMttr.vue'
import WidgetFortigateTopSourceIps from '../widgets/fortigate/WidgetFortigateTopSourceIps.vue'
import { isVisualTemplateId, visualTemplates, type VisualTemplate } from '../../constants/visualTemplates'
import type { ProviderDataField, ProviderDataGroup } from '../../services/providerDataClient'
import type { WidgetFieldBinding } from '../../types/dashboard'
import { PROVIDER_FIELD_DRAG_MIME, serializeFieldBinding } from '../../utils/fieldDrag'

const dashboardStore = useDashboardStore()
const integrationsStore = useIntegrationsStore()
const providerDataStore = useProviderDataStore()
const layoutStore = useCockpitLayoutStore()
const compactStore = useWidgetCompactStore()
const widgetSeriesStore = useWidgetSeriesStore()
const { t } = useI18n()
const { activeWidgets, workspaceName, catalogItems } = storeToRefs(dashboardStore)
const { buildPaneWidth, minimapCollapsed } = storeToRefs(layoutStore)

// --- workspace rename (inline editable header) ---
const renameDraft = ref('')
const isRenaming = ref(false)
const renameError = ref('')
const renameInput = ref<HTMLInputElement | null>(null)

async function startRename() {
  renameError.value = ''
  renameDraft.value = workspaceName.value
  isRenaming.value = true
  await nextTick()
  renameInput.value?.focus()
  renameInput.value?.select()
}

async function commitRename() {
  const next = renameDraft.value.trim()
  if (!next || next === workspaceName.value) {
    isRenaming.value = false
    return
  }
  try {
    await dashboardStore.renameActiveWorkspace(next)
    isRenaming.value = false
  } catch (error: any) {
    renameError.value = error?.message ?? t('workspaces.rename.error')
  }
}

function cancelRename() {
  isRenaming.value = false
  renameError.value = ''
}

// Browser tab title mirrors the workspace name so a renamed/imported workspace
// is identifiable from the tab strip.
watch(
  workspaceName,
  (name) => {
    if (typeof document !== 'undefined') {
      document.title = name ? `${name} · FortiDashboard` : 'FortiDashboard'
    }
  },
  { immediate: true },
)

// --- resizable build pane ---
const buildPaneResizer = useDraggableEdge({
  edge: 'left',
  getCurrent: () => buildPaneWidth.value,
  setValue: (next) => layoutStore.setBuildPaneWidth(next),
  min: BUILD_PANE_MIN_WIDTH,
  max: BUILD_PANE_MAX_WIDTH,
})
const {
  groups: dataFieldGroups,
  isLoading: isDataFieldsLoading,
  error: dataFieldsError,
} = storeToRefs(providerDataStore)

onMounted(async () => {
  window.addEventListener('keydown', handleViewportKeyDown)
  window.addEventListener('keyup', handleViewportKeyUp)
  await integrationsStore.fetchIntegrations()
  if (integrationsStore.hasWorkspaceIntegrations) {
    await loadBuildPaneData()
  }
  await dashboardStore.loadWorkspace()
  centerWorkspaceOnOrigin()
})

watch(() => integrationsStore.connectedIntegrationTypes.join('|'), (typesKey) => {
  if (typesKey) {
    loadBuildPaneData()
  } else {
    dashboardStore.fetchCatalog([])
  }
})

const severityHeatStrip = computed(() => {
  const counts: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 }
  const seenIntegrations = new Set<string>()
  for (const widget of activeWidgets.value) {
    if (widget.catalogId !== 'soc-incidents-by-severity') continue
    if (!widget.integrationId) continue
    const dedupeKey = widget.integrationId
    if (seenIntegrations.has(dedupeKey)) continue
    seenIntegrations.add(dedupeKey)
    const data: any = widgetSeriesStore.getSiblingData('soc-incidents-by-severity', widget.integrationId)
    if (!data || !Array.isArray(data.items)) continue
    for (const row of data.items) {
      if (!row || typeof row !== 'object') continue
      const sev = String(row.severity ?? '').toLowerCase()
      const count = Number(row.count) || 0
      if (sev in counts) counts[sev] += count
    }
  }
  return counts
})

const heatStripTotal = computed(() => Object.values(severityHeatStrip.value).reduce((sum, v) => sum + v, 0))

const isBuildPaneOpen = ref(true)
const activeBuildTab = ref<'filters' | 'visuals' | 'data'>('visuals')
const fortigateIntegrations = computed(() => integrationsStore.integrations.filter(i => i.type === 'fortigate'))
const connectedIntegrationTypes = computed(() => integrationsStore.connectedIntegrationTypes)
const dataFieldCount = computed(() => dataFieldGroups.value.reduce((total, group) => total + group.fields.length, 0))
const dataFieldCountLabel = computed(() => `${dataFieldCount.value} field${dataFieldCount.value === 1 ? '' : 's'} available`)
const visualPresetCountLabel = computed(() => `${catalogItems.value.length} preset${catalogItems.value.length === 1 ? '' : 's'} ready`)
const isVisualCatalogLoading = computed(() => !dashboardStore.isCatalogLoaded && catalogItems.value.length === 0)
const isVisualCatalogEmpty = computed(() => dashboardStore.isCatalogLoaded && catalogItems.value.length === 0)
const catalogGroups = computed(() => {
  const groups = new Map<string, { id: string, label: string, items: typeof catalogItems.value }>()
  for (const item of catalogItems.value) {
    const key = item.integrationType || item.source || 'custom'
    const label = categoryLabelForIntegration(key)
    if (!groups.has(key)) groups.set(key, { id: key, label, items: [] })
    groups.get(key)?.items.push(item)
  }
  return Array.from(groups.values())
})
let buildPaneDataLoad: Promise<void> | null = null

const WORKSPACE_WIDTH_PX = 200000
const WORKSPACE_HEIGHT_PX = 200000
const WORKSPACE_ORIGIN_X_PX = WORKSPACE_WIDTH_PX / 2
const WORKSPACE_ORIGIN_Y_PX = WORKSPACE_HEIGHT_PX / 2
const WORKSPACE_DOT_SIZE_PX = 24
const MINIMAP_WIDTH_PX = 160
const MINIMAP_HEIGHT_PX = 104
const MIN_ZOOM = 0.2
const MAX_ZOOM = 3
const WORKSPACE_WIDGET_DRAG_MIME = 'application/x-fortidashboard-widget'

const workspaceViewport = ref<HTMLElement | null>(null)
const viewportScroll = ref({ x: 0, y: 0 })
const isSpacePanning = ref(false)
const isViewportPanning = ref(false)

let panStartX = 0
let panStartY = 0
let panStartScrollLeft = 0
let panStartScrollTop = 0
let hasCenteredWorkspace = false

type WorkspaceWidgetDragPayload = {
  kind: 'catalog' | 'template'
  catalogId: string
}

const expandedFolders = ref<Record<string, boolean>>({
  'system': true
})

function toggleFolder(id: string) {
  expandedFolders.value[id] = !expandedFolders.value[id]
}

function integrationForCatalogId(catalogId: string) {
  const catalogItem = catalogItems.value.find(item => item.id === catalogId)
  const integrationType = catalogItem?.integrationType || catalogItem?.source
  if (integrationType) {
    return integrationsStore.integrations.find(integration => integration.type === integrationType)
  }
  return integrationsStore.integrations[0]
}

function handleAddWidget(catalogId: string) {
  const integration = integrationForCatalogId(catalogId)
  if (integration) {
    dashboardStore.addWidget(catalogId, integration.id)
  }
}

async function loadBuildPaneData() {
  if (buildPaneDataLoad) return buildPaneDataLoad
  buildPaneDataLoad = (async () => {
    const tasks: Array<Promise<unknown>> = []
    tasks.push(dashboardStore.fetchCatalog(connectedIntegrationTypes.value))
    if (!providerDataStore.isLoading) {
      if (integrationsStore.hasWorkspaceIntegrations) {
        tasks.push(providerDataStore.fetchFieldsForIntegrations(integrationsStore.integrations))
      }
    }
    await Promise.all(tasks)
    expandDataFieldGroups()
  })()
  try {
    await buildPaneDataLoad
  } finally {
    buildPaneDataLoad = null
  }
}

function handleAddVisualTemplate(templateId: string) {
  dashboardStore.addVisualTemplate(templateId, '')
}

function setWorkspaceWidgetDragData(
  event: DragEvent,
  payload: WorkspaceWidgetDragPayload,
) {
  if (!event.dataTransfer) return
  const serialized = JSON.stringify(payload)
  event.dataTransfer.setData(WORKSPACE_WIDGET_DRAG_MIME, serialized)
  event.dataTransfer.setData('text/plain', payload.catalogId)
  event.dataTransfer.effectAllowed = 'copy'
}

function handleCatalogWidgetDragStart(event: DragEvent, catalogId: string) {
  setWorkspaceWidgetDragData(event, { kind: 'catalog', catalogId })
}

function handleVisualTemplateDragStart(event: DragEvent, templateId: string) {
  setWorkspaceWidgetDragData(event, { kind: 'template', catalogId: templateId })
}

function parseWorkspaceWidgetDrag(dataTransfer: DataTransfer | null): WorkspaceWidgetDragPayload | null {
  if (!dataTransfer) return null
  const raw = dataTransfer.getData(WORKSPACE_WIDGET_DRAG_MIME)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    if (
      (parsed.kind !== 'catalog' && parsed.kind !== 'template')
      || typeof parsed.catalogId !== 'string'
    ) {
      return null
    }
    return {
      kind: parsed.kind,
      catalogId: parsed.catalogId,
    }
  } catch {
    return null
  }
}

function handleWorkspaceDragOver(event: DragEvent) {
  const dataTransfer = event.dataTransfer
  if (!dataTransfer) return
  const hasWidgetPayload = Boolean(dataTransfer?.types?.includes(WORKSPACE_WIDGET_DRAG_MIME))
  if (!hasWidgetPayload) return
  event.preventDefault()
  dataTransfer.dropEffect = 'copy'
}

function workspacePointFromEvent(event: DragEvent) {
  const viewport = workspaceViewport.value
  if (!viewport) return { x: 0, y: 0 }
  const rect = viewport.getBoundingClientRect()
  return {
    x: (viewport.scrollLeft + event.clientX - rect.left - WORKSPACE_ORIGIN_X_PX * dashboardStore.zoom) / dashboardStore.zoom,
    y: (viewport.scrollTop + event.clientY - rect.top - WORKSPACE_ORIGIN_Y_PX * dashboardStore.zoom) / dashboardStore.zoom,
  }
}

function handleWorkspaceDrop(event: DragEvent) {
  const payload = parseWorkspaceWidgetDrag(event.dataTransfer)
  if (!payload) return
  event.preventDefault()
  event.stopPropagation()

  const position = workspacePointFromEvent(event)

  if (payload.kind === 'catalog') {
    const integration = integrationForCatalogId(payload.catalogId)
    if (!integration) return
    dashboardStore.addWidget(payload.catalogId, integration.id, position)
    return
  }

  dashboardStore.addVisualTemplate(payload.catalogId, '', position)
}

function retryVisualPresets() {
  dashboardStore.fetchCatalog(connectedIntegrationTypes.value)
}

function retryProviderFields() {
  providerDataStore.fetchFieldsForIntegrations(integrationsStore.integrations).then(expandDataFieldGroups)
}

function expandDataFieldGroups() {
  for (const group of dataFieldGroups.value) {
    if (expandedFolders.value[group.id] === undefined) {
      expandedFolders.value[group.id] = true
    }
  }
}

function categoryLabelForIntegration(integrationType: string) {
  switch (integrationType) {
    case 'fortigate':
      return 'Network / FortiGate'
    case 'siem_kowalski':
      return 'SIEM / Incidents'
    case 'xdr_rico':
      return 'XDR / Endpoints'
    case 'soar_skipper':
      return 'SOAR / Playbooks'
    default:
      return 'Other Integrations'
  }
}

function fieldBindingFromProviderField(
  field: ProviderDataField,
  group: ProviderDataGroup,
): WidgetFieldBinding {
  return {
    fieldId: field.id,
    label: field.label,
    type: field.type,
    unit: field.unit,
    source: field.source,
    provider: field.provider ?? providerDataStore.provider,
    integrationType: field.integrationType ?? field.provider,
    integrationId: field.integrationId,
    groupId: group.id,
    groupName: group.name,
  }
}

function handleFieldDragStart(event: DragEvent, field: ProviderDataField, group: ProviderDataGroup) {
  const binding = fieldBindingFromProviderField(field, group)
  event.dataTransfer?.setData(PROVIDER_FIELD_DRAG_MIME, serializeFieldBinding(binding))
  event.dataTransfer?.setData('text/plain', binding.fieldId)
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
  }
}

function handleFieldDrop(payload: { instanceId: string, binding: WidgetFieldBinding }) {
  dashboardStore.bindFieldToWidget(payload.instanceId, payload.binding)
}

const workspaceSurfaceStyle = computed(() => ({
  width: `${WORKSPACE_WIDTH_PX * dashboardStore.zoom}px`,
  height: `${WORKSPACE_HEIGHT_PX * dashboardStore.zoom}px`,
}))

const workspaceStageStyle = computed(() => ({
  left: `${WORKSPACE_ORIGIN_X_PX * dashboardStore.zoom}px`,
  top: `${WORKSPACE_ORIGIN_Y_PX * dashboardStore.zoom}px`,
  width: '1px',
  height: '1px',
  transform: `scale(${dashboardStore.zoom})`,
}))

const workspaceDotCanvasStyle = computed(() => ({
  backgroundImage: 'radial-gradient(circle at center, rgba(148, 163, 184, 0.26) 1px, transparent 1.3px)',
  backgroundSize: `${WORKSPACE_DOT_SIZE_PX}px ${WORKSPACE_DOT_SIZE_PX}px`,
}))

const viewportWorldRect = computed(() => {
  const viewport = workspaceViewport.value
  const width = Math.max(1, viewport?.clientWidth ?? 1)
  const height = Math.max(1, viewport?.clientHeight ?? 1)
  return {
    x: (viewportScroll.value.x - WORKSPACE_ORIGIN_X_PX * dashboardStore.zoom) / dashboardStore.zoom,
    y: (viewportScroll.value.y - WORKSPACE_ORIGIN_Y_PX * dashboardStore.zoom) / dashboardStore.zoom,
    w: width / dashboardStore.zoom,
    h: height / dashboardStore.zoom,
  }
})

const minimapBounds = computed(() => {
  const viewport = viewportWorldRect.value
  const xs = [viewport.x, viewport.x + viewport.w, 0]
  const ys = [viewport.y, viewport.y + viewport.h, 0]

  for (const widget of activeWidgets.value) {
    xs.push(widget.layout.x, widget.layout.x + widget.layout.w)
    ys.push(widget.layout.y, widget.layout.y + widget.layout.h)
  }

  const padding = 480
  const minX = Math.min(...xs) - padding
  const maxX = Math.max(...xs) + padding
  const minY = Math.min(...ys) - padding
  const maxY = Math.max(...ys) + padding
  return {
    x: minX,
    y: minY,
    w: Math.max(1000, maxX - minX),
    h: Math.max(700, maxY - minY),
  }
})

function minimapRectStyle(rect: { x: number, y: number, w: number, h: number }) {
  const bounds = minimapBounds.value
  return {
    left: `${((rect.x - bounds.x) / bounds.w) * MINIMAP_WIDTH_PX}px`,
    top: `${((rect.y - bounds.y) / bounds.h) * MINIMAP_HEIGHT_PX}px`,
    width: `${Math.max(3, (rect.w / bounds.w) * MINIMAP_WIDTH_PX)}px`,
    height: `${Math.max(3, (rect.h / bounds.h) * MINIMAP_HEIGHT_PX)}px`,
  }
}

const minimapViewportStyle = computed(() => minimapRectStyle(viewportWorldRect.value))
const minimapWidgetRects = computed(() => activeWidgets.value.map(widget => ({
  id: widget.instanceId,
  style: minimapRectStyle(widget.layout),
})))

// Map from catalogId to component
const widgetMap: Record<string, any> = {
  'fortigate-system-status': WidgetHealth,
  'fortigate-top-threats': WidgetThreats,
  'fortigate-network-traffic': WidgetNetwork,
  'fortigate-kpi-sessions': WidgetKpiCard,
  'fortigate-firewall-policies': WidgetFirewallPolicies,
  'fortigate-risk-posture': WidgetRiskPosture,
  'fortigate-interface-health': WidgetInterfaceHealth,
  'fortigate-recent-events': WidgetRecentEvents,
  'fortigate-anomaly-highlights': WidgetAnomalyHighlights,
  'soc-incidents-by-severity': WidgetSocIncidentsBySeverity,
  'soc-recent-incidents': WidgetSocRecentIncidents,
  'soc-top-entities': WidgetSocTopEntities,
  'xdr-endpoint-health': WidgetXdrEndpointHealth,
  'soar-active-playbook-runs': WidgetSoarPlaybookRuns,
  'soc-sla-breach': WidgetSocSlaBreach,
  'soc-mttd-mttr': WidgetSocMttdMttr,
  'fortigate-top-source-ips': WidgetFortigateTopSourceIps,
}

void WidgetGenericData

function getIconForKind(kind: string) {
  switch (kind) {
    case 'kpi': return Activity
    case 'table': return Table
    case 'chart': return Network
    case 'summary': return Activity
    case 'feed': return Table
    case 'status-list': return Network
    default: return BarChart2
  }
}

function getIconForTemplate(template: VisualTemplate) {
  switch (template.kind) {
    case 'card': return Activity
    case 'gauge': return Activity
    case 'table': return Table
    case 'bar': return BarChart2
    case 'line': return Network
    case 'feed': return Database
    case 'list': return Network
    default: return BarChart2
  }
}

function getWidgetComponent(catalogId: string) {
  if (isVisualTemplateId(catalogId)) return WidgetEmptyVisual
  return widgetMap[catalogId]
}

function fieldKey(field: string | { id: string }) {
  return typeof field === 'string' ? field : field.id
}

function fieldLabel(field: string | { label: string }) {
  return typeof field === 'string' ? field : field.label
}

function fieldTypeLabel(field: ProviderDataField) {
  return field.unit ? `${field.type} / ${field.unit}` : field.type
}

function clampZoom(value: number) {
  return Math.max(MIN_ZOOM, Math.min(value, MAX_ZOOM))
}

function syncViewportScroll() {
  const viewport = workspaceViewport.value
  if (!viewport) return
  viewportScroll.value = {
    x: viewport.scrollLeft,
    y: viewport.scrollTop,
  }
}

function centerWorkspaceOnOrigin() {
  if (hasCenteredWorkspace) return
  requestAnimationFrame(() => {
    const viewport = workspaceViewport.value
    if (!viewport) return
    hasCenteredWorkspace = true
    viewport.scrollLeft = WORKSPACE_ORIGIN_X_PX * dashboardStore.zoom - viewport.clientWidth / 2
    viewport.scrollTop = WORKSPACE_ORIGIN_Y_PX * dashboardStore.zoom - viewport.clientHeight / 2
    syncViewportScroll()
  })
}

function handleWheel(e: WheelEvent) {
  const viewport = workspaceViewport.value
  if (!viewport) return

  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const previousZoom = dashboardStore.zoom
    const zoomSensitivity = 0.001
    const nextZoom = clampZoom(previousZoom - e.deltaY * zoomSensitivity)
    if (nextZoom === previousZoom) return

    const rect = viewport.getBoundingClientRect()
    const pointerX = e.clientX - rect.left
    const pointerY = e.clientY - rect.top
    const logicalX = (viewport.scrollLeft + pointerX - WORKSPACE_ORIGIN_X_PX * previousZoom) / previousZoom
    const logicalY = (viewport.scrollTop + pointerY - WORKSPACE_ORIGIN_Y_PX * previousZoom) / previousZoom

    dashboardStore.setZoom(nextZoom)

    requestAnimationFrame(() => {
      viewport.scrollLeft = WORKSPACE_ORIGIN_X_PX * nextZoom + logicalX * nextZoom - pointerX
      viewport.scrollTop = WORKSPACE_ORIGIN_Y_PX * nextZoom + logicalY * nextZoom - pointerY
      syncViewportScroll()
    })
    return
  }

  e.preventDefault()
  if (e.shiftKey) {
    viewport.scrollLeft += e.deltaY + e.deltaX
  } else {
    viewport.scrollLeft += e.deltaX
    viewport.scrollTop += e.deltaY
  }
  syncViewportScroll()
}

function handleViewportKeyDown(event: KeyboardEvent) {
  if (isEditableTarget(event.target)) return
  if (event.code === 'Space') {
    event.preventDefault()
    isSpacePanning.value = true
    return
  }
  if (event.code === 'KeyC' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    event.preventDefault()
    compactStore.toggle()
  }
}

function handleViewportKeyUp(event: KeyboardEvent) {
  if (event.code !== 'Space') return
  event.preventDefault()
  isSpacePanning.value = false
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false
  return Boolean(target.closest('input, textarea, select, button, [contenteditable="true"]'))
}

function startViewportPan(event: PointerEvent) {
  const viewport = workspaceViewport.value
  if (!viewport || (!isSpacePanning.value && event.button !== 1)) return

  event.preventDefault()
  event.stopPropagation()
  isViewportPanning.value = true
  panStartX = event.clientX
  panStartY = event.clientY
  panStartScrollLeft = viewport.scrollLeft
  panStartScrollTop = viewport.scrollTop

  window.addEventListener('pointermove', handleViewportPan)
  window.addEventListener('pointerup', stopViewportPan)
}

function handleViewportPan(event: PointerEvent) {
  if (!isViewportPanning.value || !workspaceViewport.value) return
  workspaceViewport.value.scrollLeft = panStartScrollLeft - (event.clientX - panStartX)
  workspaceViewport.value.scrollTop = panStartScrollTop - (event.clientY - panStartY)
  syncViewportScroll()
}

function stopViewportPan() {
  isViewportPanning.value = false
  window.removeEventListener('pointermove', handleViewportPan)
  window.removeEventListener('pointerup', stopViewportPan)
}

onBeforeUnmount(() => {
  stopViewportPan()
  window.removeEventListener('keydown', handleViewportKeyDown)
  window.removeEventListener('keyup', handleViewportKeyUp)
})
</script>

<template>
  <div class="flex-1 h-full overflow-hidden relative bg-theme-bg flex flex-col z-0">
    <!-- Header/Toolbar -->
    <header class="h-16 border-b border-theme-border flex items-center px-6 bg-theme-panel/50 backdrop-blur-sm z-40 relative shrink-0 justify-between">
      <div class="flex items-center gap-2 min-w-0">
        <template v-if="isRenaming">
          <input
            ref="renameInput"
            v-model="renameDraft"
            data-test="workspace-rename-input"
            class="text-xl font-medium tracking-tight bg-theme-bg border border-theme-border rounded px-2 py-0.5 outline-none focus:border-theme-primary"
            :placeholder="t('workspaces.rename.hint')"
            @keydown.enter.prevent="commitRename"
            @keydown.esc.prevent="cancelRename"
            @blur="commitRename"
          />
          <button
            type="button"
            class="text-theme-text-muted hover:text-emerald-400 p-1"
            :title="t('common.save')"
            @mousedown.prevent="commitRename"
          >
            <Check :size="16" />
          </button>
          <button
            type="button"
            class="text-theme-text-muted hover:text-red-400 p-1"
            :title="t('common.cancel')"
            @mousedown.prevent="cancelRename"
          >
            <X :size="16" />
          </button>
        </template>
        <template v-else>
          <h1
            data-test="workspace-title"
            class="text-xl font-medium tracking-tight truncate"
          >
            {{ workspaceName }}
          </h1>
          <button
            type="button"
            data-test="workspace-rename-button"
            class="text-theme-text-muted hover:text-theme-text p-1 rounded hover:bg-theme-border/40"
            :title="t('workspaces.rename.tooltip')"
            @click="startRename"
          >
            <Pencil :size="14" />
          </button>
        </template>
        <span
          v-if="renameError"
          class="text-xs text-red-400 ml-2"
        >{{ renameError }}</span>
      </div>

      <div class="flex items-center gap-3">
        <div
          v-if="heatStripTotal > 0"
          data-test="severity-heat-strip"
          class="flex items-center gap-2 rounded-lg border border-theme-border bg-theme-bg/60 px-3 py-1.5 text-xs"
          title="Aggregated SIEM severity posture across active workspaces"
        >
          <span class="text-[10px] uppercase tracking-wider text-theme-text-muted">SOC</span>
          <span v-if="severityHeatStrip.critical > 0" class="flex items-center gap-1 text-red-300">
            <span class="h-2 w-2 rounded-full bg-red-400" />
            <span class="font-semibold tabular-nums">{{ severityHeatStrip.critical }}</span>
            <span class="text-[10px] uppercase text-theme-text-muted">crit</span>
          </span>
          <span v-if="severityHeatStrip.high > 0" class="flex items-center gap-1 text-orange-300">
            <span class="h-2 w-2 rounded-full bg-orange-400" />
            <span class="font-semibold tabular-nums">{{ severityHeatStrip.high }}</span>
            <span class="text-[10px] uppercase text-theme-text-muted">high</span>
          </span>
          <span v-if="severityHeatStrip.medium > 0" class="flex items-center gap-1 text-amber-200">
            <span class="h-2 w-2 rounded-full bg-amber-400" />
            <span class="font-semibold tabular-nums">{{ severityHeatStrip.medium }}</span>
            <span class="text-[10px] uppercase text-theme-text-muted">med</span>
          </span>
          <span v-if="severityHeatStrip.low > 0" class="flex items-center gap-1 text-blue-200">
            <span class="h-2 w-2 rounded-full bg-blue-400" />
            <span class="font-semibold tabular-nums">{{ severityHeatStrip.low }}</span>
            <span class="text-[10px] uppercase text-theme-text-muted">low</span>
          </span>
        </div>

        <button
          type="button"
          data-test="widget-compact-toggle"
          @click="compactStore.toggle()"
          class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors"
          :class="compactStore.isCompact ? 'bg-theme-primary text-white' : 'bg-theme-border text-theme-text-muted hover:text-theme-text hover:bg-theme-text/10'"
          :title="compactStore.isCompact ? 'Switch to comfortable widget density' : 'Switch to compact widget density'"
        >
          <component :is="compactStore.isCompact ? Maximize2 : Minimize2" :size="14" />
          {{ compactStore.isCompact ? 'Compact' : 'Comfort' }}
        </button>

        <button
          v-if="integrationsStore.hasWorkspaceIntegrations"
          @click="isBuildPaneOpen = !isBuildPaneOpen"
          class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
          :class="isBuildPaneOpen ? 'bg-theme-primary text-white' : 'bg-theme-border text-theme-text-muted hover:text-theme-text hover:bg-theme-text/10'"
        >
          <PanelRightOpen v-if="!isBuildPaneOpen" :size="18" />
          <PanelRightClose v-else :size="18" />
          Build Pane
        </button>
      </div>
    </header>

    <div class="flex flex-1 overflow-hidden relative">
      <!-- Canvas Area -->
      <main
        ref="workspaceViewport"
        data-test="workspace-viewport"
        tabindex="0"
        class="flex-1 h-full relative overflow-auto bg-theme-bg no-scrollbar outline-none"
        :class="{
          'cursor-grab select-none': isSpacePanning && !isViewportPanning,
          'cursor-grabbing select-none': isViewportPanning,
        }"
        :style="workspaceDotCanvasStyle"
        @wheel="handleWheel"
        @scroll="syncViewportScroll"
        @keydown="handleViewportKeyDown"
        @keyup="handleViewportKeyUp"
        @pointerdown.capture="startViewportPan"
        @dragover="handleWorkspaceDragOver"
        @drop="handleWorkspaceDrop"
      >
        <div
          data-test="workspace-grid"
          class="pointer-events-none absolute inset-0 z-0"
        />

        <div class="relative z-10" :style="workspaceSurfaceStyle">
          <div
            data-test="workspace-stage"
            class="absolute origin-top-left"
            :style="workspaceStageStyle"
          >
            <DraggableWidget
              v-for="widget in activeWidgets"
              :key="widget.instanceId"
              :instance-id="widget.instanceId"
              :catalog-id="widget.catalogId"
              :integration-id="widget.integrationId"
              :layout="widget.layout"
              :field-bindings="widget.fieldBindings ?? []"
              @field-drop="handleFieldDrop"
              v-slot="{ widgetData, fieldBindings }"
            >
              <component
                :is="getWidgetComponent(widget.catalogId)"
                v-if="getWidgetComponent(widget.catalogId)"
                :data="widgetData"
                :catalog-id="widget.catalogId"
                :instance-id="widget.instanceId"
                :integration-id="widget.integrationId"
                :field-bindings="fieldBindings"
              />
              <div v-else class="text-gray-500 text-sm flex h-full items-center justify-center">
                Component not found for {{ widget.catalogId }}
              </div>
            </DraggableWidget>
          </div>
        </div>
      </main>

      <div
        data-test="workspace-minimap"
        class="absolute bottom-4 left-4 z-40 rounded-md border border-theme-border bg-theme-panel/90 p-2 shadow-2xl backdrop-blur-sm"
      >
        <div class="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wider text-theme-text-muted">
          <button
            type="button"
            data-test="minimap-toggle"
            class="flex items-center gap-1 hover:text-theme-text"
            @click="layoutStore.toggleMinimap"
          >
            <component :is="minimapCollapsed ? ChevronRight : ChevronDown" :size="12" />
            <span>Workspace</span>
          </button>
          <span>{{ Math.round(dashboardStore.zoom * 100) }}%</span>
        </div>
        <div
          v-if="!minimapCollapsed"
          class="relative overflow-hidden rounded border border-theme-border bg-theme-bg/80 mt-1"
          :style="{ width: `${MINIMAP_WIDTH_PX}px`, height: `${MINIMAP_HEIGHT_PX}px` }"
        >
          <div class="absolute left-1/2 top-0 h-full w-px bg-theme-border/45" />
          <div class="absolute left-0 top-1/2 h-px w-full bg-theme-border/45" />
          <div
            v-for="rect in minimapWidgetRects"
            :key="rect.id"
            :data-test="`minimap-widget-${rect.id}`"
            class="absolute rounded-sm bg-theme-primary/55"
            :style="rect.style"
          />
          <div
            data-test="minimap-viewport"
            class="absolute rounded-sm border border-blue-400 bg-blue-400/12"
            :style="minimapViewportStyle"
          />
        </div>
      </div>

      <!-- Build Pane resizer handle (only when open, drags the left edge) -->
      <div
        v-if="integrationsStore.hasWorkspaceIntegrations && isBuildPaneOpen"
        data-test="build-pane-resizer"
        class="z-40 w-1 cursor-col-resize self-stretch bg-transparent hover:bg-theme-primary/40 transition-colors"
        :class="{ 'bg-theme-primary/60': buildPaneResizer.isDragging.value }"
        @pointerdown="buildPaneResizer.onPointerDown"
      />

      <!-- Build Pane (Power BI style) -->
      <aside
        v-if="integrationsStore.hasWorkspaceIntegrations"
        class="h-full bg-theme-panel border-l border-theme-border flex flex-col z-30 shrink-0"
        :class="{ 'transition-all duration-300': !buildPaneResizer.isDragging.value }"
        :style="{ width: isBuildPaneOpen ? `${buildPaneWidth}px` : '0px', opacity: isBuildPaneOpen ? 1 : 0 }"
      >
        <!-- Tabs Header -->
        <div
          class="flex border-b border-theme-border shrink-0"
          :style="{ width: `${buildPaneWidth}px` }"
        >
          <button 
            @click="activeBuildTab = 'filters'"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'filters' ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
          >
            <Filter :size="14" /> Filters
          </button>
          <button 
            @click="activeBuildTab = 'visuals'"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'visuals' ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
          >
            <BarChart2 :size="14" /> Visuals
          </button>
          <button 
            @click="activeBuildTab = 'data'"
            data-test="build-tab-data"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'data' ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
          >
            <Database :size="14" /> Data
          </button>
        </div>

        <div class="flex-1 overflow-y-auto shrink-0" :style="{ width: `${buildPaneWidth}px` }">
          <!-- Filters Tab -->
          <div v-if="activeBuildTab === 'filters'" class="p-4 flex flex-col gap-6">
            <div class="flex flex-col gap-2">
              <label class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Time Range</label>
              <select class="w-full bg-theme-bg border border-theme-border rounded p-2 text-sm text-theme-text outline-none">
                <option>Last 1 hour</option>
                <option selected>Last 24 hours</option>
                <option>Last 7 days</option>
                <option>This month</option>
              </select>
            </div>
            
            <div class="flex flex-col gap-2">
              <label class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Device</label>
              <select class="w-full bg-theme-bg border border-theme-border rounded p-2 text-sm text-theme-text outline-none">
                <option value="all">All Devices</option>
                <option
                  v-for="integration in fortigateIntegrations"
                  :key="integration.id"
                  :value="integration.id"
                >
                  {{ integration.name || integration.host || integration.id }}
                </option>
              </select>
            </div>
            
            <div class="mt-4 pt-4 border-t border-theme-border">
              <button class="w-full bg-theme-border hover:opacity-80 text-theme-text rounded py-2 text-sm font-medium transition-colors">
                Apply Filters
              </button>
            </div>
          </div>

          <!-- Visualizations Tab -->
          <div v-if="activeBuildTab === 'visuals'" class="p-4 flex flex-col gap-4">
            <div class="border-b border-theme-border pb-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text">Visual analysis</h3>
                  <p class="mt-1 text-[11px] leading-snug text-theme-text-muted">
                    Connected integration presets and reusable templates for the SOC canvas.
                  </p>
                </div>
                <span class="shrink-0 rounded border border-theme-border bg-theme-bg px-2 py-1 text-[10px] font-medium text-theme-text-muted">
                  {{ isVisualCatalogLoading ? 'Loading' : visualPresetCountLabel }}
                </span>
              </div>
            </div>

            <section class="flex flex-col gap-2">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Integration presets</h3>
                <span v-if="catalogItems.length > 0" class="text-[10px] text-theme-text-muted">{{ visualPresetCountLabel }}</span>
              </div>

              <div v-if="isVisualCatalogLoading" class="rounded border border-theme-border bg-theme-bg p-3 text-sm text-theme-text-muted">
                <div class="flex items-center gap-2 font-medium text-theme-text">
                  <RefreshCcw :size="14" class="animate-spin text-theme-primary" />
                  <span>Loading widget presets</span>
                </div>
                <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                  Catalog metadata is loading for this workspace.
                </p>
              </div>

              <div v-else-if="isVisualCatalogEmpty" class="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-sm">
                <div class="flex items-center gap-2 font-medium text-amber-200">
                  <AlertTriangle :size="14" />
                  <span>No widget presets available</span>
                </div>
                <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                  Catalog status: unavailable; visual templates remain available.
                </p>
                <button
                  type="button"
                  class="mt-3 flex items-center gap-1 rounded border border-theme-border px-2 py-1 text-xs font-medium text-theme-text-muted hover:bg-theme-border hover:text-theme-text"
                  @click="retryVisualPresets"
                >
                  <RefreshCcw :size="12" />
                  Retry presets
                </button>
              </div>

              <div v-else class="flex flex-col gap-3">
                <div v-for="group in catalogGroups" :key="group.id" class="flex flex-col gap-2">
                  <div class="flex items-center justify-between gap-2">
                    <h4 class="text-[10px] font-semibold uppercase tracking-wider text-theme-text-muted">{{ group.label }}</h4>
                    <span class="text-[10px] text-theme-text-muted">{{ group.items.length }}</span>
                  </div>
                  <div class="grid grid-cols-2 gap-2">
                    <div
                      v-for="item in group.items"
                      :key="item.id"
                      @click="handleAddWidget(item.id)"
                      @dragstart="handleCatalogWidgetDragStart($event, item.id)"
                      class="bg-theme-bg border border-theme-border p-3 rounded hover:border-theme-primary/50 hover:bg-theme-border transition-colors flex flex-col items-center justify-center gap-2 cursor-pointer group text-center"
                      :title="item.title"
                      :data-test="`catalog-widget-${item.id}`"
                      draggable="true"
                    >
                      <component :is="getIconForKind(item.kind)" :size="24" class="text-theme-text-muted group-hover:text-theme-primary transition-colors" />
                      <span class="text-[10px] leading-tight font-medium text-theme-text-muted group-hover:text-theme-text">{{ item.title }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            <section class="mt-1 border-t border-theme-border pt-4">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Criar dados ao seu visual</h3>
                  <p class="mt-1 text-[11px] leading-snug text-theme-text-muted">
                    Template binding: Data fields.
                  </p>
                </div>
                <span class="shrink-0 rounded border border-theme-border bg-theme-bg px-2 py-1 text-[10px] text-theme-text-muted">
                  <Layers3 :size="11" class="mr-1 inline" />
                  {{ visualTemplates.length }}
                </span>
              </div>
              <div class="mt-3 grid grid-cols-2 gap-2">
                <div
                  v-for="template in visualTemplates"
                  :key="template.id"
                  class="bg-theme-bg border border-dashed border-theme-border p-3 rounded hover:border-theme-primary/50 hover:bg-theme-border transition-colors flex flex-col items-center justify-center gap-2 cursor-pointer group text-center"
                  :title="template.description"
                  :data-test="`visual-template-${template.id}`"
                  draggable="true"
                  @click="handleAddVisualTemplate(template.id)"
                  @dragstart="handleVisualTemplateDragStart($event, template.id)"
                >
                  <component :is="getIconForTemplate(template)" :size="23" class="text-theme-text-muted group-hover:text-theme-primary transition-colors" />
                  <span class="text-[10px] leading-tight font-medium text-theme-text-muted group-hover:text-theme-text">{{ template.title }}</span>
                </div>
              </div>
            </section>
          </div>

          <!-- Data Tab -->
          <div v-if="activeBuildTab === 'data'" class="p-4 flex flex-col gap-3">
            <div class="border-b border-theme-border pb-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h3 class="text-xs font-semibold uppercase tracking-wider text-theme-text">SOC data model</h3>
                  <p class="mt-1 text-[11px] leading-snug text-theme-text-muted">
                    Fields available for empty visual templates.
                  </p>
                </div>
                <span class="shrink-0 rounded border border-theme-border bg-theme-bg px-2 py-1 text-[10px] font-medium text-theme-text-muted">
                  {{ isDataFieldsLoading ? 'Loading' : dataFieldCountLabel }}
                </span>
              </div>
            </div>

            <div v-if="isDataFieldsLoading" class="rounded border border-theme-border bg-theme-bg p-3 text-sm text-theme-text-muted">
              <div class="flex items-center gap-2 font-medium text-theme-text">
                <RefreshCcw :size="14" class="animate-spin text-theme-primary" />
                  <span>Loading SOC fields</span>
                </div>
                <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                  Preparing normalized provider fields for live visual binding.
              </p>
            </div>
            <div v-else-if="dataFieldsError" class="rounded border border-red-500/30 bg-red-500/10 p-3 text-sm">
              <div class="flex items-center gap-2 font-medium text-red-200">
                <AlertTriangle :size="14" />
                <span>Data model unavailable</span>
              </div>
              <p class="mt-1 text-xs leading-snug text-red-300">{{ dataFieldsError }}</p>
              <button
                type="button"
                class="mt-3 flex items-center gap-1 rounded border border-red-500/30 px-2 py-1 text-xs font-medium text-red-200 hover:bg-red-500/10"
                @click="retryProviderFields"
              >
                <RefreshCcw :size="12" />
                Retry fields
              </button>
            </div>
            <div v-else-if="dataFieldGroups.length === 0" class="rounded border border-theme-border bg-theme-bg p-3 text-sm text-theme-text-muted">
              <div class="font-medium text-theme-text">No provider fields available</div>
              <p class="mt-1 text-xs leading-snug text-theme-text-muted">
                No SOC field groups returned by the provider data endpoint.
              </p>
            </div>
            
            <template v-else>
              <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Available Fields</h3>
              <div v-for="group in dataFieldGroups" :key="group.id" class="flex flex-col">
                <div 
                  class="flex items-center gap-2 p-2 hover:bg-theme-border rounded cursor-pointer transition-colors text-sm text-theme-text"
                  @click="toggleFolder(group.id)"
                >
                  <FolderOpen v-if="expandedFolders[group.id]" :size="16" class="text-amber-500" />
                  <Folder v-else :size="16" class="text-amber-500" />
                  <span class="font-medium">{{ group.name }}</span>
                </div>

                <div v-if="expandedFolders[group.id]" class="flex flex-col ml-6 pl-2 border-l border-theme-border py-1 gap-1">
                  <div v-if="group.category" class="px-1.5 pb-1 text-[10px] font-medium uppercase tracking-wider text-theme-text-muted">
                    {{ group.category }}
                  </div>
                  <div
                    v-for="field in group.fields"
                    :key="fieldKey(field)"
                    class="flex flex-col gap-1 p-1.5 text-xs text-theme-text-muted hover:text-theme-text cursor-pointer hover:bg-theme-border/50 rounded transition-colors"
                    :title="field.source"
                    :data-test="`data-field-${fieldKey(field)}`"
                    draggable="true"
                    @dragstart="handleFieldDragStart($event, field, group)"
                  >
                    <div class="flex items-center gap-2">
                      <Database :size="12" class="opacity-50" />
                      <span class="min-w-0 flex-1 truncate">{{ fieldLabel(field) }}</span>
                      <span class="rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-300">Live</span>
                    </div>
                    <div class="ml-5 flex items-center gap-2 text-[10px] text-theme-text-muted">
                      <span>{{ fieldTypeLabel(field) }}</span>
                      <span class="truncate">{{ field.source }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
