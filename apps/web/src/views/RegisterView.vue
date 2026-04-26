<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/useAuthStore'
import { useThemeStore } from '../stores/useThemeStore'
import { ShieldAlert } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()
const themeStore = useThemeStore()

const displayName = ref('')
const email = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)

async function handleRegister() {
  errorMsg.value = ''
  loading.value = true
  try {
    await authStore.register({ 
      displayName: displayName.value,
      email: email.value, 
      password: password.value 
    })
    router.push({ name: 'dashboard' })
  } catch (err: any) {
    errorMsg.value = err.message || 'Erro ao registrar usuário'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen w-full bg-theme-bg flex items-center justify-center pattern-grid relative p-4">
    <!-- Gradient Background -->
    <div class="absolute inset-0 z-0 opacity-20 pointer-events-none transition-colors duration-1000" :style="{ background: `radial-gradient(circle at top right, ${themeStore.primary}, transparent 70%)` }"></div>

    <div class="w-full max-w-md bg-theme-panel border border-theme-border rounded-2xl shadow-2xl p-8 relative z-10">
      <div class="flex flex-col items-center mb-8">
        <div class="w-16 h-16 rounded-full flex items-center justify-center mb-4 transition-colors duration-500" :style="{ backgroundColor: `${themeStore.primary}20`, color: themeStore.primary }">
          <ShieldAlert :size="32" />
        </div>
        <h1 class="text-2xl font-bold text-theme-text tracking-tight">Novo Analista</h1>
        <p class="text-sm text-theme-text-muted mt-2">Solicitar acesso ao SOC</p>
      </div>

      <form @submit.prevent="handleRegister" class="flex flex-col gap-4">
        <div v-if="errorMsg" class="bg-red-500/10 border border-red-500/50 text-red-400 text-sm p-3 rounded-lg text-center">
          {{ errorMsg }}
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-xs font-semibold text-theme-text-muted uppercase tracking-wider">Nome Completo</label>
          <input 
            v-model="displayName" 
            type="text" 
            required
            class="w-full bg-theme-bg border border-theme-border rounded-lg p-2.5 text-theme-text focus:outline-none transition-colors"
            :style="{ outlineColor: themeStore.primary }"
            placeholder="João Silva"
          />
        </div>

        <div class="flex flex-col gap-2">
          <label class="text-xs font-semibold text-theme-text-muted uppercase tracking-wider">Email Corporativo</label>
          <input 
            v-model="email" 
            type="email" 
            required
            class="w-full bg-theme-bg border border-theme-border rounded-lg p-2.5 text-theme-text focus:outline-none transition-colors"
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
            class="w-full bg-theme-bg border border-theme-border rounded-lg p-2.5 text-theme-text focus:outline-none transition-colors"
            :style="{ outlineColor: themeStore.primary }"
            placeholder="•••••••• (Mínimo 8 caracteres)"
          />
        </div>

        <button 
          type="submit" 
          :disabled="loading"
          class="w-full text-white font-medium py-3 rounded-lg mt-4 transition-all flex justify-center disabled:opacity-50 hover:brightness-110 shadow-lg"
          :style="{ backgroundColor: themeStore.primary }"
        >
          <span v-if="loading">Registrando...</span>
          <span v-else>Criar Conta</span>
        </button>

        <p class="text-center text-sm text-theme-text-muted mt-4">
          Já tem acesso? <router-link to="/login" class="transition-colors font-medium hover:brightness-110" :style="{ color: themeStore.primary }">Faça Login</router-link>
        </p>
      </form>
    </div>
  </div>
</template>
