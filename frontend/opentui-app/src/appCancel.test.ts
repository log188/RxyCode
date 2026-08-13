import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

describe("OpenTUI Esc cancel", () => {
  test("Esc clears Processing before waiting for cancel RPC", () => {
    const src = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), "App.tsx"),
      "utf8",
    );
    const esc = src.slice(src.indexOf('if (key.name === "escape")'));
    const streamingIdx = esc.indexOf("setIsStreaming(false)");
    const cancelIdx = esc.indexOf("cancelActiveRequest");
    expect(streamingIdx).toBeGreaterThanOrEqual(0);
    expect(cancelIdx).toBeGreaterThan(streamingIdx);
  });
});
