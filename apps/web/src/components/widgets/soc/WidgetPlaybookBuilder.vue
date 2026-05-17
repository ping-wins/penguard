<script setup lang="ts">
import PlaybookCanvasLayer from '../../playbooks/canvas/PlaybookCanvasLayer.vue'
</script>

<template>
  <div class="-m-4 h-[calc(100%+2rem)] w-[calc(100%+2rem)] overflow-hidden">
    <PlaybookCanvasLayer :embedded="true" />
  </div>
</template>
