import { Check, Folder, Lightbulb, Paperclip, Target } from 'lucide-react'

interface ComposerPlusMenuProps {
  open: boolean
  planMode: boolean
  onClose: () => void
  onAttachFile: () => void
  onPickWorkspace: () => void
  onOpenGoal: () => void
  onTogglePlanMode: () => void
}

function ComposerPlusMenu({
  open,
  planMode,
  onClose,
  onAttachFile,
  onPickWorkspace,
  onOpenGoal,
  onTogglePlanMode
}: ComposerPlusMenuProps): React.JSX.Element | null {
  if (!open) return null
  return (
    <div className="composer-plus-menu" role="menu" data-testid="composer-plus-menu">
      <p className="composer-plus-heading">添加</p>
      <button type="button" role="menuitem" data-testid="plus-attach" onClick={() => { onAttachFile(); onClose() }}>
        <Paperclip aria-hidden="true" size={16} />
        <span>
          <strong>文件和文件夹</strong>
          <small>把本地文件附加到这次对话</small>
        </span>
      </button>
      <button type="button" role="menuitem" data-testid="plus-workspace" onClick={() => { onPickWorkspace(); onClose() }}>
        <Folder aria-hidden="true" size={16} />
        <span>
          <strong>在项目中使用</strong>
          <small>选择工作区并开新聊天</small>
        </span>
      </button>
      <button type="button" role="menuitem" data-testid="plus-goal" onClick={() => { onOpenGoal(); onClose() }}>
        <Target aria-hidden="true" size={16} />
        <span>
          <strong>目标</strong>
          <small>设置要持续追求的目标</small>
        </span>
      </button>
      <button
        type="button"
        role="menuitem"
        data-testid="plus-plan-mode"
        className={planMode ? 'is-active' : undefined}
        onClick={() => { onTogglePlanMode(); onClose() }}
      >
        <Lightbulb aria-hidden="true" size={16} />
        <span>
          <strong>计划模式</strong>
          <small>{planMode ? '已开启，只生成和改写计划文档' : '开启计划模式'}</small>
        </span>
        {planMode ? <Check aria-hidden="true" size={14} /> : null}
      </button>
    </div>
  )
}

export default ComposerPlusMenu
