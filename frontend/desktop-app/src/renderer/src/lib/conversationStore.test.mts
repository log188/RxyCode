import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  addSession,
  addApprovalRequest,
  addUserMessage,
  applyError,
  applyFinalAnswer,
  applyMessageDelta,
  applyProtocolNotification,
  applyPromptResult,
  applyRunComplete,
  applyToolBegin,
  applyToolEnd,
  beginAssistantMessage,
  createInitialState,
  removeApprovalRequest,
  removeApprovalRequestsForSession,
  selectSession,
  setRunning,
  updateApprovalRequestStatus,
  type ConversationState
} from './conversationStore.mts'
import type { ApprovalRequest, RunComplete, ToolBegin, ToolEnd } from '@rxycode/protocol-client'

const WORKSPACE = 'D:\\workspace'

function baseState(): ConversationState {
  return addSession(createInitialState(), {
    sessionId: 's1',
    workspaceRoot: WORKSPACE
  })
}

test('addSession adds a session and activates the first one', () => {
  const state = addSession(createInitialState(), {
    sessionId: 's1',
    workspaceRoot: WORKSPACE
  })
  assert.equal(state.sessions.length, 1)
  assert.equal(state.sessions[0]?.sessionId, 's1')
  assert.equal(state.activeSessionId, 's1')
  assert.equal(state.messagesBySession['s1']?.length, 0)
})

test('addSession activates a newly created session', () => {
  const first = addSession(createInitialState(), {
    sessionId: 's1',
    workspaceRoot: WORKSPACE
  })
  const state = addSession(first, {
    sessionId: 's2',
    workspaceRoot: WORKSPACE
  })
  assert.equal(state.activeSessionId, 's2')
})

test('addSession uses a Chinese default title prefixed with 会话', () => {
  const state = addSession(createInitialState(), {
    sessionId: 'abc12345',
    workspaceRoot: WORKSPACE
  })
  assert.equal(state.sessions[0]?.title, '会话 abc12345')
})

test('addSession ignores duplicate session ids', () => {
  const once = addSession(createInitialState(), {
    sessionId: 's1',
    workspaceRoot: WORKSPACE
  })
  const twice = addSession(once, {
    sessionId: 's1',
    workspaceRoot: WORKSPACE
  })
  assert.equal(twice.sessions.length, 1)
})

test('selectSession switches the active session', () => {
  const withTwo = addSession(baseState(), {
    sessionId: 's2',
    workspaceRoot: WORKSPACE
  })
  const selected = selectSession(withTwo, 's2')
  assert.equal(selected.activeSessionId, 's2')
})

test('selectSession ignores unknown ids', () => {
  const state = baseState()
  assert.equal(selectSession(state, 'nope'), state)
})

test('addUserMessage appends a user message and titles the session from the first prompt', () => {
  const state = addUserMessage(baseState(), 's1', '帮我写一个 hello world')
  assert.equal(state.messagesBySession['s1']?.length, 1)
  assert.equal(state.messagesBySession['s1']?.[0]?.role, 'user')
  assert.equal(state.messagesBySession['s1']?.[0]?.text, '帮我写一个 hello world')
  assert.equal(state.sessions[0]?.title, '帮我写一个 hello world')
})

test('addUserMessage keeps a custom session title unchanged', () => {
  const custom = addSession(createInitialState(), {
    sessionId: 's1',
    workspaceRoot: WORKSPACE,
    title: '我的任务'
  })
  const state = addUserMessage(custom, 's1', '第一条消息')
  assert.equal(state.sessions[0]?.title, '我的任务')
})

test('addUserMessage clears a previous session error', () => {
  const errored = applyError(baseState(), 's1', 'boom')
  assert.equal(errored.errorBySession['s1'], 'boom')
  const state = addUserMessage(errored, 's1', '再试一次')
  assert.equal(state.errorBySession['s1'], null)
})

test('beginAssistantMessage marks the session running and opens a streaming placeholder', () => {
  const state = beginAssistantMessage(baseState(), 's1')
  assert.equal(state.runningBySession['s1'], true)
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.role, 'assistant')
  assert.equal(last?.status, 'streaming')
  assert.equal(last?.text, '')
})

test('beginAssistantMessage clears a previous session error', () => {
  const errored = applyError(baseState(), 's1', 'boom')
  const state = beginAssistantMessage(errored, 's1')
  assert.equal(state.errorBySession['s1'], null)
})

test('applyMessageDelta accumulates text into the latest assistant message', () => {
  let state = beginAssistantMessage(baseState(), 's1')
  state = applyMessageDelta(state, 's1', {
    method: 'event/message_delta',
    session_id: 's1',
    text: '你好'
  })
  state = applyMessageDelta(state, 's1', {
    method: 'event/message_delta',
    session_id: 's1',
    text: '，世界'
  })
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.text, '你好，世界')
})

