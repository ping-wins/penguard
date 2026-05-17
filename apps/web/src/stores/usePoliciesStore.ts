import { defineStore } from 'pinia'
import {
  policiesClient,
  type PolicyApplyResult,
  type PolicyFilters,
  type PolicyProviderSummary,
  type PolicyReview,
  type PolicyReviewCreateRequest,
  type PolicyRow,
} from '../services/policiesClient'
import { useAuthStore } from './useAuthStore'

type State = {
  providers: PolicyProviderSummary[]
  policies: PolicyRow[]
  selectedReview: PolicyReview | null
  lastApplyResult: PolicyApplyResult | null
  isLoading: boolean
  error: string | null
}

function setError(state: State, err: unknown) {
  state.error = err instanceof Error ? err.message : 'Unknown error'
}

export const usePoliciesStore = defineStore('policies', {
  state: (): State => ({
    providers: [],
    policies: [],
    selectedReview: null,
    lastApplyResult: null,
    isLoading: false,
    error: null,
  }),
  getters: {
    pendingReview(state): PolicyReview | null {
      return state.selectedReview?.status === 'pending_review' ? state.selectedReview : null
    },
    totalPolicies(state): number {
      return state.policies.length
    },
  },
  actions: {
    async loadProviders() {
      this.isLoading = true
      this.error = null
      try {
        this.providers = await policiesClient.listProviders()
      } catch (err) {
        setError(this, err)
      } finally {
        this.isLoading = false
      }
    },

    async loadPolicies(filters: PolicyFilters = {}) {
      this.isLoading = true
      this.error = null
      try {
        const data = await policiesClient.listPolicies(filters)
        this.policies = data.items
      } catch (err) {
        setError(this, err)
      } finally {
        this.isLoading = false
      }
    },

    async reviewPolicy(payload: PolicyReviewCreateRequest) {
      this.error = null
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()
      try {
        this.selectedReview = await policiesClient.createReview(payload, authStore.csrfToken)
        this.lastApplyResult = null
        return this.selectedReview
      } catch (err) {
        setError(this, err)
        throw err
      }
    },

    async applyReview(reviewId: string, reviewHash: string) {
      this.error = null
      const authStore = useAuthStore()
      if (!authStore.csrfToken) await authStore.fetchCsrf()
      try {
        this.lastApplyResult = await policiesClient.applyReview(
          reviewId,
          { reviewHash, confirmed: true },
          authStore.csrfToken,
        )
        if (this.selectedReview?.id === reviewId && this.lastApplyResult.status === 'applied') {
          this.selectedReview = { ...this.selectedReview, status: 'applied' }
        }
        return this.lastApplyResult
      } catch (err) {
        setError(this, err)
        throw err
      }
    },
  },
})
