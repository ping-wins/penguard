import { createI18n } from 'vue-i18n'
import ptBR from './messages/pt-BR'
import enUS from './messages/en-US'

export const SUPPORTED_LOCALES = ['pt-BR', 'en-US'] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]

const STORAGE_KEY = 'fortidashboard:locale'

function detectInitialLocale(): SupportedLocale {
  if (typeof window === 'undefined') return 'pt-BR'
  const stored = window.localStorage?.getItem(STORAGE_KEY)
  if (stored === 'pt-BR' || stored === 'en-US') return stored
  const navLang = window.navigator?.language ?? ''
  if (navLang.toLowerCase().startsWith('en')) return 'en-US'
  return 'pt-BR'
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectInitialLocale(),
  fallbackLocale: 'pt-BR',
  messages: {
    'pt-BR': ptBR,
    'en-US': enUS,
  },
})

export function setLocale(locale: SupportedLocale) {
  i18n.global.locale.value = locale
  if (typeof window !== 'undefined' && window.localStorage) {
    window.localStorage.setItem(STORAGE_KEY, locale)
  }
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale
  }
}

export function getLocale(): SupportedLocale {
  return i18n.global.locale.value as SupportedLocale
}
