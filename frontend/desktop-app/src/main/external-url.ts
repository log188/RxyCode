/**
 * External URL whitelist for the Desktop shell (Phase4-D3, D1 leftover).
 *
 * Only absolute http/https URLs may be handed to the system browser.
 * Anything else (javascript:, file:, data:, relative, malformed) is
 * rejected so a compromised renderer cannot open local files or run
 * script URLs through shell.openExternal.
 */
export function isSafeExternalUrl(raw: string): boolean {
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    return false
  }
  return (url.protocol === 'http:' || url.protocol === 'https:') && url.hostname.length > 0
}
