import type { WidgetDefaultSize } from '../types/dashboard'

export type VisualTemplateKind =
  | 'card'
  | 'gauge'
  | 'table'
  | 'bar'
  | 'line'
  | 'feed'
  | 'list'

export type VisualTemplate = {
  id: string
  title: string
  kind: VisualTemplateKind
  description: string
  defaultSize: WidgetDefaultSize
}

export const visualTemplates: VisualTemplate[] = [
  {
    id: 'visual-template-card',
    title: 'Card',
    kind: 'card',
    description: 'Single metric visual for one live field.',
    defaultSize: { w: 3, h: 2 },
  },
  {
    id: 'visual-template-gauge',
    title: 'Gauge',
    kind: 'gauge',
    description: 'Threshold visual for percentage or score fields.',
    defaultSize: { w: 3, h: 3 },
  },
  {
    id: 'visual-template-table',
    title: 'Table',
    kind: 'table',
    description: 'Structured rows for interfaces, policies, or events.',
    defaultSize: { w: 5, h: 4 },
  },
  {
    id: 'visual-template-bar',
    title: 'Bar Chart',
    kind: 'bar',
    description: 'Compare categorical FortiGate values.',
    defaultSize: { w: 5, h: 3 },
  },
  {
    id: 'visual-template-line',
    title: 'Line Chart',
    kind: 'line',
    description: 'Trend changing system and traffic values.',
    defaultSize: { w: 5, h: 3 },
  },
  {
    id: 'visual-template-feed',
    title: 'Event Feed',
    kind: 'feed',
    description: 'Chronological SOC events or threat logs.',
    defaultSize: { w: 5, h: 4 },
  },
  {
    id: 'visual-template-list',
    title: 'Signal List',
    kind: 'list',
    description: 'Grouped risk signals and anomaly highlights.',
    defaultSize: { w: 4, h: 4 },
  },
]

export const visualTemplatesById = Object.fromEntries(
  visualTemplates.map(template => [template.id, template]),
) as Record<string, VisualTemplate>

export function isVisualTemplateId(catalogId: string) {
  return Boolean(visualTemplatesById[catalogId])
}
