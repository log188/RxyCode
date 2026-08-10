/**
 * Strict navigation whitelist for the Desktop shell (Phase4-D3, D1
 * leftover hardening).
 *
 * The renderer may only navigate to its own exact index.html file URL
 * (production) or the exact ELECTRON_RENDERER_URL (dev). Any other
 * file://, http(s), javascript: or data: navigation is rejected.
 */
export interface NavigationPolicy {
  appIndexUrl: string
  devUrl?: string
  isDev: boolean
}

export function isAllowedNavigation(url: string, policy: NavigationPolicy): boolean {
  if (url === policy.appIndexUrl) return true
  return policy.isDev && policy.devUrl !== undefined && url === policy.devUrl
}
