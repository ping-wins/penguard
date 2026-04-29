import { defineStore } from 'pinia'
import { ref } from 'vue'
import workspaceFixture from '@fortidashboard/contracts/fixtures/workspace.json'
import catalogFixture from '@fortidashboard/contracts/fixtures/widget_catalog_fortigate.json'
import { useAuthStore } from './useAuthStore'
import { visualTemplatesById } from '../constants/visualTemplates'
import { createWidgetInstance, normalizeWorkspaceWidgets } from '../utils/widgetLayout'
import type { WidgetCatalogItem, WidgetFieldBinding, WorkspaceWidget } from '../types/dashboard'

export const useDashboardStore = defineStore('dashboard', () => {
  const activeWidgets = ref<WorkspaceWidget[]>([])
  const workspaceName = ref('SOC Overview')
  const zoom = ref(1)
  const isInitialized = ref(false)
  const isCatalogLoaded = ref(false)
  const catalogItems = ref<WidgetCatalogItem[]>([])

  let saveTimeout: ReturnType<typeof setTimeout> | null = null
  let maxZIndex = 100

  async function fetchCatalog() {
    try {
      const res = await fetch('/api/widget-catalog?integrationType=fortigate', {
        credentials: 'include'
      })
      if (!res.ok) {
        throw new Error(`Widget catalog failed with HTTP ${res.status}`)
      }
      const data = await res.json()
      catalogItems.value = data.items || []
    } catch (e) {
      console.error('Failed to fetch widget catalog', e)
      catalogItems.value = (catalogFixture as { items: WidgetCatalogItem[] }).items || []
    } finally {
      isCatalogLoaded.value = true
    }
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

  function addWidget(catalogId: string, integrationId: string) {
    const catalogItem = catalogItems.value.find(i => i.id === catalogId)
    activeWidgets.value.push(createWidgetInstance({
      catalogId,
      integrationId,
      defaultSize: catalogItem?.defaultSize,
      zIndex: ++maxZIndex
    }))
    debouncedSave()
  }

  function addVisualTemplate(templateId: string, integrationId = '') {
    const template = visualTemplatesById[templateId]
    if (!template) return
    activeWidgets.value.push(createWidgetInstance({
      catalogId: template.id,
      integrationId,
      defaultSize: template.defaultSize,
      zIndex: ++maxZIndex
    }))
    debouncedSave()
  }

  function bindFieldToWidget(instanceId: string, binding: WidgetFieldBinding) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (!widget) return

    const existingBindings = widget.fieldBindings ?? []
    if (existingBindings.some(existing => existing.fieldId === binding.fieldId)) {
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
