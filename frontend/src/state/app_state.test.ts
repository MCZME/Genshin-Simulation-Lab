// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest";
import {
  createAppState,
  readLastWorkflowId,
  rememberLastWorkflowId,
  withCurrentWorkflow,
  withWorkspace,
} from "./app_state";

beforeEach(() => {
  const storage = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => {
        storage.set(key, value);
      },
      removeItem: (key: string) => {
        storage.delete(key);
      },
      clear: () => {
        storage.clear();
      },
    },
  });
});

describe("app state", () => {
  it("创建工作区状态并接收工作区信息", () => {
    const state = withWorkspace(createAppState(), {
      initialized: true,
      asset_db_version: "2026.08.17",
    });
    expect(state.workspaceInitialized).toBe(true);
    expect(state.assetDbVersion).toBe("2026.08.17");
  });

  it("记录当前工作流", () => {
    const state = withCurrentWorkflow(createAppState(), {
      id: "wf_a",
      name: "主配队",
    });
    expect(state.workflowId).toBe("wf_a");
    expect(state.workflowName).toBe("主配队");
  });

  it("记住并读取上次打开的工作流", () => {
    expect(readLastWorkflowId()).toBeNull();
    rememberLastWorkflowId("wf_a");
    expect(readLastWorkflowId()).toBe("wf_a");
    rememberLastWorkflowId(null);
    expect(readLastWorkflowId()).toBeNull();
  });
});
