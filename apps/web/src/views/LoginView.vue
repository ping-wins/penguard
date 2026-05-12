<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '../stores/useAuthStore'
import { useThemeStore } from '../stores/useThemeStore'
import { ssoKerberosLoginUrl } from '../services/authClient'
import { Shield, KeyRound, AlertTriangle, X } from 'lucide-vue-next'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const themeStore = useThemeStore()

const email = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)
const ssoUnavailable = ref(false)

const ssoErrorText = ref('')

function ssoErrorMessage(code: string): string {
  switch (code) {
    case 'state_mismatch':
      return t('auth.sso.stateMismatch')
    case 'mock_mode':
      return t('auth.sso.mockMode')
    default:
      return t('auth.sso.unavailable')
  }
}

onMounted(() => {
  const ssoError = route.query.sso_error
  if (typeof ssoError === 'string' && ssoError.length > 0) {
    ssoErrorText.value = ssoErrorMessage(ssoError)
    ssoUnavailable.value = true
    router.replace({ name: 'login', query: {} })
  }
})

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    await authStore.login({ email: email.value, password: password.value })
    router.push({ name: 'dashboard' })
  } catch (err: any) {
    errorMsg.value = err.message || t('auth.login.errorFallback')
  } finally {
    loading.value = false
  }
}

function handleSsoLogin() {
  window.location.href = ssoKerberosLoginUrl()
}

function dismissSsoPopup() {
  ssoUnavailable.value = false
}
</script>

<template>
  <div class="min-h-screen w-full bg-theme-bg flex items-center justify-center pattern-grid relative p-4">
    <!-- Gradient Background -->
    <div class="absolute inset-0 z-0 opacity-20 pointer-events-none transition-colors duration-1000" :style="{ background: `radial-gradient(circle at top left, ${themeStore.primary}, transparent 70%)` }"></div>

    <!-- SSO Unavailable Modal -->
    <div
      v-if="ssoUnavailable"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
    >
      <div class="w-full max-w-md bg-theme-panel border border-theme-border rounded-2xl shadow-2xl p-6 relative">
        <button
          type="button"
          @click="dismissSsoPopup"
          class="absolute top-3 right-3 text-theme-text-muted hover:text-theme-text"
          :aria-label="t('common.close')"
        >
          <X :size="18" />
        </button>
        <div class="flex items-start gap-3">
          <div class="w-10 h-10 rounded-full flex items-center justify-center bg-amber-500/15 text-amber-400 shrink-0">
            <AlertTriangle :size="20" />
          </div>
          <div class="flex-1">
            <h2 class="text-lg font-semibold text-theme-text mb-2">{{ t('auth.sso.unavailableTitle') }}</h2>
            <p class="text-sm text-theme-text-muted leading-relaxed">{{ ssoErrorText }}</p>
          </div>
        </div>
        <button
          type="button"
          @click="dismissSsoPopup"
          class="w-full mt-5 text-white font-medium py-2.5 rounded-lg transition-all hover:brightness-110"
          :style="{ backgroundColor: themeStore.primary }"
        >
          {{ t('auth.sso.acknowledge') }}
        </button>
      </div>
    </div>

    <div class="w-full max-w-md bg-theme-panel border border-theme-border rounded-2xl shadow-2xl p-8 relative z-10">
      <div class="flex flex-col items-center mb-8">
        <div class="w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-colors duration-500" :style="{ backgroundColor: `${themeStore.primary}20`, color: themeStore.primary }">
          <Shield :size="32" />
        </div>
        <h1 class="text-3xl font-bold text-theme-text tracking-tight">{{ t('auth.login.title') }}</h1>
        <p class="text-sm text-theme-text-muted mt-2">{{ t('auth.login.subtitle') }}</p>
      </div>

      <form @submit.prevent="handleLogin" class="flex flex-col gap-5">
        <div v-if="errorMsg" class="bg-red-500/10 border border-red-500/50 text-red-400 text-sm p-3 rounded-lg text-center">
          {{ errorMsg }}
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-xs font-semibold text-theme-text-muted uppercase tracking-wider">{{ t('auth.login.emailLabel') }}</label>
          <input
            v-model="email"
            type="email"
            required
            class="w-full bg-theme-bg border border-theme-border rounded-lg p-3 text-theme-text focus:outline-none transition-colors"
            :style="{ outlineColor: themeStore.primary }"
            :placeholder="t('auth.login.emailPlaceholder')"
          />
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-xs font-semibold text-theme-text-muted uppercase tracking-wider">{{ t('auth.login.passwordLabel') }}</label>
          <input
            v-model="password"
            type="password"
            required
            minlength="8"
            class="w-full bg-theme-bg border border-theme-border rounded-lg p-3 text-theme-text focus:outline-none transition-colors"
            :style="{ outlineColor: themeStore.primary }"
            :placeholder="t('auth.login.passwordPlaceholder')"
          />
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full text-white font-medium py-3 rounded-lg mt-2 transition-all flex justify-center disabled:opacity-50 hover:brightness-110 shadow-lg"
          :style="{ backgroundColor: themeStore.primary }"
        >
          <span v-if="loading">{{ t('auth.login.submitLoading') }}</span>
          <span v-else>{{ t('auth.login.submit') }}</span>
        </button>

        <div class="flex items-center gap-3 my-2">
          <div class="h-px flex-1 bg-theme-border"></div>
          <span class="text-xs uppercase tracking-wider text-theme-text-muted">{{ t('common.or') }}</span>
          <div class="h-px flex-1 bg-theme-border"></div>
        </div>

        <button
          type="button"
          :disabled="loading"
          @click="handleSsoLogin"
          class="w-full font-medium py-3 rounded-lg transition-all flex items-center justify-center gap-2 border border-theme-border bg-theme-bg text-theme-text disabled:opacity-50 hover:brightness-110"
        >
          <KeyRound :size="18" />
          <span>{{ t('auth.login.ssoButton') }}</span>
        </button>

        <p class="text-center text-sm text-theme-text-muted mt-4">
          {{ t('auth.login.noAccount') }}
          <router-link to="/register" class="transition-colors font-medium hover:brightness-110" :style="{ color: themeStore.primary }">{{ t('auth.login.registerLink') }}</router-link>
        </p>
      </form>
    </div>
  </div>
</template>
