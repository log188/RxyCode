#!/usr/bin/env node
/**
 * Phase4-D6 runtime validation.
 *
 * Checks a staged runtime dir (default build/runtime/<platform>-<arch>)
 * for the expected layout, manifest metadata, a working python binary and
 * a vendored appserver entry point.
 */
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { windowsVersionedDllName } from './prepare-runtime.mts'

function fail(message: string): never {
  console.error(`RUNTIME_VERIFY_FAIL ${message}`)
  process.exit(1)
}

function argValue(argv: string[], name: string): string | null {
  const index = argv.indexOf(`--${name}`)
  return index >= 0 && argv[index + 1] !== undefined ? argv[index + 1] : null
}

const argv = process.argv.slice(2)
const platform = argValue(argv, 'platform') ?? process.platform
const arch = argValue(argv, 'arch') ?? process.arch
const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const runtimeDir = resolve(
  argValue(argv, 'dir') ?? join(appDir, 'build', 'runtime', `${platform}-${arch}`)
)

if (!existsSync(join(runtimeDir, 'manifest.json'))) {
  fail(`manifest.json missing at ${runtimeDir}`)
}
const manifest = JSON.parse(readFileSync(join(runtimeDir, 'manifest.json'), 'utf8')) as {
  platform: string
  arch: string
  pythonVersion: string
  rxycodeVersion: string
  createdAt: string
}
if (manifest.platform !== platform) fail(`manifest platform ${manifest.platform} != ${platform}`)
if (manifest.arch !== arch) fail(`manifest arch ${manifest.arch} != ${arch}`)

const pythonRel = platform === 'win32' ? 'python.exe' : join('bin', 'python3')
const pythonExe = join(runtimeDir, 'python', pythonRel)
const appDirStaged = join(runtimeDir, 'app')
if (!existsSync(pythonExe)) fail(`python binary missing at ${pythonExe}`)
if (!existsSync(join(appDirStaged, 'appserver', '__main__.py'))) {
  fail(`vendored appserver entry missing at ${appDirStaged}`)
}

const version = spawnSync(pythonExe, ['-V'], { encoding: 'utf8', timeout: 30_000 })
if (version.status !== 0) fail(`python -V failed: ${version.stderr}`)
if (platform === 'win32') {
  const dllName = windowsVersionedDllName(version.stdout.trim() || manifest.pythonVersion)
  if (dllName === null || !existsSync(join(runtimeDir, 'python', dllName))) {
    fail(
      `Windows runtime missing ${dllName ?? 'python3XY.dll'} next to python.exe; ` +
        'the stub python3.dll cannot start appserver on a machine without system CPython'
    )
  }
}

const imports = spawnSync(pythonExe, ['-c', 'import appserver; print("appserver-ok")'], {
  cwd: appDirStaged,
  encoding: 'utf8',
  timeout: 60_000
})
if (imports.status !== 0) fail(`import appserver failed: ${imports.stderr}`)

const protocolVersion = (
  JSON.parse(readFileSync(join(appDirStaged, 'protocol', 'schema.json'), 'utf8')) as {
    protocol_version: string
  }
).protocol_version

console.log(
  `RUNTIME_VERIFY_OK dir=${runtimeDir} ${version.stdout.trim()} rxycodeVersion=${manifest.rxycodeVersion} protocolVersion=${protocolVersion} createdAt=${manifest.createdAt}`
)
