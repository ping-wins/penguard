import type { WidgetFieldBinding } from '../types/dashboard'

export const PROVIDER_FIELD_DRAG_MIME = 'application/x-penguard-provider-field'

export function serializeFieldBinding(binding: WidgetFieldBinding) {
  return JSON.stringify(binding)
}

export function parseFieldBindingTransfer(dataTransfer: DataTransfer | null): WidgetFieldBinding | null {
  if (!dataTransfer) return null
  const raw = dataTransfer.getData(PROVIDER_FIELD_DRAG_MIME)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    if (
      typeof parsed.fieldId !== 'string'
      || typeof parsed.label !== 'string'
      || typeof parsed.type !== 'string'
      || typeof parsed.source !== 'string'
    ) {
      return null
    }
    return {
      fieldId: parsed.fieldId,
      label: parsed.label,
      type: parsed.type,
      unit: typeof parsed.unit === 'string' ? parsed.unit : undefined,
      source: parsed.source,
      provider: typeof parsed.provider === 'string' ? parsed.provider : undefined,
      integrationType: typeof parsed.integrationType === 'string' ? parsed.integrationType : undefined,
      integrationId: typeof parsed.integrationId === 'string' ? parsed.integrationId : undefined,
      groupId: typeof parsed.groupId === 'string' ? parsed.groupId : undefined,
      groupName: typeof parsed.groupName === 'string' ? parsed.groupName : undefined,
    }
  } catch (e) {
    return null
  }
}
