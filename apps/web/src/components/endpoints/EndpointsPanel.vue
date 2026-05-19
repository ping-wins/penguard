<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Activity, Clock, Cpu, Network, Plus, RefreshCw, Server, Shield, Trash2, User } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useEndpointsStore } from '../../stores/useEndpointsStore'
import type { Endpoint, EndpointTimelineItem } from '../../services/endpointsClient'
import { sourceBadgeFor, type SourceBadge } from '../../utils/sourceBadges'
import AgentEnrollmentModal from './AgentEnrollmentModal.vue'

const { t } = useI18n()
const store = useEndpointsStore()
const isEnrollmentModalOpen = ref(false)
const enrollmentToken = ref<string | null>(null)
const enrollmentError = ref<string | null>(null)
const isCreatingEnrollment = ref(false)
const endpointDeleteError = ref<string | null>(null)
const deletingEndpointId = ref<string | null>(null)

onMounted(() => store.refresh())

const selectedObservedSourceIp = computed(() => observedSourceIp(store.selectedEndpoint))
const selectedReportedIps = computed(() => reportedIps(store.selectedEndpoint))

function observedSourceIp(endpoint: Endpoint | null | undefined) {
  const value = endpoint?.attributes?.observedSourceIp
  return typeof value === 'string' && value.length > 0 ? value : null
}

function reportedIps(endpoint: Endpoint | null | undefined) {
  const observed = observedSourceIp(endpoint)
  return endpoint?.ipAddresses.filter((ip) => ip !== observed) ?? []
}

function primaryIp(endpoint: Endpoint) {
  return observedSourceIp(endpoint) || endpoint.ipAddresses[0] || endpoint.id
}

function formatDate(value: string | null | undefined) {
  if (!value) return '--'
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'short',
    timeStyle: 'medium',
  }).format(new Date(value))
}

function plural(count: number, singular: string, pluralLabel: string) {
  return count === 1 ? `1 ${singular}` : `${count} ${pluralLabel}`
}

function connectionLabel(connection: Record<string, any>) {
  const local = addressLabel(connection.localAddress)
  const remote = addressLabel(connection.remoteAddress)
  const route = remote ? `${local} -> ${remote}` : local
  const pid = connection.pid !== null && connection.pid !== undefined ? ` · pid ${connection.pid}` : ''
  const status = connection.status ? ` · ${connection.status}` : ''
  return `${route}${status}${pid}`
}

function addressLabel(address: any) {
  if (!address) return 'local'
  const ip = address.ip ?? '0.0.0.0'
  return address.port !== null && address.port !== undefined ? `${ip}:${address.port}` : ip
}

function timelineSummary(item: EndpointTimelineItem) {
  if (item.eventType === 'connection.snapshot') {
    const connections = Array.isArray(item.attributes.connections) ? item.attributes.connections : []
    const first = connections[0] ? connectionLabel(connections[0]) : t('endpoints.timeline.noConnections')
    return `${plural(connections.length, t('endpoints.timeline.connection'), t('endpoints.timeline.connections'))} · ${first}`
  }
  if (item.eventType === 'process.snapshot') {
    const processes = Array.isArray(item.attributes.processes) ? item.attributes.processes : []
    const first = processes[0]?.name ? ` · ${processes[0].name}` : ''
    return `${plural(processes.length, t('endpoints.timeline.process'), t('endpoints.timeline.processes'))}${first}`
  }
  if (item.eventType.startsWith('auth.')) {
    const username = item.attributes.username || item.currentUser || t('endpoints.timeline.unknownUser')
    return `${username}`
  }
  return item.title
}

function sourceBadgeClass(badge: SourceBadge) {
  if (badge.tone === 'demo') return 'border-yellow-400/40 bg-yellow-400/10 text-yellow-200'
  if (badge.tone === 'simulator') return 'border-sky-400/40 bg-sky-400/10 text-sky-200'
  if (badge.tone === 'ai') return 'border-purple-400/40 bg-purple-400/10 text-purple-200'
  return 'border-emerald-400/40 bg-emerald-400/10 text-emerald-200'
}

function openEnrollmentModal() {
  enrollmentError.value = null
  enrollmentToken.value = null
  isEnrollmentModalOpen.value = true
}

