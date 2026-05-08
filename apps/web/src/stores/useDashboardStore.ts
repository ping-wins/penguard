import { defineStore } from 'pinia'
import { ref } from 'vue'
import workspaceFixture from '@fortidashboard/contracts/fixtures/workspace.json'
import catalogFixture from '@fortidashboard/contracts/fixtures/widget_catalog_fortigate.json'
import { useAuthStore } from './useAuthStore'
import { visualTemplatesById } from '../constants/visualTemplates'
import { createWidgetInstance, normalizeWorkspaceWidgets } from '../utils/widgetLayout'
import type { WidgetCatalogItem, WidgetFieldBinding, WorkspaceWidget } from '../types/dashboard'

type WidgetInsertPosition = {
  x: number
  y: number
}

const DEFAULT_CATALOG_TYPES = ['fortigate']

export const useDashboardStore = defineStore('dashboard', () => {
  const activeWidgets = ref<WorkspaceWidget[]>([])
  const workspaceName = ref('SOC Overview')
  const zoom = ref(1)
  const isInitialized = ref(false)
  const isCatalogLoaded = ref(false)
  const catalogItems = ref<WidgetCatalogItem[]>([])

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

  async function loadWorkspace() {
    try {
      const res = await fetch('/api/workspaces/ws_default', { credentials: 'include' })
      if (res.ok) {
        const data = await res.json()
        activeWidgets.value = normalizeWorkspaceWidgets(data.widgets || [])
        workspaceName.value = data.name || 'SOC Overview'
      } else {
        activeWidgets.value = normalizeWorkspaceWidgets(workspaceFixture.widgets as WorkspaceWidget[])
        workspaceName.value = workspaceFixture.name
      }
    } catch (e) {
      console.error('Failed to load workspace', e)
      activeWidgets.value = normalizeWorkspaceWidgets(workspaceFixture.widgets as WorkspaceWidget[])
      workspaceName.value = workspaceFixture.name
    } finally {
      syncMaxZIndex()
      isInitialized.value = true
    }
  }

  async function saveWorkspace() {
    const authStore = useAuthStore()
    if (!authStore.csrfToken) {
      await authStore.fetchCsrf()
    }
    
    try {
      await fetch('/api/workspaces/ws_default', {
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
    } catch (e) {
      console.error('Failed to save workspace', e)
    }
  }

  function debouncedSave() {
    if (saveTimeout) clearTimeout(saveTimeout)
    saveTimeout = setTimeout(() => {
      saveWorkspace()
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

  return {
    activeWidgets,
    workspaceName,
    zoom,
    isInitialized,
    isCatalogLoaded,
    catalogItems,
    setZoom,
    fetchCatalog,
    loadWorkspace,
    saveWorkspace,
    updateWidgetPosition,
    updateWidgetSize,
    bringToFront,
    addWidget,
    addVisualTemplate,
    bindFieldToWidget,
    removeWidget
  }
})
