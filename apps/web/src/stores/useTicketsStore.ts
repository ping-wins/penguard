import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useRealtimeStore } from './useRealtimeStore'
import {
  listTickets,
  updateTicket as apiUpdateTicket,
  type Ticket,
  type TicketStatus,
  type TriageLevel,
} from '../services/ticketsClient'

export const useTicketsStore = defineStore('tickets', () => {
  const tickets = ref<Ticket[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  let unsubscribeRealtime: (() => void) | null = null

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      tickets.value = await listTickets()
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load tickets'
    } finally {
      isLoading.value = false
    }
  }

  function upsertTicket(ticket: Ticket) {
    const idx = tickets.value.findIndex((existing) => existing.id === ticket.id)
    if (idx >= 0) {
      tickets.value[idx] = ticket
      return
    }
    tickets.value = [ticket, ...tickets.value]
  }

  function startRealtime() {
    refresh()
    if (unsubscribeRealtime !== null) return
    unsubscribeRealtime = useRealtimeStore().subscribe((event) => {
      if (event.ticket) upsertTicket(event.ticket)
      else if (event.refresh?.includes('tickets')) void refresh()
    })
  }

  function stopRealtime() {
    unsubscribeRealtime?.()
    unsubscribeRealtime = null
  }

  async function patchTicket(
    ticketId: string,
    patch: { triageLevel?: TriageLevel; ticketStatus?: TicketStatus; assigneeUserId?: string; note?: string },
  ) {
    const updated = await apiUpdateTicket(ticketId, patch)
    upsertTicket(updated)
    return updated
  }

  return {
    tickets,
    isLoading,
    error,
    refresh,
    startRealtime,
    stopRealtime,
    patchTicket,
  }
})
