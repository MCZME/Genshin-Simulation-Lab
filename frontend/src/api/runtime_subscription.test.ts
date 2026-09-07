import { afterEach, describe, expect, it, vi } from "vitest";
import type { RunStatusResponse } from "./client";
import { isRunTerminal, pollRun } from "./runtime_subscription";

function view(state: string): RunStatusResponse {
  return {
    run_id: "run-1",
    name: "批次",
    state,
    concurrency: 1,
    cancel_requested: false,
    member_count: 0,
    members: [],
  } as RunStatusResponse;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("runtime subscription", () => {
  it("识别终态", () => {
    expect(isRunTerminal("completed")).toBe(true);
    expect(isRunTerminal("running")).toBe(false);
  });

  it("轮询直到终态并回调每次视图", async () => {
    vi.useFakeTimers();
    const getRun = vi
      .fn()
      .mockResolvedValueOnce(view("running"))
      .mockResolvedValueOnce(view("running"))
      .mockResolvedValueOnce(view("completed"));
    const onView = vi.fn();

    const promise = pollRun("run-1", onView, { intervalMs: 100, getRun });
    await vi.advanceTimersByTimeAsync(0);
    expect(onView).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(100);
    expect(onView).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(100);

    const finalView = await promise;
    expect(finalView.state).toBe("completed");
    expect(onView).toHaveBeenCalledTimes(3);
  });

  it("取消信号终止轮询", async () => {
    vi.useFakeTimers();
    const controller = new AbortController();
    const getRun = vi.fn().mockResolvedValue(view("running"));
    const promise = pollRun("run-1", vi.fn(), {
      intervalMs: 100,
      getRun,
      signal: controller.signal,
    });
    await vi.advanceTimersByTimeAsync(0);
    controller.abort();
    await expect(promise).rejects.toMatchObject({ name: "AbortError" });
  });
});
