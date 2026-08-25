/** 分析执行器：计划编译与会话组合并（契约 v2）。 */

import { describe, expect, it } from "vitest";

import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types";
import {
  buildAnalysisPlanRequest,
  executeAnalysisRegion,
  resolveBoundarySessionGroup,
} from "./analysis_runner";

function simulation(id: string, sessions: string[]): WorkflowNode {
  return { id, kind: "simulation", region_id: null, position: { x: 0, y: 0 }, params: { last_sessions: sessions } };
}

function provider(id: string, sessions: string[]): WorkflowNode {
  return { id, kind: "data_provider", region_id: null, position: { x: 0, y: 0 }, params: { session_ids: sessions } };
}

function analysisNode(id: string, kind: string, params: Record<string, unknown> = {}, regionId = "analysis-1"): WorkflowNode {
  return { id, kind, region_id: regionId, position: { x: 0, y: 0 }, params };
}

function edge(
  id: string,
  sourceNodeId: string,
  sourcePortId: string,
  targetNodeId: string,
  targetPortId: string,
): WorkflowEdge {
  return {
    id,
    source_node_id: sourceNodeId,
    source_port_id: sourcePortId,
    target_node_id: targetNodeId,
    target_port_id: targetPortId,
  };
}

function definition(nodes: WorkflowNode[], edges: WorkflowEdge[]): WorkflowDefinition {
  return {
    schema_version: 1,
    meta: { name: "t" },
    regions: [
      { id: "analysis-1", kind: "analysis", name: "分析", rect: { x: 0, y: 0, width: 600, height: 400 } },
    ],
    nodes,
    edges,
    layout: {},
  };
}

describe("会话组解析", () => {
  it("模拟节点与数据提供多源合并且保序去重", () => {
    const def = definition(
      [simulation("sim", ["s1", "s2"]), provider("prov", ["s2", "s3"])],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("b2", "prov", "out", "analysis-1", "in"),
      ],
    );
    expect(resolveBoundarySessionGroup(def, "analysis-1")).toEqual(["s1", "s2", "s3"]);
  });
});

describe("查询计划编译", () => {
  it("编译取数链：拓扑序、参数透传、输出为视图上游", () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("lim1", "limit", { count: 10 }),
        analysisNode("view1", "member_table"),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "lim1", "in"),
        edge("e2", "lim1", "out", "view1", "in"),
      ],
    );

    const request = buildAnalysisPlanRequest(def, "analysis-1");

    expect(request.session_ids).toEqual(["a"]);
    expect(request.nodes.find((node) => node.id === "runs1")?.inputs).toEqual([]);
    expect(request.nodes.map((node) => node.id)).toEqual(["runs1", "lim1"]);
    expect(request.nodes[1].params).toEqual({ count: 10 });
    expect(request.outputs).toEqual(["lim1"]);
  });

  it("join 按端口名对齐左右输入顺序", () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("ev1", "fetch", { source: "events" }),
        analysisNode("j1", "join", { left_key: "session_id", right_key: "session_id" }),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("w2", "analysis-1", "in", "ev1", "in"),
        edge("e1", "runs1", "out", "j1", "left"),
        edge("e2", "ev1", "out", "j1", "right"),
      ],
    );

    const request = buildAnalysisPlanRequest(def, "analysis-1");
    const joinNode = request.nodes.find((node) => node.id === "j1");
    expect(joinNode?.inputs).toEqual(["runs1", "ev1"]);
  });
});

describe("计划执行", () => {
  it("把响应表映射为节点结果并标记错误", async () => {
    const def = definition(
      [simulation("sim", ["a"]), analysisNode("runs1", "fetch", { source: "runs" })],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
      ],
    );

    let captured: unknown;
    const results = await executeAnalysisRegion(def, "analysis-1", async (request) => {
      captured = request;
      return {
        tables: {
          runs1: { columns: [{ name: "session_id", type: "string" }], rows: [["a"]], truncated: false },
        },
      };
    });

    expect((captured as { outputs: string[] }).outputs).toEqual(["runs1"]);
    expect(results.get("runs1")?.status).toBe("ready");
  });

  it("端点失败时所有输出节点携带错误状态", async () => {
    const def = definition(
      [simulation("sim", ["a"]), analysisNode("runs1", "fetch", { source: "runs" })],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
      ],
    );

    const results = await executeAnalysisRegion(def, "analysis-1", async () => {
      throw new Error("后端不可用");
    });

    expect(results.get("runs1")?.status).toBe("error");
    expect(results.get("runs1")?.error).toContain("后端不可用");
  });
});
