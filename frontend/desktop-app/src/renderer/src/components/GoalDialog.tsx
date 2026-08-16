import { useEffect, useRef } from 'react'

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
  const inputRef = useRef<HTMLTextAreaElement | null>(null)

  useEffect(() => {
    if (!open) return
    inputRef.current?.focus()
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      event.stopPropagation()
      onClose()
    }
    window.addEventListener('keydown', closeOnEscape, true)
    return () => window.removeEventListener('keydown', closeOnEscape, true)
  }, [open, onClose])

  if (!open) return null
  return (
    <div
      className="confirm-overlay"
      role="presentation"
      data-testid="goal-dialog"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div className="confirm-dialog goal-dialog" role="dialog" aria-modal="true" aria-labelledby="goal-title">
        <h2 id="goal-title">目标</h2>
        <p>设置要持续追求的目标。之后每一轮对话都会带上它，直到你清除。</p>
        <textarea
          ref={inputRef}
          data-testid="goal-input"
          aria-label="持续目标"
          placeholder="/goal 例如：把登录流程做成可演示的产品"
          value={value}
          rows={4}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
              event.preventDefault()
              onSave()
            }
          }}
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
