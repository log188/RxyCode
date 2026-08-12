/* Auto-generated. Edit protocol/schema.json then run: bun run generate */

export type RxyCodeProtocol = ClientRequest | ProtocolNotification | ServerRequestMessage;
export type ClientRequest =
  | InitializeRequest
  | NewSessionRequest
  | PromptRequest
  | InterruptRequest
  | SetThinkingExpandedRequest
  | WarmSessionRequest
  | SessionSetModelRequest
  | SessionsListRequest
  | SessionEventsRequest
  | SessionRenameRequest
  | SessionTrashRequest
  | SessionRestoreRequest
  | SessionPurgeRequest
  | SubagentCapabilityRequest
  | SubagentsListRequest
  | AgentInvokeRequest
  | TaskStartRequest
  | ChildSessionsListRequest
  | ChildSessionEventsRequest
  | ChildSessionCancelRequest
  | ChildSessionRetryRequest
  | ShutdownRequest
  | ModelsListRequest
  | ModelsPresetsRequest
  | ModelsDiscoverRequest
  | ModelsOnboardRequest
  | ModelsOnboardBatchRequest
  | ModelsRemoveRequest
  | ModelsSetActiveRequest
  | ModelsTestConnectionRequest
  | CredentialsUpsertRequest
  | CredentialsDeleteRequest;
export type Method = "initialize";
export type ClientName = string;
export type ClientVersion = string;
export type ProtocolVersion = string;
export type Capabilities = {
  [k: string]: unknown;
} | null;
export type Method1 = "session/new";
export type WorkspaceRoot = string;
export type Model = string | null;
export type Method2 = "session/prompt";
export type SessionId = string;
export type Text = string;
/**
 * Optional wall-clock limit for this prompt (maps execution.tool_timeout_seconds semantics).
 */
export type TimeoutSeconds = number | null;
/**
 * Agent run mode (build/plan/compose); defaults to build.
 */
export type Mode = string | null;
/**
 * When true, ProtocolTui emits event/reasoning_snapshot chunks.
 */
export type ThinkingExpanded = boolean | null;
export type Method3 = "session/interrupt";
export type SessionId1 = string;
export type Method4 = "session/set_thinking_expanded";
export type SessionId2 = string;
export type Expanded = boolean;
export type Method5 = "session/warm";
export type SessionId3 = string;
/**
 * Optional wall-clock limit for bootstrap (defaults to appserver warm timeout).
 */
export type TimeoutSeconds1 = number | null;
export type Method6 = "session/set_model";
export type SessionId4 = string;
export type ModelId = string;
export type Method7 = "sessions/list";
export type IncludeTrashed = boolean;
export type Method8 = "session/events";
export type SessionId5 = string;
export type Cursor = number;
export type Method9 = "session/rename";
export type SessionId6 = string;
export type Title = string;
export type Method10 = "session/trash";
export type SessionId7 = string;
export type Method11 = "session/restore";
export type SessionId8 = string;
export type Method12 = "session/purge";
export type SessionId9 = string;
export type Method13 = "subagents/capability";
export type RootSessionId = string | null;
export type Method14 = "subagents/list";
export type RootSessionId1 = string;
export type Method15 = "agent/invoke";
export type RootSessionId2 = string;
export type ParentSessionId = string | null;
export type RequestId = string | null;
export type AgentId = string;
export type Prompt = string;
export type OutputSchema = string | null;
export type RequestedBudget = {
  [k: string]: unknown;
} | null;
export type RequestedWorkspace = {
  [k: string]: unknown;
} | null;
export type Method16 = "task/start";
export type RootSessionId3 = string;
export type ParentSessionId1 = string | null;
export type RequestId1 = string | null;
export type AgentId1 = string;
export type Prompt1 = string;
export type OutputSchema1 = string | null;
export type RequestedBudget1 = {
  [k: string]: unknown;
} | null;
export type RequestedWorkspace1 = {
  [k: string]: unknown;
} | null;
export type Method17 = "child_sessions/list";
export type RootSessionId4 = string;
export type Method18 = "child_sessions/events";
export type RootSessionId5 = string;
export type Cursor1 = number;
export type Method19 = "child_sessions/cancel";
export type RootSessionId6 = string;
export type SessionId10 = string | null;
export type Method20 = "child_sessions/retry";
export type RootSessionId7 = string;
export type SessionId11 = string;
export type RequestId2 = string | null;
export type Method21 = "shutdown";
export type Reason = string | null;
export type Method22 = "models/list";
export type Method23 = "models/presets";
export type Method24 = "models/discover";
export type ApiKey = string;
export type BaseUrl = string;
export type Method25 = "models/onboard";
export type ProviderModelId = string;
export type ApiKey1 = string;
export type BaseUrl1 = string;
export type Nickname = string | null;
export type Method26 = "models/onboard_batch";
export type ApiKey2 = string;
export type BaseUrl2 = string;
export type ModelIds = string[];
export type ProviderId = string | null;
export type ProviderName = string | null;
export type ActiveModelId = string | null;
export type SkipProbe = boolean;
export type Method27 = "models/remove";
export type Id = string;
export type Method28 = "models/set_active";
export type Id1 = string;
export type Method29 = "models/test_connection";
export type Id2 = string;
export type Method30 = "credentials/upsert";
export type Id3 = string;
export type ApiKey3 = string;
export type Method31 = "credentials/delete";
export type Id4 = string;
export type ProtocolNotification =
  | MessageDelta
  | ProgressUpdate
  | ReasoningSnapshot
  | PlanUpdate
  | StepProgress
  | TaskStarted
  | ToolBegin
  | ToolEnd
  | TaskComplete
  | TokenUsage
  | FinalAnswer
  | RecoveryStarted
  | RecoveryAnalyzing
  | RecoveryAttempt
  | RecoveryResolved
  | RecoveryExhausted
  | ErrorNotification
  | RunComplete
  | JobStatusUpdate
  | ServerHeartbeat;
