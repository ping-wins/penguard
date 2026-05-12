import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/useAuthStore'

// Views
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import PresentationView from '../views/PresentationView.vue'
import RegisterView from '../views/RegisterView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresAuth: false }
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
      meta: { requiresAuth: true }
    },
    {
      path: '/presentation/:workspaceId',
      name: 'presentation',
      component: PresentationView,
      meta: { requiresAuth: true }
    }
  ]
})

// Navigation Guard
router.beforeEach(async (to) => {
  const authStore = useAuthStore()

  if (!authStore.isInitialized) {
    await authStore.fetchSession()
  }

  const isAuthenticated = authStore.isAuthenticated

  if (to.meta.requiresAuth && !isAuthenticated) {
    return { name: 'login' }
  }
  if (!to.meta.requiresAuth && isAuthenticated && (to.name === 'login' || to.name === 'register')) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