test('applyMessageDelta opens a streaming message when none exists', () => {
  const state = applyMessageDelta(baseState(), 's1', {
    method: 'event/message_delta',
    session_id: 's1',
    text: 'hi'
  })
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.role, 'assistant')
  assert.equal(last?.text, 'hi')
})

test('applyFinalAnswer replaces the placeholder with the final answer', () => {
  let state = beginAssistantMessage(baseState(), 's1')
  state = applyMessageDelta(state, 's1', {
    method: 'event/message_delta',
    session_id: 's1',
    text: '你好'
  })
  state = applyFinalAnswer(state, 's1', {
    method: 'event/final',
    session_id: 's1',
    run_id: 'run-1',
    text: '完整回答'
  })
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.text, '完整回答')
  assert.equal(last?.status, 'complete')
  assert.equal(last?.runId, 'run-1')
  assert.equal(state.runningBySession['s1'], false)
})

test('applyFinalAnswer creates a complete assistant message when none is streaming', () => {
  const state = applyFinalAnswer(baseState(), 's1', {
    method: 'event/final',
    session_id: 's1',
    run_id: 'run-2',
    text: '直接回答'
  })
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.text, '直接回答')
  assert.equal(last?.status, 'complete')
  assert.equal(state.runningBySession['s1'], false)
})

test('applyFinalAnswer clears a previous session error', () => {
  const errored = applyError(baseState(), 's1', 'boom')
  const state = applyFinalAnswer(errored, 's1', {
    method: 'event/final',
    session_id: 's1',
    run_id: 'run-3',
    text: '成功回答'
  })
  assert.equal(state.errorBySession['s1'], null)
})

test('applyFinalAnswer finalizes tool cards that never received a tool_end event', () => {
  let state = applyToolBegin(baseState(), 's1', toolBegin('call-1', 'glob'))
  state = applyToolBegin(state, 's1', toolBegin('call-2', 'grep'))
  state = applyFinalAnswer(state, 's1', {
    method: 'event/final',
    session_id: 's1',
    run_id: 'run-final-tools',
    text: 'done'
  })

  assert.deepEqual(
    state.toolsBySession['s1']?.map((tool) => ({ status: tool.status, summary: tool.summary })),
    [
      { status: 'ok', summary: 'completed with final answer' },
      { status: 'ok', summary: 'completed with final answer' }
    ]
  )
})

test('applyPromptResult records the final answer when no final event arrived', () => {
  let state = beginAssistantMessage(baseState(), 's1')
  state = applyPromptResult(state, 's1', {
    runId: 'run-9',
    status: 'succeeded',
    text: 'fallback answer'
  })
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.text, 'fallback answer')
  assert.equal(last?.status, 'complete')
  assert.equal(state.runningBySession['s1'], false)
})

test('applyPromptResult finalizes running tools as errors when the prompt failed without event/done', () => {
  let state = applyToolBegin(baseState(), 's1', toolBegin('call-1'))
  state = beginAssistantMessage(state, 's1')
  state = applyPromptResult(state, 's1', {
    runId: 'run-failed',
    status: 'failed',
    text: 'backend evidence failure'
  })
  const last = state.messagesBySession['s1']?.at(-1)
  const tool = state.toolsBySession['s1']?.[0]
  assert.equal(last?.text, 'backend evidence failure')
  assert.equal(last?.status, 'error')
  assert.equal(tool?.status, 'error')
  assert.equal(tool?.summary, 'run failed')
  assert.equal(state.runningBySession['s1'], false)
  assert.equal(state.errorBySession['s1'], 'run failed')
})

test('applyPromptResult clears a previous session error', () => {
  const errored = applyError(baseState(), 's1', 'boom')
  const state = applyPromptResult(errored, 's1', {
    runId: 'run-10',
    status: 'succeeded',
    text: '成功回答'
  })
  assert.equal(state.errorBySession['s1'], null)
})

test('applyError marks the latest assistant message as errored and stops running', () => {
  let state = beginAssistantMessage(baseState(), 's1')
  state = applyError(state, 's1', 'boom')
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.status, 'error')
  assert.equal(last?.text, 'boom')
  assert.equal(state.runningBySession['s1'], false)
  assert.equal(state.errorBySession['s1'], 'boom')
})

test('applyError does not append a duplicate message when the last one already errored', () => {
  let state = beginAssistantMessage(baseState(), 's1')
  state = applyError(state, 's1', 'demo failure')
  const once = state.messagesBySession['s1']
  state = applyError(state, 's1', 'demo failure')
  assert.equal(state.messagesBySession['s1']?.length, once?.length)
  assert.equal(state.messagesBySession['s1']?.at(-1)?.status, 'error')
  assert.equal(state.errorBySession['s1'], 'demo failure')
})

