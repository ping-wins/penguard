<script setup lang="ts">
import { Server } from 'lucide-vue-next'
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-forti-red">
      <Server :size="24" />
      <span class="text-xl font-bold">System Status</span>
    </div>
    
    <div class="grid grid-cols-2 gap-4 flex-1">
      <div class="bg-black/20 rounded-lg p-3 flex flex-col justify-center border-l-4 border-emerald-500">
        <span class="text-xs text-gray-400 uppercase font-semibold">CPU</span>
        <span class="text-2xl font-bold text-white">12%</span>
      </div>
      <div class="bg-black/20 rounded-lg p-3 flex flex-col justify-center border-l-4 border-amber-500">
        <span class="text-xs text-gray-400 uppercase font-semibold">Memory</span>
        <span class="text-2xl font-bold text-white">54%</span>
      </div>
      <div class="bg-black/20 rounded-lg p-3 flex flex-col justify-center border-l-4 border-blue-500 col-span-2">
        <span class="text-xs text-gray-400 uppercase font-semibold">Active Sessions</span>
        <span class="text-3xl font-bold text-white tracking-tight">3,812</span>
      </div>
    </div>
  </div>
</template>
