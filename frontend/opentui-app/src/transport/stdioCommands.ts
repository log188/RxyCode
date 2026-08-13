import type { StatusInfo } from "../types.ts";

export type StdioAdminCommand =
  | { kind: "thinking" }
  | { kind: "model"; modelId: string }
  | { kind: "http"; command: string };

/** Stdio /model must keep the live worker; HTTP /command used to kill it. */
export function shouldRestartStdioSessionOnModelSwitch(): boolean {
  return false;
}

export function parseStdioAdminCommand(command: string): StdioAdminCommand {
  const trimmed = command.trim();
  if (trimmed === "/thinking") {
    return { kind: "thinking" };
  }
  const modelMatch = trimmed.match(/^\/model\s+(\S.*)$/);
  if (modelMatch) {
    return { kind: "model", modelId: modelMatch[1].trim() };
  }
  return { kind: "http", command: trimmed };
}

export type ModelsListPayload = {
  active?: string;
  recent?: string[];
  models?: Array<{
    id: string;
    name?: string;
    nickname?: string;
    active?: boolean;
  }>;
};

/** Header/status model from config, not from a lazily started HTTP agent. */
export function statusFromModelsList(
  listed: ModelsListPayload,
  previous?: StatusInfo | null,
): StatusInfo {
  const activeId =
    listed.active || listed.models?.find((item) => item.active)?.id || "";
  const item = listed.models?.find((entry) => entry.id === activeId);
  const model =
    item?.nickname || item?.name || activeId || previous?.model || "unknown";
  return { ...(previous ?? {}), model };
}
