import test from 'node:test'
import assert from 'node:assert/strict'
import { keepPythonFile, keepVendoredFile, windowsVersionedDllName } from './prepare-runtime.mts'

function win(src: string): boolean {
  return keepPythonFile('C:/Python', src, 'win32', false)
}

function posix(src: string): boolean {
  return keepPythonFile('/opt/python', src, 'darwin', false)
}

function linux(src: string): boolean {
  return keepPythonFile('/opt/python', src, 'linux', false)
}

function winDir(src: string): boolean {
  return keepPythonFile('C:/Python', src, 'win32', true)
}

function posixDir(src: string): boolean {
  return keepPythonFile('/opt/python', src, 'darwin', true)
}
test('win32 keeps interpreter + stdlib, drops debug/Docs/test', () => {
  assert.equal(win('C:/Python/python.exe'), true)
  assert.equal(win('C:/Python/pythonw.exe'), true)
  assert.equal(win('C:/Python/python3.dll'), true)
  assert.equal(win('C:/Python/python312.dll'), true)
  assert.equal(win('C:/Python/python313.dll'), true)
  assert.equal(win('C:/Python/python314.dll'), true)
  assert.equal(win('C:/Python/vcruntime140.dll'), true)
  assert.equal(win('C:/Python/python_d.exe'), false) // debug interpreter dropped
  assert.equal(win('C:/Python/Lib/site-packages/pydantic'), true)
  assert.equal(win('C:/Python/Lib/test'), false)
  assert.equal(win('C:/Python/Lib/site-packages/pytest'), false)
  assert.equal(win('C:/Python/Lib/site-packages/scipy'), false)
  assert.equal(win('C:/Python/Doc'), false)
})

test('win32 filters pip and rxycode dist-info by dynamic version', () => {
  assert.equal(win('C:/Python/Scripts/pip.exe'), true)
  assert.equal(win('C:/Python/Scripts/pip3.12.exe'), true)
  assert.equal(win('C:/Python/Scripts/frobnicate.exe'), false)
  assert.equal(win('C:/Python/Lib/site-packages/rxycode-1.2.10.dist-info'), false)
  assert.equal(win('C:/Python/Lib/site-packages/rxycode-1.2.6.dist-info'), false)
})

test('POSIX keeps bin/python3 + lib/pythonX.Y stdlib, drops pip wrappers beyond pip3', () => {
  assert.equal(posix('/opt/python/bin/python3'), true)
  assert.equal(posix('/opt/python/bin/python3.14'), true)
  assert.equal(posix('/opt/python/bin/pip3'), true)
  assert.equal(posix('/opt/python/bin/frobnicate'), false)
  assert.equal(posix('/opt/python/lib/libpython3.14.so'), true)
  assert.equal(posix('/opt/python/lib/libpython3.14.dylib'), true)
  assert.equal(posix('/opt/python/lib/pkgconfig'), true)
  assert.equal(posix('/opt/python/lib/python3.14/site-packages/pydantic'), true)
  assert.equal(posix('/opt/python/lib/python3.14/site-packages/pytest'), false)
  assert.equal(posix('/opt/python/lib/python3.14/test'), false)
  assert.equal(posix('/opt/python/Doc'), false)
})

test('linux uses the same POSIX layout', () => {
  assert.equal(linux('/opt/python/bin/python3'), true)
  assert.equal(linux('/opt/python/lib/libpython3.13.so.1.0'), true)
  assert.equal(linux('/opt/python/lib/python3.13/site-packages/pydantic'), true)
  assert.equal(linux('/opt/python/lib/python3.13/site-packages/ruff'), false)
})

test('directory roots (bin/lib/Lib/DLLs) are always traversed', () => {
  // A directory that merely carries python executables must not be pruned
  // by the file-level name rules (this was the mac/linux ENOENT root cause).
  assert.equal(posixDir('/opt/python/bin'), true)
  assert.equal(posixDir('/opt/python/lib'), true)
  assert.equal(posixDir('/opt/python/lib/python3.14'), true)
  assert.equal(posixDir('/opt/python/lib/python3.14/site-packages'), true)
  assert.equal(winDir('C:/Python/Lib'), true)
  assert.equal(winDir('C:/Python/DLLs'), true)
  assert.equal(winDir('C:/Python/Scripts'), true)
  // Pruned subtrees stay pruned even as directories.
  assert.equal(posixDir('/opt/python/lib/python3.14/test'), false)
  assert.equal(winDir('C:/Python/Lib/site-packages/pytest'), true)
})

test('windowsVersionedDllName maps CPython X.Y to pythonXY.dll', () => {
  assert.equal(windowsVersionedDllName('3.12.10'), 'python312.dll')
  assert.equal(windowsVersionedDllName('Python 3.12.10'), 'python312.dll')
  assert.equal(windowsVersionedDllName('3.14.2'), 'python314.dll')
  assert.equal(windowsVersionedDllName('not-a-version'), null)
})

test('vendored app tree keeps appserver and drops repo junk', () => {
  const keep = (src: string): boolean => keepVendoredFile('C:/repo', src, true)
  assert.equal(keep('C:/repo/appserver/__main__.py'), true)
  assert.equal(keep('C:/repo/core/agent_v2.py'), true)
  assert.equal(keep('C:/repo/.github/workflows/ci.yml'), false)
  assert.equal(keep('C:/repo/evals/run.py'), false)
  assert.equal(keep('C:/repo/frontend/opentui-app/package.json'), false)
  assert.equal(keep('C:/repo/frontend/desktop-app/package.json'), false)
  assert.equal(keep('C:/repo/__pycache__/x.pyc'), false)
})