export type Method32 = "event/message_delta";
export type SessionId12 = string;
export type Text1 = string;
export type Method33 = "event/progress";
export type SessionId13 = string;
export type Text2 = string;
export type Method34 = "event/reasoning_snapshot";
export type SessionId14 = string;
export type Text3 = string;
export type Snapshot = boolean;
export type Method35 = "event/plan";
export type SessionId15 = string;
export type Steps = string[];
export type Method36 = "event/step";
export type SessionId16 = string;
export type Index = number;
export type Total = number;
export type Text4 = string;
export type Method37 = "event/task_started";
export type SessionId17 = string;
export type TaskId = string;
export type Title1 = string;
export type Method38 = "event/tool_begin";
export type SessionId18 = string;
export type CallId = string;
export type ToolName = string;
export type Method39 = "event/tool_end";
export type SessionId19 = string;
export type CallId1 = string;
export type Ok = boolean;
export type Summary = string;
export type Status = string | null;
export type Method40 = "event/task_complete";
export type SessionId20 = string;
export type TaskId1 = string;
export type Ok1 = boolean;
export type Method41 = "event/token_usage";
export type SessionId21 = string;
export type InputTokens = number | null;
export type OutputTokens = number | null;
export type CacheHitTokens = number | null;
export type CacheWriteTokens = number | null;
export type CacheHitRate = number | null;
export type ReportingStatus = "reported" | "partial" | "not_reported";
export type Method42 = "event/final";
export type SessionId22 = string;
export type RunId = string;
export type Text5 = string;
export type Thinking = string | null;
export type InputTokens1 = number | null;
export type OutputTokens1 = number | null;
export type CacheHitTokens1 = number | null;
export type CacheWriteTokens1 = number | null;
export type CacheHitRate1 = number | null;
export type ReportingStatus1 = "reported" | "partial" | "not_reported";
export type SessionSchemaVersion = number | null;
export type SessionId23 = string;
export type RunId1 = string;
export type RecoveryId = string;
export type EventId = string;
export type Seq = number;
export type Timestamp = string;
export type Method43 = "event/recovery_started";
export type SourceCallId = string;
export type RecoveryKind = "transport_retry" | "model_recovery" | "graph_replan";
export type ErrorKind = string;
export type MaxAttempts = number;
export type SessionId24 = string;
export type RunId2 = string;
export type RecoveryId1 = string;
export type EventId1 = string;
export type Seq1 = number;
export type Timestamp1 = string;
export type Method44 = "event/recovery_analyzing";
export type SessionId25 = string;
export type RunId3 = string;
export type RecoveryId2 = string;
export type EventId2 = string;
export type Seq2 = number;
export type Timestamp2 = string;
export type Method45 = "event/recovery_attempt";
export type Attempt = number;
export type Strategy = "same_tool" | "corrected_arguments" | "alternative_tool" | "retry_task" | "replan";
export type ReplacementCallId = string | null;
export type DisplaySummary = string;
export type SessionId26 = string;
export type RunId4 = string;
export type RecoveryId3 = string;
export type EventId3 = string;
export type Seq3 = number;
export type Timestamp3 = string;
export type Method46 = "event/recovery_resolved";
export type Attempts = number;
export type DisplaySummary1 = string;
export type SessionId27 = string;
export type RunId5 = string;
export type RecoveryId4 = string;
export type EventId4 = string;
export type Seq4 = number;
export type Timestamp4 = string;
export type Method47 = "event/recovery_exhausted";
export type Attempts1 = number;
export type FinalError = string;
export type Method48 = "event/error";
export type SessionId28 = string;
export type Message = string;
export type RunId6 = string | null;
export type Status1 = ("succeeded" | "failed" | "cancelled" | "timed_out") | null;
export type Method49 = "event/done";
export type SessionId29 = string;
export type RunId7 = string;
export type Status2 = "succeeded" | "failed" | "cancelled" | "timed_out";
export type Method50 = "event/job_status";
export type SessionId30 = string;
export type JobId = string;
export type State =
  "submitted" | "queued" | "running" | "approval" | "succeeded" | "failed" | "cancelled" | "timed_out";
