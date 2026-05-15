import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useRealtimeStore, type RealtimeWidgetSnapshot } from './useRealtimeStore'

export type WidgetRealtimeSnapshot = RealtimeWidgetSnapshot & {
  widgetId: string
  integrationId: string
  data: Record<string, unknown>
}

function snapshotKey(widgetId: string, integrationId: string) {
  return `${widgetId}::${integrationId}`
}

function normalizeSnapshot(snapshot: RealtimeWidgetSnapshot): WidgetRealtimeSnapshot | null {
  if (!snapshot?.widgetId || !snapshot.integrationId) return null
  if (!snapshot.data || typeof snapshot.data !== 'object') return null
  return {
    ...snapshot,
    integrationId: snapshot.integrationId,
    status: snapshot.status === 'error' ? 'error' : 'ready',
    refreshedAt: snapshot.refreshedAt || new Date().toISOString(),
    data: snapshot.data,
  }
}

export const useWidgetRealtimeStore = defineStore('widgetRealtime', () => {
  const snapshots = ref<Record<string, WidgetRealtimeSnapshot>>({})
  let unsubscribeRealtime: (() => void) | null = null

  function upsertSnapshot(snapshot: RealtimeWidgetSnapshot) {
    const normalized = normalizeSnapshot(snapshot)
    if (!normalized) return
    snapshots.value = {
      ...snapshots.value,
      [snapshotKey(normalized.widgetId, normalized.integrationId)]: normalized,
    }
  }

  function getSnapshot(widgetId: string, integrationId: string | null | undefined) {
    if (!integrationId) return null
    return snapshots.value[snapshotKey(widgetId, integrationId)] ?? null
  }

  function startRealtime() {
    if (unsubscribeRealtime !== null) return
    unsubscribeRealtime = useRealtimeStore().subscribe((event) => {
      if (!Array.isArray(event.widgets)) return
      for (const snapshot of event.widgets) upsertSnapshot(snapshot)
    })
  }

  function stopRealtime() {
    unsubscribeRealtime?.()
    unsubscribeRealtime = null
  }

  function clearAll() {
    snapshots.value = {}
  }

  return {
    snapshots,
    upsertSnapshot,
    getSnapshot,
    startRealtime,
    stopRealtime,
    clearAll,
  }
})
