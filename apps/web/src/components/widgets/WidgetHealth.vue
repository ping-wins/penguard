<script setup lang="ts">
import { Server } from 'lucide-vue-next'

defineProps<{ data: any }>()
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-theme-text">
      <Server :size="24" class="text-theme-primary" />
      <span class="text-xl font-bold">System Status</span>
    </div>
    
    <div class="grid grid-cols-2 gap-4 flex-1">
      <div class="bg-theme-text/5 rounded-md p-3 flex flex-col justify-center border-l-4 border-emerald-500">
        <span class="text-xs text-theme-text-muted uppercase font-semibold">CPU</span>
        <span class="text-2xl font-bold text-theme-text">{{ data?.cpu || 0 }}%</span>
      </div>
      <div class="bg-theme-text/5 rounded-md p-3 flex flex-col justify-center border-l-4 border-amber-500">
        <span class="text-xs text-theme-text-muted uppercase font-semibold">Memory</span>
        <span class="text-2xl font-bold text-theme-text">{{ data?.memory || 0 }}%</span>
      </div>
      <div class="bg-theme-text/5 rounded-md p-3 flex flex-col justify-center border-l-4 border-blue-500 col-span-2">
        <span class="text-xs text-theme-text-muted uppercase font-semibold">Active Sessions</span>
        <span class="text-3xl font-bold text-theme-text tracking-tight">{{ data?.sessions?.toLocaleString() || 0 }}</span>
      </div>
    </div>
  </div>
</template>
