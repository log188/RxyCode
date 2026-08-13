import { useEffect, useState } from 'react'
import type { QuestionRequest } from '@rxycode/protocol-client'

interface QuestionModalProps {
  request: QuestionRequest
  onAnswer: (answer: string) => void
  onCancel: () => void
}

function QuestionModal({ request, onAnswer, onCancel }: QuestionModalProps): React.JSX.Element {
  const options = request.options ?? []
  const hasOptions = options.length > 0
  const [draft, setDraft] = useState('')

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape') return
      event.preventDefault()
      onCancel()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onCancel])

  return (
    <div className="approval-overlay">
      <div className="approval-dialog" role="dialog" aria-modal="true">
        <div className="approval-header">
          <span className="approval-title">{request.header || '需要你的选择'}</span>
        </div>
        <div className="approval-action">{request.question}</div>
        {hasOptions ? (
          <div className="approval-actions" style={{ flexDirection: 'column', alignItems: 'stretch' }}>
            {options.map((option) => (
              <button
                key={option.value}
                type="button"
                className="approval-approve"
                onClick={() => onAnswer(option.value)}
              >
                {option.label}
              </button>
            ))}
            <button type="button" className="approval-reject" onClick={onCancel}>
              取消
            </button>
          </div>
        ) : (
          <form
            className="approval-actions"
            style={{ flexDirection: 'column', alignItems: 'stretch' }}
            onSubmit={(event) => {
              event.preventDefault()
              onAnswer(draft.trim())
            }}
          >
            <input
              autoFocus
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="输入回答"
            />
            <div className="approval-actions">
              <button type="submit" className="approval-approve" disabled={!draft.trim()}>
                提交
              </button>
              <button type="button" className="approval-reject" onClick={onCancel}>
                取消
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

export default QuestionModal
