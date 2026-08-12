import { useEffect, useState } from 'react'
import type { ApprovalActionScope, ApprovalExpiryHours } from '../lib/approvalPolicy.mts'
import type { ApprovalRequestItem } from '../lib/conversationStore.mts'

const EXPIRY_OPTIONS: Array<{ value: ApprovalExpiryHours; label: string }> = [
  { value: 1, label: '1 小时' },
  { value: 24, label: '24 小时' },
  { value: 168, label: '7 天' }
]

const SCOPE_OPTIONS: Array<{ value: ApprovalActionScope; label: string; hint: string }> = [
  { value: 'exact', label: '仅此动作', hint: '只匹配完全相同的一条动作' },
  { value: 'prefix', label: '同类动作', hint: '匹配以该描述开头的动作' },
  { value: 'any', label: '此工作区此等级', hint: '允许该风险等级的全部动作' }
]

interface ApprovalModalProps {
  item: ApprovalRequestItem
  onApprove: () => void
  onReject: () => void
  onAlwaysAllow: (scope: ApprovalActionScope, expiresInHours: ApprovalExpiryHours) => void
  onDismiss: () => void
}

function ApprovalModal({
  item,
  onApprove,
  onReject,
  onAlwaysAllow,
  onDismiss
}: ApprovalModalProps): React.JSX.Element {
  const [formOpen, setFormOpen] = useState(false)
  const [scope, setScope] = useState<ApprovalActionScope>('exact')
  const [expiresInHours, setExpiresInHours] = useState<ApprovalExpiryHours>(24)

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onDismiss()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onDismiss])

  if (item.status === 'error') {
    return (
      <div className="approval-overlay">
        <div className="approval-dialog error" role="dialog" aria-modal="true">
          <div className="approval-header">
            <span className="approval-title">审批请求失败</span>
          </div>
          <div className="approval-action">{item.action}</div>
          <div className="approval-error-message">
            {item.error ?? '无法响应审批请求（连接可能已断开）。'}
          </div>
          <div className="approval-actions">
            <button type="button" className="approval-dismiss" onClick={onDismiss}>
              关闭
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="approval-overlay">
      <div className="approval-dialog" role="dialog" aria-modal="true">
        <div className="approval-header">
          <span className={`approval-risk ${item.riskLevel.toLowerCase()}`}>{item.riskLevel}</span>
          <span className="approval-title">审批请求</span>
        </div>
        <div className="approval-action">{item.action}</div>
        {item.details !== undefined && Object.keys(item.details).length > 0 && (
          <pre className="approval-details">{JSON.stringify(item.details, null, 2)}</pre>
        )}

        {item.status === 'submitting' ? (
          <div className="approval-submitting">正在提交…</div>
        ) : formOpen ? (
          <div className="approval-scope-form">
            <div className="approval-form-label">始终允许的作用域</div>
            {SCOPE_OPTIONS.map((option) => (
              <label key={option.value} className="approval-scope-option">
                <input
                  type="radio"
                  name="approval-scope"
                  value={option.value}
                  checked={scope === option.value}
                  onChange={() => setScope(option.value)}
                />
                <span>
                  <span className="approval-scope-name">{option.label}</span>
                  <span className="approval-scope-hint">{option.hint}</span>
                </span>
              </label>
            ))}
            <div className="approval-form-label">有效期</div>
            <select
              className="approval-expiry"
              value={expiresInHours}
              onChange={(event) =>
                setExpiresInHours(Number(event.target.value) as ApprovalExpiryHours)
              }
            >
              {EXPIRY_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <div className="approval-actions">
              <button
                type="button"
                className="save-rule"
                onClick={() => onAlwaysAllow(scope, expiresInHours)}
              >
                保存并允许
              </button>
              <button type="button" className="cancel-rule" onClick={() => setFormOpen(false)}>
                取消
              </button>
            </div>
          </div>
        ) : (
          <div className="approval-actions">
            <button type="button" className="approve" onClick={onApprove}>
              批准
            </button>
            <button type="button" className="reject" onClick={onReject}>
              拒绝
            </button>
            <button type="button" className="always-allow" onClick={() => setFormOpen(true)}>
              始终允许…
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export default ApprovalModal
