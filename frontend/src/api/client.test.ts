import { afterEach, describe, expect, it, vi } from "vitest";
import {
  deleteWorkflow,
  getWorkspace,
  saveWorkflow,
  submitRun,
  validateInputs,
} from "./client";

function stubFetch(response: {
  ok: boolean;
  status: number;
  body: unknown;
}): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: response.ok,
    status: response.status,
    json: async () => response.body,
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("api client", () => {
  it("读取工作区信息", async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 200,
      body: { initialized: true, asset_db_version: "v1", name: "Lab" },
    });
    const workspace = await getWorkspace();
    expect(workspace.asset_db_version).toBe("v1");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/workspace",
      expect.objectContaining({ headers: { "Content-Type": "application/json" } }),
    );
  });

  it("保存工作流", async () => {
    stubFetch({
      ok: true,
      status: 200,
      body: { id: "wf_1", name: "示例", updated_at: "t", definition: {} },
    });
    const detail = await saveWorkflow("wf_1", { schema_version: 1 });
    expect(detail.id).toBe("wf_1");
  });

  it("校验输入并返回响应", async () => {
    stubFetch({
      ok: true,
      status: 200,
      body: { ok: true, members: [{ item_id: "a", ok: true, details: [] }] },
    });
    const result = await validateInputs([{ item_id: "a", input: {} }]);
    expect(result.ok).toBe(true);
  });

  it("提交批次", async () => {
    const fetchMock = stubFetch({
      ok: true,
      status: 202,
      body: { run_id: "run_1", state: "queued", members: [] },
    });
    await submitRun([{ item_id: "a", input: {} }], { name: "批次", concurrency: 2 });
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      name: "批次",
      concurrency: 2,
      members: [{ item_id: "a", input: {} }],
    });
  });

  it("错误响应映射为 ApiError", async () => {
    stubFetch({
      ok: false,
      status: 400,
      body: { code: "validation_failed", message: "输入无效", details: [{ path: "team" }] },
    });
    await expect(validateInputs([{ item_id: "a", input: {} }])).rejects.toMatchObject({
      name: "ApiError",
      code: "validation_failed",
      status: 400,
      details: [{ path: "team" }],
    });
  });

  it("204 删除返回 undefined", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => {
        throw new Error("no body");
      },
    });
    vi.stubGlobal("fetch", fetchMock);
    await expect(deleteWorkflow("wf_1")).resolves.toBeUndefined();
  });
});
