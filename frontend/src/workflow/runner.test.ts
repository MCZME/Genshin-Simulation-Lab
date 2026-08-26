import { describe, expect, it } from "vitest";
import type {
  Diagnostic,
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowRegion,
} from "./types";
import {
  hasRunnableBatch,
  paceBuildSteps,
  planAnalysisInputRun,
  planRegionRun,
  planWorkflowRun,
  scopedDiagnostics,
  validationErrorMessage,
} from "./runner";

function makeRegion(id: string): WorkflowRegion {
  return { id, kind: "configuration", name: `区域${id}`, rect: { x: 0, y: 0, width: 800, height: 600 } };
}

function makeAnalysisRegion(id: string): WorkflowRegion {
  return { id, kind: "analysis", name: `分析区域${id}`, rect: { x: 0, y: 0, width: 800, height: 600 } };
}

function makeNode(
  id: string,
  kind: string,
  params: Record<string, unknown> = {},
  regionId: string | null = "region-1",
): WorkflowNode {
  return { id, kind, region_id: regionId, position: { x: 0, y: 0 }, params };
}

function makeEdge(
  id: string,
  source: string,
  sourcePort: string,
  target: string,
  targetPort: string,
): WorkflowEdge {
  return {
    id,
    source_node_id: source,
    source_port_id: sourcePort,
    target_node_id: target,
    target_port_id: targetPort,
  };
}

function makeDefinition(
  regions: WorkflowRegion[],
  nodes: WorkflowNode[],
  edges: WorkflowEdge[],
): WorkflowDefinition {
  return { schema_version: 1, meta: { name: "测试工作流" }, regions, nodes, edges, layout: {} };
}

/** root + meta(name) 汇入区域边界，产出 1 个成员。 */
function simpleRegionNodes(regionId: string, metaName: string): WorkflowNode[] {
  return [
    makeNode(`${regionId}-root`, "root", {}, regionId),
    makeNode(`${regionId}-meta`, "meta", { name: metaName, description: "" }, regionId),
  ];
}

function regionBoundaryEdges(regionId: string): WorkflowEdge[] {
  return [
    makeEdge(`${regionId}-b1`, `${regionId}-root`, "out", regionId, "out"),
    makeEdge(`${regionId}-b2`, `${regionId}-meta`, "out", regionId, "out"),
  ];
}

