import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  findBundledRuntime,
  pythonExeName,
  readRuntimeManifest,
  type RuntimeManifest
} from './runtime.ts'

function fixtureDir(): string {
  return mkdtempSync(join(tmpdir(), 'rxycode-runtime-test-'))
}

const VALID_MANIFEST: RuntimeManifest = {
  platform: 'win32',
  arch: 'x64',
  pythonVersion: '3.14.2',
  rxycodeVersion: '1.2.6',
  createdAt: '2026-08-08T00:00:00.000Z'
}

function writeManifest(runtimeDir: string, manifest: RuntimeManifest): void {
  writeFileSync(join(runtimeDir, 'manifest.json'), JSON.stringify(manifest))
}

function writeFullRuntime(base: string, manifest: RuntimeManifest = VALID_MANIFEST): string {
  const runtimeDir = join(base, 'runtime', `${manifest.platform}-${manifest.arch}`)
  mkdirSync(join(runtimeDir, 'python'), { recursive: true })
  mkdirSync(join(runtimeDir, 'app', 'appserver'), { recursive: true })
  writeManifest(runtimeDir, manifest)
  writeFileSync(join(runtimeDir, 'python', 'python.exe'), 'fake')
  writeFileSync(join(runtimeDir, 'app', 'appserver', '__main__.py'), '')
  return runtimeDir
}

test('pythonExeName maps win32 to python.exe', () => {
  assert.equal(pythonExeName('win32'), 'python.exe')
})

test('pythonExeName maps darwin and linux to bin/python3', () => {
  assert.equal(pythonExeName('darwin'), 'bin/python3')
  assert.equal(pythonExeName('linux'), 'bin/python3')
})

test('readRuntimeManifest parses a valid manifest', () => {
  const base = fixtureDir()
  try {
    const runtimeDir = join(base, 'runtime', 'win32-x64')
    mkdirSync(runtimeDir, { recursive: true })
    writeManifest(runtimeDir, VALID_MANIFEST)
    assert.deepEqual(readRuntimeManifest(runtimeDir), VALID_MANIFEST)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('readRuntimeManifest returns null for a missing manifest', () => {
  const base = fixtureDir()
  try {
    mkdirSync(join(base, 'runtime', 'win32-x64'), { recursive: true })
    assert.equal(readRuntimeManifest(join(base, 'runtime', 'win32-x64')), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('readRuntimeManifest returns null for invalid JSON', () => {
  const base = fixtureDir()
  try {
    const runtimeDir = join(base, 'runtime', 'win32-x64')
    mkdirSync(runtimeDir, { recursive: true })
    writeFileSync(join(runtimeDir, 'manifest.json'), '{not json')
    assert.equal(readRuntimeManifest(runtimeDir), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('findBundledRuntime returns null when there is no runtime dir', () => {
  const base = fixtureDir()
  try {
    assert.equal(findBundledRuntime(base, 'win32', 'x64'), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('findBundledRuntime returns null when the manifest platform mismatches', () => {
  const base = fixtureDir()
  try {
    writeFullRuntime(base, { ...VALID_MANIFEST, platform: 'linux' })
    assert.equal(findBundledRuntime(base, 'win32', 'x64'), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('findBundledRuntime returns null when the manifest arch mismatches', () => {
  const base = fixtureDir()
  try {
    writeFullRuntime(base, { ...VALID_MANIFEST, arch: 'arm64' })
    assert.equal(findBundledRuntime(base, 'win32', 'x64'), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('findBundledRuntime returns null when the python binary is missing', () => {
  const base = fixtureDir()
  try {
    const runtimeDir = writeFullRuntime(base)
    rmSync(join(runtimeDir, 'python', 'python.exe'))
    assert.equal(findBundledRuntime(base, 'win32', 'x64'), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('findBundledRuntime returns null when appserver entry is missing', () => {
  const base = fixtureDir()
  try {
    const runtimeDir = writeFullRuntime(base)
    rmSync(join(runtimeDir, 'app'), { recursive: true, force: true })
    assert.equal(findBundledRuntime(base, 'win32', 'x64'), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('findBundledRuntime returns python and app dirs for a complete runtime', () => {
  const base = fixtureDir()
  try {
    writeFullRuntime(base)
    const runtime = findBundledRuntime(base, 'win32', 'x64')
    assert.notEqual(runtime, null)
    assert.equal(runtime?.manifest.platform, 'win32')
    assert.equal(runtime?.manifest.arch, 'x64')
    assert.equal(runtime?.python, join(base, 'runtime', 'win32-x64', 'python', 'python.exe'))
    assert.equal(runtime?.appDir, join(base, 'runtime', 'win32-x64', 'app'))
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})

test('findBundledRuntime defaults to the current platform and arch', () => {
  const base = fixtureDir()
  try {
    writeFullRuntime(base, {
      ...VALID_MANIFEST,
      platform: process.platform,
      arch: process.arch
    })
    assert.notEqual(findBundledRuntime(base), null)
  } finally {
    rmSync(base, { recursive: true, force: true })
  }
})
