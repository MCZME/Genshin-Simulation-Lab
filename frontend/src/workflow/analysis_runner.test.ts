/** 分析执行器：计划编译与会话组合并（契约 v2）。 */

import { describe, expect, it } from "vitest";

import type { WorkflowDefinition, WorkflowEdge, WorkflowNode } from "./types";
import {
  applyViewSelectionSingles,
  buildAnalysisPlanRequest,
  executeAnalysisSelectionBranch,
  executeAnalysisRegionByNodes,
  executeAnalysisRegion,
  populateAnalysisTerminalResults,
  resolveBoundarySessionGroup,
} from "./analysis_runner";
import type { AnalysisNodeResult } from "./analysis_runner";

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

  it("展示配置转发节点不进入计划，其上游表作为视图输出", () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("cfg1", "table_config", {
          condition_columns: [],
          data_columns: [],
        }),
        analysisNode("view1", "member_table"),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "cfg1", "in"),
        edge("e2", "cfg1", "out", "view1", "in"),
      ],
    );

    const request = buildAnalysisPlanRequest(def, "analysis-1");

    expect(request.nodes.map((node) => node.id)).toEqual(["runs1"]);
    expect(request.outputs).toEqual(["runs1"]);
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

describe("节点运行时执行", () => {
  it("按拓扑序逐节点执行并把上游阶段引用传入下游", async () => {
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
    const executions: { nodeId: string; inputStages: string[] }[] = [];
    const createContext = async () => ({ context_id: "ctx-1" });
    const executeNode = async (
      contextId: string,
      execution: { node_id: string; input_stages: string[] },
    ) => {
      expect(contextId).toBe("ctx-1");
      executions.push({
        nodeId: execution.node_id,
        inputStages: execution.input_stages,
      });
      return {
        stage_id: `stage-${execution.node_id}`,
        columns: [{ name: "session_id", type: "string" }],
        rows: [["a"]],
        truncated: false,
      };
    };
    const closeContext = async (contextId: string) => {
      expect(contextId).toBe("ctx-1");
    };

    const results = await executeAnalysisRegionByNodes(
      def,
      "analysis-1",
      executeNode,
      createContext,
      closeContext,
    );

    expect(executions.map((item) => item.nodeId)).toEqual(["runs1", "lim1"]);
    expect(executions[0]?.inputStages).toEqual([]);
    expect(executions[1]?.inputStages).toEqual(["stage-runs1"]);
    expect(results.get("lim1")?.status).toBe("ready");
    expect(results.get("lim1")?.stage_id).toBe("stage-lim1");
  });

  it("单节点失败只置自身与下游错误，不再调用后端", async () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("lim1", "limit", { count: 10 }),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "lim1", "in"),
      ],
    );
    const createContext = async () => ({ context_id: "ctx-1" });
    const executeNode = async (
      _contextId: string,
      execution: { node_id: string },
    ) => {
      if (execution.node_id === "runs1") {
        throw new Error("取数失败");
      }
      throw new Error("不应执行");
    };
    const closed: string[] = [];
    const closeContext = async (contextId: string) => {
      closed.push(contextId);
    };

    const results = await executeAnalysisRegionByNodes(
      def,
      "analysis-1",
      executeNode,
      createContext,
      closeContext,
    );

    expect(results.get("runs1")?.status).toBe("error");
    expect(results.get("lim1")?.status).toBe("error");
    expect(closed).toEqual(["ctx-1"]);
  });

  it("视图只在点击后执行 selection 下游，整区刷新不执行选择分支", async () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("view1", "pie"),
        analysisNode("lim1", "limit", { count: 5 }),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "view1", "in"),
        edge("e2", "view1", "selection", "lim1", "in"),
      ],
    );
    const executions: { nodeId: string; inputStages: string[] }[] = [];
    const createContext = async () => ({ context_id: "ctx-1" });
    const executeNode = async (
      contextId: string,
      execution: { node_id: string; input_stages: string[] },
    ) => {
      expect(contextId).toBe("ctx-1");
      executions.push({
        nodeId: execution.node_id,
        inputStages: execution.input_stages,
      });
      return {
        stage_id: `stage-${execution.node_id}`,
        columns: [{ name: "session_id", type: "string" }],
        rows: [["a"]],
        truncated: false,
      };
    };

    const results = await executeAnalysisRegionByNodes(
      def,
      "analysis-1",
      executeNode,
      createContext,
      async () => {},
    );

    expect(executions.map((item) => item.nodeId)).toEqual(["runs1"]);
    expect(results.get("view1")?.stage_id).toBe("stage-runs1");
    expect(results.has("lim1")).toBe(false);
  });

  it("多输入饼图先合并输入阶段供选择使用，不执行选择下游", async () => {
    const def = definition(
      [
        simulation("sim", ["a", "b"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("runs2", "fetch", { source: "runs" }),
        analysisNode("view1", "pie"),
        analysisNode("lim1", "limit", { count: 5 }),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("w2", "analysis-1", "in", "runs2", "in"),
        edge("e1", "runs1", "out", "view1", "in"),
        edge("e2", "runs2", "out", "view1", "in"),
        edge("e3", "view1", "selection", "lim1", "in"),
      ],
    );
    const mergedCalls: string[][] = [];
    const executions: { nodeId: string; inputStages: string[] }[] = [];
    const executeNode = async (
      contextId: string,
      execution: { node_id: string; input_stages: string[] },
    ) => {
      expect(contextId).toBe("ctx-1");
      executions.push({
        nodeId: execution.node_id,
        inputStages: execution.input_stages,
      });
      return {
        stage_id: `stage-${execution.node_id}`,
        columns: [{ name: "session_id", type: "string" }],
        rows: [],
        truncated: false,
      };
    };
    const mergeStages = async (contextId: string, stageIds: string[]) => {
      expect(contextId).toBe("ctx-1");
      mergedCalls.push(stageIds);
      return {
        stage_id: "stage-merged",
        columns: [{ name: "session_id", type: "string" }],
        rows: [],
        truncated: false,
      };
    };

    const results = await executeAnalysisRegionByNodes(
      def,
      "analysis-1",
      executeNode,
      async () => ({ context_id: "ctx-1" }),
      async () => {},
      mergeStages,
    );

    expect(mergedCalls).toEqual([["stage-runs1", "stage-runs2"]]);
    expect(executions.find((item) => item.nodeId === "lim1")).toBeUndefined();
    expect(results.get("view1")?.stage_id).toBe("stage-merged");
  });

  it("从视图选择阶段执行下游分支", async () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("view1", "pie"),
        analysisNode("lim1", "limit", { count: 1 }),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "view1", "in"),
        edge("e2", "view1", "selection", "lim1", "in"),
      ],
    );
    const executions: { nodeId: string; inputStages: string[] }[] = [];
    const executeNode = async (
      contextId: string,
      execution: { node_id: string; input_stages: string[] },
    ) => {
      expect(contextId).toBe("ctx-1");
      executions.push({
        nodeId: execution.node_id,
        inputStages: execution.input_stages,
      });
      return {
        stage_id: "stage-selected-limit",
        columns: [{ name: "session_id", type: "string" }],
        rows: [["a"]],
        truncated: false,
      };
    };

    const results = await executeAnalysisSelectionBranch(
      def,
      "analysis-1",
      "view1",
      "ctx-1",
      "stage-selected",
      new Map([["runs1", "stage-runs1"]]),
      executeNode,
    );

    expect(executions).toEqual([
      { nodeId: "lim1", inputStages: ["stage-selected"] },
    ]);
    expect(results.get("lim1")?.status).toBe("ready");
    expect(results.get("lim1")?.stage_id).toBe("stage-selected-limit");
  });

  it("选择分支结果补齐配置转发、下游视图与获取单行", async () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("view1", "pie"),
        analysisNode("lim1", "limit", { count: 1 }),
        analysisNode("cfg1", "table_config"),
        analysisNode("view2", "member_table"),
        analysisNode("single1", "single"),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "view1", "in"),
        edge("e2", "view1", "selection", "lim1", "in"),
        edge("e3", "lim1", "out", "cfg1", "in"),
        edge("e4", "cfg1", "out", "view2", "in"),
        edge("e5", "lim1", "out", "single1", "in"),
      ],
    );
    const executeNode = async (
      _contextId: string,
      execution: { node_id: string },
    ) => {
      expect(execution.node_id).toBe("lim1");
      return {
        stage_id: "stage-selected-limit",
        columns: [{ name: "session_id", type: "string" }],
        rows: [["a"]],
        truncated: false,
      };
    };

    const branchResults = await executeAnalysisSelectionBranch(
      def,
      "analysis-1",
      "view1",
      "ctx-1",
      "stage-selected",
      new Map([["runs1", "stage-runs1"]]),
      executeNode,
    );
    const current = new Map<string, AnalysisNodeResult>([
      [
        "runs1",
        {
          status: "ready",
          stage_id: "stage-runs1",
          table: {
            columns: [{ name: "session_id", type: "string" }],
            rows: [["a"]],
            truncated: false,
          },
        },
      ],
      ...branchResults,
    ]);

    const populated = populateAnalysisTerminalResults(def, "analysis-1", current);

    expect(populated.get("cfg1")?.status).toBe("ready");
    expect(populated.get("cfg1")?.table?.rows).toEqual([["a"]]);
    expect(populated.get("view2")?.status).toBe("ready");
    expect(populated.get("view2")?.stage_id).toBe("stage-selected-limit");
    expect(populated.get("single1")).toEqual({
      status: "ready",
      item: { session_id: "a" },
    });
  });

  it("分支内上游失败时下游不回退旧阶段", async () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("view1", "pie"),
        analysisNode("lim1", "limit", { count: 1 }),
        analysisNode("proj1", "project", {
          columns: [{ name: "session_id" }],
        }),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "view1", "in"),
        edge("e2", "view1", "selection", "lim1", "in"),
        edge("e3", "lim1", "out", "proj1", "in"),
      ],
    );
    const executed: string[] = [];
    const executeNode = async (
      _contextId: string,
      execution: { node_id: string },
    ) => {
      executed.push(execution.node_id);
      throw new Error("不应执行");
    };

    const results = await executeAnalysisSelectionBranch(
      def,
      "analysis-1",
      "view1",
      "ctx-1",
      "stage-selected",
      new Map([
        ["runs1", "stage-runs1"],
        ["lim1", "stage-lim1-old"],
        ["proj1", "stage-proj1-old"],
      ]),
      executeNode,
    );

    expect(results.get("lim1")?.status).toBe("error");
    expect(results.get("proj1")?.status).toBe("error");
    expect(executed).toEqual(["lim1"]);
  });

  it("未点击时饼图 selection 直连的获取单行不取整组数据", () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("view1", "pie"),
        analysisNode("single1", "single"),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "view1", "in"),
        edge("e2", "view1", "selection", "single1", "in"),
      ],
    );
    const results = new Map<string, AnalysisNodeResult>([
      [
        "runs1",
        {
          status: "ready",
          stage_id: "stage-runs1",
          table: {
            columns: [{ name: "session_id", type: "string" }],
            rows: [["a"], ["b"]],
            truncated: false,
          },
        },
      ],
      ["view1", { status: "ready", stage_id: "stage-runs1" }],
      ["single1", { status: "loading" }],
    ]);

    const populated = populateAnalysisTerminalResults(def, "analysis-1", results);

    expect(populated.get("view1")?.table?.rows).toEqual([["a"], ["b"]]);
    expect(populated.get("single1")).toEqual({ status: "idle" });
  });

  it("点击后写入的选中行 item 不会被终端补齐覆盖", () => {
    const def = definition(
      [
        simulation("sim", ["a"]),
        analysisNode("runs1", "fetch", { source: "runs" }),
        analysisNode("view1", "pie"),
        analysisNode("single1", "single"),
      ],
      [
        edge("b1", "sim", "out", "analysis-1", "in"),
        edge("w1", "analysis-1", "in", "runs1", "in"),
        edge("e1", "runs1", "out", "view1", "in"),
        edge("e2", "view1", "selection", "single1", "in"),
      ],
    );
    const results = new Map<string, AnalysisNodeResult>([
      [
        "runs1",
        {
          status: "ready",
          stage_id: "stage-runs1",
          table: {
            columns: [{ name: "session_id", type: "string" }],
            rows: [["a"], ["b"]],
            truncated: false,
          },
        },
      ],
      ["view1", { status: "ready", stage_id: "stage-runs1" }],
    ]);
    applyViewSelectionSingles(def, "analysis-1", "view1", {
      stage_id: "stage-selected",
      source_node_id: "view1",
      columns: [{ name: "session_id", type: "string" }],
      rows: [["b"]],
      truncated: false,
    }, results);

    const populated = populateAnalysisTerminalResults(def, "analysis-1", results);

    expect(populated.get("single1")).toEqual({
      status: "ready",
      item: { session_id: "b" },
    });
  });
});
