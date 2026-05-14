import { defineStore } from 'pinia'
import { ref } from 'vue'
import { extractSeriesSample, SERIES_CAPACITY, type SeriesSample } from '../lib/widgetSeries'

type InstanceBuffer = Record<string, number[]>

function siblingKey(widgetId: string, integrationId: string | null | undefined) {
  return `${widgetId}::${integrationId ?? ''}`
}

export const useWidgetSeriesStore = defineStore('widgetSeries', () => {
  const buffer = ref<Record<string, InstanceBuffer>>({})
  const latestData = ref<Record<string, unknown>>({})

  function recordSample(instanceId: string, widgetId: string, data: unknown, integrationId?: string | null) {
    if (integrationId !== undefined) {
      latestData.value = { ...latestData.value, [siblingKey(widgetId, integrationId)]: data }
    }
    const sample = extractSeriesSample(widgetId, data)
    if (!sample) return
    const instanceBuffer: InstanceBuffer = buffer.value[instanceId] ?? {}
    for (const [metric, value] of Object.entries(sample)) {
      const points = instanceBuffer[metric] ? [...instanceBuffer[metric]] : []
      points.push(value)
      while (points.length > SERIES_CAPACITY) points.shift()
      instanceBuffer[metric] = points
    }
    buffer.value = { ...buffer.value, [instanceId]: instanceBuffer }
  }

  function getSiblingData(widgetId: string, integrationId: string | null | undefined): unknown {
    return latestData.value[siblingKey(widgetId, integrationId)] ?? null
  }

  function getSeries(instanceId: string, metric: string): number[] {
    return buffer.value[instanceId]?.[metric] ?? []
  }

  function getInstanceSnapshot(instanceId: string): SeriesSample {
    const instance = buffer.value[instanceId]
    if (!instance) return {}
    const snapshot: SeriesSample = {}
    for (const [metric, points] of Object.entries(instance)) {
      const last = points[points.length - 1]
      if (typeof last === 'number') snapshot[metric] = last
    }
    return snapshot
  }

  function getSampleCount(instanceId: string): number {
    const instance = buffer.value[instanceId]
    if (!instance) return 0
    return Math.max(0, ...Object.values(instance).map((arr) => arr.length))
  }

  function clearInstance(instanceId: string) {
    if (!(instanceId in buffer.value)) return
    const next = { ...buffer.value }
    delete next[instanceId]
    buffer.value = next
  }

  function clearAll() {
    buffer.value = {}
    latestData.value = {}
  }

  return {
    buffer,
    latestData,
    recordSample,
    getSeries,
    getSiblingData,
    getInstanceSnapshot,
    getSampleCount,
    clearInstance,
    clearAll,
  }
})
