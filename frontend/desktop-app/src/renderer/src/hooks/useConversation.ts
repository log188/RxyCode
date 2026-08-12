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
import type {
  ApprovalRequest,
  ApprovalResponse,
  InterruptRequest,
  ProtocolClient
} from '@rxycode/protocol-client'
import {
  addApprovalRequest,
  addSession,
  addUserMessage,
  applyError,
  applyPromptResult,
  applyProtocolNotification,
  beginAssistantMessage,
  beginMentionDispatch,
  createInitialState,
  hydrateChildSessions,
  hydrateSessions,
  parseLeadingAgentMentions,
  purgeSession,
  replaySessionEvents,
  renameSession,
  removeApprovalRequest,
  restoreSession,
  selectSession as selectSessionReducer,
  setSessionModel,
  trashSession,
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
import { PerformanceTraceRegistry, publishPerformanceTrace } from '../lib/performanceTrace.mts'

export interface UseConversationResult {
  state: ConversationState
  connectionError: string | null
  protocolClient: ProtocolClient | null
  approvalRules: ApprovalRule[]
  createSession: () => Promise<void>
  selectSession: (sessionId: string) => void
  renameSession: (sessionId: string, title: string) => Promise<boolean>
  trashSession: (sessionId: string) => Promise<boolean>
  restoreSession: (sessionId: string) => Promise<boolean>
  purgeSession: (sessionId: string) => Promise<boolean>
  setSessionModel: (sessionId: string, modelId: string, providerId?: string | null) => Promise<boolean>
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
  const [protocolClient, setProtocolClient] = useState<ProtocolClient | null>(null)
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
  const performanceTraceRef = useRef(new PerformanceTraceRegistry())

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
    const sessionId = typeof params === 'object' && params !== null &&
      typeof (params as Record<string, unknown>).session_id === 'string'
      ? String((params as Record<string, unknown>).session_id)
      : null
    if (sessionId !== null) {
      const trace = performanceTraceRef.current
      if (method === 'event/job_status') trace.mark(sessionId, 'worker_bootstrap')
      if (method === 'event/message_delta') {
        trace.mark(sessionId, 'model_request')
        trace.mark(sessionId, 'first_token')
      }
      if (method === 'event/tool_begin') trace.mark(sessionId, 'tool_begin')
      if (method.startsWith('event/recovery_')) trace.mark(sessionId, 'recovery')
      if (method === 'event/final') {
        trace.mark(sessionId, 'final')
        const publish = (): void => {
          trace.mark(sessionId, 'renderer_paint')
          publishPerformanceTrace(trace.snapshot())
        }
        if (typeof requestAnimationFrame === 'function') requestAnimationFrame(publish)
        else publish()
      }
    }
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
        .then(async () => {
          if (connectionRef.current !== connection) return
          const client = connection.client
          setProtocolClient(client)
          setConnectionError(null)
          if (client === null) return
          let sessionsForReplay: Array<{ sessionId: string }> = stateRef.current.sessions
            .map((session) => ({ sessionId: session.sessionId }))
          try {
            const taskList = await client.requestWithTimeout<{
              sessions: Array<Record<string, unknown>>
            }>('sessions/list', { include_trashed: true }, 10_000)
            sessionsForReplay = taskList.sessions
              .filter((item) => typeof item.session_id === 'string' && String(item.session_id) !== '')
              .map((item) => ({ sessionId: String(item.session_id) }))
            setState((current) =>
              hydrateSessions(
                current,
                taskList.sessions.map((item) => ({
                  session_id: String(item.session_id ?? ''),
                  title: typeof item.title === 'string' ? item.title : undefined,
                  workspace_root: String(item.workspace_root ?? ''),
                  model_id: typeof item.model_id === 'string' ? item.model_id : null,
                  provider_id: typeof item.provider_id === 'string' ? item.provider_id : null,
                  status: typeof item.status === 'string' ? item.status as never : undefined,
                  created_at: typeof item.created_at === 'string' ? item.created_at : undefined,
                  updated_at: typeof item.updated_at === 'string' ? item.updated_at : undefined,
                  trashed_at: item.trashed_at === null || typeof item.trashed_at === 'string'
                    ? item.trashed_at
                    : null
                }))
              )
            )
          } catch {
            // Desktop task persistence is a minor-version extension. A
            // pre-extension appserver still keeps the in-memory task created
            // by the renderer, so attachment remains usable.
          }
          for (const session of sessionsForReplay) {
            const rootSessionId = session.sessionId
            const sessionCursor = stateRef.current.sessionEventCursorBySession[rootSessionId] ?? 0
            try {
              let replay = await client.requestWithTimeout<{
                events: Array<{
                  seq: number
                  method: string
                  params: Record<string, unknown>
                }>
                next_cursor: number
                gap_detected: boolean
              }>('session/events', {
                session_id: rootSessionId,
                cursor: sessionCursor
              }, 10_000)
              if (replay.gap_detected) {
                // The task store is append-only. Replaying from zero is the
                // authoritative repair path when a cursor gap is detected.
                replay = await client.requestWithTimeout<{
                  events: Array<{
                    seq: number
                    method: string
                    params: Record<string, unknown>
                  }>
                  next_cursor: number
                  gap_detected: boolean
                }>('session/events', { session_id: rootSessionId, cursor: 0 }, 10_000)
              }
              setState((current) => replaySessionEvents(
                current,
                rootSessionId,
                replay.events,
                replay.next_cursor,
                replay.gap_detected
              ))
            } catch (error) {
              const message = error instanceof Error ? error.message : String(error)
              setConnectionError(`session event recovery failed: ${message}`)
            }
            const cursor = stateRef.current.childEventCursorByRoot[rootSessionId] ?? 0
            try {
              const replay = await client.requestWithTimeout<{
                events: Record<string, unknown>[]
                next_cursor: number
                gap_detected: boolean
              }>('child_sessions/events', {
                root_session_id: rootSessionId,
                cursor
              }, 10_000)
              setState((current) =>
                replay.events.reduce((next, event) => {
                  const method = typeof event.event_name === 'string' ? event.event_name : ''
                  return method.startsWith('child_session/')
                    ? applyProtocolNotification(next, method, event)
                    : next
                }, current)
              )
              if (replay.gap_detected) {
                const snapshot = await client.requestWithTimeout<{
                  sessions: Record<string, unknown>[]
                }>('child_sessions/list', { root_session_id: rootSessionId }, 10_000)
                setState((current) =>
                  hydrateChildSessions(
                    current,
                    rootSessionId,
                    snapshot.sessions,
                    replay.next_cursor
                  )
                )
              }
            } catch (error) {
              const message = error instanceof Error ? error.message : String(error)
              setConnectionError(`child session recovery failed: ${message}`)
            }
          }
        })
        .catch((error: unknown) => {
          const message = error instanceof Error ? error.message : String(error)
          console.error('initialize failed', error)
          setConnectionError(message)
        })
    } else {
      connection.detach('appserver not running')
      setProtocolClient(null)
      queueMicrotask(() => setConnectionError(null))
    }
  }, [platform, info, status, handleNotification, handleServerRequest, handleServerRequestAborted])

  // The status effect above supplies user-facing detach reasons. Only the
  // actual component unmount needs an additional transport cleanup.
  useEffect(() => {
    return () => {
      connectionRef.current?.detach('conversation unmounted')
      connectionRef.current = null
    }
  }, [])

  const createSession = useCallback(async (): Promise<void> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined || info === null) return
    try {
      const created = await client.requestWithTimeout<{
        session_id: string
        workspace_root: string
        model_id?: string | null
        provider_id?: string | null
      }>('session/new', { workspace_root: workspaceRootOverride ?? info.repoRoot }, 10_000)
      setState((current) =>
        addSession(current, {
          sessionId: created.session_id,
          workspaceRoot: created.workspace_root,
          modelId: created.model_id ?? null,
          providerId: created.provider_id ?? null
        })
      )
    } catch (error) {
      console.error('session/new failed', error)
    }
  }, [info, workspaceRootOverride])

  const selectSession = useCallback((sessionId: string): void => {
    setState((current) => selectSessionReducer(current, sessionId))
  }, [])

  const renameTask = useCallback(async (sessionId: string, title: string): Promise<boolean> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined) return false
    try {
      await client.requestWithTimeout('session/rename', { session_id: sessionId, title }, 10_000)
      setState((current) => renameSession(current, sessionId, title))
      return true
    } catch {
      return false
    }
  }, [])

  const trashTask = useCallback(async (sessionId: string): Promise<boolean> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined) return false
    try {
      await client.requestWithTimeout('session/trash', { session_id: sessionId }, 10_000)
      setState((current) => trashSession(current, sessionId))
      return true
    } catch {
      return false
    }
  }, [])

  const restoreTask = useCallback(async (sessionId: string): Promise<boolean> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined) return false
    try {
      await client.requestWithTimeout('session/restore', { session_id: sessionId }, 10_000)
      setState((current) => restoreSession(current, sessionId))
      return true
    } catch {
      return false
    }
  }, [])

  const purgeTask = useCallback(async (sessionId: string): Promise<boolean> => {
    const client = connectionRef.current?.client
    if (client === null || client === undefined) return false
    try {
      await client.requestWithTimeout('session/purge', { session_id: sessionId }, 10_000)
      setState((current) => purgeSession(current, sessionId))
      return true
    } catch {
      return false
    }
  }, [])

  const setTaskModel = useCallback(
    async (sessionId: string, modelId: string, providerId: string | null = null): Promise<boolean> => {
      const client = connectionRef.current?.client
      if (client === null || client === undefined) return false
      if (stateRef.current.runningBySession[sessionId] === true) return false
      try {
        const result = await client.requestWithTimeout<{ ok?: boolean; provider_id?: string | null }>(
          'session/set_model',
          { session_id: sessionId, model_id: modelId },
          30_000
        )
        if (result.ok !== true) return false
        setState((current) => setSessionModel(current, sessionId, modelId, result.provider_id ?? providerId))
        return true
      } catch {
        return false
      }
    },
    []
  )
  const sendMessage = useCallback(async (text: string): Promise<void> => {
    const client = connectionRef.current?.client
    const trimmed = text.trim()
    const sessionId = stateRef.current.activeSessionId
    if (client === null || client === undefined || sessionId === null || trimmed === '') return
    if (stateRef.current.runningBySession[sessionId] === true) return
    const trace = performanceTraceRef.current
    trace.startRun(sessionId)
    trace.mark(sessionId, 'send_click')
    const mention = parseLeadingAgentMentions(trimmed)
    if (mention !== null) {
      if (mention.prompt === '') {
        setState((current) => applyError(current, sessionId, 'An @agent mention requires a task prompt.'))
        return
      }
      setState((current) =>
        beginMentionDispatch(
          beginAssistantMessage(addUserMessage(current, sessionId, trimmed), sessionId),
          sessionId,
          mention.agentIds
        )
      )
      try {
        await Promise.all(
          mention.agentIds.map(async (agentId) =>
            client.requestWithTimeout(
              'agent/invoke',
              {
                agent_id: agentId,
                prompt: mention.prompt,
                parent_session_id: sessionId,
                request_id: crypto.randomUUID()
              },
              10_000
            )
          )
        )
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        setState((current) => applyError(current, sessionId, message))
      }
      return
    }
    setState((current) => addUserMessage(current, sessionId, trimmed))
    setState((current) => beginAssistantMessage(current, sessionId))
    try {
      trace.mark(sessionId, 'rpc_sent')
      const result = await client.requestWithTimeout<{
        run_id: string
        status: string
        text: string
      // Complex agent runs routinely exceed two minutes. The appserver owns
      // stall detection and cancellation; this is only a final transport
      // safety net so the renderer cannot retain a request forever.
      }>('session/prompt', { session_id: sessionId, text: trimmed }, 15 * 60_000)
      trace.mark(sessionId, 'rpc_received')
      trace.mark(sessionId, 'final')
      trace.mark(sessionId, 'renderer_paint')
      publishPerformanceTrace(trace.snapshot())
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
    protocolClient,
    approvalRules,
    createSession,
    selectSession,
    renameSession: renameTask,
    trashSession: trashTask,
    restoreSession: restoreTask,
    purgeSession: purgeTask,
    setSessionModel: setTaskModel,
    sendMessage,
    interrupt,
    resolveApproval,
    saveAlwaysAllowRule,
    revokeApprovalRule,
    dismissApproval
  }
}
