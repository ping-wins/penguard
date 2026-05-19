<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Copy, Loader2, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  open: boolean
  enrollmentToken: string | null
  isCreating: boolean
  error: string | null
}>()

const emit = defineEmits<{
  close: []
  submit: [payload: { displayName?: string; hostnameHint?: string }]
  copy: [enrollmentToken: string]
}>()

const { t } = useI18n()
const displayName = ref('')
const hostnameHint = ref('')

const canSubmit = computed(() => !props.isCreating)

watch(() => props.open, (open) => {
  if (!open) {
    displayName.value = ''
    hostnameHint.value = ''
  }
})

function submit() {
  if (!canSubmit.value) return
  emit('submit', {
    displayName: displayName.value.trim() || undefined,
    hostnameHint: hostnameHint.value.trim() || undefined,
  })
}

function copyEnrollmentToken() {
  if (props.enrollmentToken) emit('copy', props.enrollmentToken)
}
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    role="dialog"
    aria-modal="true"
    :aria-label="t('endpoints.enrollment.title')"
  >
    <div class="w-full max-w-xl rounded-lg border border-theme-border bg-theme-panel shadow-2xl">
      <header class="flex items-start justify-between gap-3 border-b border-theme-border p-4">
        <div>
          <h3 class="text-base font-bold text-theme-text">{{ t('endpoints.enrollment.title') }}</h3>
          <p class="mt-1 text-xs leading-snug text-theme-text-muted">
            {{ t('endpoints.enrollment.description') }}
          </p>
        </div>
        <button
          type="button"
          class="rounded border border-theme-border p-2 text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text"
          :title="t('common.close')"
          @click="emit('close')"
        >
          <X :size="16" />
        </button>
      </header>

      <form data-test="agent-enrollment-form" class="space-y-4 p-4" @submit.prevent="submit">
        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">
            {{ t('endpoints.enrollment.displayName') }}
          </span>
          <input
            v-model="displayName"
            name="displayName"
            type="text"
            class="mt-1 w-full rounded border border-theme-border bg-theme-bg px-3 py-2 text-sm text-theme-text outline-none focus:border-theme-primary"
            :placeholder="t('endpoints.enrollment.displayNamePlaceholder')"
          />
        </label>

        <label class="block">
          <span class="text-xs font-semibold uppercase tracking-wider text-theme-text-muted">
            {{ t('endpoints.enrollment.hostnameHint') }}
          </span>
          <input
            v-model="hostnameHint"
            name="hostnameHint"
            type="text"
            class="mt-1 w-full rounded border border-theme-border bg-theme-bg px-3 py-2 text-sm text-theme-text outline-none focus:border-theme-primary"
            :placeholder="t('endpoints.enrollment.hostnameHintPlaceholder')"
          />
        </label>

        <div v-if="error" class="rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
          {{ error }}
        </div>

        <button
          type="submit"
          class="inline-flex items-center gap-2 rounded border border-theme-primary bg-theme-primary px-3 py-2 text-sm font-semibold text-white transition-opacity disabled:cursor-wait disabled:opacity-70"
          :disabled="!canSubmit"
        >
          <Loader2 v-if="isCreating" :size="15" class="animate-spin" />
          {{ t('endpoints.enrollment.generate') }}
        </button>

        <section v-if="enrollmentToken" class="space-y-2">
          <div class="rounded border border-yellow-400/40 bg-yellow-400/10 p-2 text-xs leading-snug text-yellow-100">
            {{ t('endpoints.enrollment.oneTimeWarning') }}
          </div>
          <div class="rounded border border-theme-border bg-theme-bg p-3">
            <div
              data-test="agent-enrollment-token"
              class="break-all font-mono text-lg font-semibold leading-snug text-theme-text"
            >
              {{ enrollmentToken }}
            </div>
            <div class="flex justify-end border-t border-theme-border p-2">
              <button
                type="button"
                data-test="copy-agent-token"
                class="inline-flex items-center gap-2 rounded border border-theme-border px-3 py-1.5 text-xs font-semibold text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text"
                @click="copyEnrollmentToken"
              >
                <Copy :size="14" />
                {{ t('endpoints.enrollment.copy') }}
              </button>
            </div>
          </div>
        </section>
      </form>
    </div>
  </div>
</template>
