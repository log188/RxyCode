/**
 * Linux packaged-app launch switches.
 *
 * AppImages cannot chmod the bundled chrome-sandbox to SUID, so Chromium
 * aborts before a window appears. `--no-sandbox` is the same workaround
 * other unsigned Electron AppImages use. Dev `npm run dev` stays sandboxed.
 */
export function shouldDisableLinuxSandbox(
  platform: NodeJS.Platform,
  packaged: boolean
): boolean {
  return platform === 'linux' && packaged
}
