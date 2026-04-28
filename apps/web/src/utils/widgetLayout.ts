import type { WidgetDefaultSize, WidgetLayout, WorkspaceWidget } from '../types/dashboard'

const GRID_COLUMN_PX = 100
const GRID_ROW_PX = 90
const GRID_PADDING_PX = 20
const GRID_UNIT_THRESHOLD = 24

type CreateWidgetInstanceOptions = {
  catalogId: string
  integrationId: string
  defaultSize?: WidgetDefaultSize
  instanceId?: string
  zIndex: number
}

function isGridUnitSize(w: number, h: number) {
  return w > 0 && h > 0 && w <= GRID_UNIT_THRESHOLD && h <= GRID_UNIT_THRESHOLD
}

function gridSizeToPixels(size: WidgetDefaultSize) {
  return {
    w: size.w * GRID_COLUMN_PX + GRID_PADDING_PX,
    h: size.h * GRID_ROW_PX + GRID_PADDING_PX,
  }
}

export function normalizeWidgetLayout(layout: WidgetLayout): WidgetLayout {
  const normalized = {
    x: Number(layout.x) || 0,
    y: Number(layout.y) || 0,
    w: Number(layout.w) || 320,
    h: Number(layout.h) || 240,
    z: Number(layout.z) || 10,
  }

  if (!isGridUnitSize(normalized.w, normalized.h)) {
    return normalized
  }

  return {
    ...normalized,
    ...gridSizeToPixels({ w: normalized.w, h: normalized.h }),
  }
}

export function normalizeWorkspaceWidgets(widgets: WorkspaceWidget[]): WorkspaceWidget[] {
  return widgets.map((widget) => ({
    ...widget,
    layout: normalizeWidgetLayout(widget.layout),
  }))
}

export function createWidgetInstance({
  catalogId,
  integrationId,
  defaultSize = { w: 3, h: 2 },
  instanceId = `w_${Math.random().toString(36).slice(2, 11)}`,
  zIndex,
}: CreateWidgetInstanceOptions): WorkspaceWidget {
  return {
    instanceId,
    catalogId,
    integrationId,
    layout: {
      x: 50,
      y: 50,
      ...gridSizeToPixels(defaultSize),
      z: zIndex,
    },
  }
}
