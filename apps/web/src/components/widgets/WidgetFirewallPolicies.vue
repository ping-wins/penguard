<script setup lang="ts">
import { ListChecks } from 'lucide-vue-next'

defineProps<{ data: any }>()
</script>

<template>
  <div class="h-full w-full flex flex-col gap-4">
    <div class="flex items-center gap-3 text-blue-400">
      <ListChecks :size="24" />
      <span class="text-xl font-bold">Firewall Policies</span>
    </div>

    <div class="flex-1 bg-theme-text/5 rounded-md overflow-y-auto no-scrollbar">
      <div class="grid grid-cols-[1fr_auto] gap-x-3 px-3 py-2 text-[10px] uppercase tracking-wide text-theme-text-muted border-b border-theme-border/50">
        <span>Policy</span>
        <span>Status</span>
      </div>

      <div
        v-for="policy in data?.policies || []"
        :key="policy.id || policy.name"
        class="px-3 py-2 border-b border-theme-border/40 last:border-0 text-sm"
      >
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <div class="font-semibold text-theme-text truncate">{{ policy.name || `Policy ${policy.id}` }}</div>
            <div class="mt-1 text-xs text-theme-text-muted">
              {{ policy.srcIntf || 'any' }} to {{ policy.dstIntf || 'any' }}
            </div>
          </div>
          <div class="text-right shrink-0">
            <div class="text-xs font-semibold" :class="policy.action === 'deny' ? 'text-red-400' : 'text-emerald-400'">
              {{ policy.action || 'unknown' }}
            </div>
            <div class="text-[10px] text-theme-text-muted">{{ policy.status || 'unknown' }}</div>
          </div>
        </div>
      </div>

      <div v-if="!(data?.policies?.length)" class="h-full min-h-32 flex items-center justify-center text-xs text-theme-text-muted italic p-4 text-center">
        Nenhuma política retornada pelo FortiGate.
      </div>
    </div>
  </div>
</template>