describe("planWorkflowRun", () => {
  it("一个模拟节点对应一个批次，批次名取区域元信息名称", () => {
    const definition = makeDefinition(
      [makeRegion("region-1")],
      [
        ...simpleRegionNodes("region-1", "主配队"),
        makeNode("sim-1", "simulation", {}, null),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
      ],
    );
    const plan = planWorkflowRun(definition);
    expect(plan.ok).toBe(true);
    expect(plan.batches).toHaveLength(1);
    expect(plan.batches[0].nodeId).toBe("sim-1");
    expect(plan.batches[0].name).toBe("主配队");
    expect(plan.batches[0].members).toHaveLength(1);
    expect(plan.batches[0].concurrency).toBeNull();
    expect(plan.participating).toHaveLength(1);
    expect(plan.participating[0].methods.map((method) => method.nodeId)).toEqual([
      "region-1-root",
      "region-1-meta",
    ]);
    expect(plan.skippedRegionIds).toEqual([]);
  });

  it("多个区域连同一模拟节点时按连线顺序合并成一批", () => {
    const definition = makeDefinition(
      [makeRegion("region-1"), makeRegion("region-2")],
      [
        ...simpleRegionNodes("region-1", "区域一"),
        ...simpleRegionNodes("region-2", "区域二"),
        makeNode("sim-1", "simulation", {}, null),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        ...regionBoundaryEdges("region-2"),
        makeEdge("l1", "region-2", "out", "sim-1", "in"),
        makeEdge("l2", "region-1", "out", "sim-1", "in"),
      ],
    );
    const plan = planWorkflowRun(definition);
    expect(plan.ok).toBe(true);
    expect(plan.batches).toHaveLength(1);
    // 连线顺序：l1 在前，区域二先行汇入。
    expect(plan.batches[0].sourceRegionIds).toEqual(["region-2", "region-1"]);
    expect(plan.batches[0].members).toHaveLength(2);
    // 批次名取所连第一个区域的元信息名称。
    expect(plan.batches[0].name).toBe("区域二");
  });

  it("未连接模拟节点的配置区域被跳过，不参与任何批次", () => {
    const definition = makeDefinition(
      [makeRegion("region-1"), makeRegion("region-2")],
      [
        ...simpleRegionNodes("region-1", "区域一"),
        ...simpleRegionNodes("region-2", "区域二"),
        makeNode("sim-1", "simulation", {}, null),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        ...regionBoundaryEdges("region-2"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
      ],
    );
    const plan = planWorkflowRun(definition);
    expect(plan.ok).toBe(true);
    expect(plan.skippedRegionIds).toEqual(["region-2"]);
    expect(plan.batches[0].members).toHaveLength(1);
  });

  it("模拟节点未连接配置区域时报构建错误", () => {
    const definition = makeDefinition(
      [makeRegion("region-1")],
      [...simpleRegionNodes("region-1", "区域一"), makeNode("sim-1", "simulation", {}, null)],
      regionBoundaryEdges("region-1"),
    );
    const plan = planWorkflowRun(definition);
    expect(plan.ok).toBe(false);
    expect(plan.errors).toHaveLength(1);
    expect(plan.errors[0]).toContain("批次无法成立");
  });

  it("同一批次内 item_id 重复时报构建错误（root 兜底碰撞）", () => {
    const definition = makeDefinition(
      [makeRegion("region-1"), makeRegion("region-2")],
      [
        makeNode("r1-root", "root", {}, "region-1"),
        makeNode("r2-root", "root", {}, "region-2"),
        makeNode("sim-1", "simulation", {}, null),
      ],
      [
        makeEdge("b1", "r1-root", "out", "region-1", "out"),
        makeEdge("b2", "r2-root", "out", "region-2", "out"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
        makeEdge("l2", "region-2", "out", "sim-1", "in"),
      ],
    );
    const plan = planWorkflowRun(definition);
    expect(plan.ok).toBe(false);
    expect(plan.errors.some((message) => message.includes("root"))).toBe(true);
  });

  it("并发度取节点参数，越界值视为自动", () => {
    const definition = makeDefinition(
      [makeRegion("region-1")],
      [
        ...simpleRegionNodes("region-1", "区域一"),
        makeNode("sim-1", "simulation", { concurrency: 8 }, null),
        makeNode("sim-2", "simulation", { concurrency: 99 }, null),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
        makeEdge("l2", "region-1", "out", "sim-2", "in"),
      ],
    );
    const plan = planWorkflowRun(definition);
    expect(plan.ok).toBe(true);
    const byNode = new Map(plan.batches.map((batch) => [batch.nodeId, batch]));
    expect(byNode.get("sim-1")?.concurrency).toBe(8);
    expect(byNode.get("sim-2")?.concurrency).toBeNull();
  });

  it("hasRunnableBatch 反映是否存在连接了配置区域的模拟节点", () => {
    const connected = makeDefinition(
      [makeRegion("region-1")],
      [...simpleRegionNodes("region-1", "区域一"), makeNode("sim-1", "simulation", {}, null)],
      [
        ...regionBoundaryEdges("region-1"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
      ],
    );
    expect(hasRunnableBatch(connected)).toBe(true);

    const unconnected = makeDefinition(
      [makeRegion("region-1")],
      [...simpleRegionNodes("region-1", "区域一"), makeNode("sim-1", "simulation", {}, null)],
      regionBoundaryEdges("region-1"),
    );
    expect(hasRunnableBatch(unconnected)).toBe(false);
  });
});

describe("planRegionRun", () => {
  it("区域运行只编译目标区域并为所连模拟节点生成批次", () => {
    const definition = makeDefinition(
      [makeRegion("region-1")],
      [
        ...simpleRegionNodes("region-1", "区域一"),
        makeNode("sim-1", "simulation", {}, null),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
      ],
    );
    const plan = planRegionRun(definition, "region-1");
    expect(plan.ok).toBe(true);
    expect(plan.batches).toHaveLength(1);
    expect(plan.batches[0].nodeId).toBe("sim-1");
    expect(plan.batches[0].sourceRegionIds).toEqual(["region-1"]);
    expect(plan.batches[0].members).toHaveLength(1);
    expect(plan.participating[0].methods.map((method) => method.nodeId)).toEqual([
      "region-1-root",
      "region-1-meta",
    ]);
    expect(plan.skippedRegionIds).toEqual([]);
  });

  it("没有数据汇入的区域无法编译", () => {
    const definition = makeDefinition(
      [makeRegion("region-1")],
      [makeNode("root", "root")],
      [],
    );
    const plan = planRegionRun(definition, "region-1");
    expect(plan.ok).toBe(false);
    expect(plan.errors.join("")).toContain("无法编译");
  });

  it("未连接模拟节点的区域无法成立批次", () => {
    const definition = makeDefinition(
      [makeRegion("region-1")],
      simpleRegionNodes("region-1", "区域一"),
      regionBoundaryEdges("region-1"),
    );
    const plan = planRegionRun(definition, "region-1");
    expect(plan.ok).toBe(false);
    expect(plan.errors.join("")).toContain("未连接模拟节点");
  });
});

describe("planAnalysisInputRun", () => {
  it("边界连接的模拟节点缺会话时生成补跑批次", () => {
    const definition = makeDefinition(
      [makeRegion("region-1"), makeAnalysisRegion("analysis-1")],
      [
        ...simpleRegionNodes("region-1", "主配队"),
        makeNode("sim-1", "simulation", {}, null),
        makeNode("fetch-1", "fetch", { source: "runs" }, "analysis-1"),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
        makeEdge("a1", "sim-1", "out", "analysis-1", "in"),
        makeEdge("a2", "analysis-1", "in", "fetch-1", "in"),
      ],
    );
    const plan = planAnalysisInputRun(definition, "analysis-1");
    expect(plan.ok).toBe(true);
    expect(plan.batches).toHaveLength(1);
    expect(plan.batches[0].nodeId).toBe("sim-1");
    expect(plan.batches[0].members).toHaveLength(1);
    expect(plan.participating).toHaveLength(1);
  });

  it("模拟节点已有会话时不产生补跑批次", () => {
    const definition = makeDefinition(
      [makeRegion("region-1"), makeAnalysisRegion("analysis-1")],
      [
        ...simpleRegionNodes("region-1", "主配队"),
        makeNode("sim-1", "simulation", { last_sessions: ["run:1"] }, null),
        makeNode("fetch-1", "fetch", { source: "runs" }, "analysis-1"),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
        makeEdge("a1", "sim-1", "out", "analysis-1", "in"),
        makeEdge("a2", "analysis-1", "in", "fetch-1", "in"),
      ],
    );
    const plan = planAnalysisInputRun(definition, "analysis-1");
    expect(plan.ok).toBe(true);
    expect(plan.batches).toHaveLength(0);
    expect(plan.errors).toHaveLength(0);
  });

  it("只连数据提供节点时无需补跑", () => {
    const definition = makeDefinition(
      [makeAnalysisRegion("analysis-1")],
      [
        makeNode("dp-1", "data_provider", { session_ids: ["run:1"] }, null),
        makeNode("fetch-1", "fetch", { source: "runs" }, "analysis-1"),
      ],
      [
        makeEdge("a1", "dp-1", "out", "analysis-1", "in"),
        makeEdge("a2", "analysis-1", "in", "fetch-1", "in"),
      ],
    );
    const plan = planAnalysisInputRun(definition, "analysis-1");
    expect(plan.ok).toBe(true);
    expect(plan.batches).toHaveLength(0);
  });

  it("缺会话的模拟节点未连接配置区域时报错", () => {
    const definition = makeDefinition(
      [makeAnalysisRegion("analysis-1")],
      [
        makeNode("sim-1", "simulation", {}, null),
        makeNode("fetch-1", "fetch", { source: "runs" }, "analysis-1"),
      ],
      [
        makeEdge("a1", "sim-1", "out", "analysis-1", "in"),
        makeEdge("a2", "analysis-1", "in", "fetch-1", "in"),
      ],
    );
    const plan = planAnalysisInputRun(definition, "analysis-1");
    expect(plan.ok).toBe(false);
    expect(plan.errors.join("")).toContain("未连接配置区域");
  });

  it("未连接分析区域的模拟节点即使缺会话也不补跑", () => {
    const definition = makeDefinition(
      [makeRegion("region-1"), makeAnalysisRegion("analysis-1")],
      [
        ...simpleRegionNodes("region-1", "主配队"),
        makeNode("sim-1", "simulation", {}, null),
        makeNode("fetch-1", "fetch", { source: "runs" }, "analysis-1"),
      ],
      [
        ...regionBoundaryEdges("region-1"),
        makeEdge("l1", "region-1", "out", "sim-1", "in"),
        makeEdge("a1", "analysis-1", "in", "fetch-1", "in"),
      ],
    );
    const plan = planAnalysisInputRun(definition, "analysis-1");
    expect(plan.ok).toBe(true);
    expect(plan.batches).toHaveLength(0);
  });
});

describe("validationErrorMessage", () => {
  it("聚合失败成员与首条后端诊断", () => {
    const message = validationErrorMessage({
      ok: false,
      members: [
        { item_id: "a", ok: true },
        {
          item_id: "b",
          ok: false,
          details: [{ severity: "error", code: "ASSET_NOT_FOUND", message: "资产不存在" }],
        },
        { item_id: "c", ok: false, details: [] },
      ],
    });
    expect(message).toContain("2 个成员");
    expect(message).toContain("b：资产不存在");
    expect(message).toContain("c");
  });
});

describe("scopedDiagnostics", () => {
  const definition = makeDefinition(
    [makeRegion("region-1"), makeRegion("region-2")],
    [
      makeNode("r1-char", "character", { slot: 1, asset: "character:a" }, "region-1"),
      makeNode("r2-char", "character", { slot: 1, asset: "character:missing" }, "region-2"),
      makeNode("sim-1", "simulation", {}, null),
    ],
    [makeEdge("l1", "region-1", "out", "sim-1", "in")],
  );
  const diagnostics: Diagnostic[] = [
    {
      severity: "error",
      code: "ASSET_NOT_FOUND",
      message: "资产不存在：character:missing",
      node_id: "r2-char",
      edge_id: null,
      region_id: null,
      path: "asset",
    },
    {
      severity: "error",
      code: "PARAM_INVALID",
      message: "参数无效",
      node_id: "r1-char",
      edge_id: null,
      region_id: null,
      path: "slot",
    },
    {
      severity: "error",
      code: "PARAM_INVALID",
      message: "并发度无效",
      node_id: "sim-1",
      edge_id: null,
      region_id: null,
      path: "concurrency",
    },
    {
      severity: "error",
      code: "META_INVALID",
      message: "meta.name 必须是字符串",
      node_id: null,
      edge_id: null,
      region_id: null,
      path: null,
    },
    {
      severity: "error",
      code: "PORT_INVALID",
      message: "端口错误",
      node_id: null,
      edge_id: "l1",
      region_id: null,
      path: null,
    },
  ];

  it("区域运行只保留目标区域节点、所连模拟节点与全局诊断", () => {
    const codes = scopedDiagnostics(definition, diagnostics, new Set(["region-1"])).map(
      (item) => item.code,
    );
    expect(codes).toEqual(["PARAM_INVALID", "PARAM_INVALID", "META_INVALID", "PORT_INVALID"]);
  });

  it("其他区域的节点诊断不阻断目标区域运行", () => {
    const codes = scopedDiagnostics(definition, diagnostics, new Set(["region-2"])).map(
      (item) => item.code,
    );
    expect(codes).toEqual(["ASSET_NOT_FOUND", "META_INVALID"]);
  });
});

describe("paceBuildSteps", () => {
  it("启用时限速推进：每个节点 running → 等待 → done", async () => {
    const events: string[] = [];
    const sleeps: number[] = [];
    await paceBuildSteps(
      [
        {
          regionId: "region-1",
          methods: [{ nodeId: "a" }, { nodeId: "b" }],
        },
      ],
      {
        enabled: true,
        stepMs: 5,
        sleep: async (ms) => {
          sleeps.push(ms);
        },
        onMethodStatus: (regionId, nodeId, status) => {
          events.push(`${regionId}:${nodeId}:${status}`);
        },
      },
    );
    expect(events).toEqual([
      "region-1:a:running",
      "region-1:a:done",
      "region-1:b:running",
      "region-1:b:done",
    ]);
    expect(sleeps).toEqual([5, 5]);
  });

  it("禁用时不等待，直接完成", async () => {
    const events: string[] = [];
    const sleeps: number[] = [];
    await paceBuildSteps(
      [{ regionId: "r", methods: [{ nodeId: "a" }, { nodeId: "b" }] }],
      {
        enabled: false,
        sleep: async (ms) => {
          sleeps.push(ms);
        },
        onMethodStatus: (_regionId, nodeId, status) => {
          events.push(`${nodeId}:${status}`);
        },
      },
    );
    expect(events).toEqual(["a:running", "a:done", "b:running", "b:done"]);
    expect(sleeps).toEqual([]);
  });

  it("取消后剩余节点标记跳过且不再等待", async () => {
    const events: string[] = [];
    const sleeps: number[] = [];
    let stopped = false;
    await paceBuildSteps(
      [{ regionId: "r", methods: [{ nodeId: "a" }, { nodeId: "b" }, { nodeId: "c" }] }],
      {
        enabled: true,
        stepMs: 5,
        sleep: async (ms) => {
          sleeps.push(ms);
          // 第一个节点等待后取消
          stopped = true;
        },
        shouldStop: () => stopped,
        onMethodStatus: (_regionId, nodeId, status) => {
          events.push(`${nodeId}:${status}`);
        },
      },
    );
    expect(events).toEqual(["a:running", "a:done", "b:skipped", "c:skipped"]);
    expect(sleeps).toEqual([5]);
  });
});
