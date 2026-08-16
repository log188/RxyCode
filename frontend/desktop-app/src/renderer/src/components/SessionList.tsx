import { Pencil, Plus, RotateCcw, Search, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { RunState, SessionEntry } from '../lib/conversationStore.mts'

interface SessionListProps {
  sessions: SessionEntry[]
  activeSessionId: string | null
  runStateBySession?: Record<string, RunState>
  childCountBySession?: Record<string, number>
  disabled: boolean
  onCreate: () => void
  onSelect: (sessionId: string) => void
  onRename?: (sessionId: string, title: string) => void
  onTrash?: (sessionId: string) => void
  onRestore?: (sessionId: string) => void
  onPurge?: (sessionId: string) => void
}

function SessionList({
  sessions,
  activeSessionId,
  runStateBySession = {},
  childCountBySession = {},
  disabled,
  onCreate,
  onSelect,
  onRename,
  onTrash,
  onRestore,
  onPurge
}: SessionListProps): React.JSX.Element {
  const [query, setQuery] = useState('')
  const [showTrash, setShowTrash] = useState(false)
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [purgeId, setPurgeId] = useState<string | null>(null)
  const renameInputRef = useRef<HTMLInputElement>(null)
  const purgeCancelRef = useRef<HTMLButtonElement>(null)
  const normalizedQuery = query.trim().toLowerCase()
  const matches = (session: SessionEntry): boolean =>
    normalizedQuery === '' || `${session.title} ${session.workspaceRoot}`.toLowerCase().includes(normalizedQuery)
  const activeTasks = useMemo(
    () => sessions.filter((session) => session.trashedAt === null && matches(session)),
    [sessions, normalizedQuery]
  )
  const trashedTasks = useMemo(
    () => sessions.filter((session) => session.trashedAt !== null && matches(session)),
    [sessions, normalizedQuery]
  )

  useEffect(() => {
    if (renamingId !== null) renameInputRef.current?.focus()
  }, [renamingId])

  useEffect(() => {
    if (purgeId === null) return
    purgeCancelRef.current?.focus()
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') setPurgeId(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [purgeId])

  const requestRename = (session: SessionEntry): void => {
    if (onRename === undefined) return
    setRenamingId(session.sessionId)
    setRenameValue(session.title)
  }

  const submitRename = (sessionId: string): void => {
    const next = renameValue.trim()
    if (onRename !== undefined && next !== '') onRename(sessionId, next)
    setRenamingId(null)
    setRenameValue('')
  }

  const renderTask = (session: SessionEntry, trashed: boolean): React.JSX.Element => {
    const state = runStateBySession[session.sessionId] ?? 'succeeded'
    const childCount = childCountBySession[session.sessionId] ?? 0
    return (
      <li key={session.sessionId} className="session-row">
        <div className="session-row-main">
          {renamingId === session.sessionId && !trashed ? (
            <form
              className="session-rename-form"
              onSubmit={(event) => {
                event.preventDefault()
                submitRename(session.sessionId)
              }}
              onClick={(event) => event.stopPropagation()}
            >
              <input
                ref={renameInputRef}
                value={renameValue}
                onChange={(event) => setRenameValue(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') {
                    event.preventDefault()
                    setRenamingId(null)
                    setRenameValue('')
                  }
                }}
                aria-label={`Rename ${session.title}`}
                data-testid={`rename-input-${session.sessionId}`}
              />
              <button type="submit" className="rename-save" data-testid={`rename-save-${session.sessionId}`}>Save</button>
              <button type="button" className="rename-cancel" data-testid={`rename-cancel-${session.sessionId}`} onClick={() => { setRenamingId(null); setRenameValue('') }}>Cancel</button>
            </form>
          ) : (
            <button
              type="button"
              className={`session-item${session.sessionId === activeSessionId ? ' active' : ''}`}
              onClick={() => onSelect(session.sessionId)}
              disabled={trashed}
              data-testid={`session-${session.sessionId}`}
            >
              <span className="session-title-row">
                <span className="session-title">{session.title}</span>
                {!trashed && <span className={'session-state state-' + state}>{state === 'succeeded' ? 'ready' : state}</span>}
              </span>
              <span className="session-id">{session.sessionId}</span>
              <span className="session-workspace" title={session.workspaceRoot}>{session.workspaceRoot}</span>
              {childCount > 0 && <span className="session-child-count">{childCount} child agents</span>}
            </button>
          )}
        </div>
        <div className="session-actions" aria-label={`${session.title} actions`}>
          {trashed ? (
            <>
              <button type="button" className="icon-button" title="Restore task" aria-label="Restore task" data-testid={`restore-task-${session.sessionId}`} onClick={() => onRestore?.(session.sessionId)}>
                <RotateCcw aria-hidden="true" size={14} />
              </button>
              <button type="button" className="icon-button danger" title="Delete permanently" aria-label="Delete permanently" data-testid={`purge-task-${session.sessionId}`} onClick={() => {
                setPurgeId(session.sessionId)
              }}>
                <Trash2 aria-hidden="true" size={14} />
              </button>
            </>
          ) : (
            <>
              <button type="button" className="icon-button" title="Rename task" aria-label="Rename task" data-testid={`rename-task-${session.sessionId}`} onClick={() => requestRename(session)}>
                <Pencil aria-hidden="true" size={14} />
              </button>
              <button type="button" className="icon-button danger" title="Move to recently deleted" aria-label="Move to recently deleted" data-testid={`trash-task-${session.sessionId}`} onClick={() => onTrash?.(session.sessionId)}>
                <Trash2 aria-hidden="true" size={14} />
              </button>
            </>
          )}
        </div>
      </li>
    )
  }

  return (
    <aside className="session-panel" data-testid="session-nav" aria-label="Tasks and sessions">
      <div className="panel-header">
        <span className="panel-title">Tasks</span>
        <button type="button" className="new-session" onClick={onCreate} disabled={disabled} title="New task" aria-label="New task" data-testid="new-session">
          <Plus aria-hidden="true" size={16} />
        </button>
      </div>
      <label className="session-search">
        <Search aria-hidden="true" size={14} />
        <span className="sr-only">Search tasks</span>
        <input type="search" placeholder="Search tasks" aria-label="Search tasks" value={query} onChange={(event) => setQuery(event.target.value)} />
      </label>
      {activeTasks.length === 0 && trashedTasks.length === 0 ? (
        <p className="empty-hint">No tasks yet. Create a task to begin.</p>
      ) : (
        <>
          {activeTasks.length > 0 && <ul className="session-list">{activeTasks.map((session) => renderTask(session, false))}</ul>}
          {trashedTasks.length > 0 && (
            <section className="recently-deleted">
              <button type="button" className="trash-toggle" aria-expanded={showTrash} onClick={() => setShowTrash((value) => !value)}>
                Recently deleted ({trashedTasks.length})
              </button>
              {showTrash && <ul className="session-list trashed-list">{trashedTasks.map((session) => renderTask(session, true))}</ul>}
            </section>
          )}
        </>
      )}
      {purgeId !== null && (
        <div className="task-dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPurgeId(null) }}>
          <section className="task-dialog" role="dialog" aria-modal="true" aria-labelledby="purge-task-title" data-testid="purge-dialog">
            <p className="inspector-eyebrow">PERMANENT ACTION</p>
            <h2 id="purge-task-title">Delete this task permanently?</h2>
            <p>Only the saved task history will be removed. Workspace files, repositories, and generated artifacts are not deleted.</p>
            <div className="task-dialog-actions">
              <button ref={purgeCancelRef} type="button" onClick={() => setPurgeId(null)}>Cancel</button>
              <button type="button" className="danger" onClick={() => { onPurge?.(purgeId); setPurgeId(null) }}>Delete permanently</button>
            </div>
          </section>
        </div>
      )}
    </aside>
  )
}

export default SessionList
