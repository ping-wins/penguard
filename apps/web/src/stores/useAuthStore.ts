import { defineStore } from 'pinia'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    isAuthenticated: false,
    user: null as any,
    isInitialized: false,
    csrfToken: ''
  }),
  actions: {
    async fetchCsrf() {
      try {
        const res = await fetch('/api/auth/csrf')
        if (res.ok) {
          const data = await res.json()
          this.csrfToken = data.csrfToken
        }
      } catch (e) {
        console.error('Failed to fetch CSRF token', e)
      }
    },
    
    async fetchSession() {
      try {
        const res = await fetch('/api/auth/me', { credentials: 'include' })
        if (res.ok) {
          const data = await res.json()
          this.isAuthenticated = data.authenticated
          this.user = data.user
        } else {
          this.isAuthenticated = false
          this.user = null
        }
      } catch (e) {
        this.isAuthenticated = false
        this.user = null
      } finally {
        this.isInitialized = true
      }
    },

    async login(payload: any) {
      if (!this.csrfToken) await this.fetchCsrf()
      
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': this.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify(payload)
      })
      
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        let msg = 'Credenciais inválidas'
        if (errData.detail) {
          msg = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail)
        }
        throw new Error(msg)
      }
      
      const data = await res.json()
      this.isAuthenticated = true
      this.user = data.user
      return data
    },

    async register(payload: any) {
      if (!this.csrfToken) await this.fetchCsrf()
      
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': this.csrfToken
        },
        credentials: 'include',
        body: JSON.stringify(payload)
      })
      
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        let msg = 'Falha no registro'
        if (errData.detail) {
          if (Array.isArray(errData.detail) && errData.detail[0]?.msg) {
             msg = errData.detail[0].msg
          } else {
             msg = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail)
          }
        }
        throw new Error(msg)
      }
      
      const data = await res.json()
      this.isAuthenticated = true
      this.user = data.user
      return data
    },

    async logout() {
      if (!this.csrfToken) await this.fetchCsrf()
      
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: {
          'X-CSRF-Token': this.csrfToken
        },
        credentials: 'include'
      })
      
      this.isAuthenticated = false
      this.user = null
    }
  }
})
