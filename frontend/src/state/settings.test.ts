import { afterEach, describe, expect, it, vi } from "vitest";
import { createAppSettings, coerceAppSettings, toSettingsPayload } from "./settings";

const fetchMock = vi.fn();

function apiResponse(body: unknown, ok = true): Response {
  return {
    ok,
    status: ok ? 200 : 409,
    json: async () => body,
  } as unknown as Response;
}

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("app settings", () => {
  it("默认启用运行动画、关闭开发者模式", () => {
    expect(createAppSettings().runAnimation).toBe(true);
    expect(createAppSettings().developerEnabled).toBe(false);
    expect(coerceAppSettings(null).runAnimation).toBe(true);
    expect(coerceAppSettings(null).developerEnabled).toBe(false);
  });

  it("合并后端设置视图，字段缺失或非法回退默认", () => {
    expect(coerceAppSettings({ run_animation: false }).runAnimation).toBe(false);
    expect(coerceAppSettings({}).runAnimation).toBe(true);
    expect(coerceAppSettings({ run_animation: "yes" }).runAnimation).toBe(true);
    expect(coerceAppSettings({ developer: { enabled: true } }).developerEnabled).toBe(true);
    expect(coerceAppSettings({ developer: { enabled: "yes" } }).developerEnabled).toBe(false);
    expect(coerceAppSettings({ developer: null }).developerEnabled).toBe(false);
  });

  it("读取工作区数据目录（只读展示）", () => {
    expect(coerceAppSettings({ workspace: { data_dir: "lab-data" } }).workspaceDataDir).toBe(
      "lab-data",
    );
    expect(coerceAppSettings({ workspace: {} }).workspaceDataDir).toBeNull();
    expect(coerceAppSettings({ workspace: { data_dir: "" } }).workspaceDataDir).toBeNull();
    expect(createAppSettings().workspaceDataDir).toBeNull();
  });

  it("生成后端保存负载", () => {
    expect(
      toSettingsPayload({ runAnimation: false, developerEnabled: true, workspaceDataDir: null }),
    ).toEqual({ run_animation: false, developer_enabled: true });
  });

  it("loadAppSettingsFromApi 读取后端设置", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValueOnce(
      apiResponse({
        run_animation: false,
        developer: { enabled: true },
        workspace: { data_dir: "data" },
      }),
    );
    const { loadAppSettingsFromApi } = await import("./settings");

    const settings = await loadAppSettingsFromApi();

    expect(settings.runAnimation).toBe(false);
    expect(settings.developerEnabled).toBe(true);
    expect(settings.workspaceDataDir).toBe("data");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/settings");
    expect(init.method).toBeUndefined();
  });

  it("loadAppSettingsFromApi 失败时回退默认值", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValueOnce(apiResponse({ code: "workspace_not_initialized" }, false));
    const { loadAppSettingsFromApi } = await import("./settings");

    const settings = await loadAppSettingsFromApi();

    expect(settings.runAnimation).toBe(true);
    expect(settings.developerEnabled).toBe(false);
  });

  it("saveAppSettingsToApi 调用 PUT /settings", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValueOnce(apiResponse({ run_animation: false }));
    const { saveAppSettingsToApi } = await import("./settings");

    await saveAppSettingsToApi({
      runAnimation: false,
      developerEnabled: true,
      workspaceDataDir: null,
    });

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/settings");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(String(init.body))).toEqual({
      run_animation: false,
      developer_enabled: true,
    });
  });
});
