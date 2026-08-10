import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  pickWorkspaceDirectory,
  type DirectoryDialog,
  type DirectoryDialogOptions
} from './workspace-dialog.ts'

function createFakeDialog(result: {
  canceled: boolean
  filePaths: string[]
}): DirectoryDialog & { lastOptions?: DirectoryDialogOptions } {
  const fake: DirectoryDialog & { lastOptions?: DirectoryDialogOptions } = {
    async showOpenDialog(options) {
      fake.lastOptions = options
      return result
    }
  }
  return fake
}

test('pickWorkspaceDirectory returns the selected directory path', async () => {
  const dialog = createFakeDialog({ canceled: false, filePaths: ['D:\\demo-workspace'] })
  assert.equal(await pickWorkspaceDirectory(dialog), 'D:\\demo-workspace')
})

test('pickWorkspaceDirectory returns null when the dialog is canceled', async () => {
  const dialog = createFakeDialog({ canceled: true, filePaths: [] })
  assert.equal(await pickWorkspaceDirectory(dialog), null)
})

test('pickWorkspaceDirectory returns null when no path was selected', async () => {
  const dialog = createFakeDialog({ canceled: false, filePaths: [] })
  assert.equal(await pickWorkspaceDirectory(dialog), null)
})

test('pickWorkspaceDirectory requests an open-directory dialog', async () => {
  const dialog = createFakeDialog({ canceled: false, filePaths: ['D:\\demo-workspace'] })
  await pickWorkspaceDirectory(dialog)
  assert.ok(
    dialog.lastOptions?.properties.includes('openDirectory'),
    'expected openDirectory in dialog properties'
  )
})
