import { FolderGit2, GitBranch, Sparkles } from 'lucide-react'

interface TaskHeaderProps {
  title: string
  workspaceRoot: string
  modelLabel: string
  runState: string
}

function TaskHeader({
  title,
  workspaceRoot,
  modelLabel,
  runState
}: TaskHeaderProps): React.JSX.Element {
  return (
    <header className="task-header">
      <div>
        <p className="task-kicker">TASK</p>
        <h1>{title}</h1>
      </div>
      <div className="task-metadata" aria-label="Task metadata">
        <span title={workspaceRoot}>
          <FolderGit2 aria-hidden="true" size={14} />
          {workspaceRoot === '' ? 'No workspace selected' : workspaceRoot}
        </span>
        <span>
          <GitBranch aria-hidden="true" size={14} />
          workspace
        </span>
        <span>
          <Sparkles aria-hidden="true" size={14} />
          {modelLabel}
        </span>
        <span className={'task-status state-' + runState}>{runState.replace('_', ' ')}</span>
      </div>
    </header>
  )
}

export default TaskHeader