test('messages are kept per session', () => {
  const two = addSession(baseState(), {
    sessionId: 's2',
    workspaceRoot: WORKSPACE
  })
  const state = addUserMessage(two, 's2', 'second session')
  assert.equal(state.messagesBySession['s1']?.length, 0)
  assert.equal(state.messagesBySession['s2']?.length, 1)
})

test('setRunning flips the running flag', () => {
  const state = setRunning(baseState(), 's1', true)
  assert.equal(state.runningBySession['s1'], true)
  const stopped = setRunning(state, 's1', false)
  assert.equal(stopped.runningBySession['s1'], false)
})

function toolBegin(callId: string, toolName = 'read_file'): ToolBegin {
  return {
    method: 'event/tool_begin',
    session_id: 's1',
    call_id: callId,
    tool_name: toolName
  }
}

function toolEnd(callId: string, ok: boolean, summary: string): ToolEnd {
  return {
    method: 'event/tool_end',
    session_id: 's1',
    call_id: callId,
    ok,
    summary
  }
}

function runDone(status: 'succeeded' | 'failed' | 'cancelled' | 'timed_out'): RunComplete {
  return {
    method: 'event/done',
    session_id: 's1',
    run_id: 'run-7',
    status
  }
}

test('applyToolBegin appends a running tool card to the session', () => {
  const state = applyToolBegin(baseState(), 's1', {
    ...toolBegin('call-1'),
    arguments: { path: 'D:\\a.txt' }
  })
  const tools = state.toolsBySession['s1']
  assert.equal(tools?.length, 1)
  assert.equal(tools?.[0]?.callId, 'call-1')
  assert.equal(tools?.[0]?.toolName, 'read_file')
  assert.equal(tools?.[0]?.status, 'running')
  assert.deepEqual(tools?.[0]?.arguments, { path: 'D:\\a.txt' })
})

test('applyToolEnd marks the matching tool card ok with its summary', () => {
  let state = applyToolBegin(baseState(), 's1', toolBegin('call-1'))
  state = applyToolEnd(state, 's1', toolEnd('call-1', true, '2 lines'))
  const tool = state.toolsBySession['s1']?.[0]
  assert.equal(tool?.status, 'ok')
  assert.equal(tool?.summary, '2 lines')
})

test('applyToolEnd marks the matching tool card error when the call failed', () => {
  let state = applyToolBegin(baseState(), 's1', toolBegin('call-1'))
  state = applyToolEnd(state, 's1', toolEnd('call-1', false, 'boom'))
  const tool = state.toolsBySession['s1']?.[0]
  assert.equal(tool?.status, 'error')
  assert.equal(tool?.summary, 'boom')
})

test('applyToolEnd ignores unknown call ids without changing state', () => {
  const state = applyToolBegin(baseState(), 's1', toolBegin('call-1'))
  const next = applyToolEnd(state, 's1', toolEnd('call-nope', true, 'x'))
  assert.equal(next, state)
})

test('applyToolBegin replaces an existing card with the same call id', () => {
  let state = applyToolBegin(baseState(), 's1', toolBegin('call-1', 'read_file'))
  state = applyToolBegin(baseState(), 's1', {
    ...toolBegin('call-1', 'write_file'),
    arguments: { path: 'D:\\b.txt' }
  })
  const tools = state.toolsBySession['s1']
  assert.equal(tools?.length, 1)
  assert.equal(tools?.[0]?.toolName, 'write_file')
  assert.deepEqual(tools?.[0]?.arguments, { path: 'D:\\b.txt' })
})

test('applyRunComplete stops the session and keeps partial streaming text on cancel', () => {
  let state = beginAssistantMessage(baseState(), 's1')
  state = applyMessageDelta(state, 's1', {
    method: 'event/message_delta',
    session_id: 's1',
    text: 'partial'
  })
  state = applyRunComplete(state, 's1', runDone('cancelled'))
  assert.equal(state.runningBySession['s1'], false)
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.text, 'partial')
  assert.equal(last?.status, 'complete')
  assert.equal(last?.runId, 'run-7')
})

test('applyRunComplete marks a failed run as an error', () => {
  let state = beginAssistantMessage(baseState(), 's1')
  state = applyMessageDelta(state, 's1', {
    method: 'event/message_delta',
    session_id: 's1',
    text: 'partial'
  })
  state = applyRunComplete(state, 's1', runDone('failed'))
  const last = state.messagesBySession['s1']?.at(-1)
  assert.equal(last?.status, 'error')
  assert.equal(state.errorBySession['s1'], 'run failed')
  assert.equal(state.runningBySession['s1'], false)
})

