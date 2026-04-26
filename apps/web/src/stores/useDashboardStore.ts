import { defineStore } from 'pinia'
import { ref } from 'vue'
import workspaceFixture from '@fortidashboard/contracts/fixtures/workspace.json'
import catalogData from '@fortidashboard/contracts/fixtures/catalog.json'

export const useDashboardStore = defineStore('dashboard', () => {
  const activeWidgets = ref(workspaceFixture.widgets)
  const workspaceName = ref(workspaceFixture.name)

  let maxZIndex = 100 // Ponto de partida seguro

  function updateWidgetPosition(instanceId: string, x: number, y: number) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (widget && widget.layout) {
      widget.layout.x = x
      widget.layout.y = y
    }
  }

  function updateWidgetSize(instanceId: string, w: number, h: number) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (widget && widget.layout) {
      widget.layout.w = w
      widget.layout.h = h
    }
  }

  function bringToFront(instanceId: string) {
    const widget = activeWidgets.value.find(w => w.instanceId === instanceId)
    if (widget && widget.layout) {
      maxZIndex += 1
      widget.layout.z = maxZIndex
    }
  }

  function addWidget(catalogId: string, integrationId: string = 'int_fgt_01') {
    const newId = 'w_' + Math.random().toString(36).substr(2, 9)
    const catalogItem = catalogData.items.find(i => i.id === catalogId)
    const w = catalogItem?.defaultSize.w || 320
    const h = catalogItem?.defaultSize.h || 240
    
    maxZIndex += 1
    activeWidgets.value.push({
      instanceId: newId,
      catalogId,
      integrationId,
      layout: { x: window.innerWidth / 2 - w/2, y: window.innerHeight / 2 - h/2, w, h, z: maxZIndex }
    })
  }

  function removeWidget(instanceId: string) {
    activeWidgets.value = activeWidgets.value.filter(w => w.instanceId !== instanceId)
  }

  return {
    activeWidgets,
    workspaceName,
    updateWidgetPosition,
    updateWidgetSize,
    bringToFront,
    addWidget,
    removeWidget
  }
})
