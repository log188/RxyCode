import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

function lockRootName(lockPath: string): { name: string; packagesName: string } {
  const lock = JSON.parse(readFileSync(lockPath, 'utf8')) as {
    name: string
    packages: { '': { name: string } }
  }
  return { name: lock.name, packagesName: lock.packages[''].name }
}

test('root package-lock.json name matches package.json', () => {
  const pkg = JSON.parse(readFileSync(join(appRoot, 'package.json'), 'utf8')) as { name: string }
  const lock = lockRootName(join(appRoot, 'package-lock.json'))
  assert.equal(lock.name, pkg.name)
  assert.equal(lock.packagesName, pkg.name)
})

test('shared protocol-client package-lock.json name matches its package.json', () => {
  const rootProtocolClient = join(appRoot, '..', 'protocol-client')
  const pkg = JSON.parse(
    readFileSync(join(rootProtocolClient, 'package.json'), 'utf8')
  ) as { name: string }
  const lock = lockRootName(join(rootProtocolClient, 'package-lock.json'))
  assert.equal(lock.name, pkg.name)
  assert.equal(lock.packagesName, pkg.name)
})
