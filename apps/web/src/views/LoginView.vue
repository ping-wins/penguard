<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/useAuthStore'
import { useThemeStore } from '../stores/useThemeStore'
import { Shield } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()

const email = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    await authStore.login({ email: email.value, password: password.value })
    router.push({ name: 'dashboard' })
  } catch (err: any) {
    errorMsg.value = err.message || 'Erro ao efetuar login'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen w-full bg-theme-bg flex items-center justify-center pattern-grid relative p-4">
    <!-- Gradient Background -->
    <div class="absolute inset-0 z-0 opacity-20 pointer-events-none transition-colors duration-1000" :style="{ background: `radial-gradient(circle at top left, ${themeStore.primary}, transparent 70%)` }"></div>

    <div class="w-full max-w-md bg-theme-panel border border-theme-border rounded-2xl shadow-2xl p-8 relative z-10">
      <div class="flex flex-col items-center mb-8">
        <div class="w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-colors duration-500" :style="{ backgroundColor: `${themeStore.primary}20`, color: themeStore.primary }">
          <Shield :size="32" />
        </div>
        <h1 class="text-3xl font-bold text-theme-text tracking-tight">FortiDashboard</h1>
        <p class="text-sm text-theme-text-muted mt-2">Next-Gen SOC Analytics</p>
      </div>

      <form @submit.prevent="handleLogin" class="flex flex-col gap-5">
        <div v-if="errorMsg" class="bg-red-500/10 border border-red-500/50 text-red-400 text-sm p-3 rounded-lg text-center">
          {{ errorMsg }}
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-xs font-semibold text-theme-text-muted uppercase tracking-wider">Email Corporativo</label>
          <input 
            v-model="email" 
            type="email" 
            required
            class="w-full bg-theme-bg border border-theme-border rounded-lg p-3 text-theme-text focus:outline-none transition-colors"
            :style="{ outlineColor: themeStore.primary }"
            placeholder="analyst@soc.local"
          />
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-xs font-semibold text-theme-text-muted uppercase tracking-wider">Senha</label>
          <input 
            v-model="password" 
            type="password" 
            required
            minlength="8"
            class="w-full bg-theme-bg border border-theme-border rounded-lg p-3 text-theme-text focus:outline-none transition-colors"
            :style="{ outlineColor: themeStore.primary }"
            placeholder="••••••••"
          />
        </div>

        <button 
          type="submit" 
          :disabled="loading"
          class="w-full text-white font-medium py-3 rounded-lg mt-2 transition-all flex justify-center disabled:opacity-50 hover:brightness-110 shadow-lg"
          :style="{ backgroundColor: themeStore.primary }"
        >
          <span v-if="loading">Autenticando...</span>
          <span v-else>Entrar no Workspace</span>
        </button>

        <p class="text-center text-sm text-theme-text-muted mt-4">
          Não tem uma conta? <router-link to="/register" class="transition-colors font-medium hover:brightness-110" :style="{ color: themeStore.primary }">Registre-se</router-link>
        </p>
      </form>
    </div>
  </div>
</template>
