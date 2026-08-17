'use strict'

/**
 * electron-builder's Windows zip target is flat: extracting dumps exe +
 * resources/ into the current directory. Re-pack into a single wrapper
 * folder named after the zip (minus .zip) so the portable archive matches
 * the macOS zip/dmg layout.
 */
const { spawnSync } = require('node:child_process')
const { basename } = require('node:path')

function wrapperNameFromZip(zipPath) {
  return basename(zipPath, '.zip')
}

function resolvePython() {
  const fromEnv = process.env.PYTHON
  if (fromEnv) return fromEnv
  return process.platform === 'win32' ? 'python' : 'python3'
}

const REWRAP_PY = `
import sys
import zipfile
from io import BytesIO
from pathlib import Path

src = Path(sys.argv[1])
prefix = sys.argv[2].replace("\\\\", "/").strip("/") + "/"

with zipfile.ZipFile(src, "r") as zin:
    names = [name.replace("\\\\", "/") for name in zin.namelist() if name and name != "/"]
    tops = {name.split("/")[0] for name in names}
    if len(tops) == 1:
        sys.exit(0)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            name = info.filename.replace("\\\\", "/")
            if not name:
                continue
            new_name = prefix + name.lstrip("/")
            if info.is_dir() or name.endswith("/"):
                zout.writestr(new_name if new_name.endswith("/") else new_name + "/", b"")
                continue
            new_info = zipfile.ZipInfo(filename=new_name)
            new_info.compress_type = zipfile.ZIP_DEFLATED
            new_info.external_attr = info.external_attr
            new_info.date_time = info.date_time
            zout.writestr(new_info, zin.read(info.filename))
    src.write_bytes(buf.getvalue())
`

function wrapWindowsZip(zipPath, python) {
  const wrapper = wrapperNameFromZip(zipPath)
  const result = spawnSync(python ?? resolvePython(), ['-c', REWRAP_PY, zipPath, wrapper], {
    encoding: 'utf8'
  })
  if (result.status !== 0) {
    throw new Error(
      `wrap Windows zip failed (status ${String(result.status)}): ${result.stderr || result.stdout}`
    )
  }
  return wrapper
}

async function afterAllArtifactBuild(buildResult) {
  const paths = buildResult && Array.isArray(buildResult.artifactPaths) ? buildResult.artifactPaths : []
  for (const artifact of paths) {
    if (typeof artifact !== 'string' || !artifact.toLowerCase().endsWith('.zip')) continue
    if (!/-win/i.test(basename(artifact))) continue
    wrapWindowsZip(artifact)
  }
  return []
}

module.exports = afterAllArtifactBuild
module.exports.default = afterAllArtifactBuild
module.exports.wrapWindowsZip = wrapWindowsZip
module.exports.wrapperNameFromZip = wrapperNameFromZip
