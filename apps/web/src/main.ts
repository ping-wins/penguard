import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import { i18n, getLocale } from './i18n'
import './style.css'
import App from './App.vue'

if (typeof document !== 'undefined') {
  document.documentElement.lang = getLocale()
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.mount('#app')
