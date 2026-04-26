<script setup lang="ts">
import { ref } from 'vue'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { storeToRefs } from 'pinia'
import { PanelRightClose, PanelRightOpen, Filter, BarChart2, Database, Folder, FolderOpen, Table, Activity, Network } from 'lucide-vue-next'
import DraggableWidget from './DraggableWidget.vue'
import WidgetHealth from '../widgets/WidgetHealth.vue'
import WidgetThreats from '../widgets/WidgetThreats.vue'
import WidgetNetwork from '../widgets/WidgetNetwork.vue'
import WidgetKpiCard from '../widgets/WidgetKpiCard.vue'

import catalogData from '@fortidashboard/contracts/fixtures/catalog.json'
import dataFields from '@fortidashboard/contracts/fixtures/data-fields.json'

const dashboardStore = useDashboardStore()
const { activeWidgets, workspaceName } = storeToRefs(dashboardStore)

const isBuildPaneOpen = ref(true)
const activeBuildTab = ref<'filters' | 'visuals' | 'data'>('visuals')

const expandedFolders = ref<Record<string, boolean>>({
  'system': true
})

function toggleFolder(id: string) {
  expandedFolders.value[id] = !expandedFolders.value[id]
}

function handleAddWidget(catalogId: string) {
  dashboardStore.addWidget(catalogId)
}

// Map from catalogId to component
const widgetMap: Record<string, any> = {
  'fortigate-system-status': WidgetHealth,
  'fortigate-top-threats': WidgetThreats,
  'fortigate-network-traffic': WidgetNetwork,
  'fortigate-kpi-sessions': WidgetKpiCard
}

function getIconForKind(kind: string) {
  switch (kind) {
    case 'kpi': return Activity
    case 'table': return Table
    case 'chart': return Network
    default: return BarChart2
  }
}

function handleWheel(e: WheelEvent) {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    const zoomSensitivity = 0.001
    const newZoom = dashboardStore.zoom - e.deltaY * zoomSensitivity
    dashboardStore.setZoom(Math.max(0.2, Math.min(newZoom, 3))) // Zoom entre 20% e 300%
  }
}
</script>

<template>
  <div class="flex-1 h-full overflow-hidden relative bg-theme-bg flex flex-col z-0">
    <!-- Header/Toolbar -->
    <header class="h-16 border-b border-theme-border flex items-center px-6 bg-theme-panel/50 backdrop-blur-sm z-40 relative shrink-0 justify-between">
      <h1 class="text-xl font-medium tracking-tight">{{ workspaceName }}</h1>
      
      <button 
        @click="isBuildPaneOpen = !isBuildPaneOpen" 
        class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
        :class="isBuildPaneOpen ? 'bg-theme-primary text-white' : 'bg-theme-border text-theme-text-muted hover:text-theme-text hover:bg-theme-text/10'"
      >
        <PanelRightOpen v-if="!isBuildPaneOpen" :size="18" />
        <PanelRightClose v-else :size="18" />
        Build Pane
      </button>
    </header>

    <div class="flex flex-1 overflow-hidden relative">
      <!-- Canvas Area -->
      <main class="flex-1 h-full relative overflow-auto bg-theme-bg no-scrollbar" @wheel="handleWheel">
        <div class="absolute inset-0 origin-top-left" :style="{ transform: `scale(${dashboardStore.zoom})`, width: `${100/dashboardStore.zoom}%`, height: `${100/dashboardStore.zoom}%` }">
          
          <!-- Grid Background -->
          <div class="absolute inset-0 z-0 opacity-10 pointer-events-none pattern-grid bg-fixed" 
               style="background-image: linear-gradient(#333 1px, transparent 1px), linear-gradient(90deg, #333 1px, transparent 1px); background-size: 80px 80px;">
          </div>
          
          <DraggableWidget
            v-for="widget in activeWidgets"
            :key="widget.instanceId"
            :instance-id="widget.instanceId"
            :catalog-id="widget.catalogId"
            :layout="widget.layout"
          >
            <component :is="widgetMap[widget.catalogId]" v-if="widgetMap[widget.catalogId]" />
            <div v-else class="text-gray-500 text-sm flex h-full items-center justify-center">
              Component not found for {{ widget.catalogId }}
            </div>
          </DraggableWidget>
        </div>
      </main>

      <!-- Build Pane (Power BI style) -->
      <aside 
        class="h-full bg-theme-panel border-l border-theme-border transition-all duration-300 flex flex-col z-30 shrink-0"
        :style="{ width: isBuildPaneOpen ? '300px' : '0px', opacity: isBuildPaneOpen ? 1 : 0 }"
      >
        <!-- Tabs Header -->
        <div class="flex border-b border-theme-border w-[300px] shrink-0">
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
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'data' ? 'border-theme-primary text-theme-primary' : 'border-transparent text-theme-text-muted hover:text-theme-text'"
          >
            <Database :size="14" /> Data
          </button>
        </div>

        <div class="flex-1 overflow-y-auto w-[300px] shrink-0">
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
                <option value="int_fgt_01" selected>FortiGate Lab (FGT-VM)</option>
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
            <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider">Modules Catalog</h3>
            <div class="grid grid-cols-2 gap-2">
              <div 
                v-for="item in catalogData.items" 
                :key="item.id"
                @click="handleAddWidget(item.id)"
                class="bg-theme-bg border border-theme-border p-3 rounded hover:border-theme-primary/50 hover:bg-theme-border transition-colors flex flex-col items-center justify-center gap-2 cursor-pointer group text-center"
                :title="item.title"
              >
                <component :is="getIconForKind(item.kind)" :size="24" class="text-theme-text-muted group-hover:text-theme-primary transition-colors" />
                <span class="text-[10px] leading-tight font-medium text-theme-text-muted group-hover:text-theme-text">{{ item.title }}</span>
              </div>
            </div>
          </div>

          <!-- Data Tab -->
          <div v-if="activeBuildTab === 'data'" class="p-4 flex flex-col gap-2">
            <h3 class="text-xs font-medium text-theme-text-muted uppercase tracking-wider mb-2">Available Fields</h3>
            
            <div v-for="group in dataFields.groups" :key="group.id" class="flex flex-col">
              <div 
                class="flex items-center gap-2 p-2 hover:bg-theme-border rounded cursor-pointer transition-colors text-sm text-theme-text"
                @click="toggleFolder(group.id)"
              >
                <FolderOpen v-if="expandedFolders[group.id]" :size="16" class="text-amber-500" />
                <Folder v-else :size="16" class="text-amber-500" />
                <span class="font-medium">{{ group.name }}</span>
              </div>
              
              <div v-if="expandedFolders[group.id]" class="flex flex-col ml-6 pl-2 border-l border-theme-border py-1 gap-1">
                <div 
                  v-for="field in group.fields" 
                  :key="field"
                  class="flex items-center gap-2 p-1.5 text-xs text-theme-text-muted hover:text-theme-text cursor-pointer hover:bg-theme-border/50 rounded transition-colors"
                >
                  <Database :size="12" class="opacity-50" />
                  {{ field }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>
