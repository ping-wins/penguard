import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import {
  installMarketplaceAddon,
  listMarketplaceAddons,
  type AddonManifest,
} from '../services/marketplaceClient'

export const useMarketplaceStore = defineStore('marketplace', () => {
  const addons = ref<AddonManifest[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const hasLoadedOnce = ref(false)
  const installingId = ref<string | null>(null)

  const byCategory = computed(() => {
    const groups: Record<string, AddonManifest[]> = {}
    for (const addon of addons.value) {
      const category = addon.category || 'other'
      if (!groups[category]) groups[category] = []
      groups[category].push(addon)
    }
    return groups
  })

  async function refresh(): Promise<void> {
    isLoading.value = true
    error.value = null
    try {
      addons.value = await listMarketplaceAddons()
      hasLoadedOnce.value = true
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to load marketplace'
    } finally {
      isLoading.value = false
    }
  }

  async function install(addon: AddonManifest): Promise<void> {
    installingId.value = addon.id
    error.value = null
    try {
      await installMarketplaceAddon(addon.id, addon.version)
      await refresh()
    } catch (err: any) {
      error.value = err?.message ?? 'Failed to install marketplace add-on'
      throw err
    } finally {
      installingId.value = null
    }
  }

  return {
    addons,
    isLoading,
    error,
    hasLoadedOnce,
    installingId,
    byCategory,
    refresh,
    install,
  }
})
