import { test } from 'node:test'
import assert from 'node:assert/strict'
import type { ApprovalRequest } from '@rxycode/protocol-client'
import {
  APPROVAL_RULES_STORAGE_KEY,
  createApprovalRule,
  findAutoApprovalRule,
  isRuleExpired,
  loadApprovalRules,
  pruneExpiredRules,
  ruleMatchesRequest,
  saveApprovalRules,
  type ApprovalRule,
  type ApprovalRiskLevel,
  type StorageLike
} from './approvalPolicy.mts'

const NOW = 1_700_000_000_000
const WORKSPACE = 'D:\\workspace'

function approvalRequest(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    method: 'approval/request',
    session_id: 's1',
    request_id: 'apr-1',
    risk_level: 'WRITE',
    action: 'bash: write demo.txt',
    details: { tool_name: 'bash' },
    ...overrides
  }
}

function exactRule(now: number = NOW): ApprovalRule {
  return createApprovalRule(
    {
      workspaceRoot: WORKSPACE,
      riskLevel: 'WRITE',
      actionScope: 'exact',
      action: 'bash: write demo.txt',
      expiresInHours: 24
    },
    now
  )
}

function createFakeStorage(initial: Record<string, string> = {}): {
  data: Record<string, string>
  getItem: StorageLike['getItem']
  setItem: StorageLike['setItem']
} {
  const data: Record<string, string> = { ...initial }
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value
    }
  }
}

test('createApprovalRule stores scope, risk, workspace and derives expiry from hours', () => {
  const rule = exactRule()
  assert.equal(rule.workspaceRoot, WORKSPACE)
  assert.equal(rule.riskLevel, 'WRITE')
  assert.equal(rule.actionScope, 'exact')
  assert.equal(rule.action, 'bash: write demo.txt')
  assert.equal(rule.createdAt, NOW)
  assert.equal(rule.expiresAt, NOW + 24 * 3600 * 1000)
  assert.ok(rule.id.length > 0)
})

test('createApprovalRule rejects invalid risk levels', () => {
  assert.throws(
    () =>
      createApprovalRule(
        {
          workspaceRoot: WORKSPACE,
          riskLevel: 'ANY' as ApprovalRiskLevel,
          actionScope: 'any',
          action: '',
          expiresInHours: 24
        },
        NOW
      ),
    /risk level/
  )
})

test('createApprovalRule rejects empty actions for exact and prefix scopes', () => {
  assert.throws(
    () =>
      createApprovalRule(
        {
          workspaceRoot: WORKSPACE,
          riskLevel: 'WRITE',
          actionScope: 'exact',
          action: '',
          expiresInHours: 24
        },
        NOW
      ),
    /action/
  )
  assert.throws(
    () =>
      createApprovalRule(
        {
          workspaceRoot: WORKSPACE,
          riskLevel: 'WRITE',
          actionScope: 'prefix',
          action: '  ',
          expiresInHours: 24
        },
        NOW
      ),
    /action/
  )
})

test('ruleMatchesRequest requires the same workspace and risk level', () => {
  const rule = exactRule()
  assert.equal(ruleMatchesRequest(rule, approvalRequest(), WORKSPACE, NOW), true)
  assert.equal(ruleMatchesRequest(rule, approvalRequest(), 'D:\\other', NOW), false)
  assert.equal(
    ruleMatchesRequest(rule, approvalRequest({ risk_level: 'DANGER' }), WORKSPACE, NOW),
    false
  )
})

test('exact scope matches only the exact action', () => {
  const rule = exactRule()
  assert.equal(
    ruleMatchesRequest(rule, approvalRequest({ action: 'bash: write demo.txt' }), WORKSPACE, NOW),
    true
  )
  assert.equal(
    ruleMatchesRequest(rule, approvalRequest({ action: 'bash: write other.txt' }), WORKSPACE, NOW),
    false
  )
})

