import { C } from "./theme.ts";

/**
 * Chat ScrollBox style for OpenTUI.
 *
 * The viewport grows to fill leftover height. Content also fills that
 * viewport, but `justifyContent: "flex-end"` packs messages against the
 * composer instead of the header. Without that, a few tool lines sit at the
 * top of the pane while the pink input box stays at the bottom — the
 * "命令与输出分离" gap (same failure mode as Ink ChatPanel 问题3).
 *
 * stickyStart "bottom" still follows new lines once content overflows.
 */
export const CHAT_SCROLLBOX_STYLE = {
  rootOptions: { flexGrow: 1, border: false as const, backgroundColor: C.bg },
  viewportOptions: { flexGrow: 1, backgroundColor: C.bg, paddingRight: 1 },
  contentOptions: {
    flexGrow: 1,
    flexDirection: "column" as const,
    justifyContent: "flex-end" as const,
    backgroundColor: C.bg,
  },
};

export function chatContentPinsToComposer(contentOptions: {
  justifyContent?: string;
}): boolean {
  return contentOptions.justifyContent === "flex-end";
}

/** Max blank rows allowed between last chat line and the composer chrome. */
export const MAX_COMPOSER_GAP_LINES = 4;

export function gapBetweenMarkers(
  frame: string,
  lastChatMarker: string,
  composerMarker: string,
): number {
  const lines = frame.replace(/\r\n/g, "\n").split("\n");
  const lastChat = lines.findLastIndex((line) => line.includes(lastChatMarker));
  const composer = lines.findIndex((line) => line.includes(composerMarker));
  if (lastChat < 0 || composer < 0) {
    throw new Error(
      `markers missing lastChat=${lastChat} composer=${composer}\n${frame}`,
    );
  }
  return composer - lastChat - 1;
}
