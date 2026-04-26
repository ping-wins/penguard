<script setup lang="ts">
import { ref } from 'vue'
import { LayoutDashboard, Settings, Menu, MessageSquare, Send } from 'lucide-vue-next'
import catalogData from '@fortidashboard/contracts/fixtures/catalog.json'
import { useDashboardStore } from '../../stores/useDashboardStore'

const store = useDashboardStore()
const activeTab = ref<'none' | 'chat'>('none')

const chatInput = ref('')
const chatMessages = ref<{role: 'user' | 'assistant', text: string}[]>([
  { role: 'assistant', text: 'Olá! Sou sua analista de SOC virtual. Que painel deseja adicionar?' }
])
const isThinking = ref(false)

function toggleTab(tab: 'chat') {
  activeTab.value = activeTab.value === tab ? 'none' : tab
}

function handleAddWidget(catalogId: string) {
  store.addWidget(catalogId)
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
    <aside class="w-16 h-full bg-forti-panel flex flex-col items-center py-4 border-r border-gray-800 shrink-0 z-20">
      <div class="mb-8 cursor-pointer hover:text-white transition-colors">
        <Menu :size="24" />
      </div>
      
      <nav class="flex flex-col gap-4 flex-1">
        <div 
          class="p-3 rounded-lg cursor-pointer transition-colors"
          :class="activeTab === 'none' ? 'bg-forti-red/10 text-forti-red' : 'hover:bg-gray-800'"
          @click="activeTab = 'none'"
          title="Dashboard"
        >
          <LayoutDashboard :size="20" />
        </div>

        <div 
          class="p-3 rounded-lg cursor-pointer transition-colors relative"
          :class="activeTab === 'chat' ? 'bg-forti-red/10 text-forti-red' : 'hover:bg-gray-800'"
          @click="toggleTab('chat')"
          title="SOC Assistant"
        >
          <MessageSquare :size="20" />
        </div>
      </nav>
      
      <div class="mt-auto p-3 rounded-lg hover:bg-gray-800 cursor-pointer transition-colors" title="Configurações">
        <Settings :size="20" />
      </div>
    </aside>

    <!-- Drawer Panel -->
    <div 
      class="h-full bg-[#181818] border-r border-gray-800 flex flex-col transition-all duration-300 overflow-hidden z-10"
      :style="{ width: activeTab !== 'none' ? '320px' : '0px', opacity: activeTab !== 'none' ? 1 : 0 }"
    >
      <!-- Chat Tab -->
      <div v-if="activeTab === 'chat'" class="p-4 flex flex-col h-full w-[320px] shrink-0">
        <h2 class="font-bold text-lg mb-4 text-white">Assistente IA</h2>
        
        <div class="flex-1 overflow-y-auto flex flex-col gap-3 pr-2 mb-4">
          <div 
            v-for="(msg, i) in chatMessages" 
            :key="i"
            class="p-3 rounded-lg text-sm"
            :class="msg.role === 'user' ? 'bg-forti-red/20 text-white self-end ml-4' : 'bg-gray-800 text-gray-200 self-start mr-4'"
          >
            {{ msg.text }}
          </div>
          <div v-if="isThinking" class="bg-gray-800 text-gray-400 p-3 rounded-lg self-start text-xs italic animate-pulse">
            Analisando...
          </div>
        </div>

        <form @submit.prevent="handleChatSubmit" class="mt-auto relative">
          <input 
            v-model="chatInput" 
            type="text" 
            placeholder="Ex: Adicione ameaças..."
            class="w-full bg-black/50 border border-gray-700 rounded-lg pl-3 pr-10 py-2.5 text-sm focus:outline-none focus:border-forti-red focus:ring-1 focus:ring-forti-red text-white"
            :disabled="isThinking"
          />
          <button 
            type="submit" 
            class="absolute right-2 top-2.5 text-gray-400 hover:text-white disabled:opacity-50"
            :disabled="isThinking || !chatInput.trim()"
          >
            <Send :size="18" />
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
