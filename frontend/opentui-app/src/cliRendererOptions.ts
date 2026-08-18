/**
 * OpenTUI mouse tracking on Windows.
 *
 * Scroll, copy, and edge auto-scroll need useMouse (1000/1002 + SGR 1006).
 * All-motion 1003 emits ESC [ < 35 ; x ; y M on every hover; cmd/ConPTY
 * paints those as [[<35;46;17M^. Keep clicks/drag/wheel on, movement off.
 * RXYCODE_MOUSE=0 disables tracking; RXYCODE_MOUSE_MOVE=1 opts into 1003.
 */
export type CliRendererMouseOptions = {
  useMouse: boolean;
  enableMouseMovement: boolean;
};

export const DISABLE_ALL_MOTION = "\x1b[?1003l";
export const DISABLE_MOUSE_TRACKING = "\x1b[?1003l\x1b[?1002l\x1b[?1000l\x1b[?1006l";

/** Hover-only SGR (button 35). Must not match click / drag / wheel. */
const SGR_HOVER = /(?:\x1b)?\[<35;\d+;\d+[Mm]/;

export function isWindowsHost(platform: NodeJS.Platform = process.platform): boolean {
  return platform === "win32";
}

export function resolveCliRendererMouseOptions(
  env: NodeJS.ProcessEnv = process.env,
  platform: NodeJS.Platform = process.platform,
): CliRendererMouseOptions {
  const forceOff = env.RXYCODE_MOUSE === "0";
  const forceMove = env.RXYCODE_MOUSE_MOVE === "1";
  if (forceOff) {
    return { useMouse: false, enableMouseMovement: false };
  }
  return {
    useMouse: true,
    enableMouseMovement: forceMove || !isWindowsHost(platform),
  };
}

export function writeDisableAllMotion(
  stream: { write: (chunk: string) => unknown } = process.stdout,
): void {
  try {
    stream.write(DISABLE_ALL_MOTION);
  } catch {
    // terminal may already be gone
  }
}

export function writeDisableMouseTracking(
  stream: { write: (chunk: string) => unknown } = process.stdout,
): void {
  try {
    stream.write(DISABLE_MOUSE_TRACKING);
  } catch {
    // terminal may already be gone
  }
}

/** Eat leftover hover reports so they never reach the textarea as text. */
export function consumeSgrMouseInput(sequence: string): boolean {
  return SGR_HOVER.test(sequence);
}
