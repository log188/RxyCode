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
    context_window?: number | null;
  }>;
};

export type TokenUsagePayload = {
  input_tokens?: number | null;
  output_tokens?: number | null;
  cache_hit_tokens?: number | null;
  cache_hit_rate?: number | null;
  reporting_status?: string | null;
};

function asFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
}

function formatCacheSize(tokens: number): string {
  if (tokens <= 0) return "0B";
  if (tokens < 1000) return String(Math.round(tokens));
  if (tokens < 1_000_000) return `${(tokens / 1000).toFixed(1)}K`;
  return `${(tokens / 1_000_000).toFixed(2)}M`;
}

/** Map a protocol usage payload onto the OpenTUI status bar fields. */
export function applyTokenUsageToStatus(
  previous: StatusInfo | null | undefined,
  usage: TokenUsagePayload,
): StatusInfo {
  const base = { ...(previous ?? {}) };
  if (usage.reporting_status === "not_reported") {
    return base;
  }
  const input = asFiniteNumber(usage.input_tokens);
  const output = asFiniteNumber(usage.output_tokens);
  const cacheHit = asFiniteNumber(usage.cache_hit_tokens);
  const cacheRate = asFiniteNumber(usage.cache_hit_rate);
  if (input == null && output == null && cacheHit == null && cacheRate == null) {
    return base;
  }
  const used = (input ?? 0) + (output ?? 0);
  return {
    ...base,
    input_tokens: input ?? base.input_tokens,
    output_tokens: output ?? base.output_tokens,
    context_used_k: used > 0 ? Math.round(used / 100) / 10 : (base.context_used_k ?? 0),
    cache_size: cacheHit != null ? formatCacheSize(cacheHit) : (base.cache_size ?? "0B"),
    cache_rate:
      cacheRate != null ? `${cacheRate.toFixed(1)}%` : (base.cache_rate ?? "0.0%"),
  };
}

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
  const window = item?.context_window;
  const contextMaxK =
    typeof window === "number" && window > 0
      ? Math.round(window / 1000)
      : previous?.context_max_k;
  return {
    ...(previous ?? {}),
    model,
    ...(contextMaxK != null ? { context_max_k: contextMaxK } : {}),
  };
}
