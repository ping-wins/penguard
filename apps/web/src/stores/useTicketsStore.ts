import { defineStore } from 'pinia'
import { ref } from 'vue'
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
  let pollHandle: ReturnType<typeof setInterval> | null = null

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

  function startPolling(intervalMs = 8000) {
    stopPolling()
    refresh()
    pollHandle = setInterval(refresh, intervalMs)
  }

  function stopPolling() {
    if (pollHandle !== null) {
      clearInterval(pollHandle)
      pollHandle = null
    }
  }

  async function patchTicket(
    ticketId: string,
    patch: { triageLevel?: TriageLevel; ticketStatus?: TicketStatus; assigneeUserId?: string; note?: string },
  ) {
    const updated = await apiUpdateTicket(ticketId, patch)
    const idx = tickets.value.findIndex((t) => t.id === ticketId)
    if (idx >= 0) tickets.value[idx] = updated
    else tickets.value.unshift(updated)
    return updated
  }

  return {
    tickets,
    isLoading,
    error,
    refresh,
    startPolling,
    stopPolling,
    patchTicket,
  }
})
