export type ModelsUnavailableReason = 'not-connected' | 'method-not-found' | 'error'

export interface ModelsUnavailableCopy {
  title: string
  detail: string
  blockedPrerequisite: boolean
}

export function classifyModelsListFailure(
  error: unknown,
  clientPresent: boolean
): ModelsUnavailableReason {
  if (!clientPresent) return 'not-connected'
  if (isMethodNotFound(error)) return 'method-not-found'
  return 'error'
}

function isMethodNotFound(error: unknown): boolean {
  if (
    error !== null &&
    typeof error === 'object' &&
    'code' in error &&
    (error as { code: unknown }).code === -32601
  ) {
    return true
  }
  const message = error instanceof Error ? error.message : String(error ?? '')
  return /method not found/i.test(message)
}

export function modelsUnavailableCopy(
  reason: ModelsUnavailableReason,
  error: string | null,
  kind: 'models' | 'credentials' = 'models'
): ModelsUnavailableCopy {
  if (reason === 'not-connected') {
    return {
      title:
        kind === 'models'
          ? '模型管理不可用（后端未连接）'
          : 'API Key 管理不可用（后端未连接）',
      detail: error
        ? `appserver 尚未连接：${error}`
        : 'appserver 尚未连接。请确认 Desktop 已启动捆绑的 Python 运行时；若刚安装，重启应用后再试。',
      blockedPrerequisite: false
    }
  }
  if (reason === 'method-not-found') {
    return {
      title:
        kind === 'models'
          ? '模型管理不可用（旧版 appserver）'
          : 'API Key 管理不可用（旧版 appserver）',
      detail:
        kind === 'models'
          ? '当前 appserver 未提供 models/* JSON-RPC 方法。请升级后端到支持模型管理的版本后再试。'
          : '当前 appserver 未提供 credentials/* JSON-RPC 方法。密钥由后端加密存储，桌面端只提交、不回显。',
      blockedPrerequisite: true
    }
  }
  return {
    title: kind === 'models' ? '模型管理不可用' : 'API Key 管理不可用',
    detail:
      error ||
      (kind === 'models' ? 'models/list 调用失败。' : '凭据接口调用失败。'),
    blockedPrerequisite: false
  }
}
