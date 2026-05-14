<script setup lang="ts">
import { ShieldAlert } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetEmptyState from './shell/WidgetEmptyState.vue'

const props = defineProps<{ data: any, catalogId?: string }>()
void props
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-top-threats'"
    title="Top Threats"
    subtitle="FortiGate threat log"
    :icon="ShieldAlert"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
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
        <WidgetEmptyState
          v-if="!(data?.threats?.length)"
          title="No recent threats"
          hint="FortiGate threat log is empty. Verify policy logging, generate routed traffic, then run ingestion from the integration card."
        />
      </div>
    </template>
  </WidgetShell>
</template>
