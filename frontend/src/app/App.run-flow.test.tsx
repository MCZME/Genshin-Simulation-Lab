// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { RunStatusResponse } from "../api/client";
import { App } from "./App";

const { oneRegionDefinition, twoRegionDefinition, conflictDefinition } = vi.hoisted(() => {
  const region = (id: string) => ({
    id,
    kind: "configuration",
    name: `区域${id}`,
    rect: { x: 0, y: 0, width: 800, height: 600 },
  });
  const node = (
    id: string,
    kind: string,
    params: Record<string, unknown> = {},
    regionId: string | null = "region-1",
  ) => ({ id, kind, region_id: regionId, position: { x: 0, y: 0 }, params });
  const edge = (
    id: string,
    source: string,
    sourcePort: string,
    target: string,
    targetPort: string,
  ) => ({
    id,
    source_node_id: source,
    source_port_id: sourcePort,
    target_node_id: target,
    target_port_id: targetPort,
  });
  const definition = (
    regionIds: string[],
    simulationIds: string[],
  ) => {
    const nodes = [];
    const edges = [];
    for (const regionId of regionIds) {
      nodes.push(
        node(`${regionId}-root`, "root", {}, regionId),
        node(`${regionId}-char`, "character", { slot: 1, asset: "character:barbara" }, regionId),
        node(`${regionId}-target`, "target", { index: 0, level: 90 }, regionId),
      );
      edges.push(
        edge(`${regionId}-e1`, `${regionId}-root`, "out", regionId, "out"),
        edge(`${regionId}-e2`, `${regionId}-char`, "out", regionId, "out"),
        edge(`${regionId}-e3`, `${regionId}-target`, "out", regionId, "out"),
      );
    }
    for (const [index, simulationId] of simulationIds.entries()) {
      nodes.push(node(simulationId, "simulation", {}, null));
      edges.push(edge(`sim-${index}`, regionIds[index], "out", simulationId, "in"));
    }
    return {
      schema_version: 1,
      meta: { name: "测试工作流" },
      regions: regionIds.map(region),
      nodes,
      edges,
      layout: {},
    };
  };
  const conflictDefinition = {
    schema_version: 1,
    meta: { name: "测试工作流" },
    regions: [region("region-1")],
    nodes: [
      node("region-1-root", "root", {}, "region-1"),
      node("w1", "weapon", { slot: 1, asset: "weapon:a" }, "region-1"),
      node("w2", "weapon", { slot: 1, asset: "weapon:b" }, "region-1"),
      node("sim-1", "simulation", {}, null),
    ],
    edges: [
      edge("c1", "region-1-root", "out", "region-1", "out"),
      edge("c2", "w1", "out", "region-1", "out"),
      edge("c3", "w2", "out", "region-1", "out"),
      edge("c4", "region-1", "out", "sim-1", "in"),
    ],
    layout: {},
  };
  return {
    oneRegionDefinition: definition(["region-1"], ["sim-1"]),
    twoRegionDefinition: definition(["region-1", "region-2"], ["sim-1", "sim-2"]),
    conflictDefinition,
  };
});

const mocks = vi.hoisted(() => ({
  getWorkspace: vi.fn(),
  listWorkflows: vi.fn(),
  getWorkflow: vi.fn(),
  createWorkflow: vi.fn(),
  deleteWorkflow: vi.fn(),
  saveWorkflow: vi.fn(),
  searchAssets: vi.fn(),
  getAsset: vi.fn(),
  validateInputs: vi.fn(),
  submitRun: vi.fn(),
  getRun: vi.fn(),
  cancelRun: vi.fn(),
  pollRun: vi.fn(),
}));

vi.mock("../api/client", () => ({
  getWorkspace: mocks.getWorkspace,
  listWorkflows: mocks.listWorkflows,
  getWorkflow: mocks.getWorkflow,
  createWorkflow: mocks.createWorkflow,
  deleteWorkflow: mocks.deleteWorkflow,
  saveWorkflow: mocks.saveWorkflow,
  searchAssets: mocks.searchAssets,
  getAsset: mocks.getAsset,
  validateInputs: mocks.validateInputs,
  submitRun: mocks.submitRun,
  getRun: mocks.getRun,
  cancelRun: mocks.cancelRun,
}));

