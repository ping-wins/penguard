<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, Boxes, ChevronRight, Plug, RefreshCcw, Search, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useMarketplaceStore } from '../../stores/useMarketplaceStore'
import type { AddonManifest } from '../../services/marketplaceClient'

const { t } = useI18n()
const emit = defineEmits<{ install: [addon: AddonManifest] }>()

const store = useMarketplaceStore()
const search = ref('')
const selected = ref<AddonManifest | null>(null)

const filtered = computed<AddonManifest[]>(() => {
  const term = search.value.trim().toLowerCase()
  if (!term) return store.addons
  return store.addons.filter((addon) => {
    return (
      addon.name.toLowerCase().includes(term)
      || addon.vendor.toLowerCase().includes(term)
      || addon.category.toLowerCase().includes(term)
      || addon.description.toLowerCase().includes(term)
    )
  })
})

function addonVersion(addon: AddonManifest) {
  return addon.version ?? addon.latestVersion ?? addon.versions?.[0] ?? ''
}

function addonRoutes(addon: AddonManifest) {
  return addon.routes ?? []
}

function addonWidgets(addon: AddonManifest) {
  return addon.widgets ?? []
}

function addonSiemEventTypes(addon: AddonManifest) {
  return addon.siemEventTypes ?? []
}

function addonAuthFields(addon: AddonManifest) {
  return addon.provider?.auth?.fields ?? []
}

async function installAddon(addon: AddonManifest) {
  try {
    await store.install(addon)
    emit('install', addon)
  } catch {
    // store.error already set; swallow to keep UI responsive
  }
}

onMounted(() => {
  if (!store.hasLoadedOnce) store.refresh()
})
</script>

