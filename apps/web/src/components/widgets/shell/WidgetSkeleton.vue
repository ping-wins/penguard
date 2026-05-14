<script setup lang="ts">
defineProps<{ label?: string }>()
</script>

<template>
  <div class="flex h-full w-full flex-col gap-3 p-1" aria-busy="true" aria-live="polite">
    <div class="flex items-center gap-2">
      <div class="h-4 w-4 animate-pulse rounded-full bg-theme-text/10" />
      <div class="h-3 w-32 animate-pulse rounded bg-theme-text/10" />
    </div>
    <div class="grid grid-cols-2 gap-2">
      <div class="h-14 animate-pulse rounded-md bg-theme-text/5 border-l-4 border-theme-text/10" />
      <div class="h-14 animate-pulse rounded-md bg-theme-text/5 border-l-4 border-theme-text/10" />
    </div>
    <div class="flex flex-1 flex-col gap-1.5">
      <div class="h-3 animate-pulse rounded bg-theme-text/5" />
      <div class="h-3 w-5/6 animate-pulse rounded bg-theme-text/5" />
      <div class="h-3 w-4/6 animate-pulse rounded bg-theme-text/5" />
      <div class="h-3 w-5/6 animate-pulse rounded bg-theme-text/5" />
    </div>
    <span class="sr-only">{{ label || 'Loading widget data' }}</span>
  </div>
</template>
