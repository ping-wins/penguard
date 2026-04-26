<script setup lang="ts">
import { Network } from 'lucide-vue-next'
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-emerald-500">
      <Network :size="24" />
      <span class="text-xl font-bold">Network Traffic</span>
    </div>
    
    <div class="flex-1 bg-black/20 rounded-lg flex items-end p-2 gap-1 overflow-hidden">
      <div v-for="h in [20, 50, 80, 40, 60, 90, 30, 70, 100, 50, 40]" :key="h" 
           class="flex-1 bg-emerald-500/50 rounded-t-sm transition-all hover:bg-emerald-400/80" 
           :style="{ height: h + '%' }"></div>
    </div>
  </div>
</template>
