<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useThemeStore } from '../../stores/useThemeStore'
import { X, Moon, Sun, Type, Layout, Search, Image as ImageIcon } from 'lucide-vue-next'

const props = defineProps<{
  isOpen: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const themeStore = useThemeStore()
const { t } = useI18n()

const localPrimary = ref(themeStore.primary)
const localSecondary = ref(themeStore.secondary)
const localNeutral = ref(themeStore.neutral)

type ThemeMode = 'light' | 'dark'

interface ThemePreset {
  id: string
  nameKey: string
  mode: ThemeMode
  primary: string
  secondary: string
  neutral: string
}

const presets: ThemePreset[] = [
  { id: 'custom', nameKey: 'settings.themeBuilder.presets.custom', mode: 'dark', primary: '', secondary: '', neutral: '' },
  { id: 'fortinet', nameKey: 'settings.themeBuilder.presets.fortinet', mode: 'dark', primary: '#ea0029', secondary: '#5f78a3', neutral: '#1a1c1e' },
  { id: 'cyber', nameKey: 'settings.themeBuilder.presets.cyber', mode: 'dark', primary: '#00e5ff', secondary: '#0f766e', neutral: '#0f172a' },
  { id: 'emerald', nameKey: 'settings.themeBuilder.presets.emerald', mode: 'dark', primary: '#00ff66', secondary: '#166534', neutral: '#052e16' },
  { id: 'light_ocean', nameKey: 'settings.themeBuilder.presets.lightOcean', mode: 'light', primary: '#0284c7', secondary: '#38bdf8', neutral: '#f8fafc' },
  { id: 'opera', nameKey: 'settings.themeBuilder.presets.opera', mode: 'dark', primary: '#fa196e', secondary: '#9d174d', neutral: '#121212' },
]

const activePreset = ref('custom')

function applyPreset(preset: ThemePreset) {
  activePreset.value = preset.id
  if (preset.id !== 'custom') {
    localPrimary.value = preset.primary
    localSecondary.value = preset.secondary
    localNeutral.value = preset.neutral
    themeStore.setMode(preset.mode)
    updateColors()
  }
}

function updateColors() {
  activePreset.value = 'custom'
  themeStore.setColors({
    primary: localPrimary.value,
    secondary: localSecondary.value,
    neutral: localNeutral.value
  })
}

function setMode(mode: ThemeMode) {
  activePreset.value = 'custom'
  themeStore.setMode(mode)
  localNeutral.value = themeStore.neutral
}
</script>

<template>
  <div v-if="isOpen" class="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 md:p-8">
    <div class="bg-theme-bg border border-theme-border rounded-2xl w-full max-w-6xl max-h-[90vh] shadow-2xl flex flex-col overflow-hidden text-theme-text transition-colors duration-300">
      
      <!-- Header -->
      <header class="flex justify-between items-center p-6 border-b border-theme-border bg-theme-panel transition-colors duration-300">
        <div>
          <h2 class="text-2xl font-bold">{{ t('settings.themeBuilder.title') }}</h2>
          <p class="text-theme-text-muted text-sm mt-1">{{ t('settings.themeBuilder.subtitle') }}</p>
        </div>
        <button
          @click="emit('close')"
          class="p-2 rounded-lg hover:bg-theme-border text-theme-text-muted hover:text-theme-text transition-colors"
          :aria-label="t('common.close')"
        >
          <X :size="24" />
        </button>
      </header>

      <!-- Content -->
      <div class="flex-1 overflow-hidden flex flex-col lg:flex-row">
        
        <!-- Sidebar Controls -->
        <aside class="w-full lg:w-[340px] border-r border-theme-border bg-theme-panel p-6 flex flex-col gap-8 overflow-y-auto transition-colors duration-300">
          
          <!-- Presets Section -->
          <section>
            <h3 class="text-sm font-semibold uppercase tracking-wider text-theme-text-muted mb-3">
              {{ t('settings.themeBuilder.presetsTitle') }}
            </h3>
            <div class="grid grid-cols-2 gap-3">
              <button 
                v-for="preset in presets" 
                :key="preset.id"
                @click="applyPreset(preset)"
                class="flex flex-col items-center justify-center p-3 rounded-xl border transition-all group"
                :class="activePreset === preset.id ? 'border-theme-primary bg-theme-primary/10' : 'border-theme-border hover:bg-theme-bg'"
              >
                <div v-if="preset.id === 'custom'" class="w-8 h-8 rounded-full mb-2 flex items-center justify-center border-2 border-dashed border-theme-text-muted text-theme-text-muted group-hover:text-theme-text transition-colors">
                  <Layout :size="14" />
                </div>
                <div v-else class="flex gap-1 mb-2 h-8 items-center">
                  <div class="w-4 h-4 rounded-full shadow-sm" :style="{ backgroundColor: preset.primary }"></div>
                  <div class="w-4 h-4 rounded-full shadow-sm" :style="{ backgroundColor: preset.secondary }"></div>
                </div>
                <span class="text-[10px] font-semibold text-theme-text text-center">{{ t(preset.nameKey) }}</span>
                <span v-if="preset.id !== 'custom'" class="text-[9px] text-theme-text-muted capitalize mt-1">
                  {{ t('settings.themeBuilder.modeLabel', { mode: t(`settings.themeBuilder.modes.${preset.mode}`) }) }}
                </span>
              </button>
            </div>
          </section>

          <div v-if="activePreset === 'custom'" class="flex flex-col gap-8 animate-in fade-in slide-in-from-top-4 duration-300">
            <!-- Mode Switch -->
            <section>
              <h3 class="text-sm font-semibold uppercase tracking-wider text-theme-text-muted mb-3">
                {{ t('settings.themeBuilder.customMode') }}
              </h3>
            <div class="flex bg-theme-bg rounded-lg p-1 border border-theme-border">
              <button 
                @click="setMode('light')"
                class="flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-all"
                :class="themeStore.mode === 'light' ? 'bg-white text-black shadow-sm' : 'text-theme-text-muted hover:text-theme-text'"
              >
                <Sun :size="16" /> {{ t('settings.themeBuilder.modes.light') }}
              </button>
              <button 
                @click="setMode('dark')"
                class="flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-all"
                :class="themeStore.mode === 'dark' ? 'bg-gray-800 text-white shadow-sm' : 'text-theme-text-muted hover:text-theme-text'"
              >
                <Moon :size="16" /> {{ t('settings.themeBuilder.modes.dark') }}
              </button>
            </div>
          </section>

          <!-- Colors -->
          <section>
            <h3 class="text-sm font-semibold uppercase tracking-wider text-theme-text-muted mb-3">
              {{ t('settings.themeBuilder.colorPalette') }}
            </h3>
            
            <div class="space-y-4">
              <!-- Primary -->
              <div class="bg-theme-bg p-4 rounded-xl border border-theme-border">
                <div class="flex justify-between items-center mb-2">
                  <span class="text-sm font-medium">{{ t('settings.themeBuilder.colors.primary') }}</span>
                  <span class="text-xs font-mono text-theme-text-muted">{{ localPrimary }}</span>
                </div>
                <div class="flex gap-3">
                  <input type="color" v-model="localPrimary" @input="updateColors" class="w-10 h-10 rounded cursor-pointer border-0 p-0 bg-transparent" />
                  <div class="flex-1 rounded-md" :style="{ backgroundColor: localPrimary }"></div>
                </div>
              </div>

              <!-- Secondary -->
              <div class="bg-theme-bg p-4 rounded-xl border border-theme-border">
                <div class="flex justify-between items-center mb-2">
                  <span class="text-sm font-medium">{{ t('settings.themeBuilder.colors.secondary') }}</span>
                  <span class="text-xs font-mono text-theme-text-muted">{{ localSecondary }}</span>
                </div>
                <div class="flex gap-3">
                  <input type="color" v-model="localSecondary" @input="updateColors" class="w-10 h-10 rounded cursor-pointer border-0 p-0 bg-transparent" />
                  <div class="flex-1 rounded-md" :style="{ backgroundColor: localSecondary }"></div>
                </div>
              </div>

              <!-- Neutral -->
              <div class="bg-theme-bg p-4 rounded-xl border border-theme-border">
                <div class="flex justify-between items-center mb-2">
                  <span class="text-sm font-medium">{{ t('settings.themeBuilder.colors.neutral') }}</span>
                  <span class="text-xs font-mono text-theme-text-muted">{{ localNeutral }}</span>
                </div>
                <div class="flex gap-3">
                  <input type="color" v-model="localNeutral" @input="updateColors" class="w-10 h-10 rounded cursor-pointer border-0 p-0 bg-transparent" />
                  <div class="flex-1 rounded-md" :style="{ backgroundColor: localNeutral }"></div>
                </div>
              </div>
              </div>
            </section>
          </div>
        </aside>

        <!-- Preview Area -->
        <main class="flex-1 bg-theme-bg p-8 overflow-y-auto transition-colors duration-300">
          <div class="max-w-4xl mx-auto space-y-8">
            
            <!-- Typography -->
            <section class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="bg-theme-panel border border-theme-border rounded-xl p-6 transition-colors duration-300">
                <div class="flex justify-between text-xs text-theme-text-muted uppercase tracking-widest mb-4">
                  <span>{{ t('settings.themeBuilder.preview.headline') }}</span>
                  <span>Inter</span>
                </div>
                <div class="text-7xl font-bold tracking-tight">Aa</div>
              </div>
              <div class="bg-theme-panel border border-theme-border rounded-xl p-6 transition-colors duration-300">
                <div class="flex justify-between text-xs text-theme-text-muted uppercase tracking-widest mb-4">
                  <span>{{ t('settings.themeBuilder.preview.body') }}</span>
                  <span>Inter</span>
                </div>
                <div class="text-5xl font-medium tracking-tight">Aa</div>
              </div>
            </section>

            <!-- Buttons & Inputs -->
            <section class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div class="bg-theme-panel border border-theme-border rounded-xl p-6 flex flex-col justify-center items-center gap-4 transition-colors duration-300">
                <div class="flex gap-4">
                  <button class="px-6 py-2.5 rounded-lg text-white font-medium shadow-lg transition-colors" :style="{ backgroundColor: themeStore.primary }">
                    {{ t('settings.themeBuilder.preview.primaryButton') }}
                  </button>
                  <button class="px-6 py-2.5 rounded-lg text-white font-medium shadow-lg transition-colors" :style="{ backgroundColor: themeStore.secondary }">
                    {{ t('settings.themeBuilder.preview.secondaryButton') }}
                  </button>
                </div>
                <div class="flex gap-4">
                  <button class="px-6 py-2.5 rounded-lg border-2 font-medium transition-colors" :style="{ borderColor: themeStore.primary, color: themeStore.primary }">
                    {{ t('settings.themeBuilder.preview.outlinedButton') }}
                  </button>
                  <button class="px-6 py-2.5 rounded-lg border border-theme-border font-medium hover:bg-theme-border transition-colors">
                    {{ t('settings.themeBuilder.preview.neutralButton') }}
                  </button>
                </div>
              </div>

              <div class="bg-theme-panel border border-theme-border rounded-xl p-6 flex flex-col justify-center items-center gap-6 transition-colors duration-300">
                <div class="w-full max-w-sm relative">
                  <Search :size="18" class="absolute left-3 top-3 text-theme-text-muted" />
                  <input
                    type="text"
                    :placeholder="t('settings.themeBuilder.preview.searchPlaceholder')"
                    class="w-full bg-theme-bg border border-theme-border rounded-lg pl-10 pr-4 py-2.5 text-sm focus:outline-none transition-colors duration-300"
                    :style="{ borderColor: themeStore.primary }"
                  />
                </div>
                <div class="flex gap-4">
                  <div class="w-10 h-10 rounded-full flex items-center justify-center text-white shadow-md" :style="{ backgroundColor: themeStore.primary }">
                    <ImageIcon :size="18" />
                  </div>
                  <div class="w-10 h-10 rounded-full flex items-center justify-center text-white shadow-md" :style="{ backgroundColor: themeStore.secondary }">
                    <Type :size="18" />
                  </div>
                  <div class="w-10 h-10 rounded-full flex items-center justify-center bg-theme-bg border border-theme-border text-theme-text transition-colors duration-300">
                    <Layout :size="18" />
                  </div>
                </div>
              </div>
            </section>

          </div>
        </main>
      </div>
    </div>
  </div>
</template>
