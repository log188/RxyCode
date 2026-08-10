// POSIX orphan guard: stays alive detached from the Electron process and
// SIGKILLs the appserver process group when the parent disappears (DC5).
const [parentPid, childPid] = process.argv.slice(2).map(Number)

if (!Number.isInteger(parentPid) || !Number.isInteger(childPid)) {
  process.exit(2)
}

/** @returns {boolean} */
// eslint-disable-next-line @typescript-eslint/explicit-function-return-type -- plain JS helper; JSDoc documents the contract
function isAlive(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

const timer = setInterval(() => {
  if (!isAlive(parentPid)) {
    clearInterval(timer)
    try {
      process.kill(-childPid, 'SIGKILL')
    } catch {
      try {
        process.kill(childPid, 'SIGKILL')
      } catch {
        // already gone
      }
    }
    process.exit(0)
  }
  if (!isAlive(childPid)) {
    clearInterval(timer)
    process.exit(0)
  }
}, 300)
