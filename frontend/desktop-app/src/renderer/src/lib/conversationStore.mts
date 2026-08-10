/**
 * Pure conversation/session state for the Phase4-D2 main window.
 *
 * Kept framework-agnostic and dependency-free (runtime) so the reducer
 * logic is unit-testable with the Node built-in test runner and stays
 * isolated from React and Electron (DC2/DC3).
 */
import type {
  ApprovalRequest,
  ErrorNotification,
  FinalAnswer,
  JobStatusUpdate,
  MessageDelta,
  RunComplete,
  ToolBegin,
  ToolEnd
} from '@rxycode/protocol-client'

export type MessageRole = 'user' | 'assistant'
export type MessageStatus = 'streaming' | 'complete' | 'error'
export type ToolCallStatus = 'running' | 'ok' | 'error'

export interface ChatMessage {
  id: string
  role: MessageRole
  text: string
  status?: MessageStatus
  runId?: string
}

export interface ToolCall {
  callId: string
  toolName: string
  arguments?: Record<string, unknown>
  status: ToolCallStatus
  summary?: string
}

export interface SessionEntry {
  sessionId: string
  title: string
  workspaceRoot: string
  createdAt: number
}

export interface ConversationState {
  sessions: SessionEntry[]
  activeSessionId: string | null
  messagesBySession: Record<string, ChatMessage[]>
  toolsBySession: Record<string, ToolCall[]>
  runningBySession: Record<string, boolean>
  errorBySession: Record<string, string | null>
  approvals: ApprovalRequestItem[]
}

export type ApprovalRequestStatus = 'pending' | 'submitting' | 'error'

export interface ApprovalRequestItem {
  requestId: string
  sessionId: string
  riskLevel: string
  action: string
  details?: Record<string, unknown>
  status: ApprovalRequestStatus
  error?: string
}

export interface NewSessionInput {
  sessionId: string
  workspaceRoot: string
  title?: string
  createdAt?: number
}

export interface PromptResult {
  runId: string
  status: string
  text: string
}

export function createInitialState(): ConversationState {
  return {
    sessions: [],
    activeSessionId: null,
    messagesBySession: {},
    toolsBySession: {},
    runningBySession: {},
    errorBySession: {},
    approvals: []
  }
}

function defaultTitle(sessionId: string): string {
  return `会话 ${sessionId.slice(0, 8)}`
}

function messagesFor(state: ConversationState, sessionId: string): ChatMessage[] {
  return state.messagesBySession[sessionId] ?? []
}

function toolsFor(state: ConversationState, sessionId: string): ToolCall[] {
  return state.toolsBySession[sessionId] ?? []
}

function nextMessageId(state: ConversationState, sessionId: string, role: MessageRole): string {
  return `${sessionId}:${role}:${messagesFor(state, sessionId).length}`
}

function withMessages(
  state: ConversationState,
  sessionId: string,
  messages: ChatMessage[]
): ConversationState {
  return {
    ...state,
    messagesBySession: { ...state.messagesBySession, [sessionId]: messages }
  }
}

export function addSession(state: ConversationState, input: NewSessionInput): ConversationState {
  if (state.sessions.some((session) => session.sessionId === input.sessionId)) {
    return state
  }
  const session: SessionEntry = {
    sessionId: input.sessionId,
    title: input.title ?? defaultTitle(input.sessionId),
    workspaceRoot: input.workspaceRoot,
    createdAt: input.createdAt ?? Date.now()
  }
  return {
    ...state,
    sessions: [...state.sessions, session],
    activeSessionId: state.activeSessionId ?? session.sessionId,
    messagesBySession: { ...state.messagesBySession, [session.sessionId]: [] },
    runningBySession: { ...state.runningBySession, [session.sessionId]: false },
    errorBySession: { ...state.errorBySession, [session.sessionId]: null }
  }
}

export function selectSession(state: ConversationState, sessionId: string): ConversationState {
  if (!state.sessions.some((session) => session.sessionId === sessionId)) {
    return state
  }
  if (state.activeSessionId === sessionId) {
    return state
  }
  return { ...state, activeSessionId: sessionId }
}

export function addUserMessage(
  state: ConversationState,
  sessionId: string,
  text: string
): ConversationState {
  const messages = [
    ...messagesFor(state, sessionId),
    {
      id: nextMessageId(state, sessionId, 'user'),
      role: 'user' as const,
      text,
      status: 'complete' as const
    }
  ]
  return {
    ...withMessages(state, sessionId, messages),
    errorBySession: { ...state.errorBySession, [sessionId]: null },
    sessions: state.sessions.map((session) =>
      session.sessionId === sessionId && session.title.startsWith('会话 ')
        ? { ...session, title: text.slice(0, 20) }
        : session
    )
  }
}

