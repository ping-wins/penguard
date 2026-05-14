<script setup lang="ts">
import { computed, ref } from 'vue'
import { Target } from 'lucide-vue-next'
import WidgetShell from '../shell/WidgetShell.vue'
import WidgetEntityChip from '../shell/WidgetEntityChip.vue'
import WidgetKpiTile from '../shell/WidgetKpiTile.vue'
import { useWidgetSeriesStore } from '../../../stores/useWidgetSeriesStore'
import { useWidgetSeries } from '../../../composables/useWidgetSeries'

const props = defineProps<{
  data: any
  instanceId: string
  integrationId: string
  catalogId: string
}>()

const entities = computed<Array<{ field: string, value: string, count: number }>>(() => {
  const raw = Array.isArray(props.data?.entities) ? props.data.entities : []
  return raw
    .filter((row: any) => row && typeof row === 'object')
    .map((row: any) => ({
      field: String(row.field ?? ''),
      value: String(row.value ?? ''),
      count: Number(row.count) || 0,
    }))
    .sort((a: { count: number }, b: { count: number }) => b.count - a.count)
})

const uniqueSeries = useWidgetSeries(props.instanceId, 'uniqueEntities')
const seriesStore = useWidgetSeriesStore()

const selected = ref<{ field: string, value: string } | null>(null)

function selectEntity(payload: { field: string | null, value: string }) {
  if (!payload.value) return
  const next = { field: payload.field ?? '', value: payload.value }
  if (selected.value && selected.value.field === next.field && selected.value.value === next.value) {
    selected.value = null
    return
  }
  selected.value = next
}

const siblingIncidents = computed<any[]>(() => {
  const snapshot: any = seriesStore.getSiblingData('soc-recent-incidents', props.integrationId)
  if (!snapshot || !Array.isArray(snapshot.incidents)) return []
  return snapshot.incidents
})

const matchingIncidents = computed(() => {
  if (!selected.value) return [] as any[]
  return siblingIncidents.value.filter((inc: any) => {
    const entityValue = inc?.entities?.[selected.value!.field]
    return entityValue !== undefined && String(entityValue) === selected.value!.value
  })
})

const byField = computed(() => {
  const grouped = new Map<string, Array<{ value: string, count: number }>>()
  for (const entity of entities.value) {
    if (!grouped.has(entity.field)) grouped.set(entity.field, [])
    grouped.get(entity.field)!.push({ value: entity.value, count: entity.count })
  }
  return Array.from(grouped.entries()).map(([field, list]) => ({ field, list: list.slice(0, 5) }))
})
</script>

<template>
  <WidgetShell
    :widget-id="catalogId"
    title="Top Entities"
    subtitle="Incident entity hits"
    :icon="Target"
    source="siem_kowalski"
  >
    <template #glance>
      <div class="grid grid-cols-2 gap-2">
        <WidgetKpiTile label="Unique entities" :value="entities.length" :series="uniqueSeries.points.value" />
        <WidgetKpiTile label="Top hit" :value="entities[0]?.count ?? 0" :tone="entities[0]?.count ? 'warning' : 'default'" />
      </div>
      <div class="mt-1 flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto no-scrollbar">
        <div v-for="entity in entities.slice(0, 6)" :key="`${entity.field}::${entity.value}`">
          <WidgetEntityChip
            :field="entity.field"
            :value="entity.value"
            :count="entity.count"
            :selected="selected?.field === entity.field && selected?.value === entity.value"
            @click="selectEntity"
          />
        </div>
        <div v-if="entities.length === 0" class="flex flex-1 items-center justify-center text-xs italic text-theme-text-muted">
          No entity hits.
        </div>
      </div>
    </template>

    <template #drill>
      <div v-if="!selected" class="text-xs text-theme-text-muted">
        Select an entity to see incidents touching it.
      </div>
      <div v-else class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-theme-text-muted">
          <span>{{ selected.field }}: <span class="font-mono normal-case text-theme-text">{{ selected.value }}</span></span>
          <span>{{ matchingIncidents.length }} incidents</span>
        </div>
        <div v-if="matchingIncidents.length === 0" class="rounded border border-dashed border-theme-border bg-theme-bg/50 p-2 text-xs text-theme-text-muted">
          Add the Recent Incidents widget to see related incidents.
        </div>
        <div v-else class="flex max-h-40 flex-col gap-1 overflow-y-auto no-scrollbar">
          <div
            v-for="incident in matchingIncidents.slice(0, 10)"
            :key="incident.id"
            class="flex items-center justify-between gap-2 rounded bg-theme-text/5 px-2 py-1 text-xs"
          >
            <span class="truncate text-theme-text">{{ incident.title || incident.id }}</span>
            <span class="shrink-0 text-[10px] text-theme-text-muted">{{ incident.severity }}</span>
          </div>
        </div>
      </div>
    </template>

    <template #detail>
      <div class="flex flex-col gap-4">
        <section v-for="group in byField" :key="group.field">
          <h3 class="mb-1 text-xs font-semibold uppercase tracking-wide text-theme-text-muted">{{ group.field }}</h3>
          <div class="flex flex-wrap gap-1.5">
            <WidgetEntityChip
              v-for="row in group.list"
              :key="`${group.field}::${row.value}`"
              :field="group.field"
              :value="row.value"
              :count="row.count"
              @click="selectEntity"
            />
          </div>
        </section>
      </div>
    </template>
  </WidgetShell>
</template>
