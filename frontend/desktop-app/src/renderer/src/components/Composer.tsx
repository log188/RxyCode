import { ArrowUp, ChevronDown, Mic, Paperclip, Plus, Square } from 'lucide-react'
import { useRef, useState } from 'react'
import type { ModelEntry } from '../hooks/useModels'
import { groupModelsByProvider } from '../lib/modelPresentation.mts'
import type { PermissionMode } from '../lib/desktopPreferences.mts'
import { canSubmitComposer, shouldSubmitOnKey } from '../lib/composerBehavior.mts'

interface ComposerProps {
  disabled: boolean
  running: boolean
  onSend: (text: string) => void
  onStop: () => void
  models: ModelEntry[]
  modelsLoading?: boolean
  selectedModelId: string
  onSelectModel: (modelId: string) => void
  permissionMode: PermissionMode
  onRequestPermissionModeChange: (mode: PermissionMode) => void
}

const MODE_LABELS: Record<PermissionMode, string> = {
  confirm_all: 'Ask before changes',
  auto_edit: 'Auto-edit',
  full_auto: 'Full access'
}

function Composer({
  disabled,
  running,
  onSend,
  onStop,
  models,
  modelsLoading = false,
  selectedModelId,
  onSelectModel,
  permissionMode,
  onRequestPermissionModeChange
}: ComposerProps): React.JSX.Element {
  const [text, setText] = useState('')
  const [attachment, setAttachment] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const canSend = canSubmitComposer({ disabled, running, text })
  const groups = groupModelsByProvider(models)

  const submit = (): void => {
    if (!canSend) return
    onSend(text.trim())
    setText('')
  }

  return (
    <footer className="composer" data-testid="composer">
      <form className="composer-surface" data-testid="composer-surface" onSubmit={(event) => { event.preventDefault(); submit() }}>
        {attachment !== null && (
          <div className="composer-attachment" data-testid="composer-attachment">
            <Paperclip aria-hidden="true" size={13} />
            <span>{attachment}</span>
            <button
              type="button"
              className="composer-attachment-remove"
              aria-label="Remove attachment"
              onClick={() => setAttachment(null)}
            >
              ×
            </button>
          </div>
        )}
        <textarea
          aria-label="Task prompt"
          data-testid="composer-input"
          value={text}
          placeholder={
            disabled
              ? 'Waiting for appserver…'
              : running
                ? 'Running — press Stop to cancel'
                : 'Describe the task…'
          }
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Escape' && running) {
              event.preventDefault()
              onStop()
            } else if (shouldSubmitOnKey({ key: event.key, shiftKey: event.shiftKey, running })) {
              event.preventDefault()
              submit()
            }
          }}
          rows={1}
          disabled={disabled}
        />
        <input
          ref={fileInputRef}
          type="file"
          className="composer-file-input"
          aria-hidden="true"
          tabIndex={-1}
          onChange={(event) => setAttachment(event.target.files?.[0]?.name ?? null)}
        />
        <div className="composer-toolbar">
          <div className="composer-toolbar-left">
            <button
              type="button"
              className="composer-icon-button"
              aria-label="Add attachment"
              title="Add attachment"
              onClick={() => fileInputRef.current?.click()}
              disabled={disabled || running}
            >
              <Plus aria-hidden="true" size={18} />
            </button>
            <label className="composer-permission-control">
              <span className="sr-only">Permission mode for this task</span>
              <select
                aria-label="Permission mode for this task"
                data-testid="composer-permission-mode"
                value={permissionMode}
                disabled={disabled || running}
                onChange={(event) => onRequestPermissionModeChange(event.target.value as PermissionMode)}
              >
                {(Object.keys(MODE_LABELS) as PermissionMode[]).map((mode) => (
                  <option key={mode} value={mode}>{MODE_LABELS[mode]}</option>
                ))}
              </select>
              <ChevronDown aria-hidden="true" size={13} />
            </label>
          </div>
          <div className="composer-toolbar-right">
            <label className="composer-model-control">
              <span className="sr-only">Task model</span>
              <select
                id="composer-model"
                aria-label="Task model"
                data-testid="composer-model"
                value={selectedModelId}
                disabled={disabled || running || models.length === 0}
                onChange={(event) => onSelectModel(event.target.value)}
              >
                {models.length === 0 ? (
                  <option value="">{modelsLoading ? 'Loading models…' : 'No configured models'}</option>
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
              <ChevronDown aria-hidden="true" size={13} />
            </label>
            <button
              type="button"
              className="composer-icon-button composer-mic"
              aria-label="Voice input unavailable"
              title="Voice input is not configured"
              disabled
            >
              <Mic aria-hidden="true" size={16} />
            </button>
            <button
              type={running ? 'button' : 'submit'}
              className={running ? 'composer-send composer-stop stop' : 'composer-send send'}
              data-testid={running ? 'composer-stop' : 'composer-send'}
              aria-label={running ? 'Stop task' : 'Send task'}
              onClick={running ? onStop : undefined}
              disabled={!running && !canSend}
            >
              {running ? <Square aria-hidden="true" size={14} fill="currentColor" /> : <ArrowUp aria-hidden="true" size={19} />}
            </button>
          </div>
        </div>
      </form>
    </footer>
  )
}

export default Composer
