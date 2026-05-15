export type AddonAuthField = {
  id: string
  label: string
  type: 'text' | 'url' | 'secret' | 'boolean' | 'number'
  required?: boolean
  default?: unknown
  placeholder?: string
}

export type AddonAuth = {
  kind: 'apiKey' | 'oauth2' | 'none'
  fields: AddonAuthField[]
}

export type AddonRoute = {
  id: string
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  path: string
  summary?: string
  params?: Array<{ name: string, repeated?: boolean, required?: boolean }>
}

export type AddonManifest = {
  id: string
  version: string
  name: string
  vendor: string
  category: string
  description: string
  icon?: string
  minDashboardVersion?: string
  provider: { type: string, auth: AddonAuth }
  routes: AddonRoute[]
  widgets: string[]
  siemEventTypes: string[]
  installed?: boolean
  installedVersion?: string | null
}

type ListResponse = { items: AddonManifest[], count: number, catalogError?: string | null }

export async function listMarketplaceAddons(): Promise<AddonManifest[]> {
  const response = await fetch('/api/marketplace/addons', { credentials: 'include' })
  if (!response.ok) throw new Error('Failed to load marketplace add-ons')
  const data = (await response.json()) as ListResponse
  return data.items ?? []
}

export async function getMarketplaceAddon(addonId: string): Promise<AddonManifest> {
  const response = await fetch(`/api/marketplace/addons/${encodeURIComponent(addonId)}`, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Failed to load add-on detail')
  return (await response.json()) as AddonManifest
}

export async function installMarketplaceAddon(
  addonId: string,
  version: string,
): Promise<void> {
  const response = await fetch(
    `/api/marketplace/addons/${encodeURIComponent(addonId)}/install`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    },
  )
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? 'Failed to install add-on')
  }
}
