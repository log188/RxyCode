import { useState } from 'react'
import ApprovalModal from './components/ApprovalModal'
import ApprovalRulesModal from './components/ApprovalRulesModal'
import ChatArea from './components/ChatArea'
import Composer from './components/Composer'
import SessionList from './components/SessionList'
import SettingsPage from './components/SettingsPage'
import { useConversation } from './hooks/useConversation'
import { useModels } from './hooks/useModels'
import {
  effectiveWorkspaceRoot,
  loadWorkspaceSettings,
  normalizeWorkspaceRoot,
  saveWorkspaceSettings,
  type WorkspaceSettings
} from './lib/workspaceSettings.mts'
import { usePlatform } from '../../platform/index.mts'

function App(): React.JSX.Element {
  const { platform, info, status } = usePlatform()
  const [workspaceSettings, setWorkspaceSettings] = useState<WorkspaceSettings>(() =>
    loadWorkspaceSettings(window.localStorage)
  )
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [pickingWorkspace, setPickingWorkspace] = useState(false)
  const conversation = useConversation(platform, info, status, workspaceSettings.workspaceRoot)
  const [rulesOpen, setRulesOpen] = useState(false)
  const activeSessionId = conversation.state.activeSessionId
  const running = activeSessionId !== null && conversation.state.runningBySession[activeSessionId]
  const pendingApproval = conversation.state.approvals[0] ?? null
  const effectiveWorkspace = effectiveWorkspaceRoot(workspaceSettings, info?.repoRoot ?? '')
  const models = useModels({
    client: conversation.protocolClient,
    refreshKey: settingsOpen ? 1 : 0
  })

  const start = (): void => {
    platform.start()
  }
  const stop = (): void => {
    platform.stop()
  }
  const pickWorkspace = async (): Promise<void> => {
    setPickingWorkspace(true)
    try {
      const picked = await platform.pickWorkspaceDirectory()
      if (picked !== null) {
        const next: WorkspaceSettings = { workspaceRoot: normalizeWorkspaceRoot(picked) }
        setWorkspaceSettings(next)
        saveWorkspaceSettings(next, window.localStorage)
      }
    } finally {
      setPickingWorkspace(false)
    }
  }
  const clearWorkspace = (): void => {
    const next: WorkspaceSettings = { workspaceRoot: null }
    setWorkspaceSettings(next)
    saveWorkspaceSettings(next, window.localStorage)
  }

  return (
    <div className="workspace">
      <header className="topbar">
        <div className="brand">RxyCode Desktop</div>
        <div className="row">
          <span className={`badge ${status}`}>{status}</span>
          <span className="label">appserver</span>
          <button type="button" className="settings-button" onClick={() => setSettingsOpen(true)}>
            设置
          </button>
          <button type="button" className="rules-button" onClick={() => setRulesOpen(true)}>
            权限
          </button>
          <button
            type="button"
            className="appserver-start"
            onClick={start}
            disabled={status === 'running' || status === 'starting'}
          >
            Start
          </button>
          <button
            type="button"
            className="appserver-stop"
            onClick={stop}
            disabled={status === 'stopped' || status === 'crashed'}
          >
            Stop
          </button>
        </div>
      </header>
      <div className="main-layout">
        <SessionList
          sessions={conversation.state.sessions}
          activeSessionId={activeSessionId}
          onCreate={() => void conversation.createSession()}
          onSelect={conversation.selectSession}
          disabled={status !== 'running'}
        />
        <div className="chat-column">
          {conversation.connectionError !== null && (
            <div className="error-banner">appserver 连接失败：{conversation.connectionError}</div>
          )}
          <ChatArea
            messages={
              activeSessionId !== null
                ? (conversation.state.messagesBySession[activeSessionId] ?? [])
                : []
            }
            tools={
              activeSessionId !== null
                ? (conversation.state.toolsBySession[activeSessionId] ?? [])
                : []
            }
            running={running}
            error={
              activeSessionId !== null
                ? (conversation.state.errorBySession[activeSessionId] ?? null)
                : null
            }
          />
          <Composer
            disabled={status !== 'running' || activeSessionId === null}
            running={running}
            onSend={(text) => void conversation.sendMessage(text)}
            onStop={() => void conversation.interrupt()}
          />
        </div>
      </div>
      {pendingApproval !== null && (
        <ApprovalModal
          item={pendingApproval}
          onApprove={() => conversation.resolveApproval(pendingApproval.requestId, 'approved')}
          onReject={() => conversation.resolveApproval(pendingApproval.requestId, 'rejected')}
          onAlwaysAllow={(scope, hours) =>
            conversation.saveAlwaysAllowRule(pendingApproval.requestId, scope, hours)
          }
          onDismiss={() => conversation.dismissApproval(pendingApproval.requestId)}
        />
      )}
      <ApprovalRulesModal
        open={rulesOpen}
        rules={conversation.approvalRules}
        onClose={() => setRulesOpen(false)}
        onRevoke={conversation.revokeApprovalRule}
      />
      {settingsOpen && (
        <SettingsPage
          appVersion={info?.appVersion ?? ''}
          repoRoot={info?.repoRoot ?? ''}
          savedWorkspaceRoot={workspaceSettings.workspaceRoot}
          effectiveWorkspaceRoot={effectiveWorkspace}
          picking={pickingWorkspace}
          onClose={() => setSettingsOpen(false)}
          onPickWorkspace={() => void pickWorkspace()}
          onClearWorkspace={clearWorkspace}
          models={models}
        />
      )}
    </div>
  )
}

export default App
