import { useEffect, useRef } from 'react'
import type { ChatMessage, ToolCall } from '../lib/conversationStore.mts'

interface ChatAreaProps {
  messages: ChatMessage[]
  tools: ToolCall[]
  running: boolean
  error: string | null
}

function ChatArea({ messages, tools, running, error }: ChatAreaProps): React.JSX.Element {
  const scrollRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el !== null) el.scrollTop = el.scrollHeight
  }, [messages, tools, running, error])

  if (messages.length === 0) {
    return (
      <section className="chat-area" ref={scrollRef}>
        <div className="chat-empty">
          <p>新建会话后，在下方输入你的需求</p>
        </div>
      </section>
    )
  }
  return (
    <section className="chat-area" ref={scrollRef}>
      <div className="chat-messages">
        {messages.map((message) => (
          <div
            key={message.id}
            className={`message ${message.role}${message.status === 'error' ? ' error' : ''}`}
          >
            <div className="message-role">{message.role === 'user' ? '你' : 'Agent'}</div>
            <div className="message-text">
              {message.text !== '' ? message.text : message.status === 'streaming' ? '…' : ''}
            </div>
          </div>
        ))}
        {tools.length > 0 && (
          <div className="tool-cards">
            {tools.map((tool) => (
              <div key={tool.callId} className={`tool-card ${tool.status}`}>
                <span className="tool-name">{tool.toolName}</span>
                <span className="tool-status">
                  {tool.status === 'running' ? '运行中' : tool.status === 'ok' ? '完成' : '失败'}
                </span>
                {tool.summary !== undefined && <span className="tool-summary">{tool.summary}</span>}
              </div>
            ))}
          </div>
        )}
        {running && <div className="running-indicator">运行中…</div>}
      </div>
      {error !== null && <div className="error-banner">{error}</div>}
    </section>
  )
}

export default ChatArea
