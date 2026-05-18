<script setup lang="ts">
import PlaybookCanvasLayer from './canvas/PlaybookCanvasLayer.vue'
</script>

<template>
  <main data-test="playbook-builder-main-surface" class="h-full min-w-0 flex-1 overflow-hidden bg-theme-bg">
    <PlaybookCanvasLayer surface />
  </main>
</template>
