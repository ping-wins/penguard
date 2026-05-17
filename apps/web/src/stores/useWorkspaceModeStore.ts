import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'fortidashboard.workspaceMode'
const LEGACY_COMPACT_KEY = 'fortidashboard.widgetCompact'

export type WorkspaceMode = 'canvas' | 'grid'

function readInitial(): WorkspaceMode {
  if (typeof localStorage === 'undefined') return 'canvas'
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'grid' || stored === 'canvas') return stored
    const legacy = localStorage.getItem(LEGACY_COMPACT_KEY)
    if (legacy === '1') return 'grid'
    return 'canvas'
  } catch {
    return 'canvas'
  }
}

export const useWorkspaceModeStore = defineStore('workspaceMode', () => {
  const mode = ref<WorkspaceMode>(readInitial())

  function persist() {
    if (typeof localStorage === 'undefined') return
    try {
      localStorage.setItem(STORAGE_KEY, mode.value)
    } catch {
      // ignore quota errors
    }
  }

  function setMode(next: WorkspaceMode) {
    if (mode.value === next) return
    mode.value = next
    persist()
  }

  function toggle() {
    setMode(mode.value === 'canvas' ? 'grid' : 'canvas')
  }

  return { mode, setMode, toggle }
})
