import { defineStore } from 'pinia'

type ThemeMode = 'dark' | 'light'

interface ThemeState {
  mode: ThemeMode
  primary: string
  secondary: string
  neutral: string
}

const defaultDark: ThemeState = {
  mode: 'dark',
  primary: '#1275E2',
  secondary: '#5F78A3',
  neutral: '#1A1C1E'
}

const defaultLight: ThemeState = {
  mode: 'light',
  primary: '#1275E2',
  secondary: '#5F78A3',
  neutral: '#F8FAFC'
}

export const useThemeStore = defineStore('theme', {
  state: (): ThemeState & { isBuilderOpen: boolean } => {
    const defaultState = { ...defaultDark, isBuilderOpen: false }
    const saved = localStorage.getItem('theme-settings')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        return { ...defaultState, ...parsed }
      } catch (e) {
        return defaultState
      }
    }
    return defaultState
  },
  actions: {
    openBuilder() {
      this.isBuilderOpen = true
    },
    closeBuilder() {
      this.isBuilderOpen = false
    },
    setMode(mode: ThemeMode) {
      this.mode = mode
      if (mode === 'light' && this.neutral === defaultDark.neutral) {
         this.neutral = defaultLight.neutral
      } else if (mode === 'dark' && this.neutral === defaultLight.neutral) {
         this.neutral = defaultDark.neutral
      }
      this.saveAndApply()
    },
    setColors(colors: Partial<Omit<ThemeState, 'mode'>>) {
      if (colors.primary) this.primary = colors.primary
      if (colors.secondary) this.secondary = colors.secondary
      if (colors.neutral) this.neutral = colors.neutral
      this.saveAndApply()
    },
    saveAndApply() {
      localStorage.setItem('theme-settings', JSON.stringify({
        mode: this.mode,
        primary: this.primary,
        secondary: this.secondary,
        neutral: this.neutral
      }))
      this.applyTheme()
    },
    applyTheme() {
      const root = document.documentElement.style
      root.setProperty('--theme-primary', this.primary)
      root.setProperty('--theme-secondary', this.secondary)
      root.setProperty('--theme-neutral', this.neutral)
      
      if (this.mode === 'dark') {
        root.setProperty('--theme-bg', '#121212')
        root.setProperty('--theme-panel', '#1e1e1e')
        root.setProperty('--theme-text', '#e2e8f0')
        root.setProperty('--theme-text-muted', '#94a3b8')
        root.setProperty('--theme-border', '#374151')
      } else {
        root.setProperty('--theme-bg', '#F1F5F9')
        root.setProperty('--theme-panel', '#FFFFFF')
        root.setProperty('--theme-text', '#0F172A')
        root.setProperty('--theme-text-muted', '#64748B')
        root.setProperty('--theme-border', '#CBD5E1')
      }
    }
  }
})
