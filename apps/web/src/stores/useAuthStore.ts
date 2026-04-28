import { defineStore } from 'pinia'
import {
  fetchBrowserSession,
  fetchCsrfToken,
  loginWithBrowserSession,
  logoutBrowserSession,
  registerWithBrowserSession,
  type AuthUser,
} from '../services/authClient'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    isAuthenticated: false,
    user: null as AuthUser | null,
    isInitialized: false,
    csrfToken: ''
  }),
  actions: {
    async fetchCsrf() {
      this.csrfToken = await fetchCsrfToken()
      return this.csrfToken
    },
    
    async fetchSession() {
      try {
        const data = await fetchBrowserSession()
        this.isAuthenticated = data.authenticated
        this.user = data.user
      } catch (e) {
        this.isAuthenticated = false
        this.user = null
      } finally {
        this.isInitialized = true
      }
    },

    async login(payload: any) {
      const session = await loginWithBrowserSession(payload)
      this.isAuthenticated = session.authenticated
      this.user = session.user
      this.isInitialized = true
      this.csrfToken = ''
      return session
    },

    async register(payload: any) {
      const session = await registerWithBrowserSession(payload)
      this.isAuthenticated = session.authenticated
      this.user = session.user
      this.isInitialized = true
      this.csrfToken = ''
      return session
    },

    async logout() {
      await logoutBrowserSession()
      this.isAuthenticated = false
      this.user = null
      this.isInitialized = true
      this.csrfToken = ''
    }
  }
})
