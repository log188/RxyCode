export {
  ProtocolClient,
  ProtocolRpcError,
  type JsonRpcErrorObject,
  type JsonRpcId,
  type NotificationHandler,
  type ServerRequestHandler
} from './client.ts'

export type {
  ApprovalResponse,
  ApprovalRequest,
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
  ToolEnd
} from './generated/types.ts'
