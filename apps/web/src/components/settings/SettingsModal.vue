<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  X,
  UserCog,
  Palette,
  Languages,
  LogOut,
  Mail,
  IdCard,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/useAuthStore'
import { useThemeStore } from '../../stores/useThemeStore'
import { setLocale, type SupportedLocale } from '../../i18n'

const props = defineProps<{ isOpen: boolean }>()
const emit = defineEmits<{ close: [] }>()

const authStore = useAuthStore()
const themeStore = useThemeStore()
const router = useRouter()
const { t, locale } = useI18n()

type Tab = 'profile' | 'appearance' | 'language'
const activeTab = ref<Tab>('profile')
const localeSaved = ref(false)

const tabs = computed<{ id: Tab; label: string; icon: any }[]>(() => [
  { id: 'profile', label: t('settings.tabs.profile'), icon: UserCog },
  { id: 'appearance', label: t('settings.tabs.appearance'), icon: Palette },
  { id: 'language', label: t('settings.tabs.language'), icon: Languages },
])

function close() {
  emit('close')
}

function changeLocale(value: SupportedLocale) {
  setLocale(value)
  localeSaved.value = true
  window.setTimeout(() => {
    localeSaved.value = false
  }, 2200)
}

function openThemeBuilder() {
  close()
  themeStore.openBuilder()
}

async function handleLogout() {
  close()
  await authStore.logout()
  router.push({ name: 'login' })
}

const keycloakAccountUrl = computed(() => {
  // Best-effort: derive from window origin; falls back to a sensible default.
  if (typeof window === 'undefined') return 'http://localhost:8080/realms/fortidashboard/account'
  const port = '8080'
  const host = window.location.hostname || 'localhost'
  return `http://${host}:${port}/realms/fortidashboard/account`
})

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      activeTab.value = 'profile'
      localeSaved.value = false
    }
  },
)
</script>

