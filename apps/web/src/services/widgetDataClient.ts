import type { WidgetDataResponse } from '../types/dashboard'

type WidgetDataReady = {
  state: 'ready'
  data: Record<string, unknown>
  response: WidgetDataResponse
}

type WidgetDataError = {
  state: 'error'
  errorMessage: string
  response?: WidgetDataResponse
}

export type WidgetDataResult = WidgetDataReady | WidgetDataError

type FetchWidgetDataOptions = {
  dataEndpoint: string
  integrationId: string
  fetcher?: typeof fetch
  signal?: AbortSignal
}

function buildWidgetDataUrl(dataEndpoint: string, integrationId: string) {
  const separator = dataEndpoint.includes('?') ? '&' : '?'
  return `${dataEndpoint}${separator}integrationId=${encodeURIComponent(integrationId)}`
}

export async function fetchWidgetData({
  dataEndpoint,
  integrationId,
  fetcher = globalThis.fetch.bind(globalThis),
  signal,
}: FetchWidgetDataOptions): Promise<WidgetDataResult> {
  const requestInit: RequestInit = { credentials: 'include' }
  if (signal) requestInit.signal = signal

  const response = await fetcher(buildWidgetDataUrl(dataEndpoint, integrationId), requestInit)
  if (!response.ok) {
    return { state: 'error', errorMessage: `HTTP Error ${response.status}` }
  }

  const payload = await response.json() as WidgetDataResponse
  if (payload.status === 'error') {
    return {
      state: 'error',
      errorMessage: payload.meta?.error?.message || 'Widget error occurred',
      response: payload,
    }
  }

  return {
    state: 'ready',
    data: payload.data || {},
    response: payload,
  }
}
