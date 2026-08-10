#!/usr/bin/env node
/**
 * Update feed smoke (Phase4-D7).
 *
 * Runs the packaged (win-unpacked) app in update-smoke mode against a local
 * generic feed served by this script and asserts the real electron-updater
 * flow: check -> update-available -> download -> update-downloaded. The app
 * never installs or restarts; a failed check/download must leave the app
 * running (the old version stays untouched).
 *
 * Prerequisite: `npm run build:unpack` (win-unpacked + setup artifact).
 */
import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import { createReadStream, existsSync, mkdtempSync, readFileSync, statSync } from 'node:fs'
import { createServer } from 'node:http'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const EXE = join(ROOT, 'dist', 'win-unpacked', 'rxycode-desktop.exe')
const SETUP = join(ROOT, 'dist', 'rxycode-desktop-0.1.0-setup.exe')
const FEED_VERSION = '0.1.1'
const FEED_FILE = 'rxycode-desktop-0.1.1-setup.exe'

function fail(message: string): never {
  console.error(`UPDATE_SMOKE_FAIL ${message}`)
  process.exit(1)
}

async function main(): Promise<number> {
  if (!existsSync(EXE)) {
    console.error(`UPDATE_SMOKE_ABORT missing ${EXE}; run "npm run build:unpack" first`)
    return 1
  }
  const payload = existsSync(SETUP) ? SETUP : EXE
  const size = statSync(payload).size
  const sha512 = createHash('sha512').update(readFileSync(payload)).digest('base64')
  const latestYml = [
    'version: ' + FEED_VERSION,
    'files:',
    '  - url: ' + FEED_FILE,
    '    sha512: ' + sha512,
    '    size: ' + size,
    'path: ' + FEED_FILE,
    'sha512: ' + sha512,
    "releaseDate: '2026-08-08T00:00:00.000Z'",
    ''
  ].join('\n')

  const server = createServer((request, response) => {
    const url = (request.url ?? '/').split('?')[0]
    if (url === '/latest.yml') {
      response.writeHead(200, { 'content-type': 'text/yaml' })
      response.end(latestYml)
      return
    }
    if (url === '/' + FEED_FILE) {
      response.writeHead(200, { 'content-type': 'application/octet-stream' })
      createReadStream(payload).pipe(response)
      return
    }
    response.writeHead(404)
    response.end('not found')
  })

  await new Promise<void>((resolveListen) => server.listen(0, '127.0.0.1', resolveListen))
  const address = server.address()
  if (address === null || typeof address === 'string') {
    server.close()
    fail('failed to bind the local update feed')
  }
  const feedUrl = `http://127.0.0.1:${address.port}`

  const userData = mkdtempSync(join(tmpdir(), 'rxycode-update-smoke-'))
  const output: string[] = []
  const app = spawn(EXE, [], {
    cwd: userData,
    env: {
      ...process.env,
      RXYCODE_DESKTOP_UPDATE_SMOKE: '1',
      RXYCODE_UPDATE_FEED_URL: feedUrl,
      RXYCODE_DESKTOP_USER_DATA: userData,
      // electron-updater derives its download cache from LOCALAPPDATA on
      // Windows (not Electron's cache path), so redirect it into the temp
      // profile to keep the smoke run fully isolated.
      LOCALAPPDATA: userData,
      RXYCODE_APPSERVER_STUB: '1'
    },
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe']
  })
  app.stdout.setEncoding('utf8')
  app.stdout.on('data', (chunk: string) => {
    process.stdout.write(chunk)
    output.push(chunk)
  })
  app.stderr.on('data', (chunk: string) => {
    process.stderr.write(chunk)
  })

  const timeout = setTimeout(() => {
    console.error('UPDATE_SMOKE_ABORT timed out waiting for the update smoke run')
    app.kill()
  }, 180_000)

  const exitCode = await new Promise<number>((resolveExit) => {
    app.on('exit', (code) => {
      clearTimeout(timeout)
      resolveExit(code ?? -1)
    })
  })

  server.close()
  const all = output.join('')
  const failures: string[] = []
  if (exitCode !== 0) failures.push(`app exit code ${exitCode}`)
  if (all.includes('UPDATE_SMOKE_FAILED')) failures.push('UPDATE_SMOKE_FAILED marker present')
  if (all.includes('SMOKE_FAILED')) failures.push('SMOKE_FAILED marker present')
  const available = all.match(/UPDATE_STATUS (\{.*"status":"available".*\})/)
  const downloaded = all.match(/UPDATE_STATUS (\{.*"status":"downloaded".*\})/)
  if (available === null) failures.push('update-available status marker missing')
  if (downloaded === null) failures.push('update-downloaded status marker missing')
  if (!all.includes('UPDATE_SMOKE_OK')) failures.push('UPDATE_SMOKE_OK marker missing')
  if (available !== null) {
    const parsed = JSON.parse(available[1]) as { availableVersion?: unknown }
    if (parsed.availableVersion !== FEED_VERSION) {
      failures.push(
        `availableVersion ${String(parsed.availableVersion)} (expected ${FEED_VERSION})`
      )
    }
  }
  if (failures.length > 0) fail(failures.join('; '))
  console.log(
    `UPDATE_SMOKE_OK app version stays 0.1.0, feed ${FEED_VERSION} checked+downloaded (not installed)`
  )
  return 0
}

main()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error(`UPDATE_SMOKE_FAILED ${String(error)}`)
    process.exit(1)
  })
