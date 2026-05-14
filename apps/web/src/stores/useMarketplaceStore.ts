import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { listMarketplaceAddons, type AddonManifest } from '../services/marketplaceClient'

export const useMarketplaceStore = defineStore('marketplace', () => {
  const addons = ref<AddonManifest[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const hasLoadedOnce = ref(false)

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

  return { addons, isLoading, error, hasLoadedOnce, byCategory, refresh }
})
