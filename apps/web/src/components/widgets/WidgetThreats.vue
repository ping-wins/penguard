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
      <div v-for="(threat, i) in data?.threats || []" :key="i" class="bg-theme-text/5 rounded p-2 flex justify-between items-center text-sm">
        <span class="text-theme-text">{{ threat.name }}</span>
        <span class="text-theme-primary font-bold font-mono">{{ threat.srcIp }}</span>
      </div>
      <div v-if="!(data?.threats?.length)" class="text-xs text-theme-text-muted italic flex-1 flex items-center justify-center">
        Nenhuma ameaça recente.
      </div>
    </div>
  </div>
</template>
