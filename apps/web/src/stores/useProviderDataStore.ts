import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchFortigateDataFields,
  ProviderDataApiError,
  type ProviderDataGroup,
} from '../services/providerDataClient'

export const useProviderDataStore = defineStore('providerData', () => {
  const provider = ref('fortigate')
  const groups = ref<ProviderDataGroup[]>([])
  const isLoading = ref(false)
  const isLoaded = ref(false)
  const error = ref<string | null>(null)

  async function fetchFortigateFields() {
    isLoading.value = true
    error.value = null
    try {
      const response = await fetchFortigateDataFields()
      provider.value = response.provider
      groups.value = response.groups
      isLoaded.value = true
    } catch (caught) {
      error.value = caught instanceof ProviderDataApiError
        ? caught.message
        : 'Unable to load provider data fields'
      groups.value = []
    } finally {
      isLoading.value = false
    }
  }

  return {
    provider,
    groups,
    isLoading,
    isLoaded,
    error,
    fetchFortigateFields,
  }
})
