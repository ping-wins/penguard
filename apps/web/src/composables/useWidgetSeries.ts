import { computed } from 'vue'
import { useWidgetSeriesStore } from '../stores/useWidgetSeriesStore'
import { SERIES_CAPACITY } from '../lib/widgetSeries'

export function useWidgetSeries(instanceId: string, metric: string) {
  const store = useWidgetSeriesStore()
  const points = computed(() => store.getSeries(instanceId, metric))
  const sampleCount = computed(() => store.getSampleCount(instanceId))
  const capacity = SERIES_CAPACITY
  return { points, sampleCount, capacity }
}

export function useWidgetSeriesSnapshot(instanceId: string) {
  const store = useWidgetSeriesStore()
  const snapshot = computed(() => store.getInstanceSnapshot(instanceId))
  return snapshot
}
