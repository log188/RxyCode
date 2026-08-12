import { useState } from 'react'
import type { ModelEntry } from '../hooks/useModels'
import { groupModelsByProvider } from '../lib/modelPresentation.mts'

interface ComposerProps {
  disabled: boolean
  running: boolean
  onSend: (text: string) => void
  onStop: () => void
  models: ModelEntry[]
  selectedModelId: string
  onSelectModel: (modelId: string) => void
  onOpenModelSettings?: () => void
}

function Composer({
  disabled,
  running,
  onSend,
  onStop,
  models,
  selectedModelId,
  onSelectModel,
  onOpenModelSettings
}: ComposerProps): React.JSX.Element {
  const [text, setText] = useState('')
  const canSend = !disabled && !running && text.trim() !== ''

  const submit = (): void => {
    if (!canSend) return
    onSend(text)
    setText('')
  }

  const handleAction = (): void => {
    if (running) onStop()
    else submit()
  }

  const groups = groupModelsByProvider(models)

  return (
    <footer className="composer">
      <textarea
        aria-label="Task prompt"
        value={text}
        placeholder={
          disabled
            ? 'Waiting for appserver…'
            : running
              ? 'Running — press Stop to cancel'
              : 'Describe the task… Enter to send, Shift+Enter for a new line'
        }
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && running) {
            event.preventDefault()
            onStop()
          } else if (!running && event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            submit()
          }
        }}
        rows={3}
      />
      <div className="composer-controls">
        <div className="composer-model-control">
          <label htmlFor="composer-model">Model</label>
          <select
            id="composer-model"
            aria-label="Task model"
            value={selectedModelId}
            disabled={disabled || running || models.length === 0}
            onChange={(event) => onSelectModel(event.target.value)}
          >
            {models.length === 0 ? (
              <option value="">No configured models</option>
            ) : (
              groups.map(([group, entries]) => (
                <optgroup key={group} label={group}>
                  {entries.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.nickname || model.name || model.provider_model_id}
                    </option>
                  ))}
                </optgroup>
              ))
            )}
          </select>
          {onOpenModelSettings !== undefined && (
            <button type="button" className="model-manage" onClick={onOpenModelSettings}>
              Manage
            </button>
          )}
        </div>
        <button
          type="button"
          className={running ? 'stop' : 'send'}
          onClick={handleAction}
          disabled={!running && !canSend}
        >
          {running ? 'Stop' : 'Send'}
        </button>
      </div>
    </footer>
  )
}

export default Composer