export type Method51 = "event/server_heartbeat";
export type UptimeSeconds = number;
export type ActiveJobs = number;
export type Degraded = boolean;
export type ServerRequestMessage = ApprovalRequest | ApprovalResponse | QuestionRequest | QuestionResponse;
export type Method52 = "approval/request";
export type SessionId31 = string;
export type RequestId3 = string;
export type RiskLevel = "READ" | "WRITE" | "DANGER";
export type Action = string;
export type RequestId4 = string;
export type Decision = "approved" | "rejected" | "allow_once" | "always_allow_level";
export type Method53 = "question/request";
export type SessionId32 = string;
export type QuestionId = string;
export type Question = string;
export type Header = string;
export type Label = string;
export type Value = string;
export type Options = QuestionOption[];
export type InputType = "choice" | "text";
export type QuestionId1 = string;
export type Answer = string | null;
export type Cancelled = boolean;
export type TimedOut = boolean;
export type Unavailable = boolean;

/**
 * JSON-RPC handshake on connect (future ``python -m appserver``).
 *
 * ``client_name`` / ``client_version`` identify the OpenTUI or Desktop client;
 * ``protocol_version`` must equal ``protocol.version.PROTOCOL_VERSION``;
 * ``capabilities`` is an optional client feature manifest (unused in HTTP mode).
 */
export interface InitializeRequest {
  method?: Method;
  client_name: ClientName;
  client_version: ClientVersion;
  protocol_version: ProtocolVersion;
  capabilities?: Capabilities;
  [k: string]: unknown;
}
/**
 * Bind a workspace and chat namespace (maps ``_activate_session`` in api_server.py).
 *
 * ``workspace_root`` is the repo root passed to AgentV2 tools (today ``Path.cwd()``);
 * ``model`` optionally overrides the default from ``config/settings.py``.
 */
export interface NewSessionRequest {
  method?: Method1;
  workspace_root: WorkspaceRoot;
  model?: Model;
  [k: string]: unknown;
}
/**
 * One user turn (maps ``POST /chat`` ``ChatRequest`` in api_server.py).
 *
 * ``session_id`` uses ``memory.long_term.validate_session_id``; ``text`` is
 * ``ChatRequest.message``; ``timeout_seconds`` mirrors execution tool timeout
 * semantics when appserver enforces wall-clock limits.
 * ``mode`` selects AgentV2 run mode; ``thinking_expanded`` gates reasoning
 * stream emission on ``ProtocolTui``.
 */
