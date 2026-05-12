import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listTickets, type Ticket } from '../services/ticketsClient'

export type IncidentToast = {
  id: string
  ticketId: string
  title: string
  severity: string
  triageLevel: string
  createdAt: string
  expiresAt: number
}

const TOAST_TTL_MS = 12_000
const POLL_INTERVAL_MS = 5_000

export const useIncidentToastsStore = defineStore('incidentToasts', () => {
  const toasts = ref<IncidentToast[]>([])
  const knownTicketIds = ref<Set<string>>(new Set())
  const hasBootstrapped = ref(false)
  let pollHandle: ReturnType<typeof setInterval> | null = null

  async function poll() {
    try {
      const tickets = await listTickets()
      if (!hasBootstrapped.value) {
        // First poll just records the known set; nothing pops up so users
        // don't get spammed when they log in with a backlog.
        for (const ticket of tickets) {
          knownTicketIds.value.add(ticket.id)
        }
        hasBootstrapped.value = true
        return
      }
      const newTickets = tickets.filter((t) => !knownTicketIds.value.has(t.id))
      for (const ticket of newTickets) {
        knownTicketIds.value.add(ticket.id)
        pushToast(ticket)
      }
      pruneExpired()
    } catch (e) {
      console.error('Failed to poll tickets for toasts', e)
    }
  }

  function pushToast(ticket: Ticket) {
    const now = Date.now()
    const toast: IncidentToast = {
      id: `toast_${ticket.id}_${now}`,
      ticketId: ticket.id,
      title: ticket.title,
      severity: ticket.severity,
      triageLevel: ticket.triageLevel,
      createdAt: ticket.createdAt,
      expiresAt: now + TOAST_TTL_MS,
    }
    toasts.value.unshift(toast)
    if (toasts.value.length > 5) {
      toasts.value = toasts.value.slice(0, 5)
    }
  }

  function pruneExpired() {
    const now = Date.now()
    toasts.value = toasts.value.filter((t) => t.expiresAt > now)
  }

  function dismiss(toastId: string) {
    toasts.value = toasts.value.filter((t) => t.id !== toastId)
  }

  function startPolling() {
    if (pollHandle !== null) return
    poll()
    pollHandle = setInterval(() => {
      poll()
      pruneExpired()
    }, POLL_INTERVAL_MS)
  }

  function stopPolling() {
    if (pollHandle !== null) {
      clearInterval(pollHandle)
      pollHandle = null
    }
  }

  return {
    toasts,
    hasBootstrapped,
    startPolling,
    stopPolling,
    dismiss,
  }
})
