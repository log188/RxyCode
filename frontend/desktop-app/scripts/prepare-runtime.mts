#!/usr/bin/env node
/**
 * Phase4-D6 runtime staging.
 *
 * Builds a self-contained Python runtime + vendored RxyCode 1.2.6 source
 * under build/runtime/<platform>-<arch>/, which electron-builder copies
 * into the packaged app as resources/runtime/ (extraResources).
 *
 * Self-contained means the packaged app must not depend on the dev
 * machine's ../RxyCode-master checkout or a system python: the staged
 * runtime carries its own interpreter, its own site-packages and a
 * vendored copy of the RxyCode source tree. RxyCode-master is only READ.
 */
import { spawnSync } from 'node:child_process'
import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  writeFileSync
} from 'node:fs'
import { basename, dirname, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const EXPECTED_RXYCODE_VERSION = '1.2.6'

function fail(message: string): never {
  console.error(`RUNTIME_PREPARE_FAIL ${message}`)
  process.exit(1)
}

function pythonRelExe(platform: string): string {
  return platform === 'win32' ? 'python.exe' : join('bin', 'python3')
}

function argValue(argv: string[], name: string): string | null {
  const index = argv.indexOf(`--${name}`)
  return index >= 0 && argv[index + 1] !== undefined ? argv[index + 1] : null
}

function runPython(pythonExe: string, args: string[], cwd?: string): string {
  const result = spawnSync(pythonExe, args, {
    cwd,
    encoding: 'utf8',
    timeout: 120_000
  })
  if (result.status !== 0) {
    fail(`python ${args.join(' ')} failed (status ${String(result.status)}): ${result.stderr}`)
  }
  return result.stdout.trim()
}

function keepPythonFile(pythonRoot: string, src: string): boolean {
  if (src === pythonRoot) return true
  const parts = relative(pythonRoot, src).split(sep)
  const name = basename(src)
  if (name === '__pycache__' || name.endsWith('.pyc') || name.endsWith('.pdb')) return false
  const top = parts[0]
  if (top === 'Doc' || top === 'include' || top === 'libs' || top === 'share') return false
  if (top === 'DLLs') return !/_d\.pyd$/.test(name) && !/_t\.pyd$/.test(name)
  if (top === 'Lib') {
    const second = parts[1]
    if (second === 'test' || second === 'idlelib' || second === 'turtledemo' || second === 'venv') {
      return false
    }
    if (second === 'site-packages') {
      const third = parts[2]
      if (
        third !== undefined &&
        ['scipy', 'pandas', 'matplotlib', 'coverage', 'pytest', '_pytest', 'ruff'].includes(third)
      ) {
        return false
      }
      if (name === 'rxycode-1.2.6.dist-info' || name.startsWith('__editable__')) return false
    }
    return true
  }
  if (top === 'Scripts') return /^pip(3(\.\d+)?)?\.exe$/.test(name)
  if (parts.length === 1) {
    return (
      name === 'python.exe' ||
      name === 'pythonw.exe' ||
      name === 'python3.dll' ||
      name === 'python314.dll' ||
      name.startsWith('vcruntime140') ||
      name === 'LICENSE.txt'
    )
  }
  return true
}

function keepVendoredFile(repo: string, src: string): boolean {
  if (src === repo) return true
  const parts = relative(repo, src).split(sep)
  const name = basename(src)
  if (name === '__pycache__' || name.endsWith('.pyc')) return false
  const top = parts[0]
  if (
    top === '.git' ||
    top === '.pytest_cache' ||
    top === 'docs' ||
    top === 'tests' ||
    top === 'rxycode.egg-info'
  ) {
    return false
  }
  if (top === 'log' && (name.endsWith('.out') || name === 'status.json' || name.endsWith('.log'))) {
    return false
  }
  return true
}

function dirSize(dir: string): number {
  let total = 0
  const stack = [dir]
  while (stack.length > 0) {
    const current = stack.pop() as string
    for (const name of readdirSync(current)) {
      const full = join(current, name)
      const stat = statSync(full)
      if (stat.isDirectory()) stack.push(full)
      else total += stat.size
    }
  }
  return total
}

const argv = process.argv.slice(2)
const platform = argValue(argv, 'platform') ?? process.platform
const arch = argValue(argv, 'arch') ?? process.arch
const appDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const outDir = resolve(
  argValue(argv, 'out') ?? join(appDir, 'build', 'runtime', `${platform}-${arch}`)
)
console.log(`RUNTIME_PREPARE_START platform=${platform} arch=${arch} out=${outDir}`)

// 1) RxyCode source (read-only)
const repo = resolve(
  argValue(argv, 'repo') ?? process.env.RXYCODE_REPO_DIR ?? join(appDir, '..', 'RxyCode-master')
)
if (!existsSync(join(repo, 'appserver', '__main__.py'))) {
  fail(`RxyCode source not found at ${repo} (appserver/__main__.py missing)`)
}
const pyproject = readFileSync(join(repo, 'pyproject.toml'), 'utf8')
const versionMatch = pyproject.match(/^version\s*=\s*"([^"]+)"/m)
if (versionMatch === null || versionMatch[1] !== EXPECTED_RXYCODE_VERSION) {
  fail(
    `expected rxycode ${EXPECTED_RXYCODE_VERSION} in pyproject.toml, found ${versionMatch?.[1] ?? 'none'}`
  )
}