export interface PromptRequest {
  method?: Method2;
  session_id: SessionId;
  text: Text;
  timeout_seconds?: TimeoutSeconds;
  mode?: Mode;
  thinking_expanded?: ThinkingExpanded;
  [k: string]: unknown;
}
/**
 * Cancel the in-flight run (maps ``POST /cancel`` + ``Session.interrupt`` in api_server.py).
 *
 * ``session_id`` matches the active ``ChatRequest.session_id`` namespace.
 */
export interface InterruptRequest {
  method?: Method3;
  session_id: SessionId1;
  [k: string]: unknown;
}
/**
 * Sync OpenTUI /thinking expand state into appserver ProtocolTui.
 *
 * ``expanded`` mirrors the client Thought panel; when a prompt is in flight the
 * bound worker TUI is updated so mid-run expand can push an accumulated snapshot.
 */
export interface SetThinkingExpandedRequest {
  method?: Method4;
  session_id: SessionId2;
  expanded: Expanded;
  [k: string]: unknown;
}
/**
 * Pre-bootstrap AgentV2 for a session so the first prompt is not cold-start.
 *
 * Maps appserver ``AgentHost.ensure_bootstrapped`` without running a user turn.
 */
export interface WarmSessionRequest {
  method?: Method5;
  session_id: SessionId3;
  timeout_seconds?: TimeoutSeconds1;
  [k: string]: unknown;
}
/**
 * Select a model for one task without changing the global CLI default.
 *
 * Maps ``session/set_model``. The worker rejects this request while its
 * prompt is active; the selected model is persisted on the task summary.
 */
export interface SessionSetModelRequest {
  method?: Method6;
  session_id: SessionId4;
  model_id: ModelId;
  [k: string]: unknown;
}
/**
 * List persisted Desktop tasks without exposing workspace contents.
 */
export interface SessionsListRequest {
  method?: Method7;
  include_trashed?: IncludeTrashed;
  [k: string]: unknown;
}
/**
 * Replay persisted task events after a cursor.
 */
export interface SessionEventsRequest {
  method?: Method8;
  session_id: SessionId5;
  cursor?: Cursor;
  [k: string]: unknown;
}
/**
 * Rename a Desktop task; workspace files are never touched.
 */
export interface SessionRenameRequest {
  method?: Method9;
  session_id: SessionId6;
  title: Title;
  [k: string]: unknown;
}
/**
 * Soft-delete a Desktop task into Recently Deleted.
 */
export interface SessionTrashRequest {
  method?: Method10;
  session_id: SessionId7;
  [k: string]: unknown;
}
/**
 * Restore a soft-deleted Desktop task.
 */
export interface SessionRestoreRequest {
  method?: Method11;
  session_id: SessionId8;
  [k: string]: unknown;
}
/**
 * Permanently delete only a previously trashed task.
 */
export interface SessionPurgeRequest {
  method?: Method12;
  session_id: SessionId9;
  [k: string]: unknown;
}
/**
 * Discover worker-owned isolated-subagent feature flags.
 */
export interface SubagentCapabilityRequest {
  method?: Method13;
  root_session_id?: RootSessionId;
  [k: string]: unknown;
}
/**
 * List visible AgentDefinitions for mention/autocomplete UI.
 */
export interface SubagentsListRequest {
  method?: Method14;
  root_session_id: RootSessionId1;
  [k: string]: unknown;
}
/**
 * Explicit user ``@agent`` invocation in a Primary/Child tree.
 */
export interface AgentInvokeRequest {
  method?: Method15;
  root_session_id: RootSessionId2;
  parent_session_id?: ParentSessionId;
  request_id?: RequestId;
  agent_id: AgentId;
  prompt: Prompt;
  output_schema?: OutputSchema;
  requested_budget?: RequestedBudget;
  requested_workspace?: RequestedWorkspace;
  [k: string]: unknown;
}
/**
 * Start a model-driven isolated child task asynchronously.
 */
export interface TaskStartRequest {
  method?: Method16;
  root_session_id: RootSessionId3;
  parent_session_id?: ParentSessionId1;
  request_id?: RequestId1;
  agent_id: AgentId1;
  prompt: Prompt1;
  output_schema?: OutputSchema1;
  requested_budget?: RequestedBudget1;
  requested_workspace?: RequestedWorkspace1;
  [k: string]: unknown;
}
/**
 * Return the current persisted child-session tree for a Primary.
 */
