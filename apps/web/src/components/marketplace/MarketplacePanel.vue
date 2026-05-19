<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { AlertCircle, Boxes, ChevronRight, Plug, RefreshCcw, Search, Trash2, X } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useMarketplaceStore } from '../../stores/useMarketplaceStore'
import type { AddonManifest } from '../../services/marketplaceClient'
import {
  localizedAddonSearchText,
  localizeAddonAuthField,
  localizeAddonCategory,
  localizeAddonDescription,
  localizeAddonFieldType,
  localizeAddonName,
  localizeAddonRoute,
  localizeAddonSiemEventType,
  localizeAddonWidget,
  localizeMarketplaceError,
} from '../../lib/marketplaceI18n'

const { t, te } = useI18n()
const emit = defineEmits<{
  install: [addon: AddonManifest]
  uninstall: [addon: AddonManifest]
}>()

const store = useMarketplaceStore()
const search = ref('')
const selected = ref<AddonManifest | null>(null)

const filtered = computed<AddonManifest[]>(() => {
  const term = search.value.trim().toLowerCase()
  if (!term) return store.addons
  return store.addons.filter((addon) => {
    return localizedAddonSearchText(addon, translate, hasTranslation)
      .toLowerCase()
      .includes(term)
  })
})

function translate(key: string) {
  return t(key)
}

function hasTranslation(key: string) {
  return te(key)
}

function addonVersion(addon: AddonManifest) {
  return addon.version ?? addon.latestVersion ?? addon.versions?.[0] ?? ''
}

function addonName(addon: AddonManifest) {
  return localizeAddonName(addon, translate, hasTranslation)
}

function addonCategory(addon: AddonManifest) {
  return localizeAddonCategory(addon, translate, hasTranslation)
}

function addonDescription(addon: AddonManifest) {
  return localizeAddonDescription(addon, translate, hasTranslation)
}

function addonRoutes(addon: AddonManifest) {
  return (addon.routes ?? []).map(route => localizeAddonRoute(addon.id, route, translate, hasTranslation))
}

function addonWidgets(addon: AddonManifest) {
  return addon.widgets ?? []
}

function addonSiemEventTypes(addon: AddonManifest) {
  return addon.siemEventTypes ?? []
}

function addonAuthFields(addon: AddonManifest) {
  return (addon.provider?.auth?.fields ?? [])
    .map(field => localizeAddonAuthField(addon.id, field, translate, hasTranslation))
}

function addonFieldTypeLabel(fieldType: string) {
  return localizeAddonFieldType(fieldType, translate, hasTranslation)
}

function addonWidgetLabel(addon: AddonManifest, widgetId: string) {
  return localizeAddonWidget(addon.id, widgetId, translate, hasTranslation)
}

function addonSiemEventLabel(addon: AddonManifest, eventType: string) {
  return localizeAddonSiemEventType(addon.id, eventType, translate, hasTranslation)
}

function marketplaceErrorMessage(message: string) {
  return localizeMarketplaceError(message, translate, hasTranslation)
}

function isCurrentVersion(addon: AddonManifest) {
  const version = addonVersion(addon)
  return Boolean(addon.installed && version && addon.installedVersion === version)
}

async function installAddon(addon: AddonManifest) {
  try {
    await store.install(addon)
    emit('install', addon)
  } catch {
    // store.error already set; swallow to keep UI responsive
  }
}

