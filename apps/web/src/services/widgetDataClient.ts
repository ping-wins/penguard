import type { WidgetDataErrorKind, WidgetDataResponse } from '../types/dashboard'

type WidgetDataReady = {
  state: 'ready'
  data: Record<string, unknown>
  response: WidgetDataResponse
}

type WidgetDataError = {
  state: 'error'
  errorKind: WidgetDataErrorKind
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

function httpErrorKind(status: number): WidgetDataErrorKind {
  if (status === 401 || status === 403 || status === 404) return 'invalid_connection'
  return 'network'
}

function httpErrorMessage(status: number) {
  if (status === 401 || status === 403) {
    return 'Widget connection is not authorized. Check the FortiDashboard session or FortiGate integration.'
  }

  if (status === 404) {
    return 'Widget connection was not found. Reconnect or select another FortiGate integration.'
  }

  return `HTTP Error ${status}`
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
    return {
      state: 'error',
      errorKind: httpErrorKind(response.status),
      errorMessage: httpErrorMessage(response.status),
    }
  }

  const payload = await response.json() as WidgetDataResponse
  if (payload.status === 'error') {
    return {
      state: 'error',
      errorKind: 'widget_error',
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
