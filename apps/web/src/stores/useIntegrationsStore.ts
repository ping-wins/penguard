import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAuthStore } from './useAuthStore'

export const useIntegrationsStore = defineStore('integrations', () => {
  const integrations = ref<any[]>([])
  const isLoading = ref(false)
  const isTesting = ref(false)
  const error = ref<string | null>(null)

  const hasFortigate = computed(() => integrations.value.some(i => i.type === 'fortigate'))

  async function fetchIntegrations() {
    isLoading.value = true
    error.value = null
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch('/api/integrations', {
        headers: { 'X-CSRF-Token': authStore.csrfToken },
        credentials: 'include'
      })
      
      if (res.ok) {
        const data = await res.json()
        integrations.value = data.items || []
      } else {
        error.value = 'Failed to load integrations'
      }
    } catch (e) {
      error.value = 'Network error while loading integrations'
    } finally {
      isLoading.value = false
    }
  }

  async function testFortigate(host: string, apiKey: string, verifyTls: boolean) {
    isTesting.value = true
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch('/api/integrations/fortigate/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify({ host, apiKey, verifyTls })
      })

      if (res.ok) {
        const data = await res.json()
        return { success: true, data }
      } else {
        return { success: false, error: 'Connection failed' }
      }
    } catch (e) {
      return { success: false, error: 'Network error' }
    } finally {
      isTesting.value = false
    }
  }

  async function addFortigate(name: string, host: string, apiKey: string, verifyTls: boolean) {
    try {
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()

      const res = await fetch('/api/integrations/fortigate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': authStore.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify({ name, host, apiKey, verifyTls })
      })

      if (res.ok) {
        const data = await res.json()
        // Replace existing with same ID or add new
        const idx = integrations.value.findIndex(i => i.id === data.id)
        if (idx >= 0) integrations.value[idx] = data
        else integrations.value.push(data)
        
        return { success: true, data }
      } else {
        return { success: false, error: 'Failed to add integration' }
      }
    } catch (e) {
      return { success: false, error: 'Network error' }
    }
  }

  return {
    integrations,
    isLoading,
    isTesting,
    error,
    hasFortigate,
    fetchIntegrations,
    testFortigate,
    addFortigate
  }
})
