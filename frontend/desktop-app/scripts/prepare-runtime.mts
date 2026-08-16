#!/usr/bin/env node
/**
 * Phase4-D6 runtime staging.
 *
 * Builds a self-contained Python runtime + vendored RxyCode source under
 * build/runtime/<platform>-<arch>/, which electron-builder copies into the
 * packaged app as resources/runtime/ (extraResources).
 *
 * Self-contained means the packaged app must not depend on the dev
 * machine's ../RxyCode-master checkout or a system python: the staged
 * runtime carries its own interpreter, its own site-packages and a
 * vendored copy of the RxyCode source tree. RxyCode-master is only READ.
 *
 * The RxyCode version is read from pyproject.toml at staging time (no
 * hard-coded pin), so a 1.2.10 tag bundles 1.2.10 automatically.
 */
import { spawnSync } from 'node:child_process'
import {
  copyFileSync,
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  readlinkSync,
  rmSync,
  statSync,
  writeFileSync
} from 'node:fs'
import { basename, dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

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

function keepPythonFile(pythonRoot: string, src: string, platform: string): boolean {
  if (src === pythonRoot) return true
  // Split on both separators so layout checks work identically on every OS.
  const parts = relative(pythonRoot, src).split(/[\\/]/)
  const name = basename(src)
  if (name === '__pycache__' || name.endsWith('.pyc') || name.endsWith('.pdb')) return false
  const top = parts[0]
  // Windows layout: DLLs / Lib / Scripts / python*.dll.
  if (platform === 'win32') {
    if (top === 'Doc' || top === 'include' || top === 'libs' || top === 'share') return false
    if (top === 'DLLs') return !/_d\.pyd$/.test(name) && !/_t\.pyd$/.test(name)
    if (top === 'Lib') return keepStdLib(parts, name)
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
  // POSIX layout (macOS / Linux): bin / lib / lib/pythonX.Y / share.
  if (top === 'Doc' || top === 'include' || top === 'libs' || top === 'share') return false
  if (top === 'bin') {
    return (
      name === 'python3' ||
      name === 'python3.12' ||
      name === 'python3.13' ||
      name === 'python3.14' ||
      name.startsWith('pip3')
    )
  }
  if (top === 'lib') {
    const second = parts[1]
    if (second && second.startsWith('python')) {
      const third = parts[2]
      if (third === 'site-packages') return keepSitePackages(parts, name)
      // Keep stdlib modules but prune tests/docs/caches.
      if (third === 'test' || third === 'idlelib' || third === 'turtledemo' || third === 'venv') {
        return false
      }
      return true
    }
    // libpython*.so / libpython*.dylib and pkgconfig live here.
    return /^libpython/.test(name) || name === 'pkgconfig'
  }
  return true
}

function keepStdLib(parts: string[], name: string): boolean {
  const second = parts[1]
  if (second === 'test' || second === 'idlelib' || second === 'turtledemo' || second === 'venv') {
    return false
  }
  if (second === 'site-packages') return keepSitePackages(parts, name)
  return true
}

function keepSitePackages(parts: string[], name: string): boolean {
  // parts is the full relative path; find the entry right after "site-packages"
  // so the same logic works for Lib\site-packages\X and lib/pythonX.Y/site-packages/X.
  const spIdx = parts.indexOf('site-packages')
  const pkgName = spIdx >= 0 && parts[spIdx + 1] !== undefined ? parts[spIdx + 1] : name
  if (
    ['scipy', 'pandas', 'matplotlib', 'coverage', 'pytest', '_pytest', 'ruff'].includes(pkgName)
  ) {
    return false
  }
  if (name.endsWith('.dist-info') && /^rxycode-/.test(name)) return false
  if (name.startsWith('__editable__')) return false
  return true
}

export { keepPythonFile, keepSitePackages }

function keepVendoredFile(repo: string, src: string): boolean {
  if (src === repo) return true
  const parts = relative(repo, src).split(/[\\/]/)
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
  // The desktop shell must never be vendored into itself: when
  // RXYCODE_REPO_DIR points at the same checkout that contains
  // frontend/desktop-app, copying would recurse into its build/runtime
  // staging (cpSync ERR_FS_CP_EINVAL).
  if (parts[0] === 'frontend' && parts[1] === 'desktop-app') {
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

// Manual recursive copy with a per-node keep filter.
//
// Node >= 24's fs.cpSync pre-validates that the destination is not inside
// the source tree and throws ERR_FS_CP_EINVAL before the `filter` runs. Our
// staging layout (repo -> repo/frontend/desktop-app/build/runtime/<plat>/app)
// is inherently nested, so we walk the tree ourselves and skip excluded
// paths explicitly. The keep predicates are shared with the unit tests.
//
// Symbolic links (macOS/Linux `bin/python3`, `lib/libpython*.dylib`, pip
// wrappers) are dereferenced and copied as real files: a staged runtime must
// be self-contained and must not keep a dangling pointer back to the build
// machine's interpreter.
function copyTree(srcRoot: string, dstRoot: string, keep: (src: string) => boolean): void {
  const stack: Array<{ src: string; dst: string }> = [{ src: srcRoot, dst: dstRoot }]
  while (stack.length > 0) {
    const { src, dst } = stack.pop() as { src: string; dst: string }
    if (!keep(src)) continue
    mkdirSync(dst, { recursive: true })
    for (const name of readdirSync(src)) {
      const full = join(src, name)
      const target = join(dst, name)
      const stat = lstatSync(full)
      if (stat.isSymbolicLink()) {
        // Dereference: copy the link target's *content* as a real file. The
        // keep predicate was already applied to the link itself, and the
        // target may live outside pythonRoot (macOS setup-python links
        // bin/python3 to the framework), so do not re-filter the target.
        const resolved = resolve(src, readlinkSync(full))
        if (keep(full)) {
          copyFileSync(resolved, target)
        }
      } else if (stat.isDirectory()) {
        stack.push({ src: full, dst: target })
      } else if (keep(full)) {
        cpSync(full, target)
      }
    }
  }
}

const argv = process.argv.slice(2)
const isMain = process.argv[1] === fileURLToPath(import.meta.url)

if (isMain) {
  await main(argv)
}

async function main(argv: string[]): Promise<void> {
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
  if (versionMatch === null) {
    fail('unable to read rxycode version from pyproject.toml')
  }
  const rxycodeVersion = versionMatch[1]
  // No hard-coded version pin: the release pipeline guarantees pyproject's
  // version matches the tag; the runtime bundles whatever the checkout has.

  // 2) python source (full install). Probe the *base prefix* (sys.base_prefix)
  // instead of sys.executable's dirname so a venv/conda python still resolves
  // to its real stdlib + site-packages root for staging.
  const probe = spawnSync(
    argValue(argv, 'python') ?? 'python',
    ['-c', 'import sys; print(sys.base_prefix)'],
    {
      encoding: 'utf8'
    }
  )
  if (probe.status !== 0) {
    fail(`cannot resolve python: ${probe.stderr}`)
  }
  const pythonRoot = probe.stdout.trim()
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
  copyTree(pythonRoot, join(outDir, 'python'), (src) => keepPythonFile(pythonRoot, src, platform))
  copyTree(repo, join(outDir, 'app'), (src) => keepVendoredFile(repo, src))

  // 4) install the vendored RxyCode package into the runtime's site-packages
  //    (offline: no deps, no build isolation, no index access). The packaged
  //    app then carries `RxyCode.RxyCode1_1_0.*` just like a pip install.
  const pythonExe = join(outDir, 'python', pythonRelExe(platform))
  const appDirStaged = join(outDir, 'app')

  // Diagnose the staged interpreter before invoking pip: a stale symlink or a
  // broken sys.prefix on macOS/Linux manifests as spawnSync status === null,
  // which otherwise gets reported as a bare "pip install failed".
  const probeStaged = spawnSync(pythonExe, ['-c', 'import sys; print(sys.prefix, sys.version)'], {
    cwd: outDir,
    encoding: 'utf8',
    timeout: 30_000
  })
  if (probeStaged.status !== 0) {
    fail(
      `staged python ${pythonExe} failed to run (status ${String(probeStaged.status)}, ` +
        `error ${String(probeStaged.error)}): ${probeStaged.stderr}${probeStaged.stdout}`
    )
  }

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
      `pip install rxycode into runtime failed (status ${String(pip.status)}, ` +
        `error ${String(pip.error)}): ${pip.stderr}${pip.stdout}`
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
        rxycodeVersion,
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
    `RUNTIME_PREPARE_OK out=${outDir} pythonVersion=${pythonVersion} rxycodeVersion=${rxycodeVersion} protocolVersion=${protocolVersion} totalBytes=${total}`
  )
}