export function beginAssistantMessage(
  state: ConversationState,
  sessionId: string
): ConversationState {
  const messages = [
    ...messagesFor(state, sessionId),
    {
      id: nextMessageId(state, sessionId, 'assistant'),
      role: 'assistant' as const,
      text: '',
      status: 'streaming' as const
    }
  ]
  return {
    ...withMessages(state, sessionId, messages),
    runningBySession: { ...state.runningBySession, [sessionId]: true },
    errorBySession: { ...state.errorBySession, [sessionId]: null }
  }
}

export function applyMessageDelta(
  state: ConversationState,
  sessionId: string,
  delta: MessageDelta
): ConversationState {
  const messages = messagesFor(state, sessionId)
  const last = messages.at(-1)
  let next: ChatMessage[]
  if (last !== undefined && last.role === 'assistant' && last.status === 'streaming') {
    next = [...messages.slice(0, -1), { ...last, text: last.text + delta.text }]
  } else {
    next = [
      ...messages,
      {
        id: nextMessageId(state, sessionId, 'assistant'),
        role: 'assistant',
        text: delta.text,
        status: 'streaming'
      }
    ]
  }
  return {
    ...withMessages(state, sessionId, next),
    runningBySession: { ...state.runningBySession, [sessionId]: true }
  }
}

function completeAssistant(
  state: ConversationState,
  sessionId: string,
  text: string,
  runId: string
): ConversationState {
  const messages = messagesFor(state, sessionId)
  const last = messages.at(-1)
  const complete: ChatMessage = {
    id: last?.id ?? nextMessageId(state, sessionId, 'assistant'),
    role: 'assistant',
    text,
    status: 'complete',
    runId
  }
  const next =
    last !== undefined && last.role === 'assistant'
      ? [...messages.slice(0, -1), complete]
      : [...messages, complete]
  return {
    ...withMessages(state, sessionId, next),
    runningBySession: { ...state.runningBySession, [sessionId]: false },
    errorBySession: { ...state.errorBySession, [sessionId]: null }
  }
}

export function applyFinalAnswer(
  state: ConversationState,
  sessionId: string,
  final: FinalAnswer
): ConversationState {
  return completeAssistant(state, sessionId, final.text, final.run_id)
}

export function applyPromptResult(
  state: ConversationState,
  sessionId: string,
  result: PromptResult
): ConversationState {
  return completeAssistant(state, sessionId, result.text, result.runId)
}

export function applyError(
  state: ConversationState,
  sessionId: string,
  message: string
): ConversationState {
  const messages = messagesFor(state, sessionId)
  const last = messages.at(-1)
  if (last !== undefined && last.role === 'assistant' && last.status === 'error') {
    return {
      ...state,
      runningBySession: { ...state.runningBySession, [sessionId]: false },
      errorBySession: { ...state.errorBySession, [sessionId]: message }
    }
  }
  let next: ChatMessage[]
  if (last !== undefined && last.role === 'assistant' && last.status === 'streaming') {
    next = [...messages.slice(0, -1), { ...last, text: message, status: 'error' }]
  } else {
    next = [
      ...messages,
      {
        id: nextMessageId(state, sessionId, 'assistant'),
        role: 'assistant',
        text: message,
        status: 'error'
      }
    ]
  }
  return {
    ...withMessages(state, sessionId, next),
    runningBySession: { ...state.runningBySession, [sessionId]: false },
    errorBySession: { ...state.errorBySession, [sessionId]: message }
  }
}

export function setRunning(
  state: ConversationState,
  sessionId: string,
  running: boolean
): ConversationState {
  return {
    ...state,
    runningBySession: { ...state.runningBySession, [sessionId]: running }
  }
}

export function applyToolBegin(
  state: ConversationState,
  sessionId: string,
  tool: ToolBegin
): ConversationState {
  const tools = toolsFor(state, sessionId)
  const card: ToolCall = {
    callId: tool.call_id,
    toolName: tool.tool_name,
    arguments: tool.arguments,
    status: 'running'
  }
  const existing = tools.findIndex((entry) => entry.callId === tool.call_id)
  const next =
    existing >= 0
      ? [...tools.slice(0, existing), card, ...tools.slice(existing + 1)]
      : [...tools, card]
  return {
    ...state,
    toolsBySession: { ...state.toolsBySession, [sessionId]: next }
  }
}

