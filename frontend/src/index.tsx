import React from 'react';
import { render } from 'ink';
import type { ReadStream } from 'node:tty';
import App from './App.js';
import { mouseManager } from './mouse.js';
import { createMouseStdin } from './stdinBridge.js';
import { initializeTerminalCursor } from './terminalCursor.js';
import { installTerminalLifecycle } from './terminalLifecycle.js';

if (!process.stdin.isTTY) {
  console.log('RxyCode TUI requires an interactive terminal (TTY).');
  console.log('Please run this directly in a terminal, not piped.');
  process.exit(1);
}

// Attach the real stdout so the manager can toggle SGR mouse tracking, and
// create the single cleaned stdin reader that strips mouse reports before
// Ink sees them.
mouseManager.attach(process.stdout);
initializeTerminalCursor(process.stdout);
const bridge = createMouseStdin(process.stdin, process.stdout, mouseManager);

let cleanupTerminal = () => {};
const app = render(
  <App terminateProcess={() => {
    cleanupTerminal();
    setImmediate(() => process.exit(0));
  }} />,
  { stdin: bridge.stdin as unknown as ReadStream, stdout: process.stdout, exitOnCtrlC: false },
);
cleanupTerminal = installTerminalLifecycle({ app, bridge, mouseManager, stdout: process.stdout });