async function submitEnrollment(payload: { displayName?: string; hostnameHint?: string }) {
  isCreatingEnrollment.value = true
  enrollmentError.value = null
  try {
    const enrollment = await store.createEnrollment(payload)
    const pending = store.pendingEnrollments.find((item) => item.enrollmentId === enrollment.id)
    enrollmentToken.value = pending?.enrollmentToken ?? null
    store.forgetEnrollmentToken(enrollment.id)
  } catch (e: any) {
    enrollmentError.value = e?.message ?? t('endpoints.enrollment.error')
  } finally {
    isCreatingEnrollment.value = false
  }
}

async function copyEnrollmentToken(token: string) {
  const clipboard = typeof navigator !== 'undefined' ? navigator.clipboard : undefined
  if (!clipboard?.writeText) return
  await clipboard.writeText(token).catch(() => undefined)
}

function dismissPendingEnrollment(enrollmentId: string) {
  store.dismissPendingEnrollment(enrollmentId)
}

async function deleteEndpointFromPanel(endpoint: Endpoint) {
  const label = endpoint.hostname || endpoint.id
  const confirmDelete = typeof confirm === 'function'
    ? confirm(t('endpoints.removeConfirm', { label }))
    : true
  if (!confirmDelete) return
  deletingEndpointId.value = endpoint.id
  endpointDeleteError.value = null
  try {
    await store.removeEndpoint(endpoint.id)
  } catch (e: any) {
    endpointDeleteError.value = e?.message ?? t('endpoints.removeError')
  } finally {
    deletingEndpointId.value = null
  }
}
</script>

