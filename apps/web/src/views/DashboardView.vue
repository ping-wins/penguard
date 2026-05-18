<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from '../components/layout/Sidebar.vue'
import DashboardCanvas from '../components/canvas/DashboardCanvas.vue'
import PlaybookBuilderSurface from '../components/playbooks/PlaybookBuilderSurface.vue'
import ThemeBuilderModal from '../components/layout/ThemeBuilderModal.vue'
import IncidentToastContainer from '../components/notifications/IncidentToastContainer.vue'
import SettingsModal from '../components/settings/SettingsModal.vue'
import { useThemeStore } from '../stores/useThemeStore'

const themeStore = useThemeStore()
const isSettingsOpen = ref(false)
const settingsInitialTab = ref<'profile' | 'marketplace'>('profile')
type MainSurface = 'workspace' | 'playbooks'
const activeSurface = ref<MainSurface>('workspace')

function openSettings(tab: 'profile' | 'marketplace' = 'profile') {
  settingsInitialTab.value = tab
  isSettingsOpen.value = true
}

function selectSurface(surface: MainSurface) {
  activeSurface.value = surface
}
</script>

<template>
  <div class="w-screen h-screen flex overflow-hidden">
    <Sidebar
      :active-surface="activeSurface"
      @select-surface="selectSurface"
      @open-settings="openSettings"
    />
    <DashboardCanvas v-if="activeSurface === 'workspace'" />
    <PlaybookBuilderSurface v-else-if="activeSurface === 'playbooks'" />
    <ThemeBuilderModal :is-open="themeStore.isBuilderOpen" @close="themeStore.closeBuilder()" />
    <SettingsModal
      :is-open="isSettingsOpen"
      :initial-tab="settingsInitialTab"
      @close="isSettingsOpen = false"
    />
    <IncidentToastContainer />
  </div>
</template>