vi.mock("../api/runtime_subscription", () => ({
  isRunTerminal: (state: string) =>
    ["completed", "partial", "failed", "cancelled"].includes(state),
  pollRun: mocks.pollRun,
}));

vi.mock("../state/settings", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../state/settings")>();
  return {
    ...actual,
    loadAppSettingsFromApi: vi.fn(async () => ({
      ...actual.createAppSettings(),
      runAnimation: false,
    })),
  };
});

vi.mock("../components/panels/ResultsPanel", () => ({
  ResultsPanel: () => null,
}));

vi.mock("@xyflow/react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@xyflow/react")>();
  return {
    ...actual,
    Handle: () => null,
    useReactFlow: () => ({
      screenToFlowPosition: () => ({ x: 0, y: 0 }),
    }),
    useStore: (selector: (state: unknown) => unknown) =>
      selector({ connection: { inProgress: false } }),
  };
});

function runView(
  state: RunStatusResponse["state"],
  memberState: RunStatusResponse["members"][number]["state"],
  sessionId: string | null,
): RunStatusResponse {
  return {
    run_id: `run-${state}`,
    name: "测试工作流",
    state,
    concurrency: 1,
    cancel_requested: false,
    member_count: 1,
    members: [
      {
        item_id: "root",
        state: memberState,
        session_id: sessionId,
        created_at: "",
      },
    ],
  };
}

