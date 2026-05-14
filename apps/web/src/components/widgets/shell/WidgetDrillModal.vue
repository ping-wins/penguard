<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import { X } from 'lucide-vue-next'

const props = defineProps<{
  title: string
  subtitle?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const containerRef = ref<HTMLDivElement | null>(null)
let previouslyFocused: HTMLElement | null = null

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('close')
    return
  }
  if (event.key !== 'Tab' || !containerRef.value) return
  const focusable = containerRef.value.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )
  if (focusable.length === 0) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function handleBackdrop(event: MouseEvent) {
  if (event.target === event.currentTarget) emit('close')
}

onMounted(() => {
  previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null
  document.addEventListener('keydown', handleKeydown)
  document.body.style.overflow = 'hidden'
  requestAnimationFrame(() => {
    containerRef.value?.querySelector<HTMLElement>('button, [tabindex]')?.focus()
  })
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = ''
  previouslyFocused?.focus()
})
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-sm p-6"
      role="dialog"
      aria-modal="true"
      :aria-label="props.title"
      @mousedown="handleBackdrop"
    >
      <div
        ref="containerRef"
        class="flex max-h-[88vh] w-full max-w-3xl flex-col rounded-lg border border-theme-border bg-theme-panel shadow-2xl"
      >
        <header class="flex items-start justify-between gap-3 border-b border-theme-border px-5 py-3">
          <div class="min-w-0">
            <h2 class="truncate text-base font-semibold text-theme-text">{{ props.title }}</h2>
            <p v-if="props.subtitle" class="mt-0.5 truncate text-xs text-theme-text-muted">{{ props.subtitle }}</p>
          </div>
          <button
            type="button"
            class="rounded-md p-1 text-theme-text-muted hover:bg-theme-border hover:text-theme-text"
            aria-label="Close"
            @click="emit('close')"
          >
            <X :size="18" />
          </button>
        </header>
        <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          <slot />
        </div>
      </div>
    </div>
  </Teleport>
</template>
