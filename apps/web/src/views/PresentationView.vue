<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight, X, Maximize2 } from 'lucide-vue-next'
import { useThemeStore } from '../stores/useThemeStore'
import type { PresentationMetadata, WorkspaceManifest } from '../services/workspaceClient'
import { exportWorkspace } from '../services/workspaceClient'

const route = useRoute()
const router = useRouter()
const themeStore = useThemeStore()

const manifest = ref<WorkspaceManifest | null>(null)
const presentation = ref<PresentationMetadata | null>(null)
const currentSlide = ref(-1) // -1 = title slide
const loadError = ref('')
const isLoading = ref(true)

const workspaceId = computed(() => String(route.params.workspaceId ?? ''))

const totalSlides = computed(() => (presentation.value?.slides?.length ?? 0) + 1) // +1 for title

const slideRange = computed(() => ({
  index: currentSlide.value + 2,
  total: totalSlides.value,
}))

const activeSlide = computed(() => {
  if (currentSlide.value < 0) return null
  return presentation.value?.slides[currentSlide.value] ?? null
})

const activeWidget = computed(() => {
  if (!activeSlide.value || !manifest.value) return null
  return manifest.value.widgets.find((w) => w.instanceId === activeSlide.value!.widgetInstanceId)
})

async function loadManifest() {
  isLoading.value = true
  try {
    const result = await exportWorkspace(workspaceId.value)
    manifest.value = result
    presentation.value = result.presentation
    if (!result.presentation || result.presentation.slides.length === 0) {
      loadError.value = 'Workspace não tem apresentação configurada.'
    }
  } catch (e: any) {
    loadError.value = e?.message ?? 'Erro ao carregar workspace'
  } finally {
    isLoading.value = false
  }
}

function next() {
  if (currentSlide.value < (presentation.value?.slides.length ?? 0) - 1) {
    currentSlide.value += 1
  }
}

function prev() {
  if (currentSlide.value > -1) {
    currentSlide.value -= 1
  }
}

function exit() {
  router.push({ name: 'dashboard' })
}

function handleKey(e: KeyboardEvent) {
  if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {
    e.preventDefault()
    next()
  } else if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
    e.preventDefault()
    prev()
  } else if (e.key === 'Escape') {
    exit()
  } else if (e.key === 'f' || e.key === 'F') {
    toggleFullscreen()
  }
}

async function toggleFullscreen() {
  if (document.fullscreenElement) {
    await document.exitFullscreen()
  } else {
    await document.documentElement.requestFullscreen()
  }
}

const severityColor = computed(() => {
  switch (presentation.value?.severity) {
    case 'critical':
      return '#ef4444'
    case 'high':
      return '#f97316'
    case 'medium':
      return '#eab308'
    case 'low':
      return '#3b82f6'
    default:
      return themeStore.primary
  }
})

onMounted(() => {
  window.addEventListener('keydown', handleKey)
  loadManifest()
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKey)
})
</script>

