import { useState } from 'react'
import { useDiagnostics, type UpdateStatus } from '../../../platform/index.mts'

export type SettingsTab = 'model' | 'apikey' | 'workspace' | 'diagnostics'

export interface SettingsPageProps {
  appVersion: string
  repoRoot: string
  savedWorkspaceRoot: string | null
  effectiveWorkspaceRoot: string
  picking: boolean
  onClose: () => void
  onPickWorkspace: () => void
  onClearWorkspace: () => void
}

const TABS: Array<{ id: SettingsTab; label: string }> = [
  { id: 'model', label: '模型' },
  { id: 'apikey', label: 'API Key' },
  { id: 'workspace', label: '工作区' },
  { id: 'diagnostics', label: '更新与诊断' }
]

const UPDATE_STATUS_LABELS: Record<UpdateStatus, string> = {
  disabled: '不可用',
  idle: '空闲',
  checking: '检查中…',
  available: '有可用更新',
  'not-available': '已是最新',
  downloading: '下载中…',
  downloaded: '已下载，可安装',
  error: '出错'
}

function BlockedPanel({ title, detail }: { title: string; detail: string }): React.JSX.Element {
  return (
    <div className="blocked-panel">
      <span className="blocked-badge">BLOCKED_PREREQUISITE</span>
      <p className="blocked-title">{title}</p>
      <p className="blocked-detail">{detail}</p>
    </div>
  )
}

