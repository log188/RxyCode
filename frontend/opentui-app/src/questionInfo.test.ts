import { describe, expect, test } from "bun:test";
import {
  questionInfoFromParams,
  questionResultFromReply,
  summarizeQuestionToolArgs,
} from "./questionInfo.ts";

describe("questionInfoFromParams", () => {
  test("maps a choice question like the agent-slow clarifier", () => {
    const info = questionInfoFromParams({
      session_id: "s1",
      question_id: "q1",
      question: "你说的「agent慢」指的是哪个环节慢？",
      header: "确认问题",
      options: [
        { label: "我（RxyCode）响应/回复慢", value: "response" },
        { label: "某个正在运行的任务/工作流执行慢", value: "task" },
      ],
      input_type: "choice",
    });
    expect(info.questionId).toBe("q1");
    expect(info.header).toBe("确认问题");
    expect(info.inputType).toBe("choice");
    expect(info.options).toHaveLength(2);
    expect(info.options[0]).toEqual({
      label: "我（RxyCode）响应/回复慢",
      value: "response",
    });
  });

  test("free-text questions have no options", () => {
    const info = questionInfoFromParams({
      question_id: "q2",
      question: "还缺什么信息？",
    });
    expect(info.inputType).toBe("text");
    expect(info.options).toEqual([]);
  });
});

describe("questionResultFromReply", () => {
  test("selected option becomes the JSON-RPC result", () => {
    expect(
      questionResultFromReply("q1", { answer: "response" }),
    ).toEqual({
      question_id: "q1",
      answer: "response",
      cancelled: false,
      timed_out: false,
    });
  });

  test("escape maps to cancelled", () => {
    expect(questionResultFromReply("q1", { cancelled: true })).toEqual({
      question_id: "q1",
      answer: null,
      cancelled: true,
      timed_out: false,
    });
  });
});

describe("summarizeQuestionToolArgs", () => {
  test("shows the first question instead of the raw JSON blob", () => {
    expect(
      summarizeQuestionToolArgs({
        questions: [
          {
            question: "你说的「agent慢」指的是哪个环节慢？",
            header: "确认问题",
          },
        ],
      }),
    ).toBe("确认问题: 你说的「agent慢」指的是哪个环节慢？");
  });
});