export interface ChildSessionsListRequest {
  method?: Method17;
  root_session_id: RootSessionId4;
  [k: string]: unknown;
}
/**
 * Replay child events after a monotonic cursor for reconnect recovery.
 */
export interface ChildSessionEventsRequest {
  method?: Method18;
  root_session_id: RootSessionId5;
  cursor?: Cursor1;
  [k: string]: unknown;
}
/**
 * Cancel one child subtree, or all children when session_id is omitted.
 */
export interface ChildSessionCancelRequest {
  method?: Method19;
  root_session_id: RootSessionId6;
  session_id?: SessionId10;
  [k: string]: unknown;
}
/**
 * Retry a terminal child with its immutable original request snapshot.
 */
export interface ChildSessionRetryRequest {
  method?: Method20;
  root_session_id: RootSessionId7;
  session_id: SessionId11;
  request_id?: RequestId2;
  [k: string]: unknown;
}
/**
 * Graceful appserver shutdown (future ``appserver`` lifespan teardown).
 *
 * ``reason`` is logged on stderr only; HTTP ``api_server`` mode ignores this today.
 */
export interface ShutdownRequest {
  method?: Method21;
  reason?: Reason;
  [k: string]: unknown;
}
/**
 * List configured models with provider grouping and Phase 3 limit summary.
 *
 * Maps ``models/list``. Response carries ``models``, ``active``, ``recent``.
 */
export interface ModelsListRequest {
  method?: Method22;
  [k: string]: unknown;
}
/**
 * List provider connection presets (base URL only, no model ids).
 *
 * Maps ``models/presets``; the client discovers ids via ``models/discover``.
 */
export interface ModelsPresetsRequest {
  method?: Method23;
  [k: string]: unknown;
}
/**
 * Probe a provider catalogue with a credential; never persists.
 *
 * Maps ``models/discover``. ``api_key`` is never stored or echoed.
 */
export interface ModelsDiscoverRequest {
  method?: Method24;
  api_key: ApiKey;
  base_url: BaseUrl;
  [k: string]: unknown;
}
/**
 * Probe credentials in memory and persist a working model mapping.
 *
 * Maps ``models/onboard``. ``api_key`` is stored by the backend
 * credential_store (Windows DPAPI) and never returned.
 */
export interface ModelsOnboardRequest {
  method?: Method25;
  provider_model_id: ProviderModelId;
  api_key: ApiKey1;
  base_url: BaseUrl1;
  nickname?: Nickname;
  [k: string]: unknown;
}
/**
 * Probe + persist multiple models with one credential.
 *
 * Maps ``models/onboard_batch``.
 */
export interface ModelsOnboardBatchRequest {
  method?: Method26;
  api_key: ApiKey2;
  base_url: BaseUrl2;
  model_ids: ModelIds;
  provider_id?: ProviderId;
  provider_name?: ProviderName;
  active_model_id?: ActiveModelId;
  skip_probe?: SkipProbe;
  [k: string]: unknown;
}
/**
 * Remove a model by config key.
 *
 * Maps ``models/remove``.
 */
export interface ModelsRemoveRequest {
  method?: Method27;
  id: Id;
  [k: string]: unknown;
}
/**
 * Switch the active model.
 *
 * Maps ``models/set_active``.
 */
export interface ModelsSetActiveRequest {
  method?: Method28;
  id: Id1;
  [k: string]: unknown;
}
/**
 * Live credential test for an existing model.
 *
 * Maps ``models/test_connection``.
 */
export interface ModelsTestConnectionRequest {
  method?: Method29;
  id: Id2;
  [k: string]: unknown;
}
/**
 * Store/refresh a model API key (backend DPAPI, never echoed).
 *
 * Maps ``credentials/upsert``.
 */
export interface CredentialsUpsertRequest {
  method?: Method30;
  id: Id3;
  api_key: ApiKey3;
  [k: string]: unknown;
}
/**
 * Clear a model's stored API key reference.
 *
 * Maps ``credentials/delete``.
 */
