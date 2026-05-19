import type {
  AddonAuthField,
  AddonManifest,
  AddonRoute,
} from '../services/marketplaceClient'

type Translate = (key: string) => string
type TranslationExists = (key: string) => boolean

const MARKETPLACE_ERROR_KEYS: Record<string, string> = {
  'Failed to load marketplace': 'marketplace.errors.load',
  'Failed to load marketplace add-ons': 'marketplace.errors.loadAddons',
  'Failed to load add-on detail': 'marketplace.errors.loadDetail',
  'Marketplace add-on version is unavailable': 'marketplace.errors.versionUnavailable',
  'Failed to install marketplace add-on': 'marketplace.errors.install',
  'Failed to install add-on': 'marketplace.errors.install',
  'Failed to uninstall marketplace add-on': 'marketplace.errors.uninstall',
  'Failed to uninstall add-on': 'marketplace.errors.uninstall',
}

export type LocalizedAddonAuthField = AddonAuthField & {
  label: string
  placeholder?: string
}

export type LocalizedAddonRoute = AddonRoute & {
  summary?: string
}

function keyPart(value: string): string {
  return value.replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'unknown'
}

function addonBaseKey(addonId: string): string {
  return `marketplace.addons.${keyPart(addonId)}`
}

function translateOrFallback(
  t: Translate,
  te: TranslationExists,
  key: string,
  fallback: string,
): string {
  return te(key) ? t(key) : fallback
}

export function localizeAddonName(
  addon: AddonManifest,
  t: Translate,
  te: TranslationExists,
): string {
  return translateOrFallback(t, te, `${addonBaseKey(addon.id)}.name`, addon.name)
}

export function localizeAddonDescription(
  addon: AddonManifest,
  t: Translate,
  te: TranslationExists,
): string {
  return translateOrFallback(t, te, `${addonBaseKey(addon.id)}.description`, addon.description)
}

export function localizeAddonCategory(
  addon: AddonManifest,
  t: Translate,
  te: TranslationExists,
): string {
  return translateOrFallback(t, te, `${addonBaseKey(addon.id)}.category`, addon.category)
}

export function localizeAddonAuthField(
  addonId: string,
  field: AddonAuthField,
  t: Translate,
  te: TranslationExists,
): LocalizedAddonAuthField {
  const baseKey = `${addonBaseKey(addonId)}.auth.${keyPart(field.id)}`
  return {
    ...field,
    label: translateOrFallback(t, te, `${baseKey}.label`, field.label),
    placeholder: field.placeholder
      ? translateOrFallback(t, te, `${baseKey}.placeholder`, field.placeholder)
      : field.placeholder,
  }
}

export function localizeAddonFieldType(
  fieldType: string,
  t: Translate,
  te: TranslationExists,
): string {
  return translateOrFallback(
    t,
    te,
    `marketplace.fieldTypes.${keyPart(fieldType)}`,
    fieldType,
  )
}

export function localizeAddonRoute(
  addonId: string,
  route: AddonRoute,
  t: Translate,
  te: TranslationExists,
): LocalizedAddonRoute {
  const baseKey = `${addonBaseKey(addonId)}.routes.${keyPart(route.id)}`
  return {
    ...route,
    summary: route.summary
      ? translateOrFallback(t, te, `${baseKey}.summary`, route.summary)
      : route.summary,
  }
}

export function localizeAddonWidget(
  addonId: string,
  widgetId: string,
  t: Translate,
  te: TranslationExists,
): string {
  return translateOrFallback(
    t,
    te,
    `${addonBaseKey(addonId)}.widgets.${keyPart(widgetId)}`,
    widgetId,
  )
}

export function localizeAddonSiemEventType(
  addonId: string,
  eventType: string,
  t: Translate,
  te: TranslationExists,
): string {
  return translateOrFallback(
    t,
    te,
    `${addonBaseKey(addonId)}.siemEventTypes.${keyPart(eventType)}`,
    eventType,
  )
}

export function localizedAddonSearchText(
  addon: AddonManifest,
  t: Translate,
  te: TranslationExists,
): string {
  return [
    localizeAddonName(addon, t, te),
    localizeAddonCategory(addon, t, te),
    localizeAddonDescription(addon, t, te),
    addon.name,
    addon.vendor,
    addon.category,
    addon.description,
  ].join(' ')
}

export function localizeMarketplaceError(
  message: string,
  t: Translate,
  te: TranslationExists,
): string {
  const key = MARKETPLACE_ERROR_KEYS[message]
  if (!key) return message
  return translateOrFallback(t, te, key, message)
}
