import { Copy, Lightbulb } from 'lucide-react'
import { useState } from 'react'
import { shouldSubmitOnKey } from '../lib/composerBehavior.mts'
import type { PlanDocument } from '../lib/planDocument.mts'

interface PlanDocumentCardProps {
  document: PlanDocument
  showActions: boolean
  disabled?: boolean
  onBuild: () => void
  onRevise: (feedback: string) => void
  onSkip: () => void
}

function PlanDocumentCard({
  document,
  showActions,
  disabled = false,
  onBuild,
  onRevise,
  onSkip
}: PlanDocumentCardProps): React.JSX.Element {
  const [feedback, setFeedback] = useState('')
  const [copied, setCopied] = useState(false)

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(document.raw)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  const submitRevision = (): void => {
    const text = feedback.trim()
    if (text === '' || disabled) return
    onRevise(text)
    setFeedback('')
  }

  return (
    <article className="plan-document" data-testid="plan-document">
      <header className="plan-document-header">
        <div className="plan-document-kicker">
          <Lightbulb aria-hidden="true" size={15} />
          <span>计划</span>
        </div>
        <button
          type="button"
          className="plan-document-copy"
          data-testid="plan-document-copy"
          aria-label="复制计划文档"
          onClick={() => void copy()}
        >
          <Copy aria-hidden="true" size={14} />
          {copied ? '已复制' : '复制'}
        </button>
      </header>
      <h2 data-testid="plan-document-title">{document.title}</h2>
      <h3>Summary</h3>
      <p data-testid="plan-document-summary">{document.summary}</p>
      {document.steps.length > 0 && (
        <>
          <h3>Steps</h3>
          <ol data-testid="plan-document-steps">
            {document.steps.map((step, index) => (
              <li key={`${index}-${step}`}>{step}</li>
            ))}
          </ol>
        </>
      )}
      {showActions && (
        <section className="plan-actions" data-testid="plan-actions">
          <div className="plan-actions-title-row">
            <h3>实施此计划？</h3>
            <button type="button" className="plan-skip" data-testid="plan-skip" onClick={onSkip} disabled={disabled}>
              跳过
            </button>
          </div>
          <button
            type="button"
            className="plan-build"
            data-testid="plan-build"
            disabled={disabled}
            onClick={onBuild}
          >
            <span className="plan-build-index">1</span>
            <span>是，实施此计划</span>
            <span aria-hidden="true">→</span>
          </button>
          <label className="plan-revise">
            <span className="sr-only">补充说明哪里需要改进</span>
            <textarea
              data-testid="plan-revise-input"
              placeholder="请你补充说明哪里需要改进"
              value={feedback}
              disabled={disabled}
              rows={2}
              onChange={(event) => setFeedback(event.target.value)}
              onKeyDown={(event) => {
                if (shouldSubmitOnKey({ key: event.key, shiftKey: event.shiftKey, running: Boolean(disabled) })) {
                  event.preventDefault()
                  submitRevision()
                }
              }}
            />
          </label>
        </section>
      )}
    </article>
  )
}

export default PlanDocumentCard