function validationFailure(itemId: string) {
  return {
    ok: false,
    members: [
      {
        item_id: itemId,
        ok: false,
        details: [{ severity: "error", code: "ASSET_NOT_FOUND", message: "资产不存在" }],
      },
    ],
  };
}

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  mocks.getWorkspace.mockResolvedValue({
    initialized: true,
    asset_db_version: "0",
    name: "测试工作区",
  });
  mocks.listWorkflows.mockResolvedValue({
    items: [{ id: "wf-1", name: "测试工作流", updated_at: "" }],
  });
  mocks.getWorkflow.mockResolvedValue({
    id: "wf-1",
    name: "测试工作流",
    updated_at: "",
    definition: oneRegionDefinition,
  });
  mocks.searchAssets.mockImplementation(async (assetType: string, sourceId: string) => {
    const prefix =
      assetType === "characters"
        ? "character"
        : assetType === "weapons"
          ? "weapon"
          : "artifact-set";
    return {
      items: [{ asset_key: `${prefix}:${sourceId}` }],
    };
  });
  mocks.getAsset.mockResolvedValue(null);
  mocks.validateInputs.mockReset();
  mocks.submitRun.mockReset();
  mocks.pollRun.mockReset();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App 运行编排", () => {
  it("区域运行：校验失败该批标记失败并展示成员级聚合诊断", async () => {
    mocks.validateInputs.mockResolvedValue(validationFailure("root"));
    render(<App />);

    const regionRunButton = await screen.findByRole("button", { name: "区域运行" });
    expect((regionRunButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(regionRunButton);

    expect(await screen.findByText(/区域校验未通过（1 个成员）/)).not.toBeNull();
    expect(screen.getAllByText("失败").length).toBeGreaterThan(0);
    expect(screen.getByText("资产不存在")).not.toBeNull();
    expect(mocks.validateInputs).toHaveBeenCalledTimes(1);
    expect(mocks.submitRun).not.toHaveBeenCalled();
  });

  it("区域校验：校验通过后不提交模拟", async () => {
    mocks.validateInputs.mockResolvedValue({
      ok: true,
      members: [{ item_id: "root", ok: true }],
    });
    render(<App />);

    const validateButton = await screen.findByRole("button", { name: "区域校验" });
    fireEvent.click(validateButton);

    await waitFor(() => expect(mocks.validateInputs).toHaveBeenCalledTimes(1));
    expect(await screen.findByText("校验通过")).not.toBeNull();
    expect(mocks.submitRun).not.toHaveBeenCalled();
  });

  it("区域校验：校验失败标记失败且不提交模拟", async () => {
    mocks.validateInputs.mockResolvedValue(validationFailure("root"));
    render(<App />);

    const validateButton = await screen.findByRole("button", { name: "区域校验" });
    fireEvent.click(validateButton);

    expect(await screen.findByText(/区域校验未通过（1 个成员）/)).not.toBeNull();
    expect(screen.getAllByText("失败").length).toBeGreaterThan(0);
    expect(screen.getByText("资产不存在")).not.toBeNull();
    expect(mocks.submitRun).not.toHaveBeenCalled();
  });

  it("构建阶段校验失败进问题面板且不显示顶部横幅", async () => {
    mocks.getWorkflow.mockResolvedValue({
      id: "wf-1",
      name: "测试工作流",
      updated_at: "",
      definition: conflictDefinition,
    });
    render(<App />);

    const runButton = await screen.findByRole("button", { name: "全部运行" });
    await waitFor(() => expect((runButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(runButton);

    expect((await screen.findAllByText("TEAM_SLOT_CONFLICT")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("队伍槽位 1 被多个武器节点占用").length).toBeGreaterThan(0);
    expect(screen.queryByText(/构建失败/)).toBeNull();
    expect(mocks.submitRun).not.toHaveBeenCalled();
  });

  it("全部运行：某区域校验失败不影响后续批次照跑", async () => {
    mocks.getWorkflow.mockResolvedValue({
      id: "wf-1",
      name: "测试工作流",
      updated_at: "",
      definition: twoRegionDefinition,
    });
    mocks.validateInputs
      .mockResolvedValueOnce(validationFailure("root"))
      .mockResolvedValueOnce({ ok: true, members: [{ item_id: "root", ok: true }] });
    mocks.submitRun.mockResolvedValue(runView("queued", "queued", null));
    mocks.pollRun.mockResolvedValue(runView("completed", "completed", "s-2"));
    render(<App />);

    const runButton = await screen.findByRole("button", { name: "全部运行" });
    await waitFor(() => expect((runButton as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(runButton);

    await waitFor(() => expect(mocks.validateInputs).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(mocks.submitRun).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getAllByText("成功").length).toBeGreaterThan(0));
    expect(screen.getAllByText("失败").length).toBeGreaterThan(0);
  });

  it("区域运行：其他区域的失效资产不阻断目标区域运行", async () => {
    const definitionWithMissingElsewhere = structuredClone(twoRegionDefinition);
    const missingNode = definitionWithMissingElsewhere.nodes.find(
      (item) => item.id === "region-2-char",
    );
    if (missingNode === undefined) {
      throw new Error("测试定义缺少 region-2-char 节点");
    }
    missingNode.params.asset = "character:missing";
    mocks.getWorkflow.mockResolvedValue({
      id: "wf-1",
      name: "测试工作流",
      updated_at: "",
      definition: definitionWithMissingElsewhere,
    });
  mocks.searchAssets.mockImplementation(async (assetType: string, sourceId: string) => {
    const prefix =
      assetType === "characters"
        ? "character"
        : assetType === "weapons"
          ? "weapon"
          : "artifact-set";
    return {
      items: sourceId === "missing" ? [] : [{ asset_key: `${prefix}:${sourceId}` }],
    };
  });
    mocks.validateInputs.mockResolvedValue({
      ok: true,
      members: [{ item_id: "root", ok: true }],
    });
    mocks.submitRun.mockResolvedValue(runView("queued", "queued", null));
    mocks.pollRun.mockResolvedValue(runView("completed", "completed", "s-1"));
    render(<App />);

    const regionButtons = await screen.findAllByRole("button", { name: "区域运行" });
    expect(regionButtons).toHaveLength(2);
    fireEvent.click(regionButtons[0]);

    await waitFor(() => expect(mocks.validateInputs).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mocks.submitRun).toHaveBeenCalledTimes(1));
    expect(screen.getAllByText("成功").length).toBeGreaterThan(0);
    const problemsButton = screen.getByRole("button", { name: /问题/ });
    expect(problemsButton.textContent).toContain("1");
  });
});
