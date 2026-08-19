import { getRun as defaultGetRun } from "./client";
import type { RunStatusResponse } from "./client";

export interface PollRunOptions {
  intervalMs?: number;
  signal?: AbortSignal;
  getRun?: (runId: string) => Promise<RunStatusResponse>;
}

export const TERMINAL_RUN_STATES: ReadonlySet<string> = new Set([
  "completed",
  "partial",
  "failed",
  "cancelled",
]);

export function isRunTerminal(state: string): boolean {
  return TERMINAL_RUN_STATES.has(state);
}

/**
 * 轮询批次状态直到终态；每次拿到视图先回调，终态返回最后一次视图。
 */
export async function pollRun(
  runId: string,
  onView: (view: RunStatusResponse) => void,
  options: PollRunOptions = {},
): Promise<RunStatusResponse> {
  const intervalMs = options.intervalMs ?? 1000;
  const getRun = options.getRun ?? defaultGetRun;
  for (;;) {
    if (options.signal?.aborted) {
      throw new DOMException("轮询已取消", "AbortError");
    }
    const view = await getRun(runId);
    onView(view);
    if (isRunTerminal(view.state)) {
      return view;
    }
    await delay(intervalMs, options.signal);
  }
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(new DOMException("轮询已取消", "AbortError"));
      },
      { once: true },
    );
  });
}
