/** Child-session replay is optional. Timeouts must not look like a dead appserver. */
export function isNonFatalChildRecoveryError(message: string): boolean {
  const normalized = message.toLowerCase()
  return (
    normalized.includes('method not found') ||
    normalized.includes('rpc timeout') ||
    normalized.includes('timed out')
  )
}
