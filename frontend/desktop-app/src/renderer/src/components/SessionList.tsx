import type { SessionEntry } from '../lib/conversationStore.mts'

interface SessionListProps {
  sessions: SessionEntry[]
  activeSessionId: string | null
  disabled: boolean
  onCreate: () => void
  onSelect: (sessionId: string) => void
}

function SessionList({
  sessions,
  activeSessionId,
  disabled,
  onCreate,
  onSelect
}: SessionListProps): React.JSX.Element {
  return (
    <aside className="session-panel">
      <div className="panel-header">
        <span className="panel-title">会话</span>
        <button
          type="button"
          className="new-session"
          onClick={onCreate}
          disabled={disabled}
          title="新建会话"
        >
          +
        </button>
      </div>
      {sessions.length === 0 ? (
        <p className="empty-hint">暂无会话，点击 + 新建</p>
      ) : (
        <ul className="session-list">
          {sessions.map((session) => (
            <li key={session.sessionId}>
              <button
                type="button"
                className={`session-item${session.sessionId === activeSessionId ? ' active' : ''}`}
                onClick={() => onSelect(session.sessionId)}
              >
                <span className="session-title">{session.title}</span>
                <span className="session-id">{session.sessionId}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}

export default SessionList