async function uninstallAddon(addon: AddonManifest) {
  if (!addon.installed) return
  const confirmed = window.confirm(
    t('marketplace.uninstallConfirm', { name: addonName(addon) }),
  )
  if (!confirmed) return
  try {
    await store.uninstall(addon)
    if (selected.value?.id === addon.id) selected.value = null
    emit('uninstall', addon)
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
      <span>{{ marketplaceErrorMessage(store.error) }}</span>
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
                <span class="text-sm font-semibold text-theme-text truncate">{{ addonName(addon) }}</span>
                <span class="rounded border border-theme-border/70 bg-theme-text/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-theme-text-muted">{{ addonCategory(addon) }}</span>
                <span class="text-[10px] font-mono text-theme-text-muted">v{{ addonVersion(addon) }}</span>
                <span
                  v-if="addon.installed"
                  class="rounded border border-emerald-400/30 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] uppercase text-emerald-200"
                >{{ t('marketplace.installed') }}</span>
              </div>
              <p class="text-[11px] text-theme-text-muted mt-0.5">{{ addon.vendor }}</p>
              <p class="text-xs text-theme-text mt-1 line-clamp-2">{{ addonDescription(addon) }}</p>
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
                :data-test="`marketplace-install-${addon.id}`"
                class="flex items-center gap-1 rounded border border-theme-primary/40 bg-theme-primary/10 px-2 py-1 text-xs font-medium text-theme-primary hover:bg-theme-primary/20 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="isCurrentVersion(addon) || store.installingId === addon.id || !addonVersion(addon)"
                @click="installAddon(addon)"
              >
                <Plug :size="12" />
                {{ isCurrentVersion(addon) ? t('marketplace.installed') : t('marketplace.install') }}
              </button>
              <button
                v-if="addon.installed"
                type="button"
                :data-test="`marketplace-uninstall-${addon.id}`"
                class="flex items-center gap-1 rounded border border-red-400/40 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-300 hover:bg-red-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="store.uninstallingId === addon.id"
                @click="uninstallAddon(addon)"
              >
                <Trash2 :size="12" />
                {{ store.uninstallingId === addon.id ? t('marketplace.uninstalling') : t('marketplace.uninstall') }}
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
        class="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4"
        @click.self="selected = null"
      >
        <div class="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-theme-border bg-theme-panel shadow-xl">
          <header class="flex items-start justify-between gap-3 border-b border-theme-border px-4 py-3">
            <div class="min-w-0">
              <h3 class="truncate text-base font-semibold text-theme-text">{{ addonName(selected) }}</h3>
              <p class="text-[11px] text-theme-text-muted">{{ selected.vendor }} · {{ addonCategory(selected) }} · v{{ addonVersion(selected) }}</p>
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
            <p>{{ addonDescription(selected) }}</p>
            <section v-if="addonAuthFields(selected).length">
              <h4 class="text-[10px] uppercase tracking-wide text-theme-text-muted mb-1">{{ t('marketplace.authHeader') }}</h4>
              <ul class="text-xs flex flex-col gap-1">
                <li
                  v-for="field in addonAuthFields(selected)"
                  :key="field.id"
                  class="rounded border border-theme-border bg-theme-bg/50 px-2 py-1"
                >
                  <span class="font-mono text-theme-primary">{{ field.id }}</span>
                  <span class="text-theme-text-muted"> — {{ field.label }} ({{ addonFieldTypeLabel(field.type) }}{{ field.required ? `, ${t('marketplace.requiredField')}` : '' }})</span>
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
                  class="rounded border border-theme-border bg-theme-bg/50 px-2 py-0.5 text-[11px] text-theme-text"
                >{{ addonWidgetLabel(selected, widget) }}</span>
              </div>
            </section>
            <section v-if="addonSiemEventTypes(selected).length">
              <h4 class="text-[10px] uppercase tracking-wide text-theme-text-muted mb-1">{{ t('marketplace.siemHeader') }}</h4>
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="evt in addonSiemEventTypes(selected)"
                  :key="evt"
                  class="rounded border border-theme-border bg-theme-bg/50 px-2 py-0.5 text-[11px] text-theme-text"
                >{{ addonSiemEventLabel(selected, evt) }}</span>
              </div>
            </section>
          </div>
          <footer class="flex flex-wrap justify-end gap-2 border-t border-theme-border px-4 py-3">
            <button
              type="button"
              class="rounded border border-theme-border bg-theme-bg/40 px-3 py-1 text-xs text-theme-text-muted hover:text-theme-text"
              @click="selected = null"
            >{{ t('marketplace.close') }}</button>
            <button
              v-if="selected.installed"
              type="button"
              :data-test="`marketplace-detail-uninstall-${selected.id}`"
              class="flex items-center gap-1 rounded border border-red-400/40 bg-red-500/10 px-3 py-1 text-xs font-medium text-red-300 hover:bg-red-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="store.uninstallingId === selected.id"
              @click="uninstallAddon(selected)"
            >
              <Trash2 :size="12" />
              {{ store.uninstallingId === selected.id ? t('marketplace.uninstalling') : t('marketplace.uninstall') }}
            </button>
            <button
              type="button"
              class="flex items-center gap-1 rounded border border-theme-primary/40 bg-theme-primary/10 px-3 py-1 text-xs font-medium text-theme-primary hover:bg-theme-primary/20 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="isCurrentVersion(selected) || store.installingId === selected.id || !addonVersion(selected)"
              @click="installAddon(selected); selected = null"
            >
              <Plug :size="12" />
              {{ isCurrentVersion(selected) ? t('marketplace.installed') : t('marketplace.install') }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>
