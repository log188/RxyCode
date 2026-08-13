import { describe, expect, test } from "bun:test";
import {
  raceWithAbort,
  shouldClearStreamingOnNotify,
  shouldClearStreamingOnUserCancel,
} from "./streamLifecycle.ts";

describe("shouldClearStreamingOnNotify", () => {
  test("final/done/error end Processing without waiting for RPC", () => {
    expect(shouldClearStreamingOnNotify("event/final")).toBe(true);
    expect(shouldClearStreamingOnNotify("event/done")).toBe(true);
    expect(shouldClearStreamingOnNotify("event/error")).toBe(true);
  });

  test("mid-stream events keep Processing", () => {
    expect(shouldClearStreamingOnNotify("event/message_delta")).toBe(false);
    expect(shouldClearStreamingOnNotify("event/reasoning_snapshot")).toBe(false);
    expect(shouldClearStreamingOnNotify("event/tool_begin")).toBe(false);
    expect(shouldClearStreamingOnNotify("event/progress")).toBe(false);
  });

  test("user Esc cancel leaves Processing without waiting for session/prompt", () => {
    expect(shouldClearStreamingOnUserCancel()).toBe(true);
  });
});

describe("raceWithAbort", () => {
  test("already-aborted signal rejects without waiting for the request", async () => {
    const controller = new AbortController();
    controller.abort();
    const hung = new Promise<string>(() => {});
    await expect(raceWithAbort(hung, controller.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  test("abort while waiting rejects before the request resolves", async () => {
    const controller = new AbortController();
    const hung = new Promise<string>(() => {});
    const raced = raceWithAbort(hung, controller.signal);
    controller.abort();
    await expect(raced).rejects.toMatchObject({ name: "AbortError" });
  });

  test("returns the request value when not aborted", async () => {
    expect(await raceWithAbort(Promise.resolve("ok"))).toBe("ok");
  });
});
