import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'fortidashboard.widgetCompact'

function readInitial(): boolean {
  if (typeof localStorage === 'undefined') return false
  try {
    return localStorage.getItem(STORAGE_KEY) === '1'
  } catch {
    return false
  }
}

export const useWidgetCompactStore = defineStore('widgetCompact', () => {
  const isCompact = ref<boolean>(readInitial())

  function toggle() {
    isCompact.value = !isCompact.value
    persist()
  }

  function set(value: boolean) {
    isCompact.value = value
    persist()
  }

  function persist() {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.setItem(STORAGE_KEY, isCompact.value ? '1' : '0')
    } catch {
      // ignore quota errors
    }
  }

  return { isCompact, toggle, set }
})