test('prefix scope matches actions starting with the prefix', () => {
  const rule = createApprovalRule(
    {
      workspaceRoot: WORKSPACE,
      riskLevel: 'WRITE',
      actionScope: 'prefix',
      action: 'bash: write',
      expiresInHours: 24
    },
    NOW
  )
  assert.equal(
    ruleMatchesRequest(rule, approvalRequest({ action: 'bash: write demo.txt' }), WORKSPACE, NOW),
    true
  )
  assert.equal(
    ruleMatchesRequest(rule, approvalRequest({ action: 'bash: read demo.txt' }), WORKSPACE, NOW),
    false
  )
})

test('any scope matches any action at the same workspace and risk level', () => {
  const rule = createApprovalRule(
    {
      workspaceRoot: WORKSPACE,
      riskLevel: 'WRITE',
      actionScope: 'any',
      action: '',
      expiresInHours: 24
    },
    NOW
  )
  assert.equal(
    ruleMatchesRequest(rule, approvalRequest({ action: 'unrelated action' }), WORKSPACE, NOW),
    true
  )
})

test('expired rules never match', () => {
  const rule = exactRule()
  assert.equal(isRuleExpired(rule, NOW + 24 * 3600 * 1000 + 1), true)
  assert.equal(
    ruleMatchesRequest(rule, approvalRequest(), WORKSPACE, NOW + 24 * 3600 * 1000 + 1),
    false
  )
})

test('findAutoApprovalRule returns the first matching rule', () => {
  const readRule = createApprovalRule(
    {
      workspaceRoot: WORKSPACE,
      riskLevel: 'READ',
      actionScope: 'any',
      action: '',
      expiresInHours: 24
    },
    NOW
  )
  const writeRule = exactRule()
  const matched = findAutoApprovalRule([readRule, writeRule], approvalRequest(), WORKSPACE, NOW)
  assert.equal(matched?.id, writeRule.id)
})

test('findAutoApprovalRule returns null when nothing matches', () => {
  const readRule = createApprovalRule(
    {
      workspaceRoot: WORKSPACE,
      riskLevel: 'READ',
      actionScope: 'any',
      action: '',
      expiresInHours: 24
    },
    NOW
  )
  assert.equal(findAutoApprovalRule([readRule], approvalRequest(), WORKSPACE, NOW), null)
})

test('pruneExpiredRules removes expired rules', () => {
  const fresh = exactRule()
  const stale = exactRule(NOW - 48 * 3600 * 1000)
  const pruned = pruneExpiredRules([fresh, stale], NOW)
  assert.equal(pruned.length, 1)
  assert.equal(pruned[0]?.id, fresh.id)
})

test('loadApprovalRules reads valid rules, skips malformed entries and prunes expired', () => {
  const valid = exactRule()
  const stale = exactRule(NOW - 48 * 3600 * 1000)
  const storage = createFakeStorage({
    [APPROVAL_RULES_STORAGE_KEY]: JSON.stringify([
      valid,
      { id: 'not-a-rule' },
      'not-an-object',
      stale
    ])
  })
  const loaded = loadApprovalRules(storage, NOW)
  assert.equal(loaded.length, 1)
  assert.equal(loaded[0]?.id, valid.id)
})

test('loadApprovalRules returns an empty list for corrupted storage', () => {
  const storage = createFakeStorage({ [APPROVAL_RULES_STORAGE_KEY]: '{oops' })
  assert.deepEqual(loadApprovalRules(storage), [])
})

test('saveApprovalRules writes JSON to storage', () => {
  const storage = createFakeStorage()
  saveApprovalRules([exactRule()], storage)
  const raw = storage.data[APPROVAL_RULES_STORAGE_KEY]
  assert.ok(raw !== undefined)
  const parsed = JSON.parse(raw) as ApprovalRule[]
  assert.equal(parsed.length, 1)
  assert.equal(parsed[0]?.action, 'bash: write demo.txt')
})
