export type PerformanceStage =
  | 'send_click'
  | 'rpc_sent'
  | 'rpc_received'
  | 'worker_bootstrap'
  | 'model_request'
  | 'first_token'
  | 'tool_begin'
  | 'recovery'
  | 'final'
  | 'renderer_paint'

export interface PerformanceTraceSnapshot {
  sessionId: string | null
  marks: Partial<Record<PerformanceStage, number>>
  durations: Partial<Record<PerformanceStage, number>>
}

export interface PerformanceTraceRegistrySnapshot {
  activeSessionId: string | null
  sessions: Record<string, PerformanceTraceSnapshot>
}

export interface PerformanceClock {
  now(): number
}

const DEFAULT_CLOCK: PerformanceClock = {
  now: () => typeof performance === 'undefined' ? Date.now() : performance.now()
}

export class PerformanceTrace {
  private readonly clock: PerformanceClock
  private sessionId: string | null = null
  private startedAt: number | null = null
  private marks: Partial<Record<PerformanceStage, number>> = {}

  constructor(clock: PerformanceClock = DEFAULT_CLOCK) {
    this.clock = clock
  }

  startRun(sessionId: string): void {
    this.sessionId = sessionId
    this.startedAt = this.clock.now()
    this.marks = {}
  }

  mark(stage: PerformanceStage, at = this.clock.now()): void {
    if (this.startedAt === null) this.startedAt = at
    if (this.marks[stage] === undefined) this.marks[stage] = at
  }

  snapshot(): PerformanceTraceSnapshot {
    const durations: Partial<Record<PerformanceStage, number>> = {}
    if (this.startedAt !== null) {
      for (const [stage, at] of Object.entries(this.marks) as Array<[PerformanceStage, number]>) {
        durations[stage] = Math.max(0, at - this.startedAt)
      }
    }
    return {
      sessionId: this.sessionId,
      marks: { ...this.marks },
      durations
    }
  }
}

export class PerformanceTraceRegistry {
  private readonly clock: PerformanceClock
  private readonly traces = new Map<string, PerformanceTrace>()
  private activeSessionId: string | null = null

  constructor(clock: PerformanceClock = DEFAULT_CLOCK) {
    this.clock = clock
  }

  startRun(sessionId: string): void {
    let trace = this.traces.get(sessionId)
    if (trace === undefined) {
      trace = new PerformanceTrace(this.clock)
      this.traces.set(sessionId, trace)
    }
    trace.startRun(sessionId)
    this.activeSessionId = sessionId
  }

  mark(sessionId: string, stage: PerformanceStage): void {
    const trace = this.traces.get(sessionId)
    if (trace !== undefined) trace.mark(stage)
  }

  snapshot(): PerformanceTraceRegistrySnapshot {
    return {
      activeSessionId: this.activeSessionId,
      sessions: Object.fromEntries(
        [...this.traces.entries()].map(([sessionId, trace]) => [sessionId, trace.snapshot()])
      )
    }
  }
}

export function publishPerformanceTrace(snapshot: PerformanceTraceRegistrySnapshot): void {
  if (typeof window === 'undefined') return
  ;(window as Window & { __rxyDesktopPerformance?: PerformanceTraceRegistrySnapshot }).__rxyDesktopPerformance = snapshot
}
