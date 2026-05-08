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
  integrationType?: string
  requiredCapabilities: string[]
  defaultSize: WidgetDefaultSize
  dataEndpoint: string
}

export type WidgetFieldBinding = {
  fieldId: string
  label: string
  type: string
  unit?: string
  source: string
  provider?: string
  integrationType?: string
  integrationId?: string
  groupId?: string
  groupName?: string
}

export type WorkspaceWidget = {
  instanceId: string
  catalogId: string
  integrationId: string
  layout: WidgetLayout
  fieldBindings?: WidgetFieldBinding[]
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
    refreshIntervalSeconds?: number
    error?: {
      message?: string
    }
  }
}

export type WidgetDataErrorKind = 'widget_error' | 'network' | 'invalid_connection'
