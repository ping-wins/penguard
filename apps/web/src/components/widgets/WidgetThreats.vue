<script setup lang="ts">
import { ShieldAlert } from 'lucide-vue-next'
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-amber-500">
      <ShieldAlert :size="24" />
      <span class="text-xl font-bold">Top Threats</span>
    </div>
    
    <div class="flex flex-col gap-2 flex-1 overflow-y-auto pr-2">
      <div v-for="i in 4" :key="i" class="bg-black/20 rounded p-2 flex justify-between items-center text-sm">
        <span class="text-slate-300">Intrusion.Botnet.{{ i }}</span>
        <span class="text-forti-red font-bold font-mono">10.0.0.{{ 10+i }}</span>
      </div>
    </div>
  </div>
</template>
