<script setup lang="ts">
import { ref } from 'vue'
import { LayoutDashboard, Settings, Menu, MessageSquare, Send, LogOut } from 'lucide-vue-next'
import catalogData from '@fortidashboard/contracts/fixtures/catalog.json'
import { useDashboardStore } from '../../stores/useDashboardStore'
import { useAuthStore } from '../../stores/useAuthStore'
import { useThemeStore } from '../../stores/useThemeStore'
import { useRouter } from 'vue-router'

const store = useDashboardStore()
const authStore = useAuthStore()
const themeStore = useThemeStore()
const router = useRouter()
const activeTab = ref<'none' | 'chat' | 'settings'>('none')

const themeColors = [] // Removed old colors

const chatInput = ref('')
const chatMessages = ref<{role: 'user' | 'assistant', text: string}[]>([
  { role: 'assistant', text: 'Olá! Sou sua analista de SOC virtual. Que painel deseja adicionar?' }
])
const isThinking = ref(false)

function toggleTab(tab: 'chat' | 'settings') {
  activeTab.value = activeTab.value === tab ? 'none' : tab
}

function handleAddWidget(catalogId: string) {
  store.addWidget(catalogId)
}

async function handleLogout() {
  await authStore.logout()
  router.push({ name: 'login' })
}

function handleChatSubmit() {
  if (!chatInput.value.trim()) return
  
  const text = chatInput.value
  chatMessages.value.push({ role: 'user', text })
  chatInput.value = ''
  isThinking.value = true
  
  setTimeout(() => {
    isThinking.value = false
    // NLP MOCK logic
    const lowerText = text.toLowerCase()
    let found = false
    for (const item of catalogData.items) {
      if (lowerText.includes(item.title.toLowerCase()) || lowerText.includes(item.id.split('-').pop() || '')) {
        handleAddWidget(item.id)
        chatMessages.value.push({ role: 'assistant', text: `Adicionei o painel "${item.title}" para você!` })
        found = true
        break
      }
    }
    
    if (!found) {
      chatMessages.value.push({ role: 'assistant', text: 'Não encontrei um painel exato para sua solicitação. Tente pedir por "System Status", "Top Threats" ou "Network".' })
    }
  }, 1000)
}
</script>

<template>
  <div class="flex h-full relative z-50">
    <!-- Icon Bar -->
    <aside class="w-16 h-full bg-theme-panel flex flex-col items-center py-4 border-r border-theme-border shrink-0 z-20">
      <div class="mb-8 cursor-pointer hover:opacity-80 text-theme-text transition-colors">
        <Menu :size="24" />
      </div>
      
      <nav class="flex flex-col gap-4 flex-1">
        <div 
          class="p-3 rounded-lg cursor-pointer transition-colors"
          :class="activeTab === 'none' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="activeTab = 'none'"
          title="Dashboard"
        >
          <LayoutDashboard :size="20" />
        </div>

        <div 
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'chat' ? 'bg-theme-primary/10 text-theme-primary' : 'hover:bg-theme-border text-theme-text-muted hover:text-theme-text'"
          @click="toggleTab('chat')"
          title="SOC Assistant"
        >
          <MessageSquare :size="20" />
        </div>
      </nav>
      
      <div class="mt-auto flex flex-col gap-2">
        <div 
          class="p-3 rounded-lg hover:bg-theme-border cursor-pointer transition-colors relative text-theme-text-muted hover:text-theme-text"
          @click="themeStore.openBuilder()"
          title="Design System Builder"
        >
          <Settings :size="20" />
        </div>
        <div @click="handleLogout" class="p-3 rounded-lg hover:bg-red-500/20 text-theme-text-muted hover:text-red-400 cursor-pointer transition-colors" title="Sair">
          <LogOut :size="20" />
        </div>
      </div>
    </aside>

    <!-- Drawer Panel -->
    <div 
      class="h-full bg-theme-panel border-r border-theme-border flex flex-col transition-all duration-300 overflow-hidden z-10"
      :style="{ width: activeTab !== 'none' ? '320px' : '0px', opacity: activeTab !== 'none' ? 1 : 0 }"
    >
      <!-- Chat Tab -->
      <div v-if="activeTab === 'chat'" class="p-4 flex flex-col h-full w-[320px] shrink-0">
        <h2 class="font-bold text-lg mb-4 text-theme-text">Assistente IA</h2>
        
        <div class="flex-1 overflow-y-auto flex flex-col gap-3 pr-2 mb-4">
          <div 
            v-for="(msg, i) in chatMessages" 
            :key="i"
            class="p-3 rounded-lg text-sm"
            :class="msg.role === 'user' ? 'bg-theme-primary/20 text-theme-text self-end ml-4' : 'bg-theme-border text-theme-text self-start mr-4'"
          >
            {{ msg.text }}
          </div>
          <div v-if="isThinking" class="bg-theme-border text-theme-text-muted p-3 rounded-lg self-start text-xs italic animate-pulse">
            Analisando...
          </div>
        </div>

        <form @submit.prevent="handleChatSubmit" class="mt-auto relative">
          <input 
            v-model="chatInput" 
            type="text" 
            placeholder="Ex: Adicione ameaças..."
            class="w-full bg-theme-bg border border-theme-border rounded-lg pl-3 pr-10 py-2.5 text-sm focus:outline-none focus:border-theme-primary focus:ring-1 focus:ring-theme-primary text-theme-text"
            :disabled="isThinking"
          />
          <button 
            type="submit" 
            class="absolute right-2 top-2.5 text-theme-text-muted hover:text-theme-text disabled:opacity-50"
            :disabled="isThinking || !chatInput.trim()"
          >
            <Send :size="18" />
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
