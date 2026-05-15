import type { WidgetDefaultSize, WidgetLayout, WorkspaceWidget } from '../types/dashboard'

const GRID_COLUMN_PX = 100
const GRID_ROW_PX = 90
const GRID_PADDING_PX = 20
const GRID_UNIT_THRESHOLD = 24

export type WidgetSizeConstraints = {
  minW: number
  minH: number
  maxW: number
  maxH: number
}

const DEFAULT_WIDGET_SIZE_CONSTRAINTS: WidgetSizeConstraints = {
  minW: 280,
  minH: 190,
  maxW: 900,
  maxH: 680,
}

const WIDGET_SIZE_CONSTRAINTS: Record<string, WidgetSizeConstraints> = {
  'visual-template-card': { minW: 220, minH: 160, maxW: 460, maxH: 320 },
  'visual-template-gauge': { minW: 260, minH: 240, maxW: 520, maxH: 440 },
  'visual-template-table': { minW: 420, minH: 300, maxW: 960, maxH: 720 },
  'visual-template-bar': { minW: 380, minH: 260, maxW: 880, maxH: 560 },
  'visual-template-line': { minW: 380, minH: 260, maxW: 880, maxH: 560 },
  'visual-template-feed': { minW: 400, minH: 320, maxW: 840, maxH: 700 },
  'visual-template-list': { minW: 400, minH: 320, maxW: 840, maxH: 700 },
  'fortigate-system-status': { minW: 360, minH: 240, maxW: 760, maxH: 560 },
  'fortigate-kpi-sessions': { minW: 260, minH: 180, maxW: 480, maxH: 360 },
  'fortigate-network-traffic': { minW: 440, minH: 320, maxW: 960, maxH: 720 },
  'fortigate-firewall-policies': { minW: 440, minH: 320, maxW: 960, maxH: 720 },
  'fortigate-top-threats': { minW: 440, minH: 320, maxW: 960, maxH: 720 },
  'fortigate-risk-posture': { minW: 460, minH: 360, maxW: 820, maxH: 700 },
  'fortigate-interface-health': { minW: 440, minH: 340, maxW: 880, maxH: 700 },
  'fortigate-recent-events': { minW: 440, minH: 340, maxW: 880, maxH: 700 },
  'fortigate-anomaly-highlights': { minW: 420, minH: 320, maxW: 840, maxH: 680 },
  'soar-active-playbook-runs': { minW: 440, minH: 320, maxW: 900, maxH: 700 },
  'soar-playbook-run-history': { minW: 520, minH: 380, maxW: 980, maxH: 760 },
}

type CreateWidgetInstanceOptions = {
  catalogId: string
  integrationId: string
  defaultSize?: WidgetDefaultSize
  instanceId?: string
  zIndex: number
  position?: {
    x: number
    y: number
  }
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

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export function getWidgetSizeConstraints(catalogId: string): WidgetSizeConstraints {
  return WIDGET_SIZE_CONSTRAINTS[catalogId] ?? DEFAULT_WIDGET_SIZE_CONSTRAINTS
}

export function clampWidgetLayoutSize(
  layout: WidgetLayout,
  catalogId: string,
): WidgetLayout {
  const constraints = getWidgetSizeConstraints(catalogId)
  return {
    ...layout,
    w: clamp(Number(layout.w) || constraints.minW, constraints.minW, constraints.maxW),
    h: clamp(Number(layout.h) || constraints.minH, constraints.minH, constraints.maxH),
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
  position,
}: CreateWidgetInstanceOptions): WorkspaceWidget {
  return {
    instanceId,
    catalogId,
    integrationId,
    layout: {
      x: position?.x ?? 50,
      y: position?.y ?? 50,
      ...gridSizeToPixels(defaultSize),
      z: zIndex,
    },
  }
}
