import { useState } from 'react'

interface ComposerProps {
  disabled: boolean
  running: boolean
  onSend: (text: string) => void
  onStop: () => void
}

function Composer({ disabled, running, onSend, onStop }: ComposerProps): React.JSX.Element {
  const [text, setText] = useState('')
  const canSend = !disabled && !running && text.trim() !== ''

  const submit = (): void => {
    if (!canSend) return
    onSend(text)
    setText('')
  }

  const handleAction = (): void => {
    if (running) {
      onStop()
    } else {
      submit()
    }
  }

  return (
    <footer className="composer">
      <textarea
        value={text}
        placeholder={
          disabled
            ? '等待 appserver 就绪…'
            : running
              ? '正在运行，可点击停止'
              : '输入需求，Enter 发送，Shift+Enter 换行'
        }
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (!running && event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault()
            submit()
          }
        }}
        rows={3}
      />
      <button
        type="button"
        className={running ? 'stop' : 'send'}
        onClick={handleAction}
        disabled={!running && !canSend}
      >
        {running ? '停止' : '发送'}
      </button>
    </footer>
  )
}

export default Composer
