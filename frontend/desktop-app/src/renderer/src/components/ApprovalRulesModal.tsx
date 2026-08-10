import type { ApprovalActionScope, ApprovalRule } from '../lib/approvalPolicy.mts'

const SCOPE_LABELS: Record<ApprovalActionScope, string> = {
  any: '此工作区此等级',
  exact: '仅此动作',
  prefix: '同类动作'
}

interface ApprovalRulesModalProps {
  open: boolean
  rules: ApprovalRule[]
  onClose: () => void
  onRevoke: (ruleId: string) => void
}

function ApprovalRulesModal({
  open,
  rules,
  onClose,
  onRevoke
}: ApprovalRulesModalProps): React.JSX.Element | null {
  if (!open) return null
  return (
    <div className="approval-overlay">
      <div className="approval-dialog rules-dialog" role="dialog" aria-modal="true">
        <div className="approval-header">
          <span className="approval-title">权限 · 始终允许规则</span>
        </div>
        {rules.length === 0 ? (
          <div className="rules-empty">
            暂无始终允许规则。审批弹层中选择「始终允许」并设置作用域后，规则会出现在这里。
          </div>
        ) : (
          <div className="rules-list">
            {rules.map((rule) => (
              <div key={rule.id} className="rule-item">
                <div className="rule-head">
                  <span className={`approval-risk ${rule.riskLevel.toLowerCase()}`}>
                    {rule.riskLevel}
                  </span>
                  <span className="rule-scope">{SCOPE_LABELS[rule.actionScope]}</span>
                  <button type="button" className="revoke-rule" onClick={() => onRevoke(rule.id)}>
                    撤销
                  </button>
                </div>
                {rule.actionScope !== 'any' && <div className="rule-action">{rule.action}</div>}
                <div className="rule-meta">
                  工作区 {rule.workspaceRoot} · 有效期至 {new Date(rule.expiresAt).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="approval-actions">
          <button type="button" className="rules-close" onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}

export default ApprovalRulesModal
