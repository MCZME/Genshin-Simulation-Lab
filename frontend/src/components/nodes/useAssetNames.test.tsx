// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AssetListResponse } from "../../api/client";
import { useAssetNames } from "./useAssetNames";

const resolveAssetsMock = vi.hoisted(() => vi.fn());

vi.mock("../../api/client", () => ({
  resolveAssets: resolveAssetsMock,
}));

function deferredResponse(): {
  promise: Promise<AssetListResponse>;
  resolve: (value: AssetListResponse) => void;
} {
  let resolve!: (value: AssetListResponse) => void;
  const promise = new Promise<AssetListResponse>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

afterEach(() => {
  cleanup();
  resolveAssetsMock.mockReset();
});

describe("useAssetNames", () => {
  it("并发挂载时把后出现的缺失键并入队列，当前请求结束后续发", async () => {
    const calls: {
      keys: string[];
      resolve: (value: AssetListResponse) => void;
    }[] = [];
    resolveAssetsMock.mockImplementation((keys: string[]) => {
      const deferred = deferredResponse();
      calls.push({ keys: [...keys], resolve: deferred.resolve });
      return deferred.promise;
    });

    const first = renderHook(() => useAssetNames(["asset:a"]));
    expect(calls).toHaveLength(1);
    expect(calls[0].keys).toEqual(["asset:a"]);

    const second = renderHook(() => useAssetNames(["asset:b"]));
    // 第二个键在首个请求在途时不应被跳过，也不应立即发起独立请求。
    expect(calls).toHaveLength(1);

    await act(async () => {
      calls[0].resolve({
        items: [{ asset_key: "asset:a", name: "甲", source_id: "a", usable: true }],
      });
    });

    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1].keys).toEqual(["asset:b"]);
    expect(first.result.current.get("asset:a")).toBe("甲");

    await act(async () => {
      calls[1].resolve({
        items: [{ asset_key: "asset:b", name: "乙", source_id: "b", usable: true }],
      });
    });

    await waitFor(() => {
      expect(first.result.current.get("asset:a")).toBe("甲");
      expect(second.result.current.get("asset:b")).toBe("乙");
    });
  });
});