// 2) python source (full install)
const probe = spawnSync(
  argValue(argv, 'python') ?? 'python',
  ['-c', 'import sys; print(sys.executable)'],
  {
    encoding: 'utf8'
  }
)
if (probe.status !== 0) {
  fail(`cannot resolve python: ${probe.stderr}`)
}
const pythonRoot = dirname(probe.stdout.trim())
if (platform === 'win32') {
  if (!existsSync(join(pythonRoot, 'python.exe')) || !existsSync(join(pythonRoot, 'Lib'))) {
    fail(`python at ${pythonRoot} is not a full install (python.exe + Lib required)`)
  }
} else if (
  !existsSync(join(pythonRoot, 'bin', 'python3')) ||
  !existsSync(join(pythonRoot, 'lib'))
) {
  fail(`python at ${pythonRoot} is not a full install (bin/python3 + lib required)`)
}

// 3) stage copies
rmSync(outDir, { recursive: true, force: true })
mkdirSync(join(outDir, 'python'), { recursive: true })
mkdirSync(join(outDir, 'app'), { recursive: true })
cpSync(pythonRoot, join(outDir, 'python'), {
  recursive: true,
  filter: (src) => keepPythonFile(pythonRoot, src)
})
cpSync(repo, join(outDir, 'app'), {
  recursive: true,
  filter: (src) => keepVendoredFile(repo, src)
})

// 4) install the vendored RxyCode package into the runtime's site-packages
//    (offline: no deps, no build isolation, no index access). The packaged
//    app then carries `RxyCode.RxyCode1_1_0.*` just like a pip install.
const pythonExe = join(outDir, 'python', pythonRelExe(platform))
const appDirStaged = join(outDir, 'app')
const pip = spawnSync(
  pythonExe,
  [
    '-m',
    'pip',
    'install',
    '--no-deps',
    '--no-build-isolation',
    '--disable-pip-version-check',
    repo
  ],
  {
    cwd: outDir,
    env: {
      ...process.env,
      PIP_NO_INDEX: '1',
      PIP_DISABLE_PIP_VERSION_CHECK: '1',
      PYTHONNOUSERSITE: '1'
    },
    encoding: 'utf8',
    timeout: 300_000
  }
)
if (pip.status !== 0) {
  fail(
    `pip install rxycode into runtime failed (status ${String(pip.status)}): ${pip.stderr}${pip.stdout}`
  )
}

// 5) manifest + versions
const pythonVersion = runPython(pythonExe, [
  '-c',
  'import platform; print(platform.python_version())'
])
const protocolVersion = (
  JSON.parse(readFileSync(join(appDirStaged, 'protocol', 'schema.json'), 'utf8')) as {
    protocol_version: string
  }
).protocol_version
writeFileSync(
  join(outDir, 'manifest.json'),
  `${JSON.stringify(
    {
      platform,
      arch,
      pythonVersion,
      rxycodeVersion: EXPECTED_RXYCODE_VERSION,
      createdAt: new Date().toISOString()
    },
    null,
    2
  )}\n`
)

// 6) verify the staged runtime itself
runPython(pythonExe, ['-c', 'import appserver; print(appserver.__name__)'], appDirStaged)
runPython(
  pythonExe,
  [
    '-c',
    'import pydantic, yaml, jsonschema, fastapi, uvicorn, langchain, langchain_openai, langgraph, psutil, tenacity, pybreaker, numpy, httpx, aiosqlite, tiktoken, click, rich; print("deps-ok")'
  ],
  appDirStaged
)
const start = spawnSync(pythonExe, ['-m', 'appserver'], {
  cwd: appDirStaged,
  env: {
    ...process.env,
    RXYCODE_APPSERVER_STUB: '1',
    PYTHONUNBUFFERED: '1',
    PYTHONIOENCODING: 'utf-8'
  },
  input: '',
  timeout: 120_000,
  encoding: 'utf8'
})
if (start.status !== 0) {
  fail(`stub appserver start failed (status ${String(start.status)}): ${start.stderr}`)
}

const total = dirSize(outDir)
console.log(
  `RUNTIME_PREPARE_OK out=${outDir} pythonVersion=${pythonVersion} rxycodeVersion=${EXPECTED_RXYCODE_VERSION} protocolVersion=${protocolVersion} totalBytes=${total}`
)
