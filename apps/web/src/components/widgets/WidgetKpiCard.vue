<script setup lang="ts">
import { Activity, TrendingUp } from 'lucide-vue-next'
</script>

<template>
  <div class="h-full w-full flex flex-col items-center justify-center relative p-2">
    <div class="text-theme-text-muted text-sm font-medium mb-1 uppercase tracking-wide flex items-center gap-2">
      <Activity :size="16" /> Active Sessions
    </div>
    <div class="text-5xl font-bold text-theme-text tracking-tight">
      3,812
    </div>
    <div class="mt-3 text-xs flex items-center gap-1 text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded-full">
      <TrendingUp :size="12" /> +14% vs last hour
    </div>
  </div>
</template>
