<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertCircle,
  CheckCircle2,
  CircleDashed,
  Clock,
  ListChecks,
  RefreshCw,
  ShieldAlert,
} from 'lucide-vue-next'
import type { AuditEvent } from '../../services/auditClient'
import { formatAuditEvent } from './auditFormat'

const props = withDefaults(defineProps<{
  events: AuditEvent[]
  isLoading?: boolean
  error?: string | null
}>(), {
  isLoading: false,
  error: null,
})

const emit = defineEmits<{
  refresh: []
}>()

const formattedEvents = computed(() => props.events.map(formatAuditEvent))

function toneClasses(tone: string) {
  if (tone === 'success') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
  if (tone === 'failed') return 'border-red-500/30 bg-red-500/10 text-red-200'
  if (tone === 'warning') return 'border-amber-500/30 bg-amber-500/10 text-amber-200'
  return 'border-theme-border bg-theme-neutral text-theme-text-muted'
}
</script>

<template>
  <section class="flex h-full min-h-[320px] flex-col overflow-hidden rounded-lg border border-theme-border bg-theme-panel text-theme-text shadow-2xl">
    <header class="flex items-center justify-between border-b border-theme-border px-4 py-3">
      <div class="flex min-w-0 items-center gap-3">
        <div class="flex size-9 shrink-0 items-center justify-center rounded-md border border-theme-border bg-theme-neutral text-theme-primary">
          <ShieldAlert :size="18" />
        </div>
        <div class="min-w-0">
          <h2 class="truncate text-sm font-semibold">Audit trail</h2>
          <p class="truncate text-xs text-theme-text-muted">Sensitive SOC activity</p>
        </div>
      </div>
      <button
        type="button"
        class="flex size-8 items-center justify-center rounded-md border border-theme-border text-theme-text-muted transition hover:border-theme-primary hover:text-theme-text"
        aria-label="Refresh audit trail"
        @click="emit('refresh')"
      >
        <RefreshCw :size="16" />
      </button>
    </header>

    <div v-if="isLoading" class="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center text-theme-text-muted">
      <Clock :size="22" class="animate-pulse text-theme-primary" />
      <p class="text-sm font-medium text-theme-text">Loading audit trail</p>
    </div>

    <div v-else-if="error" class="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      <AlertCircle :size="24" class="text-red-300" />
      <p class="text-sm font-semibold text-theme-text">Unable to load audit trail</p>
      <p class="max-w-[28rem] text-xs text-theme-text-muted">{{ error }}</p>
    </div>

    <div v-else-if="formattedEvents.length === 0" class="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
      <ListChecks :size="24" class="text-theme-primary" />
      <p class="text-sm font-semibold text-theme-text">No sensitive activity recorded</p>
      <p class="max-w-[28rem] text-xs text-theme-text-muted">Events appear here after authentication, integration, workspace, or administrative actions.</p>
    </div>

    <ol v-else class="min-h-0 flex-1 overflow-y-auto px-4 py-3">
      <li
        v-for="event in formattedEvents"
        :key="event.id"
        class="grid grid-cols-[1.5rem_1fr] gap-3 border-b border-theme-border/70 py-3 last:border-b-0"
      >
        <div class="mt-1 flex size-6 items-center justify-center rounded-full border" :class="toneClasses(event.outcomeTone)">
          <CheckCircle2 v-if="event.outcomeTone === 'success'" :size="14" />
          <AlertCircle v-else-if="event.outcomeTone === 'failed'" :size="14" />
          <Clock v-else-if="event.outcomeTone === 'warning'" :size="14" />
          <CircleDashed v-else :size="14" />
        </div>

        <article class="min-w-0">
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 class="text-sm font-semibold text-theme-text">{{ event.title }}</h3>
            <span class="rounded border px-1.5 py-0.5 text-[11px] capitalize leading-none" :class="toneClasses(event.outcomeTone)">
              {{ event.outcomeLabel }}
            </span>
          </div>

          <p class="mt-1 text-xs text-theme-text-muted">
            {{ event.actorLabel }} · {{ event.createdAtLabel }} · {{ event.ipAddressLabel }}
          </p>
          <p class="mt-1 truncate text-[11px] text-theme-text-muted">{{ event.userAgentLabel }}</p>

          <dl v-if="event.detailRows.length" class="mt-3 grid gap-1 rounded-md border border-theme-border bg-theme-neutral/70 p-2 text-xs">
            <div
              v-for="[key, value] in event.detailRows"
              :key="key"
              class="grid grid-cols-[minmax(7rem,0.45fr)_1fr] gap-2"
            >
              <dt class="truncate text-theme-text-muted">{{ key }}</dt>
              <dd class="break-words font-mono text-[11px] text-theme-text">{{ value }}</dd>
            </div>
          </dl>
        </article>
      </li>
    </ol>
  </section>
</template>
