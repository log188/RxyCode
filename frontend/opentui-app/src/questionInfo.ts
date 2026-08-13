export interface QuestionOption {
  label: string;
  value: string;
}

export interface QuestionInfo {
  questionId: string;
  question: string;
  header: string;
  options: QuestionOption[];
  inputType: "choice" | "text";
}

export interface QuestionReply {
  answer?: string;
  cancelled?: boolean;
  timedOut?: boolean;
}

export interface QuestionResult {
  question_id: string;
  answer: string | null;
  cancelled: boolean;
  timed_out: boolean;
}

function asOption(raw: unknown): QuestionOption | null {
  if (!raw || typeof raw !== "object") return null;
  const row = raw as Record<string, unknown>;
  const value = String(row.value ?? row.label ?? "");
  const label = String(row.label ?? value);
  if (!value && !label) return null;
  return { label: label || value, value: value || label };
}

export function questionInfoFromParams(
  params: Record<string, unknown>,
): QuestionInfo {
  const options = Array.isArray(params.options)
    ? params.options.map(asOption).filter((row): row is QuestionOption => row !== null)
    : [];
  const inputType = options.length > 0 ? "choice" : "text";
  return {
    questionId: String(params.question_id ?? ""),
    question: String(params.question ?? ""),
    header: String(params.header ?? ""),
    options,
    inputType: params.input_type === "choice" || params.input_type === "text"
      ? params.input_type
      : inputType,
  };
}

export function questionResultFromReply(
  questionId: string,
  reply: QuestionReply,
): QuestionResult {
  const cancelled = Boolean(reply.cancelled);
  const timedOut = Boolean(reply.timedOut);
  return {
    question_id: questionId,
    answer: cancelled || timedOut ? null : (reply.answer ?? null),
    cancelled,
    timed_out: timedOut,
  };
}

export function summarizeQuestionToolArgs(
  args: string | Record<string, unknown> | undefined,
): string {
  let parsed: Record<string, unknown> | null = null;
  if (typeof args === "string") {
    const trimmed = args.trim();
    if (!trimmed) return "";
    try {
      parsed = JSON.parse(trimmed) as Record<string, unknown>;
    } catch {
      return args;
    }
  } else if (args && typeof args === "object") {
    parsed = args;
  }
  if (!parsed) return "";
  const questions = Array.isArray(parsed.questions) ? parsed.questions : [];
  const first = questions[0];
  if (first && typeof first === "object") {
    const row = first as Record<string, unknown>;
    const text = String(row.question ?? "");
    const header = String(row.header ?? "");
    if (header && text) return `${header}: ${text}`;
    return text || header;
  }
  if (typeof parsed.question === "string" && parsed.question) {
    return parsed.question;
  }
  return typeof args === "string" ? args : JSON.stringify(parsed);
}
