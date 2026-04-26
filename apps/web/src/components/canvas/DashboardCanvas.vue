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
</script>

<template>
  <div class="flex-1 h-full overflow-hidden relative bg-forti-dark flex flex-col">
    <!-- Header/Toolbar -->
    <header class="h-16 border-b border-gray-800 flex items-center px-6 bg-black/20 backdrop-blur-sm z-40 relative shrink-0 justify-between">
      <h1 class="text-xl font-medium tracking-tight">{{ workspaceName }}</h1>
      
      <button 
        @click="isBuildPaneOpen = !isBuildPaneOpen" 
        class="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors"
        :class="isBuildPaneOpen ? 'bg-forti-red text-white' : 'bg-gray-800 text-gray-300 hover:text-white hover:bg-gray-700'"
      >
        <PanelRightOpen v-if="!isBuildPaneOpen" :size="18" />
        <PanelRightClose v-else :size="18" />
        Build Pane
      </button>
    </header>

    <div class="flex flex-1 overflow-hidden relative">
      <!-- Canvas Area -->
      <main class="flex-1 h-full relative overflow-auto pattern-grid bg-fixed">
        <div class="absolute inset-0 z-0 opacity-10 pointer-events-none" 
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
      </main>

      <!-- Build Pane (Power BI style) -->
      <aside 
        class="h-full bg-forti-panel border-l border-gray-800 transition-all duration-300 flex flex-col z-30 shrink-0"
        :style="{ width: isBuildPaneOpen ? '300px' : '0px', opacity: isBuildPaneOpen ? 1 : 0 }"
      >
        <!-- Tabs Header -->
        <div class="flex border-b border-gray-800 w-[300px] shrink-0">
          <button 
            @click="activeBuildTab = 'filters'"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'filters' ? 'border-forti-red text-forti-red' : 'border-transparent text-gray-500 hover:text-gray-300'"
          >
            <Filter :size="14" /> Filters
          </button>
          <button 
            @click="activeBuildTab = 'visuals'"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'visuals' ? 'border-forti-red text-forti-red' : 'border-transparent text-gray-500 hover:text-gray-300'"
          >
            <BarChart2 :size="14" /> Visuals
          </button>
          <button 
            @click="activeBuildTab = 'data'"
            class="flex-1 py-3 text-xs font-medium uppercase tracking-wider flex justify-center items-center gap-1 border-b-2 transition-colors"
            :class="activeBuildTab === 'data' ? 'border-forti-red text-forti-red' : 'border-transparent text-gray-500 hover:text-gray-300'"
          >
            <Database :size="14" /> Data
          </button>
        </div>

        <div class="flex-1 overflow-y-auto w-[300px] shrink-0">
          <!-- Filters Tab -->
          <div v-if="activeBuildTab === 'filters'" class="p-4 flex flex-col gap-6">
            <div class="flex flex-col gap-2">
              <label class="text-xs font-medium text-gray-400 uppercase tracking-wider">Time Range</label>
              <select class="w-full bg-black/50 border border-gray-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-forti-red outline-none">
                <option>Last 1 hour</option>
                <option selected>Last 24 hours</option>
                <option>Last 7 days</option>
                <option>This month</option>
              </select>
            </div>
            
            <div class="flex flex-col gap-2">
              <label class="text-xs font-medium text-gray-400 uppercase tracking-wider">Device</label>
              <select class="w-full bg-black/50 border border-gray-700 rounded p-2 text-sm text-white focus:ring-1 focus:ring-forti-red outline-none">
                <option value="all">All Devices</option>
                <option value="int_fgt_01" selected>FortiGate Lab (FGT-VM)</option>
              </select>
            </div>
            
            <div class="mt-4 pt-4 border-t border-gray-800">
              <button class="w-full bg-gray-800 hover:bg-gray-700 text-white rounded py-2 text-sm font-medium transition-colors">
                Apply Filters
              </button>
            </div>
          </div>

          <!-- Visualizations Tab -->
          <div v-if="activeBuildTab === 'visuals'" class="p-4 flex flex-col gap-4">
            <h3 class="text-xs font-medium text-gray-400 uppercase tracking-wider">Modules Catalog</h3>
            <div class="grid grid-cols-2 gap-2">
              <div 
                v-for="item in catalogData.items" 
                :key="item.id"
                @click="handleAddWidget(item.id)"
                class="bg-black/30 border border-gray-800 p-3 rounded hover:border-forti-red/50 hover:bg-gray-800 transition-colors flex flex-col items-center justify-center gap-2 cursor-pointer group text-center"
                :title="item.title"
              >
                <component :is="getIconForKind(item.kind)" :size="24" class="text-gray-500 group-hover:text-forti-red transition-colors" />
                <span class="text-[10px] leading-tight font-medium text-gray-400 group-hover:text-gray-200">{{ item.title }}</span>
              </div>
            </div>
          </div>

          <!-- Data Tab -->
          <div v-if="activeBuildTab === 'data'" class="p-4 flex flex-col gap-2">
            <h3 class="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">Available Fields</h3>
            
            <div v-for="group in dataFields.groups" :key="group.id" class="flex flex-col">
              <div 
                class="flex items-center gap-2 p-2 hover:bg-gray-800 rounded cursor-pointer transition-colors text-sm text-gray-300"
                @click="toggleFolder(group.id)"
              >
                <FolderOpen v-if="expandedFolders[group.id]" :size="16" class="text-amber-500" />
                <Folder v-else :size="16" class="text-amber-500" />
                <span class="font-medium">{{ group.name }}</span>
              </div>
              
              <div v-if="expandedFolders[group.id]" class="flex flex-col ml-6 pl-2 border-l border-gray-800 py-1 gap-1">
                <div 
                  v-for="field in group.fields" 
                  :key="field"
                  class="flex items-center gap-2 p-1.5 text-xs text-gray-400 hover:text-white cursor-pointer hover:bg-gray-800/50 rounded transition-colors"
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
