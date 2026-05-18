import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useRealtimeStore } from './useRealtimeStore'
import { queryClient } from '../services/queryClient'
import { socTicketsKey } from '../services/queryKeys'
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

  function syncTicketsFromQueryCache() {
    const cached = queryClient.getQueryData<Ticket[]>(socTicketsKey())
    if (Array.isArray(cached)) tickets.value = cached
  }

  async function refresh() {
    isLoading.value = true
    error.value = null
    try {
      const nextTickets = await listTickets()
      queryClient.setQueryData(socTicketsKey(), nextTickets)
      tickets.value = nextTickets
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load tickets'
    } finally {
      isLoading.value = false
    }
  }

  function upsertTicket(ticket: Ticket) {
    queryClient.setQueryData<Ticket[]>(socTicketsKey(), (current = []) => {
      const idx = current.findIndex((existing) => existing.id === ticket.id)
      if (idx >= 0) return current.map((existing) => existing.id === ticket.id ? ticket : existing)
      return [ticket, ...current]
    })
    syncTicketsFromQueryCache()
  }

  function startRealtime() {
    refresh()
    if (unsubscribeRealtime !== null) return
    unsubscribeRealtime = useRealtimeStore().subscribe((event) => {
      if (event.ticket) {
        syncTicketsFromQueryCache()
        upsertTicket(event.ticket)
      }
      else if (event.refresh?.includes('tickets')) void refresh()
      else if (event.type === 'soc.incidents.reset') syncTicketsFromQueryCache()
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
