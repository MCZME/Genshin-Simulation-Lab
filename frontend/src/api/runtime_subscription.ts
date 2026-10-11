import { getRun as defaultGetRun } from "./client";
import type { RunStatusResponse } from "./client";

export interface PollRunOptions {
  intervalMs?: number;
  /** 瞬时错误（网络层失败）连续重试上限；超过后放弃并抛出最后一次错误。 */
  maxRetries?: number;
  /** 退避间隔上限（ms）。 */
  maxIntervalMs?: number;
  signal?: AbortSignal;
  getRun?: (runId: string) => Promise<RunStatusResponse>;
  /** 注入睡眠便于测试；默认 setTimeout，可被 signal 中断。 */
  sleep?: (ms: number, signal?: AbortSignal) => Promise<void>;
}

export const TERMINAL_RUN_STATES: ReadonlySet<string> = new Set([
  "completed",
  "partial",
  "failed",
  "cancelled",
]);

export const DEFAULT_POLL_INTERVAL_MS = 1000;
export const DEFAULT_POLL_MAX_INTERVAL_MS = 8000;
export const DEFAULT_POLL_MAX_RETRIES = 5;

export function isRunTerminal(state: string): boolean {
  return TERMINAL_RUN_STATES.has(state);
}

function abortError(): DOMException {
  return new DOMException("轮询已取消", "AbortError");
}

function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(abortError());
      },
      { once: true },
    );
  });
}

function isAbort(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

/**
 * 后端已返回错误响应（ApiError）说明传输层通畅且批次状态可查，
 * 重试没有意义；只有 fetch 层失败（断网、超时断开）才按瞬时错误重试。
 */
function isTransient(error: unknown): boolean {
  return !(error instanceof Error && error.name === "ApiError");
}

/**
 * 轮询批次状态直到终态；每次拿到视图先回调，终态返回最后一次视图。
 * 瞬时错误按指数退避重试（成功后恢复正常节奏），取消信号立即终止。
 */
export async function pollRun(
  runId: string,
  onView: (view: RunStatusResponse) => void,
  options: PollRunOptions = {},
): Promise<RunStatusResponse> {
  const intervalMs = options.intervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const maxIntervalMs = options.maxIntervalMs ?? DEFAULT_POLL_MAX_INTERVAL_MS;
  const maxRetries = options.maxRetries ?? DEFAULT_POLL_MAX_RETRIES;
  const sleep = options.sleep ?? delay;
  const getRun = options.getRun ?? defaultGetRun;
  let consecutiveFailures = 0;
  for (;;) {
    if (options.signal?.aborted) {
      throw abortError();
    }
    try {
      const view = await getRun(runId);
      onView(view);
      consecutiveFailures = 0;
      if (isRunTerminal(view.state)) {
        return view;
      }
      await sleep(intervalMs, options.signal);
    } catch (error) {
      if (isAbort(error) || !isTransient(error) || consecutiveFailures >= maxRetries) {
        throw error;
      }
      consecutiveFailures += 1;
      await sleep(
        Math.min(intervalMs * 2 ** consecutiveFailures, maxIntervalMs),
        options.signal,
      );
    }
  }
}
