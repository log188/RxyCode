import { describe, expect, test } from "bun:test";
import { applyStreamEvent, settleActiveMessages, type StreamReduceState } from "./streamReducer.ts";

function base(): StreamReduceState {
  return {
    messages: [
      {
        id: "t1",
        role: "thinking",
        content: "…",
        timestamp: 1,
        live: true,
        done: false,
      },
    ],
    thinkingId: "t1",
    assistantId: "a1",
    acc: "",
    assistantCreated: false,
    reasoningAcc: "",
    hasReasoning: false,
  };
}

const nid = (s: string) => `id-${s}`;

describe("applyStreamEvent thinking timing", () => {
  test("first token does not checkmark thinking", () => {
    let s = base();
    s = applyStreamEvent(s, { type: "reasoning", text: "plan A" }, nid);
    s = applyStreamEvent(s, { type: "token", text: "hello" }, nid);
    const thinking = s.messages.find((m) => m.id === "t1")!;
    expect(thinking.done).toBe(false);
    expect(thinking.live).toBe(true);
    expect(s.messages.some((m) => m.role === "assistant")).toBe(true);
  });

  test("reasoning accumulates after tool_result", () => {
    let s = base();
    s = applyStreamEvent(s, { type: "reasoning", text: "before" }, nid);
    s = applyStreamEvent(s, { type: "tool_call", name: "bash", args: "dir" }, nid);
    s = applyStreamEvent(s, { type: "tool_result", name: "bash", result: "ok" }, nid);
    s = applyStreamEvent(s, { type: "reasoning", text: "after tool" }, nid);
    const thinking = s.messages.find((m) => m.id === "t1")!;
    expect(thinking.content).toContain("before");
    expect(thinking.content).toContain("after tool");
    expect(thinking.done).toBe(false);
  });

  test("final marks thinking done", () => {
    let s = base();
    s = applyStreamEvent(s, { type: "reasoning", text: "x" }, nid);
    s = applyStreamEvent(s, { type: "token", text: "y" }, nid);
    s = applyStreamEvent(s, { type: "final", text: "y done" }, nid);
    const thinking = s.messages.find((m) => m.id === "t1")!;
    expect(thinking.done).toBe(true);
    expect(thinking.live).toBe(false);
  });

  test("settleActiveMessages finishes assistant and tools", () => {
    const settled = settleActiveMessages([
      { id: "t1", role: "thinking", content: "x", timestamp: 1, done: false, live: true },
      { id: "a1", role: "assistant", content: "hi", timestamp: 1, done: false },
      { id: "tool", role: "tool", content: "", timestamp: 1, toolName: "bash", toolStatus: "running" },
    ]);
    expect(settled.find((m) => m.id === "t1")!.done).toBe(true);
    expect(settled.find((m) => m.id === "a1")!.done).toBe(true);
    expect(settled.find((m) => m.id === "tool")!.toolStatus).toBe("cancelled");
  });

  test("tokens after a tool open a new assistant segment", () => {
    let s = base();
    s = applyStreamEvent(s, { type: "token", text: "先查官网" }, nid);
    s = applyStreamEvent(s, { type: "tool_call", name: "websearch", args: "gz sha" }, nid);
    s = applyStreamEvent(s, { type: "tool_result", name: "websearch", result: "ok" }, nid);
    s = applyStreamEvent(s, { type: "token", text: "再打开携程" }, nid);
    s = applyStreamEvent(s, { type: "final", text: "先查官网再打开携程完整总结" }, nid);
    const roles = s.messages.map((m) => (m.role === "tool" ? `tool:${m.toolName}` : m.role));
    expect(roles).toEqual(["thinking", "assistant", "tool:websearch", "assistant"]);
    const assistants = s.messages.filter((m) => m.role === "assistant");
    expect(assistants[0]?.content).toBe("先查官网");
    expect(assistants[1]?.content).toBe("再打开携程");
  });

  test("question tool_call shows the prompt instead of raw JSON", () => {
    const next = applyStreamEvent(
      base(),
      {
        type: "tool_call",
        name: "question",
        args: {
          questions: [{ question: "哪个环节慢？", header: "确认问题" }],
        },
      },
      nid,
    );
    const tool = next.messages.find((m) => m.role === "tool");
    expect(tool?.toolName).toBe("question");
    expect(tool?.content).toBe("确认问题: 哪个环节慢？");
    expect(tool?.content).not.toContain("questions");
  });

  test("stage separator progress becomes a system line", () => {
    const next = applyStreamEvent(
      base(),
      { type: "progress", text: "──────── plan · architect ────────" },
      nid,
    );
    const sep = next.messages.find((m) => m.role === "system");
    expect(sep?.content).toContain("plan · architect");
  });
});