<template>
  <section class="flex h-full w-[480px] flex-col p-4">
    <header class="mb-4 flex items-start justify-between gap-3">
      <div>
        <h2 class="text-lg font-bold text-theme-text">{{ t('endpoints.title') }}</h2>
        <p class="mt-1 text-xs leading-snug text-theme-text-muted">
          {{ t('endpoints.subtitle') }}
        </p>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <button
          type="button"
          data-test="add-windows-agent"
          class="inline-flex items-center gap-2 rounded border border-theme-primary bg-theme-primary px-3 py-2 text-xs font-semibold text-white transition-opacity hover:opacity-90"
          @click="openEnrollmentModal"
        >
          <Plus :size="15" />
          {{ t('endpoints.enrollment.addWindowsAgent') }}
        </button>
        <button
          type="button"
          class="rounded border border-theme-border p-2 text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text disabled:opacity-50"
          :disabled="store.isLoading"
          :title="t('common.refresh')"
          @click="store.refresh()"
        >
          <RefreshCw :size="16" />
        </button>
      </div>
    </header>

    <div v-if="store.error || endpointDeleteError" class="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
      {{ store.error || endpointDeleteError }}
    </div>

    <div class="grid min-h-0 flex-1 grid-rows-[minmax(120px,190px)_1fr] gap-3">
      <section class="min-h-0 rounded-lg border border-theme-border bg-theme-bg/60">
        <div class="flex items-center justify-between border-b border-theme-border px-3 py-2">
          <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-theme-text-muted">
            <Server :size="14" />
            {{ t('endpoints.inventory') }}
          </div>
          <span class="text-[10px] text-theme-text-muted">
            {{ store.endpoints.length }} {{ t('endpoints.endpointsLabel') }}
          </span>
        </div>

        <div class="h-[138px] overflow-y-auto p-2">
          <div v-if="store.pendingEnrollments.length > 0" class="mb-2 space-y-2">
            <article
              v-for="pending in store.pendingEnrollments"
              :key="pending.enrollmentId"
              data-test="pending-endpoint"
              class="rounded border border-yellow-400/40 bg-yellow-400/10 p-2"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="truncate text-sm font-semibold text-theme-text">{{ pending.displayName }}</div>
                  <div v-if="pending.hostnameHint" class="mt-1 truncate font-mono text-[11px] text-theme-text-muted">
                    {{ pending.hostnameHint }}
                  </div>
                </div>
                <span class="rounded border border-yellow-400/40 px-2 py-0.5 text-[10px] uppercase text-yellow-100">
                  {{ t('endpoints.enrollment.pending') }}
                </span>
                <button
                  type="button"
                  data-test="dismiss-pending-endpoint"
                  class="rounded border border-yellow-400/40 p-1 text-yellow-100 transition-colors hover:bg-yellow-400/20"
                  :title="t('endpoints.enrollment.dismissPending')"
                  @click="dismissPendingEnrollment(pending.enrollmentId)"
                >
                  <Trash2 :size="13" />
                </button>
              </div>
              <p class="mt-2 text-xs text-yellow-100">
                {{ t('endpoints.enrollment.waitingForHeartbeat') }}
              </p>
            </article>
          </div>
          <div v-if="store.isLoading && store.endpoints.length === 0" class="p-3 text-sm text-theme-text-muted">
            {{ t('common.loading') }}
          </div>
          <div v-else-if="store.endpoints.length === 0" class="p-3 text-sm text-theme-text-muted">
            {{ t('endpoints.empty') }}
          </div>
          <template v-else>
            <div
              v-for="endpoint in store.endpoints"
              :key="endpoint.id"
              :data-test="`endpoint-row-${endpoint.id}`"
              class="mb-2 w-full rounded border px-3 py-2 text-left transition-colors"
              :class="store.selectedEndpointId === endpoint.id ? 'border-theme-primary bg-theme-primary/10' : 'border-theme-border bg-theme-panel hover:bg-theme-border/40'"
            >
              <div class="flex items-start gap-2">
                <button
                  type="button"
                  class="min-w-0 flex-1 text-left"
                  @click="store.selectEndpoint(endpoint.id)"
                >
                  <div class="flex items-center justify-between gap-2">
                    <span class="truncate text-sm font-semibold text-theme-text">{{ endpoint.hostname || endpoint.id }}</span>
                    <span class="rounded border border-theme-border px-2 py-0.5 text-[10px] uppercase text-theme-text-muted">
                      {{ endpoint.health }}
                    </span>
                  </div>
                  <div class="mt-1 truncate font-mono text-xs text-theme-text-muted">
                    {{ primaryIp(endpoint) }}
                  </div>
                  <div
                    v-if="observedSourceIp(endpoint)"
                    class="mt-1 text-[10px] font-semibold uppercase tracking-wider text-theme-primary"
                  >
                    {{ t('endpoints.observedViaApi') }}
                  </div>
                </button>
                <button
                  type="button"
                  :data-test="`delete-endpoint-${endpoint.id}`"
                  class="mt-0.5 rounded border border-theme-border p-1.5 text-theme-text-muted transition-colors hover:border-red-400/50 hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
                  :disabled="deletingEndpointId === endpoint.id"
                  :title="t('endpoints.remove')"
                  @click="deleteEndpointFromPanel(endpoint)"
                >
                  <Trash2 :size="14" />
                </button>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section class="min-h-0 overflow-hidden rounded-lg border border-theme-border bg-theme-bg/60">
        <div v-if="!store.selectedEndpoint" class="flex h-full items-center justify-center p-6 text-center text-sm text-theme-text-muted">
          {{ t('endpoints.selectHint') }}
        </div>
        <div v-else class="flex h-full min-h-0 flex-col">
          <div class="border-b border-theme-border p-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="truncate text-base font-bold text-theme-text">
                  {{ store.selectedEndpoint.hostname || store.selectedEndpoint.id }}
                </div>
                <div class="mt-1 truncate text-xs text-theme-text-muted">
                  {{ store.selectedEndpoint.id }}
                </div>
              </div>
              <span class="rounded border border-theme-border px-2 py-1 text-xs uppercase text-theme-text-muted">
                {{ store.selectedEndpoint.health }}
              </span>
            </div>

            <div class="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div class="rounded border border-theme-border bg-theme-panel p-2">
                <div class="flex items-center gap-1 text-theme-text-muted">
                  <Clock :size="13" />
                  {{ t('endpoints.lastSeen') }}
                </div>
                <div class="mt-1 text-theme-text">{{ formatDate(store.selectedEndpoint.lastSeenAt) }}</div>
              </div>
              <div class="rounded border border-theme-border bg-theme-panel p-2">
                <div class="flex items-center gap-1 text-theme-text-muted">
                  <User :size="13" />
                  {{ t('endpoints.user') }}
                </div>
                <div class="mt-1 truncate text-theme-text">{{ store.selectedEndpoint.currentUser || '--' }}</div>
              </div>
              <div class="rounded border border-theme-border bg-theme-panel p-2">
                <div class="flex items-center gap-1 text-theme-text-muted">
                  <Network :size="13" />
                  {{ t('endpoints.connections') }}
                </div>
                <div class="mt-1 text-theme-text">{{ store.latestConnectionCount }}</div>
              </div>
              <div class="rounded border border-theme-border bg-theme-panel p-2">
                <div class="flex items-center gap-1 text-theme-text-muted">
                  <Cpu :size="13" />
                  {{ t('endpoints.processes') }}
                </div>
                <div class="mt-1 text-theme-text">{{ store.latestProcessCount }}</div>
              </div>
            </div>

            <div class="mt-3 flex flex-wrap gap-1">
              <span
                v-if="selectedObservedSourceIp"
                class="rounded border border-theme-primary/40 bg-theme-primary/10 px-2 py-0.5 font-mono text-[10px] text-theme-primary"
              >
                {{ t('endpoints.observedViaApi') }} {{ selectedObservedSourceIp }}
              </span>
              <span
                v-for="ip in selectedReportedIps.slice(0, 6)"
                :key="ip"
                class="rounded border border-theme-border bg-theme-panel px-2 py-0.5 font-mono text-[10px] text-theme-text-muted"
              >
                {{ ip }}
              </span>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto p-3">
            <section class="mb-3 rounded border border-theme-border bg-theme-panel p-3">
              <div class="mb-2 flex items-center justify-between gap-2">
                <div class="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-theme-text-muted">
                  <Shield :size="14" />
                  {{ t('endpoints.related.title') }}
                </div>
                <span class="text-[10px] text-theme-text-muted">
                  {{ store.relatedIncidents.length }}
                </span>
              </div>

              <div v-if="store.isLoadingRelatedIncidents" class="text-xs text-theme-text-muted">
                {{ t('common.loading') }}
              </div>
              <div v-else-if="store.relatedIncidentsError" class="text-xs text-red-300">
                {{ store.relatedIncidentsError }}
              </div>
              <div v-else-if="store.relatedIncidents.length === 0" class="text-xs text-theme-text-muted">
                {{ t('endpoints.related.empty') }}
              </div>
              <div v-else class="space-y-2">
                <article
                  v-for="incident in store.relatedIncidents.slice(0, 5)"
                  :key="incident.id"
                  class="rounded border border-theme-border/80 bg-theme-bg/60 p-2"
                >
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div class="truncate text-xs font-semibold text-theme-text">
                        {{ incident.title }}
                      </div>
                      <div class="mt-1 flex flex-wrap gap-1">
                        <span class="rounded border border-theme-border px-1.5 py-0.5 text-[10px] uppercase text-theme-text-muted">
                          {{ incident.severity }}
                        </span>
                        <span
                          v-if="incident.triageLevel"
                          class="rounded border border-theme-border px-1.5 py-0.5 text-[10px] uppercase text-theme-text-muted"
                        >
                          {{ incident.triageLevel }}
                        </span>
                        <span
                          v-if="incident.ticketStatus"
                          class="rounded border border-theme-border px-1.5 py-0.5 text-[10px] uppercase text-theme-text-muted"
                        >
                          {{ incident.ticketStatus }}
                        </span>
                        <span
                          v-if="sourceBadgeFor(incident)"
                          class="rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase"
                          :class="sourceBadgeClass(sourceBadgeFor(incident)!)"
                        >
                          {{ t(sourceBadgeFor(incident)!.labelKey) }}
                        </span>
                      </div>
                    </div>
                  </div>
                </article>
              </div>
            </section>

            <div class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-theme-text-muted">
              <Activity :size="14" />
              {{ t('endpoints.timeline.title') }}
            </div>
            <div v-if="store.isLoadingTimeline" class="rounded border border-theme-border p-3 text-sm text-theme-text-muted">
              {{ t('common.loading') }}
            </div>
            <div v-else-if="store.timeline.length === 0" class="rounded border border-dashed border-theme-border p-3 text-sm text-theme-text-muted">
              {{ t('endpoints.timeline.empty') }}
            </div>
            <div v-else class="space-y-2">
              <article
                v-for="item in store.timeline"
                :key="item.id"
                class="rounded border border-theme-border bg-theme-panel p-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <Shield :size="14" class="text-theme-primary" />
                      <span class="truncate text-sm font-semibold text-theme-text">{{ item.title }}</span>
                    </div>
                    <p class="mt-1 break-words text-xs text-theme-text-muted">
                      {{ timelineSummary(item) }}
                    </p>
                  </div>
                  <time class="shrink-0 text-[10px] text-theme-text-muted">
                    {{ formatDate(item.occurredAt) }}
                  </time>
                </div>
              </article>
            </div>
          </div>
        </div>
      </section>
    </div>

    <AgentEnrollmentModal
      :open="isEnrollmentModalOpen"
      :enrollment-token="enrollmentToken"
      :is-creating="isCreatingEnrollment"
      :error="enrollmentError"
      @close="isEnrollmentModalOpen = false"
      @submit="submitEnrollment"
      @copy="copyEnrollmentToken"
    />
  </section>
</template>
