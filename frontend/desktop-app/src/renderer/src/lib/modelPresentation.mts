import type { ModelEntry } from '../hooks/useModels'

export function modelGroupLabel(model: Pick<ModelEntry, 'provider_name' | 'provider_id' | 'category'>): string {
  const providerName = model.provider_name?.trim() ?? ''
  const providerId = model.provider_id?.trim().toLowerCase() ?? ''
  if (providerName === '' || providerId === 'custom' || providerName === '其他') return 'Others'
  return providerName || model.category?.trim() || 'Others'
}

export function groupModelsByProvider(models: ModelEntry[]): Array<[string, ModelEntry[]]> {
  const groups = new Map<string, ModelEntry[]>()
  for (const model of models) {
    const label = modelGroupLabel(model)
    const entries = groups.get(label) ?? []
    entries.push(model)
    groups.set(label, entries)
  }
  return [...groups.entries()]
}
