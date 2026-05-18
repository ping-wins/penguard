import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  type SocAssistantSettings,
  type SocAssistantSettingsTestResult,
  type SocAssistantSettingsUpdate,
  getSocAssistantSettings,
  saveSocAssistantSettings,
  testSocAssistantSettings,
} from '../services/socAssistantSettingsClient'

export const useSocAssistantSettingsStore = defineStore('socAssistantSettings', () => {
  const settings = ref<SocAssistantSettings | null>(null)
  const testResult = ref<SocAssistantSettingsTestResult | null>(null)
  const isLoading = ref(false)
  const isSaving = ref(false)
  const isTesting = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    isLoading.value = true
    error.value = null
    try {
      settings.value = await getSocAssistantSettings()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      isLoading.value = false
    }
  }

  async function save(update: SocAssistantSettingsUpdate) {
    isSaving.value = true
    error.value = null
    testResult.value = null
    try {
      settings.value = await saveSocAssistantSettings(update)
      return settings.value
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      isSaving.value = false
    }
  }

  async function testConnection() {
    isTesting.value = true
    error.value = null
    try {
      testResult.value = await testSocAssistantSettings()
      await load()
      return testResult.value
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      isTesting.value = false
    }
  }

  return {
    settings,
    testResult,
    isLoading,
    isSaving,
    isTesting,
    error,
    load,
    save,
    testConnection,
  }
})
