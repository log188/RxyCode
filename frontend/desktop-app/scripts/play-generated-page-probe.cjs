const { app, BrowserWindow } = require('electron')
const fs = require('node:fs')

const url = process.argv.find((arg) => String(arg).startsWith('http://') || String(arg).startsWith('https://'))
const screenshotPath = process.argv.find((arg) => String(arg).endsWith('.png'))
const mode = process.argv.find((arg) => String(arg).startsWith('--mode='))?.slice('--mode='.length) || 'game'
if (!url) {
  process.stderr.write('play probe missing http url in argv: ' + JSON.stringify(process.argv))
  process.exit(1)
}

app.setPath('userData', process.cwd())
app.commandLine.appendSwitch('disable-gpu')

app.whenReady().then(async () => {
  const consoles = []
  const window = new BrowserWindow({
    show: false,
    width: 960,
    height: 540,
    webPreferences: { sandbox: false, contextIsolation: false }
  })
  window.webContents.on('console-message', (_event, level, message) => {
    consoles.push({ level, message: String(message) })
    process.stderr.write(String(message) + '\n')
  })
  await window.loadURL(url)
  await new Promise((resolve) => setTimeout(resolve, 400))
  const pageCode = [
    '(async () => {',
    '  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));',
    '  const text = (document.body && document.body.innerText || "").trim();',
    '  const control = document.querySelector("button, select, input, a[href]");',
    '  if (control instanceof HTMLElement) control.click();',
    '  await sleep(300);',
    '  return { ok: text.length > 40, reason: text.length > 40 ? undefined : "page has no usable content", title: document.title, textLength: text.length };',
    '})()'
  ].join('\n')
  const playCode = [
    '(async () => {',
    '  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));',
    '  const readState = () => ({',
    '    score: Number((document.querySelector("#score, #scoreVal") || {}).textContent || 0),',
    '    state: ((document.querySelector("#stateLabel, #state") || {}).textContent || ""),',
    '    title: document.title',
    '  });',
    '  const press = (key) => {',
    '    window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));',
    '    document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));',
    '  };',
    '  const start = document.querySelector("#startBtn, #btn-start, [data-action=\\"start\\"], button.big, button.primary");',
    '  if (!(start instanceof HTMLElement)) return { ok: false, reason: "no start control" };',
    '  start.click();',
    '  press("Enter");',
    '  press(" ");',
    '  let snapshot = readState();',
    '  for (let i = 0; i < 20 && snapshot.score <= 0 && !/running|playing|run|\u8fd0\u884c|\u8fdb\u884c|\u6e38\u73a9/i.test(snapshot.state); i += 1) {',
    '    press(" "); press("ArrowUp"); press("ArrowRight");',
    '    await sleep(250);',
    '    snapshot = readState();',
    '  }',
    '  if (snapshot.score <= 0 && !/running|playing|run|\u8fd0\u884c|\u8fdb\u884c|\u6e38\u73a9/i.test(snapshot.state)) {',
    '    return { ok: false, reason: "did not enter a running/playable state", ...snapshot };',
    '  }',
    '  for (let i = 0; i < 40 && !/over|end|fail|\u7ed3\u675f|\u5931\u8d25/i.test(snapshot.state); i += 1) {',
    '    press(" "); press("ArrowUp"); press("ArrowRight");',
    '    await sleep(250);',
    '    snapshot = readState();',
    '  }',
    '  const restart = document.querySelector("#restartBtn");',
    '  if (restart instanceof HTMLElement) restart.click(); else press("r");',
    '  await sleep(400);',
    '  return { ok: true, ...snapshot, afterRestart: readState() };',
    '})()'
  ].join('\n')
  const played = await window.webContents.executeJavaScript(mode === 'page' ? pageCode : playCode, true)
  try {
    if (screenshotPath) fs.writeFileSync(screenshotPath, (await window.webContents.capturePage()).toPNG())
  } catch {}
  process.stdout.write(JSON.stringify({ ...played, consoles }))
  app.quit()
}).catch((error) => {
  process.stderr.write(String(error && error.stack ? error.stack : error))
  app.exit(1)
})
