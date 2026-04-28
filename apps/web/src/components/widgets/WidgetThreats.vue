<script setup lang="ts">
import { ShieldAlert } from 'lucide-vue-next'

defineProps<{ data: any }>()
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-amber-500">
      <ShieldAlert :size="24" />
      <span class="text-xl font-bold">Top Threats</span>
    </div>
    
    <div class="flex flex-col gap-2 flex-1 overflow-y-auto no-scrollbar pr-2">
      <div v-for="(threat, i) in data?.threats || []" :key="i" class="bg-theme-text/5 rounded p-2 text-sm">
        <div class="flex justify-between gap-3">
          <span class="text-theme-text font-medium truncate">{{ threat.message || threat.name || 'Threat event' }}</span>
          <span class="text-theme-primary font-bold uppercase text-xs">{{ threat.severity || 'unknown' }}</span>
        </div>
        <div class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-theme-text-muted">
          <span class="font-mono">{{ threat.sourceIp || threat.srcIp || 'unknown source' }}</span>
          <span v-if="threat.destinationIp" class="font-mono">to {{ threat.destinationIp }}</span>
          <span v-if="threat.action" class="uppercase">{{ threat.action }}</span>
        </div>
      </div>
      <div v-if="!(data?.threats?.length)" class="text-xs text-theme-text-muted italic flex-1 flex items-center justify-center">
        Nenhuma ameaça recente.
      </div>
    </div>
  </div>
</template>
