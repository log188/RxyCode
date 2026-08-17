/**
 * Bundled Python runtime resolution for the packaged Desktop app (Phase4-D6).
 *
 * The packaging pipeline stages a self-contained runtime under
 * `resources/runtime/` (electron-builder extraResources):
 *
 *   resources/runtime/
 *     manifest.json          platform/arch/version metadata
 *     python/                relocatable Python install (python.exe on win32)
 *     app/                   vendored RxyCode source (appserver/__main__.py)
 *
 * The main process prefers this bundled runtime when present and falls back
 * to the development layout (python on PATH + repo root) otherwise.
 */
import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

export interface RuntimeManifest {
  platform: string
  arch: string
  pythonVersion: string
  rxycodeVersion: string
  createdAt: string
}

export interface BundledRuntime {
  manifest: RuntimeManifest
  /** Absolute path of the `runtime` directory under resources. */
  rootDir: string
  /** Absolute path of the python executable inside the runtime. */
  python: string
  /** Absolute path of the vendored RxyCode source (contains appserver/__main__.py). */
  appDir: string
}

export function pythonExeName(platform: NodeJS.Platform): string {
  // Relative path inside the runtime layout, not a host path: keep the
  // POSIX-style separator so the value is identical on every platform.
  return platform === 'win32' ? 'python.exe' : 'bin/python3'
}

export function readRuntimeManifest(runtimeDir: string): RuntimeManifest | null {
  try {
    const raw = readFileSync(join(runtimeDir, 'manifest.json'), 'utf8')
    const parsed = JSON.parse(raw) as Partial<RuntimeManifest>
    if (
      typeof parsed.platform !== 'string' ||
      typeof parsed.arch !== 'string' ||
      typeof parsed.pythonVersion !== 'string' ||
      typeof parsed.rxycodeVersion !== 'string' ||
      typeof parsed.createdAt !== 'string'
    ) {
      return null
    }
    return parsed as RuntimeManifest
  } catch {
    return null
  }
}

export function findBundledRuntime(
  resourcesDir: string,
  platform: NodeJS.Platform = process.platform,
  arch: string = process.arch
): BundledRuntime | null {
  const rootDir = join(resourcesDir, 'runtime', `${platform}-${arch}`)
  const manifest = readRuntimeManifest(rootDir)
  if (manifest === null) return null
  if (manifest.platform !== platform || manifest.arch !== arch) return null
  const python = join(rootDir, 'python', pythonExeName(platform))
  const appDir = join(rootDir, 'app')
  if (!existsSync(python)) return null
  if (!existsSync(join(appDir, 'appserver', '__main__.py'))) return null
  return { manifest, rootDir, python, appDir }
}