<template>
  <div class="flex h-full flex-col w-full">
    <div class="px-4 pt-4 pb-3 border-b border-theme-border flex items-center justify-between">
      <div>
        <h2 class="font-bold text-lg text-theme-text flex items-center gap-2">
          <Boxes :size="18" />
          {{ t('marketplace.title') }}
        </h2>
        <p class="text-xs text-theme-text-muted mt-1">{{ t('marketplace.subtitle') }}</p>
      </div>
      <button
        type="button"
        class="text-theme-text-muted hover:text-theme-text disabled:opacity-50"
        :disabled="store.isLoading"
        :title="t('marketplace.refreshTooltip')"
        @click="store.refresh()"
      >
        <RefreshCcw :size="16" :class="store.isLoading ? 'animate-spin' : ''" />
      </button>
    </div>

    <div class="px-4 py-2 border-b border-theme-border bg-theme-bg/30 flex items-center gap-2">
      <Search :size="14" class="text-theme-text-muted shrink-0" />
      <input
        v-model="search"
        type="search"
        :placeholder="t('marketplace.searchPlaceholder')"
        class="w-full bg-theme-bg/60 border border-theme-border rounded px-2 py-1 text-xs text-theme-text placeholder:text-theme-text-muted/70 focus:outline-none focus:border-theme-primary/60"
      />
    </div>

    <div
      v-if="store.error"
      class="px-4 py-2 text-xs border-b border-red-500/30 bg-red-500/10 text-red-300 flex items-start gap-2"
    >
      <AlertCircle :size="14" class="mt-0.5 shrink-0" />
      <span>{{ store.error }}</span>
    </div>

    <div class="flex-1 overflow-y-auto">
      <div
        v-if="store.isLoading && filtered.length === 0"
        class="p-4 text-xs text-theme-text-muted"
      >{{ t('marketplace.loading') }}</div>
      <div
        v-else-if="filtered.length === 0"
        class="p-4 text-xs italic text-theme-text-muted"
      >{{ store.addons.length === 0 ? t('marketplace.empty') : t('marketplace.noMatches') }}</div>
      <ul v-else class="flex flex-col gap-2 p-3">
        <li
          v-for="addon in filtered"
          :key="addon.id"
          class="rounded-lg border border-theme-border bg-theme-bg/40 p-3 hover:border-theme-primary/40 transition-colors"
        >
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span class="text-sm font-semibold text-theme-text truncate">{{ addon.name }}</span>
                <span class="rounded border border-theme-border/70 bg-theme-text/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-theme-text-muted">{{ addon.category }}</span>
                <span class="text-[10px] font-mono text-theme-text-muted">v{{ addonVersion(addon) }}</span>
                <span
                  v-if="addon.installed"
                  class="rounded border border-emerald-400/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] uppercase text-emerald-200"
                >{{ t('marketplace.installed') }}</span>
              </div>
              <p class="text-[11px] text-theme-text-muted mt-0.5">{{ addon.vendor }}</p>
              <p class="text-xs text-theme-text mt-1 line-clamp-2">{{ addon.description }}</p>
              <div class="mt-2 flex flex-wrap gap-1 text-[10px] text-theme-text-muted">
                <span>{{ t('marketplace.routesLabel', { count: addonRoutes(addon).length }) }}</span>
                <span>·</span>
                <span>{{ t('marketplace.widgetsLabel', { count: addonWidgets(addon).length }) }}</span>
                <span v-if="addonSiemEventTypes(addon).length">·</span>
                <span v-if="addonSiemEventTypes(addon).length">{{ t('marketplace.siemLabel', { count: addonSiemEventTypes(addon).length }) }}</span>
              </div>
            </div>
            <div class="flex shrink-0 flex-col gap-1">
              <button
                type="button"
                class="flex items-center gap-1 rounded border border-theme-primary/40 bg-theme-primary/10 px-2 py-1 text-xs font-medium text-theme-primary hover:bg-theme-primary/20 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="addon.installed || store.installingId === addon.id || !addonVersion(addon)"
                @click="installAddon(addon)"
              >
                <Plug :size="12" />
                {{ addon.installed ? t('marketplace.installed') : t('marketplace.install') }}
              </button>
              <button
                type="button"
                class="flex items-center justify-center gap-1 rounded border border-theme-border bg-theme-bg/40 px-2 py-1 text-[11px] text-theme-text-muted hover:text-theme-text"
                @click="selected = addon"
              >
                {{ t('marketplace.details') }}
                <ChevronRight :size="12" />
              </button>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <Teleport to="body">
      <div
        v-if="selected"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
        @click.self="selected = null"
      >
        <div class="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-theme-border bg-theme-panel shadow-xl">
          <header class="flex items-start justify-between gap-3 border-b border-theme-border px-4 py-3">
            <div class="min-w-0">
              <h3 class="truncate text-base font-semibold text-theme-text">{{ selected.name }}</h3>
              <p class="text-[11px] text-theme-text-muted">{{ selected.vendor }} · {{ selected.category }} · v{{ addonVersion(selected) }}</p>
            </div>
            <button
              type="button"
              class="rounded p-1 text-theme-text-muted hover:bg-theme-border hover:text-theme-text"
              :aria-label="t('marketplace.close')"
              @click="selected = null"
            >
              <X :size="16" />
            </button>
          </header>
          <div class="px-4 py-3 text-sm text-theme-text space-y-3">
            <p>{{ selected.description }}</p>
            <section v-if="addonAuthFields(selected).length">
              <h4 class="text-[10px] uppercase tracking-wide text-theme-text-muted mb-1">{{ t('marketplace.authHeader') }}</h4>
              <ul class="text-xs flex flex-col gap-1">
                <li
                  v-for="field in addonAuthFields(selected)"
                  :key="field.id"
                  class="rounded border border-theme-border bg-theme-bg/50 px-2 py-1"
                >
                  <span class="font-mono text-theme-primary">{{ field.id }}</span>
                  <span class="text-theme-text-muted"> — {{ field.label }} ({{ field.type }}{{ field.required ? '*' : '' }})</span>
                </li>
              </ul>
            </section>
            <section v-if="addonRoutes(selected).length">
              <h4 class="text-[10px] uppercase tracking-wide text-theme-text-muted mb-1">{{ t('marketplace.routesHeader') }}</h4>
              <ul class="text-xs font-mono space-y-1">
                <li
                  v-for="route in addonRoutes(selected)"
                  :key="route.id"
                  class="rounded border border-theme-border bg-theme-bg/50 px-2 py-1"
                >
                  <span class="text-theme-primary">{{ route.method }}</span>
                  <span class="text-theme-text"> {{ route.path }}</span>
                  <div v-if="route.summary" class="text-[11px] font-sans text-theme-text-muted">{{ route.summary }}</div>
                </li>
              </ul>
            </section>
            <section v-if="addonWidgets(selected).length">
              <h4 class="text-[10px] uppercase tracking-wide text-theme-text-muted mb-1">{{ t('marketplace.widgetsHeader') }}</h4>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="widget in addonWidgets(selected)"
                  :key="widget"
                  class="rounded border border-theme-border bg-theme-bg/50 px-2 py-0.5 text-[11px] font-mono text-theme-text"
                >{{ widget }}</span>
              </div>
            </section>
            <section v-if="addonSiemEventTypes(selected).length">
              <h4 class="text-[10px] uppercase tracking-wide text-theme-text-muted mb-1">{{ t('marketplace.siemHeader') }}</h4>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="evt in addonSiemEventTypes(selected)"
                  :key="evt"
                  class="rounded border border-theme-border bg-theme-bg/50 px-2 py-0.5 text-[11px] font-mono text-theme-text"
                >{{ evt }}</span>
              </div>
            </section>
          </div>
          <footer class="flex justify-end gap-2 border-t border-theme-border px-4 py-3">
            <button
              type="button"
              class="rounded border border-theme-border bg-theme-bg/40 px-3 py-1 text-xs text-theme-text-muted hover:text-theme-text"
              @click="selected = null"
            >{{ t('marketplace.close') }}</button>
            <button
              type="button"
              class="flex items-center gap-1 rounded border border-theme-primary/40 bg-theme-primary/10 px-3 py-1 text-xs font-medium text-theme-primary hover:bg-theme-primary/20 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="selected.installed || store.installingId === selected.id || !addonVersion(selected)"
              @click="installAddon(selected); selected = null"
            >
              <Plug :size="12" />
              {{ selected.installed ? t('marketplace.installed') : t('marketplace.install') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>
