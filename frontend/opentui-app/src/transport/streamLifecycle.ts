/** Pure helpers for when the TUI should leave the Processing state. */

/** Clear Processing as soon as the turn's terminal stream event arrives. */
export function shouldClearStreamingOnNotify(method: string): boolean {
  return (
    method === "event/final" ||
    method === "event/done" ||
    method === "event/error"
  );
}

/** Esc/Ctrl+C must leave Processing immediately, not after session/prompt returns. */
export function shouldClearStreamingOnUserCancel(): boolean {
  return true;
}

export function abortError(): Error {
  const err = new Error("Aborted");
  err.name = "AbortError";
  return err;
}

/** Stop waiting for session/prompt as soon as Esc aborts; do not wait for worker teardown. */
export function raceWithAbort<T>(
  request: Promise<T>,
  ...signals: Array<AbortSignal | undefined>
): Promise<T> {
  const active = signals.filter((signal): signal is AbortSignal => Boolean(signal));
  if (active.some((signal) => signal.aborted)) {
    return Promise.reject(abortError());
  }
  if (active.length === 0) return request;
  return new Promise<T>((resolve, reject) => {
    const onAbort = () => reject(abortError());
    for (const signal of active) {
      signal.addEventListener("abort", onAbort, { once: true });
    }
    const clear = () => {
      for (const signal of active) {
        signal.removeEventListener("abort", onAbort);
      }
    };
    request.then(
      (value) => {
        clear();
        resolve(value);
      },
      (err) => {
        clear();
        reject(err);
      },
    );
  });
}