function SettingsPage(props: SettingsPageProps): React.JSX.Element {
  const [tab, setTab] = useState<SettingsTab>('model')
  const diagnostics = useDiagnostics()
  const updateStatus = diagnostics.updateStatus?.status ?? null

  return (
    <div className="settings-overlay">
      <div className="settings-page">
        <header className="settings-header">
          <div className="settings-title">设置</div>
          <button type="button" className="settings-close" onClick={props.onClose}>
            关闭
          </button>
        </header>
        <nav className="settings-tabs">
          {TABS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              className={`settings-tab${tab === entry.id ? ' active' : ''}`}
              data-tab={entry.id}
              onClick={() => setTab(entry.id)}
            >
              {entry.label}
            </button>
          ))}
        </nav>
        <div className="settings-content">
          {tab === 'model' && (
            <section className="settings-panel">
              <h2>模型</h2>
              <BlockedPanel
                title="模型管理不可用"
                detail="后端协议契约缺失：protocol/schema.json 无 model 管理方法，Desktop 只能通过 protocol-client 消费后端 config/model_manager.py（DC1）。本卡不新增协议方法、不读取后端配置文件、不伪造数据。"
              />
              <BlockedPanel
                title="Phase 3 上限来源摘要不可用"
                detail="Phase 3（M1–M8：按真实 model_id 解析输出上限并提供 limit_source 摘要协议字段）未落地；协议无 model_max_output_tokens / resolved_max_tokens / limit_source。按验收要求，此处如实呈现阻塞状态，不展示伪造的上限数据。"
              />
            </section>
          )}
          {tab === 'apikey' && (
            <section className="settings-panel">
              <h2>API Key</h2>
              <BlockedPanel
                title="API Key 管理不可用"
                detail="后端协议契约缺失：protocol/schema.json 无凭据/模型写入方法，Desktop 无法把密钥交给后端 credential_store（DC4 要求系统密钥链；后端冻结、schema 零改动）。本卡不绕过协议自行落盘密钥。"
              />
            </section>
          )}
          {tab === 'workspace' && (
            <section className="settings-panel">
              <h2>工作区</h2>
              <div className="workspace-card">
                <div className="workspace-row">
                  <span className="label">当前生效</span>
                  <span className="workspace-path">{props.effectiveWorkspaceRoot}</span>
                </div>
                <div className="workspace-row">
                  <span className="label">已保存设置</span>
                  <span className="workspace-path">
                    {props.savedWorkspaceRoot ?? '未设置（使用后端仓库根目录）'}
                  </span>
                </div>
                <div className="workspace-actions">
                  <button
                    type="button"
                    className="workspace-pick"
                    disabled={props.picking}
                    onClick={() => void props.onPickWorkspace()}
                  >
                    {props.picking ? '选择中…' : '选择目录'}
                  </button>
                  <button
                    type="button"
                    className="workspace-clear"
                    disabled={props.savedWorkspaceRoot === null || props.picking}
                    onClick={props.onClearWorkspace}
                  >
                    恢复默认
                  </button>
                </div>
                <p className="settings-hint">
                  新会话通过既有协议字段 session/new.workspace_root
                  使用所选目录；未设置时回退到后端仓库根目录。协议与 schema.json 均未改动。
                </p>
              </div>
            </section>
          )}
          {tab === 'diagnostics' && (
            <section className="settings-panel">
              <h2>更新与诊断</h2>
              <div className="workspace-card">
                <div className="workspace-row">
                  <span className="label">当前版本</span>
                  <span className="workspace-path">{props.appVersion}</span>
                </div>
                <div className="workspace-row">
                  <span className="label">更新状态</span>
                  <span className="workspace-path">
                    {updateStatus !== null ? UPDATE_STATUS_LABELS[updateStatus] : '加载中…'}
                  </span>
                </div>
                {diagnostics.updateStatus?.error !== null &&
                  diagnostics.updateStatus?.error !== undefined && (
                    <p className="settings-hint">错误：{diagnostics.updateStatus.error}</p>
                  )}
                {diagnostics.updateStatus?.progress !== null &&
                  diagnostics.updateStatus?.progress !== undefined && (
                    <p className="settings-hint">
                      下载进度：{diagnostics.updateStatus.progress.percent.toFixed(1)}%
                    </p>
                  )}
                <div className="workspace-actions">
                  <button
                    type="button"
                    className="workspace-pick"
                    disabled={
                      updateStatus === 'checking' ||
                      updateStatus === 'downloading' ||
                      diagnostics.updateStatus === null
                    }
                    onClick={() => void diagnostics.checkForUpdates()}
                  >
                    检查更新
                  </button>
                  {updateStatus === 'available' && (
                    <button
                      type="button"
                      className="workspace-pick"
                      onClick={() => void diagnostics.downloadUpdate()}
                    >
                      下载更新
                    </button>
                  )}
                  {updateStatus === 'downloaded' && (
                    <button
                      type="button"
                      className="workspace-pick"
                      onClick={() => diagnostics.installUpdate()}
                    >
                      立即重启安装
                    </button>
                  )}
                </div>
                <p className="settings-hint">
                  更新为手动触发：检查、下载、安装均由你点击执行，启动时不会强制检查；检查或下载失败不会影响当前版本运行。
                </p>
              </div>
              <div className="workspace-card">
                <div className="workspace-row">
                  <span className="label">崩溃上报</span>
                  <label className="settings-toggle">
                    <input
                      type="checkbox"
                      checked={diagnostics.consent === true}
                      disabled={diagnostics.consent === null}
                      onChange={(event) => void diagnostics.setConsent(event.target.checked)}
                    />
                    允许上传脱敏崩溃诊断（默认关闭，切换立即生效）
                  </label>
                </div>
                <p className="settings-hint">
                  诊断包只包含版本、平台、协议状态与日志摘要，不含 API Key、代码、完整 prompt
                  或工具输入输出。未开启同意时仅在本地记录。
                </p>
                <h3>最近诊断</h3>
                {diagnostics.reports.length === 0 ? (
                  <p className="settings-hint">暂无诊断记录。</p>
                ) : (
                  <ul className="crash-report-list">
                    {diagnostics.reports.map((report) => (
                      <li key={report.id}>
                        {report.capturedAt} · {report.source}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  )
}

export default SettingsPage
