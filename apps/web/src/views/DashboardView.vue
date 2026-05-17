<script setup lang="ts">
import { ref } from 'vue'
import Sidebar from '../components/layout/Sidebar.vue'
import DashboardCanvas from '../components/canvas/DashboardCanvas.vue'
import ThemeBuilderModal from '../components/layout/ThemeBuilderModal.vue'
import IncidentToastContainer from '../components/notifications/IncidentToastContainer.vue'
import SettingsModal from '../components/settings/SettingsModal.vue'
import { useThemeStore } from '../stores/useThemeStore'

const themeStore = useThemeStore()
const isSettingsOpen = ref(false)
const settingsInitialTab = ref<'profile' | 'marketplace'>('profile')

function openSettings(tab: 'profile' | 'marketplace' = 'profile') {
  settingsInitialTab.value = tab
  isSettingsOpen.value = true
}
</script>

<template>
  <div class="w-screen h-screen flex overflow-hidden">
    <Sidebar @open-settings="openSettings" />
    <DashboardCanvas />
    <ThemeBuilderModal :is-open="themeStore.isBuilderOpen" @close="themeStore.closeBuilder()" />
    <SettingsModal
      :is-open="isSettingsOpen"
      :initial-tab="settingsInitialTab"
      @close="isSettingsOpen = false"
    />
    <IncidentToastContainer />
  </div>
</template>
