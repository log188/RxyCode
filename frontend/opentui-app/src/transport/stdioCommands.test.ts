import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseStdioAdminCommand,
  shouldRestartStdioSessionOnModelSwitch,
  statusFromModelsList,
} from "./stdioCommands.ts";

describe("stdio admin commands", () => {
  test("/model is handled locally instead of HTTP + session restart", () => {
    expect(parseStdioAdminCommand("/model deepseek/deepseek-v4-flash")).toEqual({
      kind: "model",
      modelId: "deepseek/deepseek-v4-flash",
    });
    expect(shouldRestartStdioSessionOnModelSwitch()).toBe(false);
  });

  test("/thinking stays local", () => {
    expect(parseStdioAdminCommand("/thinking")).toEqual({ kind: "thinking" });
  });

  test("other slash commands still go through HTTP admin", () => {
    expect(parseStdioAdminCommand("/status")).toEqual({
      kind: "http",
      command: "/status",
    });
  });

  test("status bar uses persisted active model before the worker starts", () => {
    const status = statusFromModelsList({
      active: "deepseek/deepseek-v4-flash",
      models: [
        {
          id: "deepseek/deepseek-v4-flash",
          name: "deepseek-v4-flash",
          nickname: "deepseek-v4-flash",
          active: true,
        },
      ],
    });
    expect(status.model).toBe("deepseek-v4-flash");
  });
});

describe("stdio transport model switch regression", () => {
  test("does not shut down the live worker after /model", () => {
    const src = readFileSync(
      path.join(path.dirname(fileURLToPath(import.meta.url)), "stdioTransport.ts"),
      "utf8",
    );
    expect(src).not.toMatch(/model_changed[\s\S]{0,400}sharedSession\.shutdown/);
  });
});
