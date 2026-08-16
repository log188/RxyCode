interface GoalDialogProps {
  open: boolean
  value: string
  onChange: (value: string) => void
  onClose: () => void
  onSave: () => void
  onClear: () => void
}

function GoalDialog({
  open,
  value,
  onChange,
  onClose,
  onSave,
  onClear
}: GoalDialogProps): React.JSX.Element | null {
  if (!open) return null
  return (
    <div className="confirm-overlay" role="presentation" data-testid="goal-dialog">
      <div className="confirm-dialog goal-dialog" role="dialog" aria-modal="true" aria-labelledby="goal-title">
        <h2 id="goal-title">目标</h2>
        <p>设置要持续追求的目标。之后每一轮对话都会带上它，直到你清除。</p>
        <textarea
          data-testid="goal-input"
          aria-label="持续目标"
          placeholder="/goal 例如：把登录流程做成可演示的产品"
          value={value}
          rows={4}
          onChange={(event) => onChange(event.target.value)}
        />
        <div className="confirm-actions">
          <button type="button" onClick={onClose}>取消</button>
          <button type="button" data-testid="goal-clear" onClick={onClear}>清除</button>
          <button type="button" className="primary-action" data-testid="goal-save" onClick={onSave}>保存目标</button>
        </div>
      </div>
    </div>
  )
}

export default GoalDialog
