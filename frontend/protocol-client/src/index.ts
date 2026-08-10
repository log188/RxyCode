export {
  ProtocolClient,
  ProtocolRpcError,
  type JsonRpcErrorObject,
  type JsonRpcId,
  type NotificationHandler,
  type ServerRequestHandler,
} from "./client.ts";

export type {
  ApprovalRequest,
  ApprovalResponse,
  ClientRequest,
  ErrorNotification,
  FinalAnswer,
  InitializeRequest,
  InterruptRequest,
  JobStatusUpdate,
  MessageDelta,
  PromptRequest,
  ProtocolNotification,
  RunComplete,
  ToolBegin,
  ToolEnd,
} from "./generated/types.ts";

/* Phase B: subagent protocol types */
export type {
  AgentMode,
  WorkspaceMode,
  TriggerKind,
  ChildStatus,
  PermissionVerdict,
  PermissionSpec,
  AgentDefinition,
  ContextReference,
  ContextEnvelope,
  BudgetSpec,
  WorkspaceScope,
  TaskRequest,
  UsageRecord,
  ErrorRecord,
  ArtifactRef,
  EvidenceRef,
  TaskResult,
  ChildSessionEvent,
  AgentInvokeRequest,
  TaskStartRequest,
} from "./generated/subagent-types.ts";