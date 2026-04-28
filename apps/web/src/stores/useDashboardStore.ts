import { defineStore } from 'pinia'
import { ref } from 'vue'
import workspaceFixture from '@fortidashboard/contracts/fixtures/workspace.json'
import { useAuthStore } from './useAuthStore'

export const useDashboardStore = defineStore('dashboard', () => {
  const activeWidgets = ref<any[]>([])
  const workspaceName = ref('SOC Overview')
  const zoom = ref(1)
  const isInitialized = ref(false)
  const catalogItems = ref<any[]>([])

  let saveTimeout: ReturnType<typeof setTimeout> | null = null

  async function fetchCatalog() {
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()
      
      const res = await fetch('/api/widget-catalog?integrationType=fortigate', {
        headers: { 'X-CSRF-Token': authStore.csrfToken },
        credentials: 'include'
      })
      if (res.ok) {
        const data = await res.json()
        catalogItems.value = data.items || []
      }
    } catch (e) {
      console.error('Failed to fetch widget catalog', e)
    }
  }

  async function loadWorkspace() {
    try {
      const res = await fetch('/api/workspaces/ws_default')
      if (res.ok) {
        const data = await res.json()
        activeWidgets.value = data.widgets || []
        workspaceName.value = data.name || 'SOC Overview'
      } else {
        activeWidgets.value = workspaceFixture.widgets
        workspaceName.value = workspaceFixture.name
      }
    } catch (e) {
      console.error('Failed to load workspace', e)
      activeWidgets.value = workspaceFixture.widgets
      workspaceName.value = workspaceFixture.name
    } finally {
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

  let maxZIndex = 100 // Ponto de partida seguro

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
    const newId = 'w_' + Math.random().toString(36).substr(2, 9)
    const catalogItem = catalogItems.value.find(i => i.id === catalogId)
    const w = catalogItem?.defaultSize.w || 320
    const h = catalogItem?.defaultSize.h || 240
    
    activeWidgets.value.push({
      instanceId: newId,
      catalogId,
      integrationId,
      layout: { x: 50, y: 50, w, h, z: ++maxZIndex }
    })
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
    catalogItems,
    setZoom,
    fetchCatalog,
    loadWorkspace,
    saveWorkspace,
    updateWidgetPosition,
    updateWidgetSize,
    bringToFront,
    addWidget,
    removeWidget
  }
})
