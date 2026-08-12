import { Activity, Menu, PanelRight, Settings, ShieldCheck, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import ApprovalModal from './components/ApprovalModal'
import ApprovalRulesModal from './components/ApprovalRulesModal'
import ChatArea from './components/ChatArea'
import Composer from './components/Composer'
import SessionList from './components/SessionList'
import SettingsPage from './components/SettingsPage'
import TaskHeader from './components/TaskHeader'
import TaskInspector from './components/TaskInspector'
import { useConversation } from './hooks/useConversation'
import { useModels } from './hooks/useModels'
import type { TimelineItem } from './lib/conversationStore.mts'
import {
  effectiveWorkspaceRoot,
  loadWorkspaceSettings,
  normalizeWorkspaceRoot,
  saveWorkspaceSettings,
  type WorkspaceSettings
} from './lib/workspaceSettings.mts'
import { usePlatform } from '../../platform/index.mts'
import {
  loadDesktopPreferences,
  saveDesktopPreferences,
  type DesktopLanguage,
  type PermissionMode,
  type ThemePreference
} from './lib/desktopPreferences.mts'

const EMPTY_USAGE = {
  inputTokens: null,
  outputTokens: null,
  cacheHitTokens: null,
  cacheWriteTokens: null,
  cacheHitRate: null,
  reportingStatus: 'not_reported' as const
}

function App(): React.JSX.Element {
  const { platform, info, status } = usePlatform()
  const [workspaceSettings, setWorkspaceSettings] = useState<WorkspaceSettings>(() =>
    loadWorkspaceSettings(window.localStorage)
  )
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [pickingWorkspace, setPickingWorkspace] = useState(false)
  const [rulesOpen, setRulesOpen] = useState(false)
  const [preferences, setPreferences] = useState(() => loadDesktopPreferences(window.localStorage))
  const { theme, permissionMode, language } = preferences
  const [pendingFullAuto, setPendingFullAuto] = useState(false)
  const [navOpen, setNavOpen] = useState(false)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [inspectorItem, setInspectorItem] = useState<TimelineItem | null>(null)
  const conversation = useConversation(platform, info, status, workspaceSettings.workspaceRoot)
  const activeSessionId = conversation.state.activeSessionId
  const running = activeSessionId !== null && conversation.state.runningBySession[activeSessionId]
  const activeSession = conversation.state.sessions.find((session) => session.sessionId === activeSessionId)
  const activeRunState =
    activeSessionId === null ? 'succeeded' : conversation.state.runStateBySession[activeSessionId] ?? 'succeeded'
  const childCountBySession = Object.fromEntries(
    Object.entries(conversation.state.childSessionsByRoot).map(([sessionId, children]) => [
      sessionId,
      children.length
    ])
  )
  const activeChildSessions =
    activeSessionId === null ? [] : (conversation.state.childSessionsByRoot[activeSessionId] ?? [])
  const pendingApproval = conversation.state.approvals[0] ?? null
  const effectiveWorkspace = effectiveWorkspaceRoot(workspaceSettings, info?.repoRoot ?? '')
  const models = useModels({
    client: conversation.protocolClient,
    refreshKey: settingsOpen ? 1 : 0
  })
  const selectedTaskModel = activeSession?.modelId ?? models.snapshot?.active ?? ''

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    saveDesktopPreferences(preferences, window.localStorage)
  }, [preferences, theme])

  const setTheme = (next: ThemePreference): void => {
    setPreferences((current) => ({ ...current, theme: next }))
  }

  const setLanguage = (next: DesktopLanguage): void => {
    setPreferences((current) => ({ ...current, language: next }))
  }

  const requestPermissionModeChange = (next: PermissionMode): void => {
    if (next === 'full_auto' && permissionMode !== 'full_auto') {
      setPendingFullAuto(true)
      return
    }
    setPreferences((current) => ({ ...current, permissionMode: next }))
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

  const openInspector = (item: TimelineItem): void => {
    setInspectorItem(item)
    setInspectorOpen(true)
  }

  return (
    <div className="workspace command-center" data-testid="task-command-center">
      <a className="skip-link" href="#task-main">Skip to task</a>
      <header className="topbar command-topbar">
        <div className="topbar-leading">
          <button
            type="button"
            className="icon-button nav-toggle"
            aria-label="Open task navigation"
            onClick={() => setNavOpen(true)}
          >
            <Menu aria-hidden="true" size={18} />
          </button>
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">R</span>
            <span>RxyCode</span>
            <span className="brand-product">Desktop</span>
          </div>
        </div>
        <div className="topbar-actions">
          <span className={'connection-status ' + status}>
            <Activity aria-hidden="true" size={14} />
            {status}
          </span>
          <button
            type="button"
            className="icon-button rules-button"
            onClick={() => setRulesOpen(true)}
            aria-label="Approval rules"
            title="Approval rules"
          >
            <ShieldCheck aria-hidden="true" size={17} />
          </button>
          <button
            type="button"
            className="icon-button settings-button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Settings"
            title="Settings"
          >
            <Settings aria-hidden="true" size={17} />
          </button>
          <button
            type="button"
            className="icon-button inspector-toggle"
            aria-label="Open task inspector"
            onClick={() => setInspectorOpen(true)}
          >
            <PanelRight aria-hidden="true" size={18} />
          </button>
        </div>
      </header>

      <div className="main-layout command-layout">
        <div className={'mobile-sheet nav-sheet' + (navOpen ? ' open' : '')}>
          <button type="button" className="sheet-backdrop" aria-label="Close navigation" onClick={() => setNavOpen(false)} />
          <div className="sheet-panel">
            <button type="button" className="sheet-close" aria-label="Close navigation" onClick={() => setNavOpen(false)}>
              <X aria-hidden="true" size={18} />
            </button>
            <SessionList
              sessions={conversation.state.sessions}
              activeSessionId={activeSessionId}
              runStateBySession={conversation.state.runStateBySession}
              childCountBySession={childCountBySession}
              disabled={status !== 'running'}
              onCreate={() => void conversation.createSession()}
              onSelect={(sessionId) => {
                conversation.selectSession(sessionId)
                setNavOpen(false)
              }}
              onRename={(sessionId, title) => void conversation.renameSession(sessionId, title)}
              onTrash={(sessionId) => void conversation.trashSession(sessionId)}
              onRestore={(sessionId) => void conversation.restoreSession(sessionId)}
              onPurge={(sessionId) => void conversation.purgeSession(sessionId)}
            />
          </div>
        </div>

        <SessionList
          sessions={conversation.state.sessions}
          activeSessionId={activeSessionId}
          runStateBySession={conversation.state.runStateBySession}
          childCountBySession={childCountBySession}
          disabled={status !== 'running'}
          onCreate={() => void conversation.createSession()}
          onSelect={conversation.selectSession}
          onRename={(sessionId, title) => void conversation.renameSession(sessionId, title)}
          onTrash={(sessionId) => void conversation.trashSession(sessionId)}
          onRestore={(sessionId) => void conversation.restoreSession(sessionId)}
          onPurge={(sessionId) => void conversation.purgeSession(sessionId)}
        />

        <main className="chat-column task-main" id="task-main" data-testid="task-main">
          <TaskHeader
            title={activeSession?.title ?? 'New task'}
            workspaceRoot={activeSession?.workspaceRoot ?? effectiveWorkspace}
            modelLabel={selectedTaskModel || 'Model not connected'}
            runState={activeRunState}
          />
          {conversation.connectionError !== null && (
            <div className="error-banner" role="alert">
              appserver connection failed: {conversation.connectionError}
            </div>
          )}
          <ChatArea
            timeline={activeSessionId !== null ? (conversation.state.timelineBySession[activeSessionId] ?? []) : []}
            running={running}
            error={activeSessionId !== null ? (conversation.state.errorBySession[activeSessionId] ?? null) : null}
            onOpenInspector={openInspector}
          />
          <Composer
            disabled={status !== 'running' || activeSessionId === null}
            running={running}
            onSend={(text) => void conversation.sendMessage(text, permissionMode)}
            onStop={() => void conversation.interrupt()}
            models={models.snapshot?.models ?? []}
            selectedModelId={selectedTaskModel}
            onSelectModel={(modelId) => {
              if (activeSessionId !== null) {
                const selected = models.snapshot?.models.find((model) => model.id === modelId)
                void conversation.setSessionModel(activeSessionId, modelId, selected?.provider_id ?? null)
              }
            }}
            permissionMode={permissionMode}
            onRequestPermissionModeChange={requestPermissionModeChange}
          />
        </main>

        {inspectorOpen && (
          <div className="contextual-inspector-slot">
            <TaskInspector
              focusItem={inspectorItem}
              usage={activeSessionId !== null ? (conversation.state.usageBySession[activeSessionId] ?? EMPTY_USAGE) : EMPTY_USAGE}
              childSessions={activeChildSessions}
              onClose={() => { setInspectorOpen(false); setInspectorItem(null) }}
              onSelectChild={(sessionId) => {
                const child = activeChildSessions.find((entry) => entry.sessionId === sessionId)
                if (child !== undefined) {
                  setInspectorItem({
                    kind: 'child_agent',
                    id: `${activeSessionId ?? 'task'}:child:${child.sessionId}`,
                    sessionId: child.sessionId,
                    agentId: child.agentId,
                    title: `@${child.agentId}`,
                    state: child.state
                  })
                }
              }}
            />
          </div>
        )}
      </div>

      <details className="diagnostics">
        <summary>Diagnostics</summary>
        <div className="diagnostics-content">
          <span>appserver: {status}</span>
          <span data-testid="diagnostics-appserver-pid">PID: {info?.appserverPid ?? 'not running'}</span>
          <span data-testid="diagnostics-pending-rpc">pending RPC: {conversation.protocolClient?.pendingRequestCount ?? 0}</span>
          <button type="button" className="appserver-start" onClick={() => platform.start()} disabled={status === 'running' || status === 'starting'}>Start</button>
          <button type="button" className="appserver-stop" onClick={() => platform.stop()} disabled={status === 'stopped' || status === 'crashed'}>Stop</button>
        </div>
      </details>

      {pendingApproval !== null && (
        <ApprovalModal
          item={pendingApproval}
          onApprove={() => conversation.resolveApproval(pendingApproval.requestId, 'approved')}
          onReject={() => conversation.resolveApproval(pendingApproval.requestId, 'rejected')}
          onAlwaysAllow={(scope, hours) => conversation.saveAlwaysAllowRule(pendingApproval.requestId, scope, hours)}
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
          onModelSelected={(modelId) => {
            const selected = models.snapshot?.models.find((model) => model.id === modelId)
            if (activeSessionId !== null) {
              void conversation.setSessionModel(activeSessionId, modelId, selected?.provider_id ?? null)
            }
            setSettingsOpen(false)
          }}
          models={models}
          permissionMode={permissionMode}
          onPermissionModeChange={requestPermissionModeChange}
          theme={theme}
          onThemeChange={setTheme}
          language={language}
          onLanguageChange={setLanguage}
        />
      )}
      {pendingFullAuto && (
        <div className="confirm-overlay" role="presentation">
          <div className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="full-auto-title">
            <h2 id="full-auto-title">Enable Full access?</h2>
            <p>This task may run write and command tools without asking each time. You can switch back from the composer.</p>
            <div className="confirm-actions">
              <button type="button" onClick={() => setPendingFullAuto(false)}>Cancel</button>
              <button type="button" className="danger-action" onClick={() => {
                setPreferences((current) => ({ ...current, permissionMode: 'full_auto' }))
                setPendingFullAuto(false)
              }}>Enable Full access</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
