import { afterEach, describe, expect, test } from "bun:test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  __resetStdioSessionForTests,
  __setPythonCmdForTests,
} from "./stdioTransport.ts";
import { resetChatTransportForTests, getChatTransport } from "./index.ts";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../..",
);
const fixturesDir = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../test-fixtures",
);
const python = process.env.PYTHON ?? "python";

async function runStartupFailureCase(
  setup: () => void,
  timeoutMs = 15_000,
): Promise<{ streaming: boolean; progress: string }> {
  process.env.RXYCODE_TRANSPORT = "stdio";
  process.env.RXYCODE_PROJECT_ROOT = repoRoot;
  process.env.RXYCODE_APPSERVER_INIT_TIMEOUT_MS = "500";
  process.env.RXYCODE_APPSERVER_SESSION_TIMEOUT_MS = "500";
  delete process.env.RXYCODE_APPSERVER_STUB;

  setup();

  const transport = getChatTransport();
  let streaming = false;
  let progress = "";

  await transport.sendChatMessage("你好", "build", {
    onMessages: () => {},
    onStreaming: (value) => {
      streaming = value;
    },
    onProgress: (text) => {
      progress = text;
    },
    onStatus: () => {},
  });

  await transport.shutdown?.();
  return { streaming, progress };
}

describe("stdio transport startup failures", () => {
  afterEach(() => {
    __resetStdioSessionForTests();
    resetChatTransportForTests();
    delete process.env.RXYCODE_TRANSPORT;
    delete process.env.RXYCODE_PROJECT_ROOT;
    delete process.env.RXYCODE_APPSERVER_PYTHON;
    delete process.env.RXYCODE_APPSERVER_INIT_TIMEOUT_MS;
    delete process.env.RXYCODE_APPSERVER_SESSION_TIMEOUT_MS;
  });

  test("invalid python executable does not stay Connecting", async () => {
    const result = await runStartupFailureCase(() => {
      process.env.RXYCODE_APPSERVER_PYTHON = "C:\\nonexistent\\rxycode-python.exe";
      __setPythonCmdForTests(null);
    });
    expect(result.streaming).toBe(false);
    expect(result.progress).toBe("");
  }, 20_000);

  test("appserver immediate exit does not stay Connecting", async () => {
    const result = await runStartupFailureCase(() => {
      __setPythonCmdForTests([python, "-c", "import sys; sys.exit(1)"]);
    });
    expect(result.streaming).toBe(false);
    expect(result.progress).toBe("");
  }, 20_000);

  test("initialize no response times out", async () => {
    const result = await runStartupFailureCase(() => {
      __setPythonCmdForTests([python, path.join(fixturesDir, "silent_appserver.py")]);
    });
    expect(result.streaming).toBe(false);
    expect(result.progress).toBe("");
  }, 20_000);

  test("session/new no response times out", async () => {
    const result = await runStartupFailureCase(() => {
      __setPythonCmdForTests([python, path.join(fixturesDir, "init_only_appserver.py")]);
    });
    expect(result.streaming).toBe(false);
    expect(result.progress).toBe("");
  }, 20_000);

  test("thought placeholder is pushed before ensureReady (FX7)", async () => {
    process.env.RXYCODE_TRANSPORT = "stdio";
    process.env.RXYCODE_PROJECT_ROOT = repoRoot;
    process.env.RXYCODE_APPSERVER_INIT_TIMEOUT_MS = "500";
    process.env.RXYCODE_APPSERVER_SESSION_TIMEOUT_MS = "500";
    __setPythonCmdForTests([python, "-c", "import sys; sys.exit(1)"]);

    const transport = getChatTransport();
    const rolesSeen: string[][] = [];
    await transport.sendChatMessage("你好", "build", {
      onMessages: (updater) => {
        rolesSeen.push(updater([]).map((m) => m.role));
      },
      onStreaming: () => {},
      onProgress: () => {},
      onStatus: () => {},
    });

    // Startup fails (worker exits), yet the assistant "…" row must already
    // have been pushed before ensureReady ever resolved/rejected — the
    // placeholder can only originate from the pre-ensureReady section.
    const thoughtAppeared = rolesSeen.some((roles) => roles.includes("thinking"));
    expect(thoughtAppeared).toBe(true);
    const settled = rolesSeen.some((roles) => {
      return roles.some((role) => role === "thinking");
    });
    expect(settled).toBe(true);

    await transport.shutdown?.();
  }, 20_000);
});
