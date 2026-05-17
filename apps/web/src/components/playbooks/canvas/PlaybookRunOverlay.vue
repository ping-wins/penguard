<script setup lang="ts">
import type { PlaybookRun, PlaybookSimulation } from '../../../services/playbooksClient'

defineProps<{
  simulation?: PlaybookSimulation | null
  run?: PlaybookRun | null
}>()
</script>

<template>
  <div
    v-if="simulation || run"
    data-test="playbook-run-overlay"
    class="rounded border border-amber-400/30 bg-amber-500/10 p-2 text-xs text-amber-100"
  >
    <div v-if="run" class="font-semibold">{{ run.id }} · {{ run.status }}</div>
    <div v-else-if="simulation" class="font-semibold">Simulation · {{ simulation.valid ? 'valid' : 'invalid' }}</div>
    <div class="mt-1 text-[11px] text-theme-text-muted">
      {{ (run?.steps ?? simulation?.steps ?? []).length }} nodes with run state
    </div>
  </div>
</template>
