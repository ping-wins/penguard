<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { AlertTriangle, BellRing, X } from 'lucide-vue-next'
import { useIncidentToastsStore } from '../../stores/useIncidentToastsStore'
import { useAuthStore } from '../../stores/useAuthStore'

const toastsStore = useIncidentToastsStore()
const authStore = useAuthStore()

const visibleToasts = computed(() => toastsStore.toasts)

function severityColor(severity: string) {
  switch ((severity || '').toLowerCase()) {
    case 'critical':
      return 'border-red-500/50 bg-red-950/80 text-red-100'
    case 'high':
      return 'border-orange-500/50 bg-orange-950/80 text-orange-100'
    case 'medium':
      return 'border-amber-500/50 bg-amber-950/80 text-amber-100'
    case 'low':
      return 'border-sky-500/50 bg-sky-950/80 text-sky-100'
    default:
      return 'border-theme-border bg-theme-panel text-theme-text'
  }
}

function triageColor(level: string) {
  if (level === 'T3') return 'border-red-500/50 text-red-300'
  if (level === 'T2') return 'border-amber-500/50 text-amber-300'
  return 'border-sky-500/50 text-sky-300'
}

onMounted(() => {
  if (authStore.isAuthenticated) {
    toastsStore.startRealtime()
  }
})

onBeforeUnmount(() => {
  toastsStore.stopRealtime()
})
</script>

<template>
  <div class="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm pointer-events-none">
    <transition-group name="toast" tag="div" class="flex flex-col gap-2">
      <div
        v-for="toast in visibleToasts"
        :key="toast.id"
        :class="[
          'pointer-events-auto rounded-xl border shadow-2xl px-4 py-3 backdrop-blur-md',
          severityColor(toast.severity),
        ]"
      >
        <div class="flex items-start gap-3">
          <div class="mt-0.5 shrink-0">
            <AlertTriangle :size="18" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs font-semibold uppercase tracking-wider flex items-center gap-1">
                <BellRing :size="12" />
                New incident
              </span>
              <span
                class="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border font-semibold"
                :class="triageColor(toast.triageLevel)"
              >
                {{ toast.triageLevel }}
              </span>
            </div>
            <div class="text-sm font-semibold truncate">{{ toast.title }}</div>
            <div class="text-xs opacity-80 font-mono mt-1">{{ toast.ticketId }}</div>
          </div>
          <button
            type="button"
            class="opacity-60 hover:opacity-100 shrink-0"
            @click="toastsStore.dismiss(toast.id)"
            aria-label="Dismiss"
          >
            <X :size="14" />
          </button>
        </div>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active {
  transition: all 220ms ease-out;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(20px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(40px);
}
</style>
