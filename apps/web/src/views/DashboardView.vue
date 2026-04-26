<script setup lang="ts">
import Sidebar from '../components/layout/Sidebar.vue'
import DashboardCanvas from '../components/canvas/DashboardCanvas.vue'
import ThemeBuilderModal from '../components/layout/ThemeBuilderModal.vue'
import { useThemeStore } from '../stores/useThemeStore'

const themeStore = useThemeStore()
</script>

<template>
  <div class="w-screen h-screen flex overflow-hidden">
    <Sidebar />
    <DashboardCanvas />
    <ThemeBuilderModal :is-open="themeStore.isBuilderOpen" @close="themeStore.closeBuilder()" />
  </div>
</template>
