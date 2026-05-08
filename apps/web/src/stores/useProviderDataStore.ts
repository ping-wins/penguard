import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  fetchFortigateDataFields,
  fetchProviderDataFields,
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

  async function fetchFieldsForIntegrations(integrations: Array<{ id: string, type: string }>) {
    const integrationTypes = Array.from(new Set(
      integrations
        .map(integration => integration.type)
        .filter(type => typeof type === 'string' && type.length > 0),
    ))
    const integrationIdByType = new Map<string, string>()
    for (const integration of integrations) {
      if (!integrationIdByType.has(integration.type)) {
        integrationIdByType.set(integration.type, integration.id)
      }
    }

    isLoading.value = true
    error.value = null
    try {
      const response = await fetchProviderDataFields({ integrationTypes })
      provider.value = response.provider
      groups.value = response.groups.map(group => ({
        ...group,
        fields: group.fields.map(field => ({
          ...field,
          integrationId: field.integrationId
            ?? integrationIdByType.get(field.integrationType ?? field.provider ?? ''),
        })),
      }))
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
    fetchFieldsForIntegrations,
  }
})