<template>
  <transition name="settings-fade">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-40 flex items-center justify-center bg-black/65 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      @click.self="close"
    >
      <div class="w-full max-w-3xl max-h-[90vh] overflow-hidden bg-theme-panel border border-theme-border rounded-2xl shadow-2xl flex flex-col">
        <header class="flex items-center justify-between px-5 py-4 border-b border-theme-border">
          <div class="flex items-center gap-2">
            <UserCog :size="18" class="text-theme-text-muted" />
            <h2 class="text-lg font-bold text-theme-text">{{ t('settings.title') }}</h2>
          </div>
          <button
            type="button"
            class="text-theme-text-muted hover:text-theme-text"
            @click="close"
            :aria-label="t('common.close')"
          >
            <X :size="18" />
          </button>
        </header>

        <div class="flex flex-1 min-h-0">
          <nav class="w-48 shrink-0 border-r border-theme-border bg-theme-bg/40 py-3">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              type="button"
              class="w-full flex items-center gap-2 px-4 py-2 text-sm text-left transition-colors"
              :class="activeTab === tab.id
                ? 'bg-theme-primary/10 text-theme-primary border-l-2 border-theme-primary'
                : 'text-theme-text-muted hover:bg-theme-border/40 hover:text-theme-text border-l-2 border-transparent'"
              @click="activeTab = tab.id"
            >
              <component :is="tab.icon" :size="15" />
              {{ tab.label }}
            </button>
          </nav>

          <section class="flex-1 overflow-y-auto p-5">
            <!-- PROFILE TAB -->
            <div v-if="activeTab === 'profile'" class="space-y-4">
              <header>
                <h3 class="text-base font-semibold text-theme-text">{{ t('settings.profile.title') }}</h3>
                <p class="text-xs text-theme-text-muted mt-1">{{ t('settings.profile.subtitle') }}</p>
              </header>
              <dl class="grid grid-cols-3 gap-x-3 gap-y-3 text-sm">
                <dt class="col-span-1 text-theme-text-muted flex items-center gap-1">
                  <Mail :size="13" />
                  {{ t('settings.profile.emailLabel') }}
                </dt>
                <dd class="col-span-2 text-theme-text font-mono break-all">
                  {{ authStore.user?.email || '—' }}
                </dd>
                <dt class="col-span-1 text-theme-text-muted flex items-center gap-1">
                  <IdCard :size="13" />
                  {{ t('settings.profile.displayNameLabel') }}
                </dt>
                <dd class="col-span-2 text-theme-text">
                  {{ authStore.user?.displayName || '—' }}
                </dd>
                <dt class="col-span-1 text-theme-text-muted flex items-center gap-1">
                  <ShieldCheck :size="13" />
                  {{ t('settings.profile.rolesLabel') }}
                </dt>
                <dd class="col-span-2 flex flex-wrap gap-1">
                  <span
                    v-for="role in authStore.user?.roles || []"
                    :key="role"
                    class="text-xs px-2 py-0.5 rounded-full border border-theme-border bg-theme-bg/60 text-theme-text"
                  >
                    {{ role }}
                  </span>
                  <span v-if="!(authStore.user?.roles || []).length" class="text-theme-text-muted">—</span>
                </dd>
                <dt class="col-span-1 text-theme-text-muted">{{ t('settings.profile.sessionLabel') }}</dt>
                <dd class="col-span-2">
                  <span
                    class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs"
                    :class="authStore.isAuthenticated
                      ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-300'
                      : 'border-red-500/40 bg-red-500/10 text-red-300'"
                  >
                    {{ authStore.isAuthenticated
                      ? t('settings.profile.authenticated')
                      : t('settings.profile.notAuthenticated') }}
                  </span>
                </dd>
              </dl>
              <p class="text-xs text-theme-text-muted">
                {{ t('settings.profile.passwordHint', { url: keycloakAccountUrl }) }}
              </p>
              <button
                type="button"
                class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20 text-sm"
                @click="handleLogout"
              >
                <LogOut :size="14" />
                {{ t('settings.profile.logout') }}
              </button>
            </div>

            <!-- APPEARANCE TAB -->
            <div v-if="activeTab === 'appearance'" class="space-y-4">
              <header>
                <h3 class="text-base font-semibold text-theme-text">{{ t('settings.appearance.title') }}</h3>
                <p class="text-xs text-theme-text-muted mt-1">{{ t('settings.appearance.subtitle') }}</p>
              </header>
              <button
                type="button"
                class="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-white hover:brightness-110 transition"
                :style="{ backgroundColor: themeStore.primary }"
                @click="openThemeBuilder"
              >
                <Palette :size="14" />
                {{ t('settings.appearance.openBuilder') }}
              </button>
            </div>

            <!-- LANGUAGE TAB -->
            <div v-if="activeTab === 'language'" class="space-y-4">
              <header>
                <h3 class="text-base font-semibold text-theme-text">{{ t('settings.language.title') }}</h3>
                <p class="text-xs text-theme-text-muted mt-1">{{ t('settings.language.subtitle') }}</p>
              </header>
              <div>
                <label class="block text-xs uppercase tracking-wider text-theme-text-muted mb-2">
                  {{ t('settings.language.label') }}
                </label>
                <div class="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    class="px-3 py-3 rounded-lg border text-sm text-left flex items-center justify-between transition"
                    :class="locale === 'pt-BR'
                      ? 'border-theme-primary bg-theme-primary/10 text-theme-text'
                      : 'border-theme-border bg-theme-bg/40 text-theme-text-muted hover:bg-theme-border/40'"
                    @click="changeLocale('pt-BR')"
                  >
                    <span>
                      <span class="font-semibold">🇧🇷 {{ t('settings.language.portuguese') }}</span>
                      <span class="block text-[10px] text-theme-text-muted mt-0.5">pt-BR</span>
                    </span>
                    <CheckCircle2 v-if="locale === 'pt-BR'" :size="14" class="text-theme-primary" />
                  </button>
                  <button
                    type="button"
                    class="px-3 py-3 rounded-lg border text-sm text-left flex items-center justify-between transition"
                    :class="locale === 'en-US'
                      ? 'border-theme-primary bg-theme-primary/10 text-theme-text'
                      : 'border-theme-border bg-theme-bg/40 text-theme-text-muted hover:bg-theme-border/40'"
                    @click="changeLocale('en-US')"
                  >
                    <span>
                      <span class="font-semibold">🇺🇸 {{ t('settings.language.english') }}</span>
                      <span class="block text-[10px] text-theme-text-muted mt-0.5">en-US</span>
                    </span>
                    <CheckCircle2 v-if="locale === 'en-US'" :size="14" class="text-theme-primary" />
                  </button>
                </div>
              </div>
              <transition name="settings-fade">
                <div
                  v-if="localeSaved"
                  class="p-2 rounded border border-emerald-500/40 bg-emerald-500/10 text-emerald-300 text-xs flex items-center gap-2"
                >
                  <CheckCircle2 :size="14" />
                  {{ t('settings.language.saved') }}
                </div>
              </transition>
            </div>
          </section>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.settings-fade-enter-active,
.settings-fade-leave-active {
  transition: opacity 180ms ease-out;
}
.settings-fade-enter-from,
.settings-fade-leave-to {
  opacity: 0;
}
</style>
