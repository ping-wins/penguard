import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

// Per-user UI preferences that don't belong to a workspace manifest: drawer
// widths, build pane width, minimap collapsed flag. Persisted in localStorage
// so the layout survives a reload without round-tripping through the BFF.

const STORAGE_KEY = 'fortidashboard:cockpit-layout'

const DEFAULT_SIDEBAR_DRAWER_WIDTH = 360
const DEFAULT_BUILD_PANE_WIDTH = 300

export const SIDEBAR_DRAWER_MIN_WIDTH = 260
export const SIDEBAR_DRAWER_MAX_WIDTH = 720
export const BUILD_PANE_MIN_WIDTH = 240
export const BUILD_PANE_MAX_WIDTH = 640

type PersistedLayout = {
  sidebarDrawerWidth: number
  buildPaneWidth: number
  minimapCollapsed: boolean
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}

function loadPersisted(): PersistedLayout {
  const fallback: PersistedLayout = {
    sidebarDrawerWidth: DEFAULT_SIDEBAR_DRAWER_WIDTH,
    buildPaneWidth: DEFAULT_BUILD_PANE_WIDTH,
    minimapCollapsed: false,
  }
  if (typeof window === 'undefined' || !window.localStorage) return fallback
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<PersistedLayout>
    return {
      sidebarDrawerWidth: clamp(
        typeof parsed.sidebarDrawerWidth === 'number'
          ? parsed.sidebarDrawerWidth
          : DEFAULT_SIDEBAR_DRAWER_WIDTH,
        SIDEBAR_DRAWER_MIN_WIDTH,
        SIDEBAR_DRAWER_MAX_WIDTH,
      ),
      buildPaneWidth: clamp(
        typeof parsed.buildPaneWidth === 'number'
          ? parsed.buildPaneWidth
          : DEFAULT_BUILD_PANE_WIDTH,
        BUILD_PANE_MIN_WIDTH,
        BUILD_PANE_MAX_WIDTH,
      ),
      minimapCollapsed: Boolean(parsed.minimapCollapsed),
    }
  } catch {
    return fallback
  }
}

export const useCockpitLayoutStore = defineStore('cockpit-layout', () => {
  const initial = loadPersisted()
  const sidebarDrawerWidth = ref(initial.sidebarDrawerWidth)
  const buildPaneWidth = ref(initial.buildPaneWidth)
  const minimapCollapsed = ref(initial.minimapCollapsed)

  function setSidebarDrawerWidth(value: number) {
    sidebarDrawerWidth.value = clamp(value, SIDEBAR_DRAWER_MIN_WIDTH, SIDEBAR_DRAWER_MAX_WIDTH)
  }

  function setBuildPaneWidth(value: number) {
    buildPaneWidth.value = clamp(value, BUILD_PANE_MIN_WIDTH, BUILD_PANE_MAX_WIDTH)
  }

  function toggleMinimap() {
    minimapCollapsed.value = !minimapCollapsed.value
  }

  if (typeof window !== 'undefined' && window.localStorage) {
    watch(
      [sidebarDrawerWidth, buildPaneWidth, minimapCollapsed],
      ([sidebar, build, collapsed]) => {
        window.localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            sidebarDrawerWidth: sidebar,
            buildPaneWidth: build,
            minimapCollapsed: collapsed,
          }),
        )
      },
    )
  }

  return {
    sidebarDrawerWidth,
    buildPaneWidth,
    minimapCollapsed,
    setSidebarDrawerWidth,
    setBuildPaneWidth,
    toggleMinimap,
  }
})