export interface CredentialsDeleteRequest {
  method?: Method31;
  id: Id4;
  [k: string]: unknown;
}
/**
 * SSE ``type: token`` via ``StreamTUI._buffer("token")`` / flush (api_server.py).
 */
export interface MessageDelta {
  method?: Method32;
  session_id: SessionId12;
  text: Text1;
  [k: string]: unknown;
}
/**
 * SSE ``type: progress`` from ``StreamTUI.write_progress`` (api_server.py).
 */
export interface ProgressUpdate {
  method?: Method33;
  session_id: SessionId13;
  text: Text2;
  [k: string]: unknown;
}
/**
 * SSE ``type: reasoning`` with ``snapshot: true`` from ``StreamTUI._emit_thinking_snapshot`` (api_server.py).
 */
export interface ReasoningSnapshot {
  method?: Method34;
  session_id: SessionId14;
  text: Text3;
  snapshot?: Snapshot;
  [k: string]: unknown;
}
/**
 * SSE ``type: plan`` from ``StreamTUI.write_plan`` (api_server.py).
 */
export interface PlanUpdate {
  method?: Method35;
  session_id: SessionId15;
  steps: Steps;
  [k: string]: unknown;
}
/**
 * SSE ``type: step`` from ``StreamTUI.write_step`` (api_server.py).
 */
export interface StepProgress {
  method?: Method36;
  session_id: SessionId16;
  index: Index;
  total: Total;
  text: Text4;
  [k: string]: unknown;
}
/**
 * Structured task boundary for LangGraph runs (future emit from chat worker).
 */
export interface TaskStarted {
  method?: Method37;
  session_id: SessionId17;
  task_id: TaskId;
  title: Title1;
  [k: string]: unknown;
}
/**
 * SSE ``type: tool_call`` from ``StreamTUI.write_tool_call`` (api_server.py).
 */
export interface ToolBegin {
  method?: Method38;
  session_id: SessionId18;
  call_id: CallId;
  tool_name: ToolName;
  arguments?: Arguments;
  [k: string]: unknown;
}
export interface Arguments {
  [k: string]: unknown;
}
/**
 * SSE ``type: tool_result`` from ``StreamTUI.write_tool_result`` (api_server.py).
 */
export interface ToolEnd {
  method?: Method39;
  session_id: SessionId19;
  call_id: CallId1;
  ok: Ok;
  summary: Summary;
  status?: Status;
  [k: string]: unknown;
}
/**
 * Structured task completion paired with ``TaskStarted``.
 */
export interface TaskComplete {
  method?: Method40;
  session_id: SessionId20;
  task_id: TaskId1;
  ok: Ok1;
  [k: string]: unknown;
}
/**
 * Reported token usage; unknown provider values stay explicitly null.
 */
export interface TokenUsage {
  method?: Method41;
  session_id: SessionId21;
  input_tokens?: InputTokens;
  output_tokens?: OutputTokens;
  cache_hit_tokens?: CacheHitTokens;
  cache_write_tokens?: CacheWriteTokens;
  cache_hit_rate?: CacheHitRate;
  reporting_status?: ReportingStatus;
  [k: string]: unknown;
}
/**
 * SSE ``type: final`` payload in ``/chat/stream`` worker (api_server.py).
 */
export interface FinalAnswer {
  method?: Method42;
  session_id: SessionId22;
  run_id: RunId;
  text: Text5;
  thinking?: Thinking;
  input_tokens?: InputTokens1;
  output_tokens?: OutputTokens1;
  cache_hit_tokens?: CacheHitTokens1;
  cache_write_tokens?: CacheWriteTokens1;
  cache_hit_rate?: CacheHitRate1;
  reporting_status?: ReportingStatus1;
  session_schema_version?: SessionSchemaVersion;
  [k: string]: unknown;
}
/**
 * Recovery budget opened after an operational failure.
 */
export interface RecoveryStarted {
  session_id: SessionId23;
  run_id: RunId1;
  recovery_id: RecoveryId;
  event_id: EventId;
  seq: Seq;
  timestamp: Timestamp;
  method?: Method43;
  source_call_id: SourceCallId;
  recovery_kind: RecoveryKind;
  error_kind: ErrorKind;
  max_attempts: MaxAttempts;
  [k: string]: unknown;
}
/**
 * Recovery planner is selecting the next user-safe strategy.
 */
