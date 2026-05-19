import { defineStore } from 'pinia'
import { ref } from 'vue'
import workspaceFixture from '@penguard/contracts/fixtures/workspace.json'
import catalogFixture from '@penguard/contracts/fixtures/widget_catalog_fortigate.json'
import { useAuthStore } from './useAuthStore'
import { visualTemplatesById } from '../constants/visualTemplates'
import { createWidgetInstance, normalizeWorkspaceWidgets } from '../utils/widgetLayout'
import type { WidgetCatalogItem, WidgetFieldBinding, WidgetLayout, WorkspaceWidget } from '../types/dashboard'
import {
  deleteWorkspace as apiDeleteWorkspace,
  listWorkspaces as apiListWorkspaces,
  rebindWidgetIntegration as apiRebindWidget,
  type WorkspaceOrigin,
  type WorkspaceSummary,
} from '../services/workspaceClient'

type WidgetInsertPosition = {
  x: number
  y: number
}

type WidgetDraftInput = {
  provider: string
  integrationId?: string | null
  visualType: string
  fieldBindings: Array<{
    fieldId: string
    label: string
    type: string
    unit?: string | null
    source?: string | null
    provider: string
    integrationId?: string | null
  }>
  layout?: {
    w?: number
    h?: number
  }
}

const DEFAULT_CATALOG_TYPES = ['fortigate']

const VISUAL_TEMPLATE_ID_BY_DRAFT_TYPE: Record<string, string> = {
  card: 'visual-template-card',
  kpi: 'visual-template-card',
  gauge: 'visual-template-gauge',
  bar: 'visual-template-bar',
  chart: 'visual-template-bar',
  line: 'visual-template-line',
  table: 'visual-template-table',
  feed: 'visual-template-feed',
  list: 'visual-template-list',
  'status-list': 'visual-template-list',
  'risk-summary': 'visual-template-list',
}

