/**
 * Workspace directory picker for the Phase4-D5 settings page.
 *
 * Electron dialog access lives in the main process (DC3); this helper keeps
 * the IPC handler logic dependency-light so the pick/cancel behavior can be
 * unit-tested without opening a real native dialog.
 */

export interface DirectoryDialogOptions {
  title?: string
  buttonLabel?: string
  properties: Array<'openDirectory' | 'createDirectory'>
}

export interface DirectoryDialog {
  showOpenDialog(options: DirectoryDialogOptions): Promise<{
    canceled: boolean
    filePaths: string[]
  }>
}

export async function pickWorkspaceDirectory(dialog: DirectoryDialog): Promise<string | null> {
  const result = await dialog.showOpenDialog({
    title: '选择工作目录',
    buttonLabel: '选择',
    properties: ['openDirectory', 'createDirectory']
  })
  if (result.canceled) return null
  const first = result.filePaths[0]
  return first !== undefined && first.trim() !== '' ? first : null
}