<template>
  <div class="min-h-screen w-full bg-theme-bg text-theme-text flex flex-col" :style="{ background: 'var(--theme-bg, #0a0a0f)' }">
    <div class="flex items-center justify-between px-6 py-3 border-b border-theme-border">
      <div class="flex items-center gap-3">
        <button type="button" @click="exit" class="text-theme-text-muted hover:text-theme-text flex items-center gap-1">
          <X :size="16" />
          Sair
        </button>
        <span class="text-sm text-theme-text-muted">{{ slideRange.index }} / {{ slideRange.total }}</span>
      </div>
      <div class="text-sm font-semibold" :style="{ color: severityColor }">
        {{ presentation?.severity?.toUpperCase() }}
      </div>
      <button type="button" @click="toggleFullscreen" class="text-theme-text-muted hover:text-theme-text flex items-center gap-1">
        <Maximize2 :size="16" />
        Tela cheia
      </button>
    </div>

    <div class="flex-1 flex items-center justify-center p-10 relative">
      <div v-if="isLoading" class="text-theme-text-muted">Carregando manifest...</div>
      <div v-else-if="loadError" class="text-red-400 max-w-md text-center">
        {{ loadError }}
        <div class="mt-4">
          <button type="button" @click="exit" class="px-4 py-2 rounded bg-theme-panel border border-theme-border">Voltar ao dashboard</button>
        </div>
      </div>

      <!-- Title Slide -->
      <div v-else-if="currentSlide === -1 && presentation" class="max-w-3xl text-center">
        <div
          class="inline-block px-4 py-1 rounded-full text-xs font-semibold mb-6"
          :style="{ backgroundColor: severityColor + '20', color: severityColor }"
        >
          {{ presentation.severity?.toUpperCase() || 'BRIEFING' }}
        </div>
        <h1 class="text-5xl font-bold mb-6 text-theme-text">{{ presentation.title }}</h1>
        <p v-if="presentation.incidentSummary" class="text-xl text-theme-text-muted leading-relaxed mb-8 whitespace-pre-line">
          {{ presentation.incidentSummary }}
        </p>
        <div class="text-sm text-theme-text-muted">
          <div v-if="presentation.presenterName">Apresentador: <b>{{ presentation.presenterName }}</b></div>
          <div v-if="presentation.audience">Audiência: <b>{{ presentation.audience }}</b></div>
          <div v-if="manifest?.metadata?.exportedAt">Exportado: {{ manifest.metadata.exportedAt }}</div>
        </div>
      </div>

      <!-- Content Slide -->
      <div v-else-if="activeSlide" class="max-w-5xl w-full">
        <div class="mb-4">
          <div class="text-xs uppercase tracking-wider text-theme-text-muted mb-1">
            Slide {{ currentSlide + 1 }}
          </div>
          <h2 class="text-3xl font-bold text-theme-text">{{ activeSlide.title }}</h2>
        </div>
        <div class="grid grid-cols-3 gap-6">
          <div class="col-span-2 bg-theme-panel border border-theme-border rounded-2xl p-6 min-h-[320px]">
            <div v-if="activeWidget" class="space-y-3">
              <div class="text-xs uppercase tracking-wider text-theme-text-muted">Widget</div>
              <div class="text-lg font-semibold text-theme-text">{{ activeWidget.catalogId }}</div>
              <div class="text-sm text-theme-text-muted">Provider: {{ activeWidget.providerType }}</div>
              <div v-if="activeWidget.fieldBindings?.length">
                <div class="text-xs uppercase tracking-wider text-theme-text-muted mt-3 mb-1">Campos exibidos</div>
                <ul class="text-sm text-theme-text space-y-1">
                  <li
                    v-for="(binding, i) in activeWidget.fieldBindings"
                    :key="i"
                    :class="{ 'font-bold': activeSlide.highlightFieldIds.includes(binding.fieldId) }"
                  >
                    • {{ binding.label }} <span class="text-theme-text-muted text-xs">({{ binding.type }}{{ binding.unit ? ' · ' + binding.unit : '' }})</span>
                  </li>
                </ul>
              </div>
              <p class="text-xs text-theme-text-muted mt-4 italic">
                * Esta é a estrutura do widget. Para visualização ao vivo, acesse o dashboard com a integração conectada.
              </p>
            </div>
            <div v-else class="text-theme-text-muted">Widget não encontrado no manifest.</div>
          </div>
          <div class="col-span-1 bg-theme-panel/60 border border-theme-border rounded-2xl p-6">
            <div class="text-xs uppercase tracking-wider text-theme-text-muted mb-2">Narração</div>
            <p class="text-sm text-theme-text whitespace-pre-line leading-relaxed">
              {{ activeSlide.narration || '(sem notas)' }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <div class="flex items-center justify-between px-6 py-4 border-t border-theme-border">
      <button
        type="button"
        @click="prev"
        :disabled="currentSlide <= -1"
        class="flex items-center gap-2 px-4 py-2 rounded-lg border border-theme-border text-theme-text disabled:opacity-30 hover:brightness-110"
      >
        <ChevronLeft :size="16" />
        Anterior
      </button>
      <div class="text-xs text-theme-text-muted">← / → · Esc para sair · F para tela cheia</div>
      <button
        type="button"
        @click="next"
        :disabled="currentSlide >= (presentation?.slides.length ?? 0) - 1"
        class="flex items-center gap-2 px-4 py-2 rounded-lg text-white hover:brightness-110 disabled:opacity-30"
        :style="{ backgroundColor: themeStore.primary }"
      >
        Próximo
        <ChevronRight :size="16" />
      </button>
    </div>
  </div>
</template>