export function applyToolEnd(
  state: ConversationState,
  sessionId: string,
  tool: ToolEnd
): ConversationState {
  const tools = toolsFor(state, sessionId)
  const index = tools.findIndex((entry) => entry.callId === tool.call_id)
  if (index < 0) return state
  const next = [...tools]
  next[index] = {
    ...tools[index]!,
    status: tool.ok ? 'ok' : 'error',
    summary: tool.summary
  }
  return {
    ...state,
    toolsBySession: { ...state.toolsBySession, [sessionId]: next }
  }
}

export function applyRunComplete(
  state: ConversationState,
  sessionId: string,
  done: RunComplete
): ConversationState {
  const messages = messagesFor(state, sessionId)
  const last = messages.at(-1)
  let next = messages
  if (last !== undefined && last.role === 'assistant' && last.status === 'streaming') {
    const failed = done.status === 'failed' || done.status === 'timed_out'
    next = [
      ...messages.slice(0, -1),
      {
        ...last,
        status: failed ? ('error' as const) : ('complete' as const),
        runId: done.run_id
      }
    ]
  }
  const tools = toolsFor(state, sessionId).map((tool) =>
    tool.status === 'running' ? { ...tool, status: 'error' as const, summary: 'interrupted' } : tool
  )
  const failed = done.status === 'failed' || done.status === 'timed_out'
  return {
    ...state,
    messagesBySession: { ...state.messagesBySession, [sessionId]: next },
    toolsBySession: { ...state.toolsBySession, [sessionId]: tools },
    runningBySession: { ...state.runningBySession, [sessionId]: false },
    errorBySession: {
      ...state.errorBySession,
      [sessionId]: failed ? `run ${done.status}` : null
    },
    approvals: state.approvals.filter((approval) => approval.sessionId !== sessionId)
  }
}

export function applyProtocolNotification(
  state: ConversationState,
  method: string,
  params: unknown
): ConversationState {
  switch (method) {
    case 'event/message_delta': {
      const delta = params as MessageDelta
      return applyMessageDelta(state, delta.session_id, delta)
    }
    case 'event/final': {
      const final = params as FinalAnswer
      return applyFinalAnswer(state, final.session_id, final)
    }
    case 'event/job_status': {
      const job = params as JobStatusUpdate
      return setRunning(state, job.session_id, job.state === 'submitted' || job.state === 'running')
    }
    case 'event/error': {
      const error = params as ErrorNotification
      return applyError(state, error.session_id, error.message)
    }
    case 'event/tool_begin': {
      const tool = params as ToolBegin
      return applyToolBegin(state, tool.session_id, tool)
    }
    case 'event/tool_end': {
      const tool = params as ToolEnd
      return applyToolEnd(state, tool.session_id, tool)
    }
    case 'event/done': {
      const done = params as RunComplete
      return applyRunComplete(state, done.session_id, done)
    }
    default:
      return state
  }
}

export function addApprovalRequest(
  state: ConversationState,
  request: ApprovalRequest
): ConversationState {
  if (state.approvals.some((item) => item.requestId === request.request_id)) {
    return state
  }
  const item: ApprovalRequestItem = {
    requestId: request.request_id,
    sessionId: request.session_id,
    riskLevel: request.risk_level,
    action: request.action,
    details: request.details,
    status: 'pending'
  }
  return { ...state, approvals: [...state.approvals, item] }
}

export function updateApprovalRequestStatus(
  state: ConversationState,
  requestId: string,
  status: ApprovalRequestStatus,
  error?: string
): ConversationState {
  const index = state.approvals.findIndex((item) => item.requestId === requestId)
  if (index < 0) return state
  const next = [...state.approvals]
  next[index] = {
    ...next[index]!,
    status,
    ...(error !== undefined ? { error } : {})
  }
  return { ...state, approvals: next }
}

export function removeApprovalRequest(
  state: ConversationState,
  requestId: string
): ConversationState {
  if (!state.approvals.some((item) => item.requestId === requestId)) return state
  return { ...state, approvals: state.approvals.filter((item) => item.requestId !== requestId) }
}

export function removeApprovalRequestsForSession(
  state: ConversationState,
  sessionId: string
): ConversationState {
  if (!state.approvals.some((item) => item.sessionId === sessionId)) return state
  return { ...state, approvals: state.approvals.filter((item) => item.sessionId !== sessionId) }
}
