#!/usr/bin/env node
/**
 * Deterministic fake appserver for the Desktop UI (no LLM, no Python).
 *
 * Speaks the same newline-delimited JSON-RPC protocol as
 * `python -m appserver` and replays the Phase4-D3 event sequences the
 * renderer must handle: message_delta streaming, tool_begin/tool_end
 * cards, event/final, event/done, event/error, and session/interrupt.
 *
 * Phase4-D4 adds approval scenarios driven by prompt text:
 *   "approval demo"   -> WRITE approval/request with a unique action, waits
 *                        for the client decision, then completes the run
 *   "approval reject" -> same flow with a fixed action for the reject demo
 *   "approval auto"   -> fixed action so a persisted always-allow rule can
 *                        auto-approve without the modal appearing
 *
 * Prompt text drives the scenario:
 *   "tool demo" -> streaming text + two tool cards + final + done
 *   "slow demo" -> streaming text + running tool card, waits for interrupt
 *   "fail demo" -> event/error + event/done failed + RPC error
 *   anything else -> streaming text + final + done
 */
/* eslint-disable @typescript-eslint/explicit-function-return-type -- plain JS protocol script */
import { createInterface } from 'node:readline'

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity })
let sessionCounter = 0
const pendingPrompts = new Map()
const pendingServerRequests = new Map()

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`)
}

function notify(method, params) {
  send({ jsonrpc: '2.0', method, params })
}

function respond(id, result) {
  send({ jsonrpc: '2.0', id, result })
}

function respondError(id, code, message) {
  send({ jsonrpc: '2.0', id, error: { code, message } })
}

function sendServerRequest(method, params) {
  return new Promise((resolve, reject) => {
    const id = `srv-${++sessionCounter}-${Date.now().toString(36)}`
    pendingServerRequests.set(id, { resolve, reject })
    send({ jsonrpc: '2.0', id, method, params })
  })
}

const sleep = (ms) => new Promise((resolveWait) => setTimeout(resolveWait, ms))

async function runApprovalPrompt(requestId, sessionId, text) {
  const runId = `demo-${++sessionCounter}`
  const isReject = text.includes('reject')
  const isAuto = text.includes('auto')
  const action = isAuto
    ? 'bash: write approval-auto.txt'
    : isReject
      ? 'bash: write approval-reject-demo.txt'
      : `bash: write approval-demo-${sessionCounter}.txt`
  const approvalId = `apr-${runId}`

  notify('event/message_delta', {
    method: 'event/message_delta',
    session_id: sessionId,
    text: '请求执行写入操作…'
  })
  await sleep(400)
  notify('event/tool_begin', {
    method: 'event/tool_begin',
    session_id: sessionId,
    call_id: approvalId,
    tool_name: 'bash',
    arguments: { command: action.replace('bash: write ', '') }
  })

  let approved = false
  let approvalError = null
  try {
    const decision = await sendServerRequest('approval/request', {
      method: 'approval/request',
      session_id: sessionId,
      request_id: approvalId,
      risk_level: 'WRITE',
      action,
      details: {
        tool_name: 'bash',
        command: action.replace('bash: write ', ''),
        workspace_root: process.cwd()
      }
    })
    approved = decision?.decision === 'approved'
  } catch {
    approved = false
    approvalError = 'approval request failed'
  }

  if (approved) {
    await sleep(1200) // keep the "submitting" state visible for screenshots
    notify('event/tool_end', {
      method: 'event/tool_end',
      session_id: sessionId,
      call_id: approvalId,
      ok: true,
      summary: '写入完成',
      status: 'succeeded'
    })
    notify('event/message_delta', {
      method: 'event/message_delta',
      session_id: sessionId,
      text: '写入完成。'
    })
  } else {
    notify('event/tool_end', {
      method: 'event/tool_end',
      session_id: sessionId,
      call_id: approvalId,
      ok: false,
      summary: approvalError === null ? '用户已拒绝' : '审批异常',
      status: 'rejected'
    })
    notify('event/message_delta', {
      method: 'event/message_delta',
      session_id: sessionId,
      text: '操作已被拒绝。'
    })
  }

  await sleep(300)
  notify('event/final', {
    method: 'event/final',
    session_id: sessionId,
    run_id: runId,
    text: approved ? '写入完成。' : '操作已被拒绝。'
  })
  notify('event/done', {
    method: 'event/done',
    session_id: sessionId,
    run_id: runId,
    status: 'succeeded'
  })
  respond(requestId, {
    run_id: runId,
    status: 'succeeded',
    text: approved ? '写入完成。' : '操作已被拒绝。'
  })
}

async function runPrompt(requestId, sessionId, text) {
  const runId = `demo-${++sessionCounter}`
  notify('event/job_status', {
    session_id: sessionId,
    job_id: `job-${runId}`,
    state: 'submitted'
  })
  notify('event/job_status', {
    session_id: sessionId,
    job_id: `job-${runId}`,
    state: 'running'
  })

  if (text.includes('fail')) {
    await sleep(300)
    notify('event/message_delta', {
      method: 'event/message_delta',
      session_id: sessionId,
      text: '执行中…'
    })
    await sleep(400)
    notify('event/error', {
      method: 'event/error',
      session_id: sessionId,
      message: 'demo failure',
      run_id: runId,
      status: 'failed'
    })
    notify('event/done', {
      method: 'event/done',
      session_id: sessionId,
      run_id: runId,
      status: 'failed'
    })
    respondError(requestId, -32000, 'demo failure')
    return
  }

  if (text.includes('approval')) {
    await runApprovalPrompt(requestId, sessionId, text)
    return
  }

  if (text.startsWith('slow')) {
    notify('event/message_delta', {
      method: 'event/message_delta',
      session_id: sessionId,
      text: '正在分析需求…'
    })
    await sleep(500)
    notify('event/tool_begin', {
      method: 'event/tool_begin',
      session_id: sessionId,
      call_id: 'slow-1',
      tool_name: 'bash',
      arguments: { command: 'analyze --slow' }
    })
    await sleep(500)
    notify('event/message_delta', {
      method: 'event/message_delta',
      session_id: sessionId,
      text: '正在深入分析…'
    })
    pendingPrompts.set(requestId, { sessionId, runId })
    return
  }

  notify('event/message_delta', {
    method: 'event/message_delta',
    session_id: sessionId,
    text: '开始处理…'
  })
  await sleep(400)
  notify('event/tool_begin', {
    method: 'event/tool_begin',
    session_id: sessionId,
    call_id: 'demo-bash',
    tool_name: 'bash',
    arguments: { command: 'ls' }
  })
  await sleep(500)
  notify('event/tool_end', {
    method: 'event/tool_end',
    session_id: sessionId,
    call_id: 'demo-bash',
    ok: true,
    summary: '3 files listed',
    status: 'succeeded'
  })
  notify('event/tool_begin', {
    method: 'event/tool_begin',
    session_id: sessionId,
    call_id: 'demo-read',
    tool_name: 'read_file',
    arguments: { path: 'README.md' }
  })
  await sleep(400)
  notify('event/tool_end', {
    method: 'event/tool_end',
    session_id: sessionId,
    call_id: 'demo-read',
    ok: true,
    summary: '886 bytes',
    status: 'succeeded'
  })
  notify('event/message_delta', {
    method: 'event/message_delta',
    session_id: sessionId,
    text: '已完成：demo 输出。'
  })
  await sleep(300)
  notify('event/final', {
    method: 'event/final',
    session_id: sessionId,
    run_id: runId,
    text: 'demo 输出完成。'
  })
  notify('event/done', {
    method: 'event/done',
    session_id: sessionId,
    run_id: runId,
    status: 'succeeded'
  })
  respond(requestId, { run_id: runId, status: 'succeeded', text: 'demo 输出完成。' })
}

function handleInterrupt(requestId, sessionId) {
  for (const [promptId, entry] of pendingPrompts) {
    if (entry.sessionId === sessionId) {
      pendingPrompts.delete(promptId)
      respond(requestId, { cancelled: true, session_id: sessionId })
      notify('event/done', {
        method: 'event/done',
        session_id: sessionId,
        run_id: entry.runId,
        status: 'cancelled'
      })
      respond(promptId, { run_id: entry.runId, status: 'cancelled', text: 'partial' })
      return
    }
  }
  respond(requestId, { cancelled: false, session_id: sessionId })
}

rl.on('line', (line) => {
  let message
  try {
    message = JSON.parse(line)
  } catch {
    return
  }
  const id = message.id
  const method = String(message.method ?? '')
  const params = message.params ?? {}

  const isServerResponse =
    id !== undefined &&
    (Object.prototype.hasOwnProperty.call(message, 'result') ||
      Object.prototype.hasOwnProperty.call(message, 'error'))
  if (isServerResponse) {
    const entry = pendingServerRequests.get(id)
    if (entry !== undefined) {
      pendingServerRequests.delete(id)
      if (Object.prototype.hasOwnProperty.call(message, 'error')) {
        entry.reject(new Error(String(message.error?.message ?? 'server request error')))
      } else {
        entry.resolve(message.result)
      }
    }
    return
  }

  if (method === 'initialize') {
    respond(id, {
      protocol_version: '1.0.0',
      server_name: 'rxycode-appserver',
      capabilities: { sessions: true, approval: true }
    })
    return
  }
  if (method === 'session/new') {
    sessionCounter += 1
    respond(id, { session_id: `demo-${sessionCounter}`, workspace_root: process.cwd() })
    return
  }
  if (method === 'session/prompt') {
    const sessionId = String(params.session_id ?? '')
    const text = String(params.text ?? '')
    void runPrompt(id, sessionId, text).catch((error) => {
      respondError(id, -32000, String(error))
      notify('event/done', {
        method: 'event/done',
        session_id: sessionId,
        run_id: 'demo-error',
        status: 'failed'
      })
    })
    return
  }
  if (method === 'session/interrupt') {
    handleInterrupt(id, String(params.session_id ?? ''))
    return
  }
  if (method === 'shutdown') {
    respond(id, { ok: true })
    process.exit(0)
    return
  }
  respondError(id, -32601, `method not found: ${method}`)
})