test('applyRunComplete clears a previous session error on success', () => {
  const errored = applyError(baseState(), 's1', 'boom')
  const state = applyRunComplete(errored, 's1', runDone('succeeded'))
  assert.equal(state.errorBySession['s1'], null)
  assert.equal(state.runningBySession['s1'], false)
})

test('applyRunComplete with no streaming message does not fabricate one', () => {
  const state = applyRunComplete(baseState(), 's1', runDone('succeeded'))
  assert.equal(state.messagesBySession['s1']?.length, 0)
  assert.equal(state.runningBySession['s1'], false)
})

test('applyRunComplete finalizes still-running tool cards as interrupted', () => {
  let state = applyToolBegin(baseState(), 's1', toolBegin('call-1'))
  state = applyRunComplete(state, 's1', runDone('cancelled'))
  const tool = state.toolsBySession['s1']?.[0]
  assert.equal(tool?.status, 'error')
  assert.equal(tool?.summary, 'interrupted')
})

test('applyProtocolNotification routes tool and done notifications into state', () => {
  let state = applyProtocolNotification(baseState(), 'event/tool_begin', toolBegin('call-1'))
  state = applyProtocolNotification(state, 'event/tool_end', toolEnd('call-1', true, 'ok'))
  state = applyProtocolNotification(state, 'event/done', runDone('cancelled'))
  const tool = state.toolsBySession['s1']?.[0]
  assert.equal(tool?.status, 'ok')
  assert.equal(state.runningBySession['s1'], false)
})

test('applyProtocolNotification ignores unknown methods without changing state', () => {
  const state = baseState()
  assert.equal(applyProtocolNotification(state, 'event/unknown', { session_id: 's1' }), state)
})

function approvalRequest(): ApprovalRequest {
  return {
    method: 'approval/request',
    session_id: 's1',
    request_id: 'apr-1',
    risk_level: 'WRITE',
    action: 'bash: write demo.txt',
    details: { tool_name: 'bash' }
  }
}

test('createInitialState starts with no approvals', () => {
  assert.deepEqual(createInitialState().approvals, [])
})

test('addApprovalRequest appends a pending approval item', () => {
  const state = addApprovalRequest(baseState(), approvalRequest())
  assert.equal(state.approvals.length, 1)
  const item = state.approvals[0]
  assert.equal(item?.requestId, 'apr-1')
  assert.equal(item?.sessionId, 's1')
  assert.equal(item?.riskLevel, 'WRITE')
  assert.equal(item?.action, 'bash: write demo.txt')
  assert.deepEqual(item?.details, { tool_name: 'bash' })
  assert.equal(item?.status, 'pending')
})

test('addApprovalRequest dedupes by request id', () => {
  const once = addApprovalRequest(baseState(), approvalRequest())
  const twice = addApprovalRequest(once, approvalRequest())
  assert.equal(twice.approvals.length, 1)
})

test('updateApprovalRequestStatus flips status and attaches an error', () => {
  let state = addApprovalRequest(baseState(), approvalRequest())
  state = updateApprovalRequestStatus(state, 'apr-1', 'submitting')
  assert.equal(state.approvals[0]?.status, 'submitting')
  state = updateApprovalRequestStatus(state, 'apr-1', 'error', '连接已断开')
  assert.equal(state.approvals[0]?.status, 'error')
  assert.equal(state.approvals[0]?.error, '连接已断开')
})

test('updateApprovalRequestStatus ignores unknown ids', () => {
  const state = addApprovalRequest(baseState(), approvalRequest())
  assert.equal(updateApprovalRequestStatus(state, 'nope', 'submitting'), state)
})

test('removeApprovalRequest removes the matching item', () => {
  let state = addApprovalRequest(baseState(), approvalRequest())
  state = removeApprovalRequest(state, 'apr-1')
  assert.equal(state.approvals.length, 0)
})

test('removeApprovalRequestsForSession removes only that session approvals', () => {
  let state = addApprovalRequest(baseState(), approvalRequest())
  state = addApprovalRequest(state, {
    ...approvalRequest(),
    request_id: 'apr-2',
    session_id: 's2'
  })
  const next = removeApprovalRequestsForSession(state, 's1')
  assert.equal(next.approvals.length, 1)
  assert.equal(next.approvals[0]?.requestId, 'apr-2')
})

test('applyRunComplete removes submitting approvals for the session', () => {
  let state = addApprovalRequest(baseState(), approvalRequest())
  state = updateApprovalRequestStatus(state, 'apr-1', 'submitting')
  state = applyRunComplete(state, 's1', runDone('succeeded'))
  assert.equal(state.approvals.length, 0)
  assert.equal(state.runningBySession['s1'], false)
})
