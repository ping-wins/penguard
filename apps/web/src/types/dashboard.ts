export type WidgetLayout = {
  x: number
  y: number
  w: number
  h: number
  z: number
}

export type WidgetDefaultSize = {
  w: number
  h: number
}

export type WidgetCatalogItem = {
  id: string
  title: string
  kind: string
  source: string
  requiredCapabilities: string[]
  defaultSize: WidgetDefaultSize
  dataEndpoint: string
}

export type WorkspaceWidget = {
  instanceId: string
  catalogId: string
  integrationId: string
  layout: WidgetLayout
}

export type WidgetDataResponse = {
  widgetId: string
  integrationId: string
  refreshedAt: string
  status: 'ready' | 'error'
  data: Record<string, unknown>
  meta?: {
    source?: string
    cacheTtlSeconds?: number
    error?: {
      message?: string
    }
  }
}
