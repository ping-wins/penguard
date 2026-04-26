<script setup lang="ts">
import Sidebar from './components/layout/Sidebar.vue'
import DashboardCanvas from './components/canvas/DashboardCanvas.vue'
</script>

<template>
  <div class="w-screen h-screen flex overflow-hidden">
    <Sidebar />
    <DashboardCanvas />
  </div>
</template>
