<script setup lang="ts">
import { Network } from 'lucide-vue-next'

defineProps<{ data: any }>()
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-emerald-500">
      <Network :size="24" />
      <span class="text-xl font-bold">Network Interfaces</span>
    </div>
    
    <div class="flex-1 bg-theme-text/5 rounded-md p-2 overflow-y-auto no-scrollbar flex flex-col gap-2">
      <div v-for="(iface, i) in data?.interfaces || []" :key="i" class="flex justify-between items-center text-sm border-b border-theme-border/50 pb-1 last:border-0">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full" :class="iface.status === 'up' ? 'bg-emerald-500' : 'bg-red-500'"></div>
          <span class="text-theme-text font-medium">{{ iface.name || iface.id }}</span>
        </div>
        <div class="flex gap-3 text-xs text-theme-text-muted">
          <span><span class="text-emerald-400">↓</span> {{ ((iface.rxBytes || 0) / 1024 / 1024).toFixed(1) }}MB</span>
          <span><span class="text-blue-400">↑</span> {{ ((iface.txBytes || 0) / 1024 / 1024).toFixed(1) }}MB</span>
        </div>
      </div>
      <div v-if="!(data?.interfaces?.length)" class="text-xs text-theme-text-muted italic flex-1 flex items-center justify-center">
        Nenhuma interface.
      </div>
    </div>
  </div>
</template>
