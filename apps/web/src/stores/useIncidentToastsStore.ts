import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listTickets, type Ticket } from '../services/ticketsClient'
import { useRealtimeStore } from './useRealtimeStore'

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

export const useIncidentToastsStore = defineStore('incidentToasts', () => {
  const toasts = ref<IncidentToast[]>([])
  const knownTicketIds = ref<Set<string>>(new Set())
  const hasBootstrapped = ref(false)
  let expiryHandle: ReturnType<typeof setInterval> | null = null
  let unsubscribeRealtime: (() => void) | null = null

  async function refreshTickets() {
    try {
      const tickets = await listTickets()
      if (!hasBootstrapped.value) {
        // First realtime hydration records the known set so users
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
      console.error('Failed to refresh tickets for toasts', e)
    }
  }

  function ingestTicket(ticket: Ticket) {
    if (!hasBootstrapped.value) {
      knownTicketIds.value.add(ticket.id)
      return
    }
    if (knownTicketIds.value.has(ticket.id)) return
    knownTicketIds.value.add(ticket.id)
    pushToast(ticket)
    pruneExpired()
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

  function startRealtime() {
    if (unsubscribeRealtime !== null) return
    refreshTickets()
    unsubscribeRealtime = useRealtimeStore().subscribe((event) => {
      if (event.ticket) ingestTicket(event.ticket)
    })
    expiryHandle = setInterval(pruneExpired, 1000)
  }

  function stopRealtime() {
    if (expiryHandle !== null) {
      clearInterval(expiryHandle)
      expiryHandle = null
    }
    unsubscribeRealtime?.()
    unsubscribeRealtime = null
  }

  return {
    toasts,
    hasBootstrapped,
    startRealtime,
    stopRealtime,
    dismiss,
  }
})
