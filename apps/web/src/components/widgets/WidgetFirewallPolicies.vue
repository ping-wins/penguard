<script setup lang="ts">
import { ListChecks } from 'lucide-vue-next'
import WidgetShell from './shell/WidgetShell.vue'
import WidgetEmptyState from './shell/WidgetEmptyState.vue'

const props = defineProps<{ data: any, catalogId?: string }>()
void props
</script>

<template>
  <WidgetShell
    :widget-id="props.catalogId || 'fortigate-firewall-policies'"
    title="Firewall Policies"
    subtitle="Active rule set"
    :icon="ListChecks"
    source="fortigate"
    :disable-drill="true"
    :disable-detail="true"
  >
    <template #glance>
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

        <WidgetEmptyState
          v-if="!(data?.policies?.length)"
          title="No policies returned"
          hint="FortiGate did not return any policy data for this integration."
        />
      </div>
    </template>
  </WidgetShell>
</template>
