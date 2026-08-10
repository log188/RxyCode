/**
 * Client-side scoped "always allow" approval rules (Phase4-D4).
 *
 * The protocol only carries one-shot approval decisions; cross-session
 * "always allow" persistence lives in the Desktop client. Every rule is
 * scoped to a workspace + risk level + action match and expires, so it can
 * never act as a global boolean (Phase D DC-A5). Matching rules auto-reply
 * `approved` and never send `always_allow_level` (which would let the
 * appserver cache the whole risk level and bypass this scope).
 */
import type { ApprovalRequest } from '@rxycode/protocol-client'

export const APPROVAL_RULES_STORAGE_KEY = 'rxycode.desktop.approvalRules.v1'

export type ApprovalRiskLevel = 'READ' | 'WRITE' | 'DANGER'
export type ApprovalActionScope = 'any' | 'exact' | 'prefix'
export type ApprovalExpiryHours = 1 | 24 | 168

export interface ApprovalRuleDraft {
  workspaceRoot: string
  riskLevel: ApprovalRiskLevel
  actionScope: ApprovalActionScope
  action: string
  expiresInHours: ApprovalExpiryHours
}

export interface ApprovalRule extends ApprovalRuleDraft {
  id: string
  createdAt: number
  expiresAt: number
}

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

const RISK_LEVELS: readonly ApprovalRiskLevel[] = ['READ', 'WRITE', 'DANGER']
const ACTION_SCOPES: readonly ApprovalActionScope[] = ['any', 'exact', 'prefix']

export function createApprovalRule(
  draft: ApprovalRuleDraft,
  now: number = Date.now()
): ApprovalRule {
  if (!RISK_LEVELS.includes(draft.riskLevel)) {
    throw new Error(`invalid approval risk level: ${draft.riskLevel}`)
  }
  if (draft.actionScope !== 'any' && draft.action.trim() === '') {
    throw new Error('approval rule action must not be empty for exact/prefix scope')
  }
  return {
    ...draft,
    id: `rule-${now.toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
    createdAt: now,
    expiresAt: now + draft.expiresInHours * 3600 * 1000
  }
}

export function isRuleExpired(rule: ApprovalRule, now: number = Date.now()): boolean {
  return rule.expiresAt <= now
}

export function pruneExpiredRules(
  rules: readonly ApprovalRule[],
  now: number = Date.now()
): ApprovalRule[] {
  return rules.filter((rule) => !isRuleExpired(rule, now))
}

export function ruleMatchesRequest(
  rule: ApprovalRule,
  request: ApprovalRequest,
  workspaceRoot: string,
  now: number = Date.now()
): boolean {
  if (isRuleExpired(rule, now)) return false
  if (rule.workspaceRoot !== workspaceRoot) return false
  if (rule.riskLevel !== request.risk_level) return false
  if (rule.actionScope === 'any') return true
  if (rule.actionScope === 'exact') return rule.action === request.action
  return request.action.startsWith(rule.action)
}

export function findAutoApprovalRule(
  rules: readonly ApprovalRule[],
  request: ApprovalRequest,
  workspaceRoot: string,
  now: number = Date.now()
): ApprovalRule | null {
  for (const rule of rules) {
    if (ruleMatchesRequest(rule, request, workspaceRoot, now)) return rule
  }
  return null
}

function isApprovalRule(value: unknown): value is ApprovalRule {
  if (typeof value !== 'object' || value === null) return false
  const rule = value as Record<string, unknown>
  return (
    typeof rule.id === 'string' &&
    typeof rule.workspaceRoot === 'string' &&
    RISK_LEVELS.includes(rule.riskLevel as ApprovalRiskLevel) &&
    ACTION_SCOPES.includes(rule.actionScope as ApprovalActionScope) &&
    typeof rule.action === 'string' &&
    typeof rule.createdAt === 'number' &&
    typeof rule.expiresAt === 'number'
  )
}

export function loadApprovalRules(storage: StorageLike, now: number = Date.now()): ApprovalRule[] {
  const raw = storage.getItem(APPROVAL_RULES_STORAGE_KEY)
  if (raw === null) return []
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return []
    return pruneExpiredRules(parsed.filter(isApprovalRule), now)
  } catch {
    return []
  }
}

export function saveApprovalRules(rules: readonly ApprovalRule[], storage: StorageLike): void {
  storage.setItem(APPROVAL_RULES_STORAGE_KEY, JSON.stringify(rules))
}
