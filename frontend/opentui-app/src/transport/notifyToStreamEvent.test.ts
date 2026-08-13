import { describe, expect, test } from "bun:test";
import { notifyToStreamEvent } from "./notifyToStreamEvent.ts";

describe("notifyToStreamEvent", () => {
  test("maps message_delta to token", () => {
    expect(
      notifyToStreamEvent("event/message_delta", { session_id: "s1", text: "hi" }),
    ).toEqual({ type: "token", text: "hi" });
  });

  test("maps tool_begin and tool_end", () => {
    expect(
      notifyToStreamEvent("event/tool_begin", {
        session_id: "s1",
        call_id: "c1",
        tool_name: "read_file",
        arguments: { path: "a.ts" },
      }),
    ).toEqual({
      type: "tool_call",
      name: "read_file",
      args: { path: "a.ts" },
    });
    expect(
      notifyToStreamEvent("event/tool_end", {
        session_id: "s1",
        call_id: "c1",
        ok: true,
        summary: "done",
      }),
    ).toEqual({
      type: "tool_result",
      name: "",
      result: "done",
      status: "success",
    });
  });

  test("maps event/final token fields for the status bar", () => {
    expect(
      notifyToStreamEvent("event/final", {
        session_id: "s1",
        run_id: "r1",
        text: "done",
        input_tokens: 900,
        output_tokens: 100,
        cache_hit_tokens: 400,
        cache_hit_rate: 44.4,
        reporting_status: "reported",
      }),
    ).toEqual({
      type: "final",
      text: "done",
      message: "done",
      input_tokens: 900,
      output_tokens: 100,
      cache_hit_tokens: 400,
      cache_hit_rate: 44.4,
      reporting_status: "reported",
    });
  });

  test("maps event/token_usage for the status bar", () => {
    expect(
      notifyToStreamEvent("event/token_usage", {
        session_id: "s1",
        input_tokens: 1200,
        output_tokens: 300,
        cache_hit_tokens: 800,
        cache_hit_rate: 66.7,
        reporting_status: "reported",
      }),
    ).toEqual({
      type: "token_usage",
      input_tokens: 1200,
      output_tokens: 300,
      cache_hit_tokens: 800,
      cache_hit_rate: 66.7,
      reporting_status: "reported",
    });
  });

  test("returns null for unknown methods", () => {
    expect(notifyToStreamEvent("event/server_heartbeat", {})).toBeNull();
  });
});
