/**
 * Workspace setting persistence for the Phase4-D5 settings page.
 *
 * Kept framework-agnostic and dependency-free so the load/save/normalize
 * rules are unit-testable with the Node built-in test runner (same pattern
 * as approvalPolicy.mts). The setting only records the user's explicit
 * workspace choice; the effective root for new sessions still falls back to
 * the appserver repo root when nothing was picked (DC1/DC2: no backend
 * logic is duplicated here, only a desktop-local UI preference).
 */

export const WORKSPACE_SETTINGS_STORAGE_KEY = 'rxycode.desktop.workspaceSettings.v1'

export interface WorkspaceSettings {
  workspaceRoot: string | null
}

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export const DEFAULT_WORKSPACE_SETTINGS: WorkspaceSettings = {
  workspaceRoot: null
}

export function normalizeWorkspaceRoot(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null
  const trimmed = value.trim()
  return trimmed === '' ? null : trimmed
}

export function loadWorkspaceSettings(storage: StorageLike): WorkspaceSettings {
  const raw = storage.getItem(WORKSPACE_SETTINGS_STORAGE_KEY)
  if (raw === null) return { ...DEFAULT_WORKSPACE_SETTINGS }
  try {
    const parsed = JSON.parse(raw) as unknown
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'workspaceRoot' in parsed &&
      (parsed as { workspaceRoot?: unknown }).workspaceRoot !== null &&
      typeof (parsed as { workspaceRoot?: unknown }).workspaceRoot !== 'string'
    ) {
      return { ...DEFAULT_WORKSPACE_SETTINGS }
    }
    const workspaceRoot = normalizeWorkspaceRoot(
      (parsed as { workspaceRoot?: unknown }).workspaceRoot as string | null | undefined
    )
    return { workspaceRoot }
  } catch {
    return { ...DEFAULT_WORKSPACE_SETTINGS }
  }
}

export function saveWorkspaceSettings(settings: WorkspaceSettings, storage: StorageLike): void {
  storage.setItem(WORKSPACE_SETTINGS_STORAGE_KEY, JSON.stringify(settings))
}

export function effectiveWorkspaceRoot(settings: WorkspaceSettings, fallbackRoot: string): string {
  return settings.workspaceRoot ?? fallbackRoot
}
