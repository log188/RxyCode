import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { createRef } from "react";
import type { ScrollBoxRenderable } from "@opentui/core";
import { testRender } from "@opentui/react/test-utils";
import {
  CHAT_SCROLLBOX_STYLE,
  MAX_COMPOSER_GAP_LINES,
  chatContentPinsToComposer,
  gapBetweenMarkers,
} from "./chatLayout.ts";

describe("chat scrollbox content must pin to the composer", () => {
  test("CHAT_SCROLLBOX_STYLE packs messages at the bottom of the pane", () => {
    expect(chatContentPinsToComposer(CHAT_SCROLLBOX_STYLE.contentOptions)).toBe(true);
    expect(CHAT_SCROLLBOX_STYLE.contentOptions.justifyContent).toBe("flex-end");
    expect(CHAT_SCROLLBOX_STYLE.rootOptions.flexGrow).toBe(1);
    expect(CHAT_SCROLLBOX_STYLE.viewportOptions.flexGrow).toBe(1);
  });

  test("missing flex-end is the regression that splits command from composer", () => {
    expect(chatContentPinsToComposer({})).toBe(false);
    expect(chatContentPinsToComposer({ justifyContent: "flex-start" })).toBe(false);
  });

  test("App.tsx uses the shared pin-to-composer scrollbox style", () => {
    const src = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
    expect(src).toContain("CHAT_SCROLLBOX_STYLE");
    expect(src).not.toMatch(/contentOptions:\s*\{\s*flexGrow:\s*1,\s*backgroundColor/);
  });
});

function ChatComposerFixture({
  lines,
  pinToComposer,
}: {
  lines: string[];
  pinToComposer: boolean;
}) {
  return (
    <box style={{ flexDirection: "column", width: "100%", height: "100%" }}>
      <box style={{ height: 1, flexShrink: 0 }}>
        <text>HEADER</text>
      </box>
      <scrollbox
        stickyScroll={true}
        stickyStart="bottom"
        flexGrow={1}
        style={{
          rootOptions: { flexGrow: 1, border: false },
          viewportOptions: { flexGrow: 1 },
          contentOptions: pinToComposer
            ? { flexGrow: 1, flexDirection: "column", justifyContent: "flex-end" }
            : { flexGrow: 1 },
        }}
      >
        {lines.map((line) => (
          <box key={line} style={{ width: "100%", height: 1, flexShrink: 0 }}>
            <text>{line}</text>
          </box>
        ))}
      </scrollbox>
      <box style={{ height: 1, flexShrink: 0 }}>
        <text>SHORTCUTS</text>
      </box>
      <box style={{ height: 3, flexShrink: 0, border: true }}>
        <text>COMPOSER</text>
      </box>
      <box style={{ height: 1, flexShrink: 0 }}>
        <text>STATUS</text>
      </box>
    </box>
  );
}

const SHORT_CHAT = ["USER-cmd write click-counter", "TOOL-ok bash", "TOOL-ok write"];

describe("OpenTUI composer gap (命令与输出分离)", () => {
  test("flex-end content keeps last tool line next to the composer", async () => {
    const { flush, captureCharFrame, renderer } = await testRender(
      <ChatComposerFixture lines={SHORT_CHAT} pinToComposer={true} />,
      { width: 80, height: 24 },
    );
    try {
      await flush();
      const frame = captureCharFrame();
      const gap = gapBetweenMarkers(frame, "TOOL-ok write", "COMPOSER");
      expect(gap).toBeGreaterThanOrEqual(0);
      expect(gap).toBeLessThanOrEqual(MAX_COMPOSER_GAP_LINES);
      expect(frame).toContain("USER-cmd write click-counter");
      expect(frame).toContain("COMPOSER");
    } finally {
      renderer.destroy();
    }
  });

  test("default stretched content is the split-layout bug", async () => {
    const { flush, captureCharFrame, renderer } = await testRender(
      <ChatComposerFixture lines={SHORT_CHAT} pinToComposer={false} />,
      { width: 80, height: 24 },
    );
    try {
      await flush();
      const frame = captureCharFrame();
      const gap = gapBetweenMarkers(frame, "TOOL-ok write", "COMPOSER");
      expect(gap).toBeGreaterThan(MAX_COMPOSER_GAP_LINES);
    } finally {
      renderer.destroy();
    }
  });

  test("overflowing chat still scrolls when messages pin to the composer", async () => {
    const scrollRef = createRef<ScrollBoxRenderable>();
    const many = Array.from({ length: 40 }, (_, i) => `CHAT-LINE-${String(i).padStart(2, "0")}`);
    const { flush, captureCharFrame, renderer } = await testRender(
      <box style={{ flexDirection: "column", width: "100%", height: "100%" }}>
        <scrollbox
          ref={scrollRef}
          stickyScroll={true}
          stickyStart="bottom"
          flexGrow={1}
          style={CHAT_SCROLLBOX_STYLE}
        >
          {many.map((line) => (
            <box key={line} style={{ width: "100%", height: 1, flexShrink: 0 }}>
              <text>{line}</text>
            </box>
          ))}
        </scrollbox>
        <box style={{ height: 3, flexShrink: 0 }}>
          <text>COMPOSER</text>
        </box>
      </box>,
      { width: 80, height: 16 },
    );
    try {
      await flush();
      const box = scrollRef.current;
      expect(box).toBeTruthy();
      if (!box) return;
      expect(box.scrollHeight).toBeGreaterThan(0);
      const frame = captureCharFrame();
      expect(frame).toContain("COMPOSER");
      expect(frame).toContain("CHAT-LINE-39");
    } finally {
      renderer.destroy();
    }
  });
});
