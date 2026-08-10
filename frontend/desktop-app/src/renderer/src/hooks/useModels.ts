/**
 * Phase 4 D5: model / credential management via appserver JSON-RPC.
 *
 * Talks only through the shared ProtocolClient (DC1). Owns its own
 * ConversationConnection so it does not interfere with the chat
 * connection; attach() runs `initialize` which now advertises the
 * `models` / `credentials` capabilities.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  createConversationConnection,
  type AppserverInfo,
  type AppserverPlatform,
  type ConversationConnection
} from '../../../platform/index.mts'

export interface ModelEntry {
  id: string
  name: string
  nickname: string
  provider_model_id: string
  base_url: string
  active: boolean
  category: string
  provider_name: string
  provider_id: string
  max_tokens_mode?: string
  resolved_max_tokens?: number | null
  limit_source?: string
  context_window?: number | null
  warning?: string | null
}

export interface ModelsSnapshot {
  models: ModelEntry[]
  active: string
  recent: string[]
}

export interface ProviderPreset {
  id: string
  name: string
  base_url: string
  category?: string
}

export interface DiscoveredModel {
  id: string
  object?: string
}

export interface OnboardResult {
  ok: boolean
  error_code?: string
  message?: string
  id?: string
  onboarded?: string[]
  failed?: Array<{ id: string; reason: string }>
}

export interface UseModelsOptions {
  platform: AppserverPlatform
  info: AppserverInfo | null
  status: 'stopped' | 'starting' | 'running' | 'crashed'
  refreshKey: number
}

export interface UseModelsResult {
  supported: boolean
  loading: boolean
  error: string | null
  snapshot: ModelsSnapshot | null
  refresh(): Promise<void>
  setActive(id: string): Promise<boolean>
  remove(id: string): Promise<boolean>
  upsertCredential(id: string, apiKey: string): Promise<boolean>
  deleteCredential(id: string): Promise<boolean>
  testConnection(id: string): Promise<{ ok: boolean; message: string }>
  listPresets(): Promise<ProviderPreset[]>
  discover(apiKey: string, baseUrl: string): Promise<DiscoveredModel[]>
  onboard(args: {
    providerModelId: string
    apiKey: string
    baseUrl: string
    nickname?: string
  }): Promise<OnboardResult>
  onboardBatch(args: {
    apiKey: string
    baseUrl: string
    modelIds: string[]
    skipProbe?: boolean
  }): Promise<OnboardResult>
}

export function useModels({
  platform,
  info,
  status,
  refreshKey
}: UseModelsOptions): UseModelsResult {
  const connectionRef = useRef<ConversationConnection | null>(null)
  const [supported, setSupported] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [snapshot, setSnapshot] = useState<ModelsSnapshot | null>(null)

  // Own connection lifecycle: attach when running, detach otherwise.
  useEffect(() => {
    if (status !== 'running' || info === null) {
      connectionRef.current?.detach(`appserver ${status}`)
      connectionRef.current = null
      return
    }
    if (connectionRef.current === null) {
      connectionRef.current = createConversationConnection({
        platform,
        onNotification: () => {}
      })
    }
    void connectionRef.current.attach(info)
    return () => {
      connectionRef.current?.detach('useModels teardown')
      connectionRef.current = null
    }
  }, [platform, info, status])

  const refresh = useCallback(async () => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined || status !== 'running') return
    setLoading(true)
    setError(null)
    try {
      const list = (await client.requestWithTimeout(
        'models/list',
        {},
        30_000
      )) as Record<string, unknown>
      setSupported(true)
      setSnapshot({
        models: (list.models ?? []) as ModelEntry[],
        active: String(list.active ?? ''),
        recent: (list.recent ?? []) as string[]
      })
    } catch (e) {
      // method-not-found / pre-D5 server: keep the BLOCKED panel visible.
      setSupported(false)
      setSnapshot(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => {
    void refresh()
  }, [refresh, refreshKey, status])

  const setActive = useCallback(
    async (id: string): Promise<boolean> => {
      const client = connectionRef.current?.client
      if (client === null || client === undefined) return false
      try {
        const r = (await client.requestWithTimeout('models/set_active', { id }, 30_000)) as {
          ok?: boolean
        }
        if (r.ok === true) await refresh()
        return r.ok === true
      } catch {
        return false
      }
    },
    [refresh]
  )

  const remove = useCallback(
    async (id: string): Promise<boolean> => {
      const client = connectionRef.current?.client
      if (client === null || client === undefined) return false
      try {
        const r = (await client.requestWithTimeout('models/remove', { id }, 30_000)) as {
          ok?: boolean
        }
        if (r.ok === true) await refresh()
        return r.ok === true
      } catch {
        return false
      }
    },
    [refresh]
  )

  const upsertCredential = useCallback(async (id: string, apiKey: string): Promise<boolean> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined) return false
    try {
      const r = (await client.requestWithTimeout('credentials/upsert', { id, api_key: apiKey }, 30_000)) as {
        ok?: boolean
      }
      return r.ok === true
    } catch {
      return false
    }
  }, [])

  const deleteCredential = useCallback(async (id: string): Promise<boolean> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined) return false
    try {
      const r = (await client.requestWithTimeout('credentials/delete', { id }, 30_000)) as {
        ok?: boolean
      }
      return r.ok === true
    } catch {
      return false
    }
  }, [])

  const testConnection = useCallback(
    async (id: string): Promise<{ ok: boolean; message: string }> => {
      const client = connectionRef.current?.client
      if (client === null || client === undefined) {
        return { ok: false, message: 'appserver not connected' }
      }
      try {
        const r = (await client.requestWithTimeout('models/test_connection', { id }, 30_000)) as {
          ok?: boolean
          message?: string
        }
        return { ok: r.ok === true, message: String(r.message ?? '') }
      } catch (e) {
        return { ok: false, message: e instanceof Error ? e.message : String(e) }
      }
    },
    []
  )

  const listPresets = useCallback(async (): Promise<ProviderPreset[]> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined) return []
    try {
      const r = (await client.requestWithTimeout('models/presets', {}, 30_000)) as {
        presets?: ProviderPreset[]
      }
      return r.presets ?? []
    } catch {
      return []
    }
  }, [])

  const discover = useCallback(
    async (apiKey: string, baseUrl: string): Promise<DiscoveredModel[]> => {
      const client = connectionRef.current?.client
      if (client === null || client === undefined) return []
      try {
        const r = (await client.requestWithTimeout(
          'models/discover',
          { api_key: apiKey, base_url: baseUrl },
          30_000
        )) as { ok?: boolean; models?: DiscoveredModel[] }
        if (r.ok === false) return []
        return r.models ?? []
      } catch {
        return []
      }
    },
    []
  )

  const onboard = useCallback(
    async (args: {
      providerModelId: string
      apiKey: string
      baseUrl: string
      nickname?: string
    }): Promise<OnboardResult> => {
      const client = connectionRef.current?.client
      if (client === null || client === undefined) {
        return { ok: false, error_code: 'transport', message: 'appserver not connected' }
      }
      try {
        const r = (await client.requestWithTimeout(
          'models/onboard',
          {
            provider_model_id: args.providerModelId,
            api_key: args.apiKey,
            base_url: args.baseUrl,
            nickname: args.nickname
          },
          30_000
        )) as OnboardResult
        if (r.ok === true) await refresh()
        return r
      } catch (e) {
        return { ok: false, error_code: 'transport', message: e instanceof Error ? e.message : String(e) }
      }
    },
    [refresh]
  )

  const onboardBatch = useCallback(
    async (args: {
      apiKey: string
      baseUrl: string
      modelIds: string[]
      skipProbe?: boolean
    }): Promise<OnboardResult> => {
      const client = connectionRef.current?.client
      if (client === null || client === undefined) {
        return { ok: false, error_code: 'transport', message: 'appserver not connected' }
      }
      try {
        const r = (await client.requestWithTimeout(
          'models/onboard_batch',
          {
            api_key: args.apiKey,
            base_url: args.baseUrl,
            model_ids: args.modelIds,
            skip_probe: args.skipProbe ?? true
          },
          60_000
        )) as OnboardResult
        if (r.ok === true) await refresh()
        return r
      } catch (e) {
        return { ok: false, error_code: 'transport', message: e instanceof Error ? e.message : String(e) }
      }
    },
    [refresh]
  )

  return {
    supported,
    loading,
    error,
    snapshot,
    refresh,
    setActive,
    remove,
    upsertCredential,
    deleteCredential,
    testConnection,
    listPresets,
    discover,
    onboard,
    onboardBatch
  }
}
