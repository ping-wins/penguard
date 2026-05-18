import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { MotionPlugin } from '@vueuse/motion'
import { VueQueryPlugin } from '@tanstack/vue-query'
import router from './router'
import { i18n, getLocale } from './i18n'
import { queryClient } from './services/queryClient'
import './style.css'
import App from './App.vue'

if (typeof document !== 'undefined') {
  document.documentElement.lang = getLocale()
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(MotionPlugin)
app.use(VueQueryPlugin, { queryClient })
app.mount('#app')
