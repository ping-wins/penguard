<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { Activity, Clock, Cpu, Network, RefreshCw, Server, Shield, User } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useEndpointsStore } from '../../stores/useEndpointsStore'
import type { EndpointTimelineItem } from '../../services/endpointsClient'

const { t } = useI18n()
const store = useEndpointsStore()

onMounted(() => store.startPolling(10000))
onBeforeUnmount(() => store.stopPolling())

const selectedIps = computed(() => store.selectedEndpoint?.ipAddresses ?? [])

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
      <button
        type="button"
        class="rounded border border-theme-border p-2 text-theme-text-muted transition-colors hover:bg-theme-border hover:text-theme-text disabled:opacity-50"
        :disabled="store.isLoading"
        :title="t('common.refresh')"
        @click="store.refresh()"
      >
        <RefreshCw :size="16" />
      </button>
    </header>

    <div v-if="store.error" class="mb-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-300">
      {{ store.error }}
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
          <div v-if="store.isLoading && store.endpoints.length === 0" class="p-3 text-sm text-theme-text-muted">
            {{ t('common.loading') }}
          </div>
          <div v-else-if="store.endpoints.length === 0" class="p-3 text-sm text-theme-text-muted">
            {{ t('endpoints.empty') }}
          </div>
          <template v-else>
            <button
              v-for="endpoint in store.endpoints"
              :key="endpoint.id"
              type="button"
              class="mb-2 w-full rounded border px-3 py-2 text-left transition-colors"
              :class="store.selectedEndpointId === endpoint.id ? 'border-theme-primary bg-theme-primary/10' : 'border-theme-border bg-theme-panel hover:bg-theme-border/40'"
              @click="store.selectEndpoint(endpoint.id)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="truncate text-sm font-semibold text-theme-text">{{ endpoint.hostname || endpoint.id }}</span>
                <span class="rounded border border-theme-border px-2 py-0.5 text-[10px] uppercase text-theme-text-muted">
                  {{ endpoint.health }}
                </span>
              </div>
              <div class="mt-1 truncate font-mono text-xs text-theme-text-muted">
                {{ endpoint.ipAddresses[0] || endpoint.id }}
              </div>
            </button>
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
                v-for="ip in selectedIps.slice(0, 6)"
                :key="ip"
                class="rounded border border-theme-border bg-theme-panel px-2 py-0.5 font-mono text-[10px] text-theme-text-muted"
              >
                {{ ip }}
              </span>
            </div>
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto p-3">
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
  </section>
</template>
