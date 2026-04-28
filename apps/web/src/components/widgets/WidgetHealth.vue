<script setup lang="ts">
import { computed } from 'vue'
import { Server } from 'lucide-vue-next'

const props = defineProps<{ data: any }>()

const deviceTitle = computed(() => props.data?.hostname || props.data?.model || 'FortiGate')
const deviceMeta = computed(() => {
  return [props.data?.model, props.data?.version].filter(Boolean).join(' / ')
})
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-theme-text">
      <Server :size="24" class="text-theme-primary" />
      <div class="min-w-0">
        <span class="text-xl font-bold">System Status</span>
        <div class="text-xs text-theme-text-muted truncate">
          <span class="font-mono text-theme-text">{{ deviceTitle }}</span>
          <span v-if="deviceMeta"> · {{ deviceMeta }}</span>
        </div>
      </div>
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
