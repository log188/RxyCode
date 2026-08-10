/**
 * Bridges the Phase4-D2 main window to the appserver through the platform
 * adapter and @rxycode/protocol-client (DC1/DC3).
 *
 * This hook never touches window.api.* directly; it only depends on
 * AppserverPlatform and ConversationConnection from src/platform/. The
 * ProtocolClient is (re)created when the appserver transitions to
 * "running", and torn down when it leaves that state.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApprovalRequest, ApprovalResponse, InterruptRequest } from '@rxycode/protocol-client'
import {
  addApprovalRequest,
  addSession,
  addUserMessage,
  applyError,
  applyPromptResult,
  applyProtocolNotification,
  beginAssistantMessage,
  createInitialState,
  removeApprovalRequest,
  selectSession as selectSessionReducer,
  updateApprovalRequestStatus,
  type ConversationState
} from '../lib/conversationStore.mts'
import {
  createApprovalRule,
  findAutoApprovalRule,
  loadApprovalRules,
  saveApprovalRules,
  type ApprovalActionScope,
  type ApprovalExpiryHours,
  type ApprovalRiskLevel,
  type ApprovalRule
} from '../lib/approvalPolicy.mts'
import {
  createConversationConnection,
  type AppserverInfo,
  type AppserverPlatform,
  type AppserverStatus,
  type ConversationConnection
} from '../../../platform/index.mts'

export interface UseConversationResult {
  state: ConversationState
  connectionError: string | null
  approvalRules: ApprovalRule[]
  createSession: () => Promise<void>
  selectSession: (sessionId: string) => void
  sendMessage: (text: string) => Promise<void>
  interrupt: () => Promise<void>
  resolveApproval: (requestId: string, decision: 'approved' | 'rejected') => void
  saveAlwaysAllowRule: (
    requestId: string,
    scope: ApprovalActionScope,
    expiresInHours: ApprovalExpiryHours
  ) => void
  revokeApprovalRule: (ruleId: string) => void
  dismissApproval: (requestId: string) => void
}

export function useConversation(
  platform: AppserverPlatform,
  info: AppserverInfo | null,
  status: AppserverStatus,
  workspaceRootOverride: string | null = null
): UseConversationResult {
  const [state, setState] = useState<ConversationState>(createInitialState)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [approvalRules, setApprovalRules] = useState<ApprovalRule[]>(() =>
    loadApprovalRules(window.localStorage)
  )
  const stateRef = useRef(state)
  const connectionRef = useRef<ConversationConnection | null>(null)
  const infoRef = useRef(info)
  const approvalRulesRef = useRef(approvalRules)
  const pendingApprovalsRef = useRef(
    new Map<
      string,
      { resolve: (response: ApprovalResponse) => void; reject: (error: Error) => void }
    >()
  )

  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    infoRef.current = info
  }, [info])

  useEffect(() => {
    approvalRulesRef.current = approvalRules
  }, [approvalRules])

  const handleNotification = useCallback((method: string, params: unknown): void => {
    setState((current) => applyProtocolNotification(current, method, params))
  }, [])

  const workspaceRootForSession = useCallback((sessionId: string): string => {
    return (
      stateRef.current.sessions.find((session) => session.sessionId === sessionId)?.workspaceRoot ??
      infoRef.current?.repoRoot ??
      ''
    )
  }, [])

  const handleServerRequest = useCallback(
    async (method: string, params: unknown): Promise<unknown> => {
      if (method !== 'approval/request') {
        throw new Error(`unsupported server request: ${method}`)
      }
      const request = params as ApprovalRequest
      const workspaceRoot = workspaceRootForSession(request.session_id)
      const matched = findAutoApprovalRule(approvalRulesRef.current, request, workspaceRoot)
      if (matched !== null) {
        return { request_id: request.request_id, decision: 'approved' } satisfies ApprovalResponse
      }
      setState((current) => addApprovalRequest(current, request))
      return new Promise<ApprovalResponse>((resolve, reject) => {
        pendingApprovalsRef.current.set(request.request_id, { resolve, reject })
      })
    },
    [workspaceRootForSession]
  )

  const resolveApproval = useCallback(
    (requestId: string, decision: 'approved' | 'rejected'): void => {
      const entry = pendingApprovalsRef.current.get(requestId)
      if (entry === undefined) return
      pendingApprovalsRef.current.delete(requestId)
      entry.resolve({ request_id: requestId, decision })
      // Keep the modal visible in "submitting" until event/done removes it,
      // so the user can see the decision was sent and is being processed.
      setState((current) => updateApprovalRequestStatus(current, requestId, 'submitting'))
    },
    []
  )

  const saveAlwaysAllowRule = useCallback(
    (requestId: string, scope: ApprovalActionScope, expiresInHours: ApprovalExpiryHours): void => {
      const item = stateRef.current.approvals.find((approval) => approval.requestId === requestId)
      if (item === undefined) return
      const rule = createApprovalRule({
        workspaceRoot: workspaceRootForSession(item.sessionId),
        riskLevel: item.riskLevel as ApprovalRiskLevel,
        actionScope: scope,
        action: item.action,
        expiresInHours
      })
      const next = [...approvalRulesRef.current, rule]
      approvalRulesRef.current = next
      setApprovalRules(next)
      saveApprovalRules(next, window.localStorage)
      resolveApproval(requestId, 'approved')
    },
    [resolveApproval, workspaceRootForSession]
  )

  const revokeApprovalRule = useCallback((ruleId: string): void => {
    const next = approvalRulesRef.current.filter((rule) => rule.id !== ruleId)
    approvalRulesRef.current = next
    setApprovalRules(next)
    saveApprovalRules(next, window.localStorage)
  }, [])

  const dismissApproval = useCallback((requestId: string): void => {
    pendingApprovalsRef.current.delete(requestId)
    setState((current) => removeApprovalRequest(current, requestId))
  }, [])

  const handleServerRequestAborted = useCallback((error: Error): void => {
    const pending = [...pendingApprovalsRef.current.entries()]
    pendingApprovalsRef.current.clear()
    for (const [, entry] of pending) {
      entry.reject(error)
    }
    setState((current) => {
      let next = current
      for (const approval of next.approvals) {
        const requestId = approval.requestId
        next = updateApprovalRequestStatus(next, requestId, 'error', error.message)
      }
      return next
    })
  }, [])

  useEffect(() => {
    if (connectionRef.current === null) {
      connectionRef.current = createConversationConnection({
        platform,
        onNotification: handleNotification,
        onServerRequest: handleServerRequest,
        onServerRequestAborted: handleServerRequestAborted,
        onConnectionError: (error) => setConnectionError(error.message)
      })
    }
    const connection = connectionRef.current
    if (status === 'running' && info !== null) {
      void connection
        .attach(info)
        .then(() => setConnectionError(null))
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : String(error)
          console.error('initialize failed', error)
          setConnectionError(message)
        })
    } else {
      connection.detach('appserver not running')
      queueMicrotask(() => setConnectionError(null))
    }
  }, [platform, info, status, handleNotification, handleServerRequest, handleServerRequestAborted])

  const createSession = useCallback(async (): Promise<void> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined || info === null) return
    try {
      const created = await client.requestWithTimeout<{
        session_id: string
        workspace_root: string
      }>('session/new', { workspace_root: workspaceRootOverride ?? info.repoRoot }, 10_000)
      setState((current) =>
        addSession(current, {
          sessionId: created.session_id,
          workspaceRoot: created.workspace_root
        })
      )
    } catch (error) {
      console.error('session/new failed', error)
    }
  }, [info, workspaceRootOverride])

  const selectSession = useCallback((sessionId: string): void => {
    setState((current) => selectSessionReducer(current, sessionId))
  }, [])

  const sendMessage = useCallback(async (text: string): Promise<void> => {
    const client = connectionRef.current?.client
    const trimmed = text.trim()
    const sessionId = stateRef.current.activeSessionId
    if (client === null || client === undefined || sessionId === null || trimmed === '') return
    if (stateRef.current.runningBySession[sessionId] === true) return
    setState((current) => addUserMessage(current, sessionId, trimmed))
    setState((current) => beginAssistantMessage(current, sessionId))
    try {
      const result = await client.requestWithTimeout<{
        run_id: string
        status: string
        text: string
      }>('session/prompt', { session_id: sessionId, text: trimmed }, 120_000)
      setState((current) =>
        applyPromptResult(current, sessionId, {
          runId: result.run_id,
          status: result.status,
          text: result.text
        })
      )
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setState((current) => applyError(current, sessionId, message))
    }
  }, [])

  const interrupt = useCallback(async (): Promise<void> => {
    const client = connectionRef.current?.client
    const sessionId = stateRef.current.activeSessionId
    if (client === null || client === undefined || sessionId === null) return
    try {
      const params: InterruptRequest = { session_id: sessionId }
      await client.requestWithTimeout('session/interrupt', params, 10_000)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setState((current) => applyError(current, sessionId, message))
    }
  }, [])

  return {
    state,
    connectionError,
    approvalRules,
    createSession,
    selectSession,
    sendMessage,
    interrupt,
    resolveApproval,
    saveAlwaysAllowRule,
    revokeApprovalRule,
    dismissApproval
  }
}