export interface RecoveryAnalyzing {
  session_id: SessionId24;
  run_id: RunId2;
  recovery_id: RecoveryId1;
  event_id: EventId1;
  seq: Seq1;
  timestamp: Timestamp1;
  method?: Method44;
  [k: string]: unknown;
}
/**
 * One concrete recovery strategy has been scheduled.
 */
export interface RecoveryAttempt {
  session_id: SessionId25;
  run_id: RunId3;
  recovery_id: RecoveryId2;
  event_id: EventId2;
  seq: Seq2;
  timestamp: Timestamp2;
  method?: Method45;
  attempt: Attempt;
  strategy: Strategy;
  replacement_call_id?: ReplacementCallId;
  display_summary: DisplaySummary;
  [k: string]: unknown;
}
/**
 * Recovery completed and the task returned to normal execution.
 */
export interface RecoveryResolved {
  session_id: SessionId26;
  run_id: RunId4;
  recovery_id: RecoveryId3;
  event_id: EventId3;
  seq: Seq3;
  timestamp: Timestamp3;
  method?: Method46;
  attempts: Attempts;
  display_summary: DisplaySummary1;
  [k: string]: unknown;
}
/**
 * Recovery budget was exhausted and a terminal error may be shown.
 */
export interface RecoveryExhausted {
  session_id: SessionId27;
  run_id: RunId5;
  recovery_id: RecoveryId4;
  event_id: EventId4;
  seq: Seq4;
  timestamp: Timestamp4;
  method?: Method47;
  attempts: Attempts1;
  final_error: FinalError;
  [k: string]: unknown;
}
/**
 * SSE ``type: error`` from ``StreamTUI.write_error`` and chat worker (api_server.py).
 */
export interface ErrorNotification {
  method?: Method48;
  session_id: SessionId28;
  message: Message;
  run_id?: RunId6;
  status?: Status1;
  [k: string]: unknown;
}
/**
 * SSE ``type: done`` from chat stream teardown (api_server.py).
 */
export interface RunComplete {
  method?: Method49;
  session_id: SessionId29;
  run_id: RunId7;
  status: Status2;
  [k: string]: unknown;
}
/**
 * Background job state for watchdog / appserver (submitted|running|failed).
 */
export interface JobStatusUpdate {
  method?: Method50;
  session_id: SessionId30;
  job_id: JobId;
  state: State;
  [k: string]: unknown;
}
/**
 * Periodic appserver liveness signal (T4 watchdog).
 */
export interface ServerHeartbeat {
  method?: Method51;
  uptime_seconds: UptimeSeconds;
  active_jobs: ActiveJobs;
  degraded: Degraded;
  [k: string]: unknown;
}
/**
 * Maps ``ApprovalRequest.to_event()`` SSE in core/safety/approval.py.
 */
export interface ApprovalRequest {
  method?: Method52;
  session_id: SessionId31;
  request_id: RequestId3;
  risk_level: RiskLevel;
  action: Action;
  details?: Details;
  [k: string]: unknown;
}
export interface Details {
  [k: string]: unknown;
}
/**
 * Reply consumed by ``POST /approve`` (api_server.py) / ``SseApproval``.
 */
export interface ApprovalResponse {
  request_id: RequestId4;
  decision: Decision;
  [k: string]: unknown;
}
/**
 * Maps ``QuestionRequest.to_event()`` in core/question.py.
 */
export interface QuestionRequest {
  method?: Method53;
  session_id: SessionId32;
  question_id: QuestionId;
  question: Question;
  header?: Header;
  options?: Options;
  input_type?: InputType;
  [k: string]: unknown;
}
/**
 * One choice row in ``QuestionRequest.options`` (``core/question.py`` ``QuestionOption.to_event``).
 */
export interface QuestionOption {
  label: Label;
  value: Value;
  [k: string]: unknown;
}
/**
 * Answer payload resolved by ``SseQuestionBroker.resolve`` (core/question.py).
 */
export interface QuestionResponse {
  question_id: QuestionId1;
  answer?: Answer;
  cancelled?: Cancelled;
  timed_out?: TimedOut;
  unavailable?: Unavailable;
  [k: string]: unknown;
}
