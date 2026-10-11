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

  it("瞬时网络错误按指数退避重试，成功后恢复正常节奏", async () => {
    vi.useFakeTimers();
    const getRun = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(view("running"))
      .mockResolvedValue(view("completed"));
    const sleep = vi.fn(async () => {});
    const finalView = await pollRun("run-1", vi.fn(), {
      intervalMs: 100,
      getRun,
      sleep,
    });
    expect(finalView.state).toBe("completed");
    expect(getRun).toHaveBeenCalledTimes(4);
    // 两次失败后退避 100*2 与 100*4；成功后恢复正常节奏 100。
    expect(sleep).toHaveBeenNthCalledWith(1, 200, undefined);
    expect(sleep).toHaveBeenNthCalledWith(2, 400, undefined);
    expect(sleep).toHaveBeenNthCalledWith(3, 100, undefined);
  });

  it("后端错误响应（ApiError）不重试直接抛出", async () => {
    vi.useFakeTimers();
    const apiError = Object.assign(new Error("HTTP 500"), { name: "ApiError" });
    const getRun = vi.fn().mockRejectedValue(apiError);
    await expect(
      pollRun("run-1", vi.fn(), { intervalMs: 100, getRun, sleep: async () => {} }),
    ).rejects.toBe(apiError);
    expect(getRun).toHaveBeenCalledTimes(1);
  });

  it("连续瞬时错误超过重试上限后放弃", async () => {
    vi.useFakeTimers();
    const getRun = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(
      pollRun("run-1", vi.fn(), {
        intervalMs: 100,
        maxRetries: 2,
        getRun,
        sleep: async () => {},
      }),
    ).rejects.toMatchObject({ name: "TypeError" });
    // 首次失败 + 2 次重试 = 3 次调用。
    expect(getRun).toHaveBeenCalledTimes(3);
  });
});