export const useDashboardStore = defineStore('dashboard', () => {
  const activeWidgets = ref<WorkspaceWidget[]>([])
  const workspaceName = ref('SOC Overview')
  const activeWorkspaceId = ref('ws_default')
  const activeWorkspaceOrigin = ref<WorkspaceOrigin | null>(null)
  const workspaces = ref<WorkspaceSummary[]>([])
  const zoom = ref(1)
  const isInitialized = ref(false)
  const isCatalogLoaded = ref(false)
  const catalogItems = ref<WidgetCatalogItem[]>([])
  const workspaceSaveError = ref<string | null>(null)

  let saveTimeout: ReturnType<typeof setTimeout> | null = null
  let maxZIndex = 100

  async function fetchCatalog(integrationTypes: string[] = DEFAULT_CATALOG_TYPES) {
    const uniqueTypes = Array.from(new Set(integrationTypes.filter(Boolean)))
    isCatalogLoaded.value = false

    if (uniqueTypes.length === 0) {
      catalogItems.value = []
      isCatalogLoaded.value = true
      return
    }

    const itemsById = new Map<string, WidgetCatalogItem>()

    await Promise.all(uniqueTypes.map(async (integrationType) => {
      try {
        const res = await fetch(`/api/widget-catalog?integrationType=${encodeURIComponent(integrationType)}`, {
          credentials: 'include'
        })
        if (!res.ok) {
          throw new Error(`Widget catalog failed with HTTP ${res.status}`)
        }
        const data = await res.json()
        for (const item of data.items || []) {
          if (itemsById.has(item.id)) continue
          itemsById.set(item.id, {
            ...item,
            integrationType: item.integrationType || integrationType,
          })
        }
      } catch (e) {
        console.error(`Failed to fetch widget catalog for ${integrationType}`, e)
      }
    }))

    if (itemsById.size === 0 && uniqueTypes.includes('fortigate')) {
      for (const item of (catalogFixture as { items: WidgetCatalogItem[] }).items || []) {
        if (itemsById.has(item.id)) continue
        itemsById.set(item.id, {
          ...item,
          integrationType: item.integrationType || 'fortigate',
        })
      }
    }

    catalogItems.value = Array.from(itemsById.values())
    isCatalogLoaded.value = true
  }

  function syncMaxZIndex() {
    maxZIndex = Math.max(100, ...activeWidgets.value.map(widget => widget.layout?.z || 0))
  }

  async function loadWorkspace(workspaceId?: string) {
    const targetId = workspaceId ?? activeWorkspaceId.value
    activeWorkspaceId.value = targetId
    try {
      const res = await fetch(`/api/workspaces/${encodeURIComponent(targetId)}`, {
        credentials: 'include',
      })
      if (res.ok) {
        const data = await res.json()
        activeWidgets.value = normalizeWorkspaceWidgets(data.widgets || [])
        workspaceName.value = data.name || 'SOC Overview'
        activeWorkspaceOrigin.value = data.origin ?? null
      } else {
        activeWidgets.value = normalizeWorkspaceWidgets(workspaceFixture.widgets as WorkspaceWidget[])
        workspaceName.value = workspaceFixture.name
        activeWorkspaceOrigin.value = null
      }
    } catch (e) {
      console.error('Failed to load workspace', e)
      activeWidgets.value = normalizeWorkspaceWidgets(workspaceFixture.widgets as WorkspaceWidget[])
      workspaceName.value = workspaceFixture.name
      activeWorkspaceOrigin.value = null
    } finally {
      syncMaxZIndex()
      isInitialized.value = true
    }
  }

  async function refreshWorkspaceList() {
    try {
      workspaces.value = await apiListWorkspaces()
    } catch (e) {
      console.error('Failed to list workspaces', e)
      workspaces.value = []
    }
  }

  async function switchWorkspace(workspaceId: string) {
    if (workspaceId === activeWorkspaceId.value) return
    await loadWorkspace(workspaceId)
    await refreshWorkspaceList()
  }

  async function deleteWorkspaceById(workspaceId: string) {
    await apiDeleteWorkspace(workspaceId)
    if (workspaceId === activeWorkspaceId.value) {
      await loadWorkspace('ws_default')
    }
    await refreshWorkspaceList()
  }

  async function renameActiveWorkspace(newName: string) {
    const trimmed = newName.trim()
    if (!trimmed || trimmed === workspaceName.value) return
    const previous = workspaceName.value
    workspaceName.value = trimmed
    try {
      await saveWorkspace()
      await refreshWorkspaceList()
    } catch (e) {
      workspaceName.value = previous
      throw e
    }
  }

  async function rebindWidget(instanceId: string, integrationId: string) {
    const result = await apiRebindWidget(activeWorkspaceId.value, instanceId, integrationId)
    const widget = activeWidgets.value.find((w) => w.instanceId === instanceId)
    if (widget) {
      widget.integrationId = integrationId
      if (Array.isArray(widget.fieldBindings) && widget.fieldBindings.length) {
        widget.fieldBindings = widget.fieldBindings.map((binding) => ({
          ...binding,
          integrationId,
        }))
      }
    }
    if (result?.origin) {
      activeWorkspaceOrigin.value = result.origin
    }
  }

  async function saveWorkspace() {
    const authStore = useAuthStore()
    if (!authStore.csrfToken) {
      await authStore.fetchCsrf()
    }

    try {
      const res = await fetch(`/api/workspaces/${encodeURIComponent(activeWorkspaceId.value)}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify({
          name: workspaceName.value,
          widgets: activeWidgets.value.map(w => ({
            ...w,
            layout: {
              x: Math.round(w.layout.x),
              y: Math.round(w.layout.y),
              w: Math.round(w.layout.w),
              h: Math.round(w.layout.h),
              z: Math.round(w.layout.z)
            }
          }))
        })
      })
      if (!res.ok) {
        throw new Error(`Workspace save failed with HTTP ${res.status}`)
      }
      workspaceSaveError.value = null
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Workspace save failed'
      workspaceSaveError.value = message
      console.error('Failed to save workspace', e)
      throw e
    }
  }

  function debouncedSave() {
    if (saveTimeout) clearTimeout(saveTimeout)
    saveTimeout = setTimeout(() => {
      saveWorkspace().catch(() => {
        // saveWorkspace already records workspaceSaveError for UI surfaces.
      })
    }, 1000)
  }

  function setZoom(val: number) {
    zoom.value = val
  }

  function updateWidgetPosition(instanceId: string, x: number, y: number) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (widget && widget.layout) {
      widget.layout.x = x
      widget.layout.y = y
      debouncedSave()
    }
  }

  function updateWidgetSize(instanceId: string, w: number, h: number) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (widget && widget.layout) {
      widget.layout.w = w
      widget.layout.h = h
      debouncedSave()
    }
  }

  function bringToFront(instanceId: string) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (widget && widget.layout) {
      maxZIndex += 1
      widget.layout.z = maxZIndex
      debouncedSave()
    }
  }

  function addWidget(catalogId: string, integrationId: string, position?: WidgetInsertPosition) {
    const catalogItem = catalogItems.value.find(i => i.id === catalogId)
    activeWidgets.value.push(createWidgetInstance({
      catalogId,
      integrationId,
      defaultSize: catalogItem?.defaultSize,
      zIndex: ++maxZIndex,
      position,
    }))
    debouncedSave()
  }

  function addVisualTemplate(templateId: string, integrationId = '', position?: WidgetInsertPosition) {
    const template = visualTemplatesById[templateId]
    if (!template) return
    activeWidgets.value.push(createWidgetInstance({
      catalogId: template.id,
      integrationId,
      defaultSize: template.defaultSize,
      zIndex: ++maxZIndex,
      position,
    }))
    debouncedSave()
  }

  function addWidgetDraft(
    draft: WidgetDraftInput,
    integrationId?: string,
    position?: WidgetInsertPosition,
  ): WorkspaceWidget | null {
    const templateId = VISUAL_TEMPLATE_ID_BY_DRAFT_TYPE[draft.visualType]
    const template = visualTemplatesById[templateId]
    if (!template) return null

    const resolvedIntegrationId = integrationId || draft.integrationId || ''
    const defaultSize = {
      w: Number(draft.layout?.w) || template.defaultSize.w,
      h: Number(draft.layout?.h) || template.defaultSize.h,
    }
    const widget = createWidgetInstance({
      catalogId: template.id,
      integrationId: resolvedIntegrationId,
      defaultSize,
      zIndex: ++maxZIndex,
      position,
    })
    widget.fieldBindings = draft.fieldBindings.map((binding): WidgetFieldBinding => ({
      fieldId: binding.fieldId,
      label: binding.label,
      type: binding.type,
      ...(binding.unit ? { unit: binding.unit } : {}),
      source: binding.source ?? '',
      provider: binding.provider,
      integrationId: binding.integrationId || resolvedIntegrationId,
      integrationType: binding.provider || draft.provider,
    }))
    activeWidgets.value.push(widget)
    debouncedSave()
    return widget
  }

  function bindFieldToWidget(instanceId: string, binding: WidgetFieldBinding) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (!widget) return

    const existingBindings = widget.fieldBindings ?? []
    if (existingBindings.some(existing => (
      existing.fieldId === binding.fieldId
      && existing.source === binding.source
      && existing.integrationId === binding.integrationId
    ))) {
      return
    }

    widget.fieldBindings = [...existingBindings, binding]
    debouncedSave()
  }

  function removeWidget(instanceId: string) {
    activeWidgets.value = activeWidgets.value.filter(w => w.instanceId !== instanceId)
    debouncedSave()
  }

  // --- workspace mode helpers (grid vs canvas) ---
  const canvasSnapshot = ref<Record<string, WidgetLayout>>({})

  function snapshotCanvasLayout() {
    const next: Record<string, WidgetLayout> = {}
    for (const widget of activeWidgets.value) {
      next[widget.instanceId] = { ...widget.layout }
    }
    canvasSnapshot.value = next
  }

  function restoreCanvasLayout() {
    const snap = canvasSnapshot.value
    let changed = false
    for (const widget of activeWidgets.value) {
      const saved = snap[widget.instanceId]
      if (!saved) continue
      widget.layout.x = saved.x
      widget.layout.y = saved.y
      widget.layout.w = saved.w
      widget.layout.h = saved.h
      widget.layout.z = saved.z
      changed = true
    }
    canvasSnapshot.value = {}
    if (changed) debouncedSave()
  }

  function packToGrid(viewportWidth: number) {
    const GAP = 16
    const PADDING = 24
    const usable = Math.max(360, viewportWidth - PADDING * 2)
    const sorted = [...activeWidgets.value].sort((a, b) => {
      if (a.layout.y !== b.layout.y) return a.layout.y - b.layout.y
      return a.layout.x - b.layout.x
    })
    let x = 0
    let y = 0
    let rowHeight = 0
    let changed = false
    for (const widget of sorted) {
      const ww = Math.min(widget.layout.w, usable)
      if (x > 0 && x + ww > usable) {
        x = 0
        y += rowHeight + GAP
        rowHeight = 0
      }
      const nextX = x
      const nextY = y
      const nextW = ww
      if (
        widget.layout.x !== nextX
        || widget.layout.y !== nextY
        || widget.layout.w !== nextW
      ) {
        widget.layout.x = nextX
        widget.layout.y = nextY
        widget.layout.w = nextW
        changed = true
      }
      x += ww + GAP
      rowHeight = Math.max(rowHeight, widget.layout.h)
    }
    if (changed) debouncedSave()
  }

  return {
    activeWidgets,
    workspaceName,
    activeWorkspaceId,
    activeWorkspaceOrigin,
    workspaces,
    zoom,
    isInitialized,
    isCatalogLoaded,
    catalogItems,
    workspaceSaveError,
    setZoom,
    fetchCatalog,
    loadWorkspace,
    saveWorkspace,
    refreshWorkspaceList,
    switchWorkspace,
    deleteWorkspaceById,
    renameActiveWorkspace,
    rebindWidget,
    updateWidgetPosition,
    updateWidgetSize,
    bringToFront,
    addWidget,
    addVisualTemplate,
    addWidgetDraft,
    bindFieldToWidget,
    removeWidget,
    canvasSnapshot,
    snapshotCanvasLayout,
    restoreCanvasLayout,
    packToGrid,
  }
})
