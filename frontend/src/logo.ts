// RxyCode wordmark — unified 7x7 block letters
// All letters exactly 7 rows × 7 cols, 2-space gap
// 'e' row 3 adjusted to fill right edge
// All lines ljust'd to 61 chars
export const WORDMARK = [
  '███████  ██   ██  ██   ██   █████    █████   ██   ██   █████ ',
  '██   ██  ██   ██  ██   ██  ██   ██  ██   ██  ██   ██  ██   ██',
  '██   ██   ██ ██   ██   ██  ██       ██   ██  ███████  ███████',
  '███████    ███     ██ ██   ██       ██   ██  ██   ██  ██   ██',
  '██   ██   ██ ██     ███    ██       ██   ██  ██   ██  ██     ',
  '██   ██  ██   ██    ███    ██   ██  ██   ██  ██   ██  ██   ██',
  '██   ██  ██   ██    ███     █████    █████   ██   ██   █████ ',
] as const;

export function centerLine(line: string, width: number): string {
  if (width <= line.length) return line;
  const pad = Math.max(0, Math.floor((width - line.length) / 2));
  return ' '.repeat(pad) + line;
}
