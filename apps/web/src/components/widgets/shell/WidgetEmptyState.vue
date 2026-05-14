<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
import type { Component } from 'vue'

defineProps<{
  title?: string
  hint?: string
  icon?: Component
}>()
</script>

<template>
  <div class="flex h-full min-h-24 flex-col items-center justify-center gap-1 rounded border border-dashed border-theme-border bg-theme-bg/40 p-4 text-center">
    <component :is="icon ?? Inbox" :size="20" class="text-theme-text-muted" />
    <span class="text-xs font-semibold text-theme-text">{{ title || 'No data' }}</span>
    <span v-if="hint" class="text-[11px] leading-snug text-theme-text-muted">{{ hint }}</span>
    <slot />
  </div>
</template>
