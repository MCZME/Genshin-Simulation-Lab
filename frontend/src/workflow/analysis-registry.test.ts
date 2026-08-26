/** 分析节点注册表（契约 v2：取数 + 关系算子族）。 */

import { describe, expect, it } from "vitest";

import { getNodeKindSpec, validateNode } from "./registry";
import { computeAnalysisShapes, fetchShape } from "./templates";
import type { WorkflowDefinition, WorkflowNode } from "./types";

describe("分析节点注册表", () => {
  it("取数节点属于分析区域，入向为会话组、出向为结果表", () => {
    const spec = getNodeKindSpec("fetch");
    expect(spec?.region).toBe("analysis");
    expect(spec?.ports.inputs).toHaveLength(1);
    expect(spec?.ports.inputs[0].dataLanguage).toBe("session_group");
    expect(spec?.ports.outputs[0].dataLanguage).toBe("table");
    expect(spec?.ports.outputs[0].cardinality).toBe("single");
  });

  it("六个单输入算子均为结果表入出，连接为双输入", () => {
    const single = ["filter", "project", "sort", "aggregate", "limit", "compute"] as const;
    for (const kind of single) {
      const spec = getNodeKindSpec(kind);
      expect(spec?.ports.inputs).toHaveLength(1);
      expect(spec?.ports.inputs[0].dataLanguage).toBe("table");
      expect(spec?.ports.outputs[0].dataLanguage).toBe("table");
    }
    const join = getNodeKindSpec("join");
    expect(join?.ports.inputs.map((port) => port.id)).toEqual(["left", "right"]);
  });

  it("旧的处理与查询参数配置节点已退役", () => {
    expect(getNodeKindSpec("processing")).toBeNull();
    expect(getNodeKindSpec("query_config")).toBeNull();
  });

  it("数据提供节点是画布级源节点，参数仅 session_ids", () => {
    const spec = getNodeKindSpec("data_provider");
    expect(spec?.region).toBeNull();
    expect(spec?.ports.inputs).toHaveLength(0);
    expect(spec?.ports.outputs[0].dataLanguage).toBe("session_group");
    expect(spec?.paramFields).toEqual({ session_ids: { type: "list" } });
    expect(spec?.defaultParams).toEqual({ session_ids: [] });
  });

  it("数据提供节点拒绝重复与超限会话", () => {
    const base = {
      id: "provider-1",
      kind: "data_provider",
      region_id: null,
      position: { x: 0, y: 0 },
    } as const;
    const duplicate = validateNode({
      ...base,
      params: { session_ids: ["a", "a"] },
    });
    const overLimit = validateNode({
      ...base,
      params: { session_ids: Array.from({ length: 1001 }, (_, index) => `s${index}`) },
    });

    expect(duplicate.some((item) => item.message.includes("重复"))).toBe(true);
    expect(overLimit.some((item) => item.message.includes("最多 1000 个"))).toBe(true);
  });
});

describe("形状推导", () => {
  const baseNode = (overrides: Partial<WorkflowNode>): WorkflowNode => ({
    id: "n1",
    kind: "fetch",
    region_id: "analysis-1",
    position: { x: 0, y: 0 },
    params: { source: "runs" },
    ...overrides,
  });

  it("获取数据（运行记录）默认携带会话列与运行列，支持快照提取列", () => {
    const node = baseNode({
      params: {
        source: "runs",
        snapshot_columns: [{ path: "team[0].character.asset_key", name: "char_1_key", type: "string" }],
      },
    });
    const shape = fetchShape(node);
    const names = shape === null ? [] : shape.map((column) => column.name);
    expect(names).toContain("session_id");
    expect(names).toContain("frames_run");
    expect(names).toContain("char_1_key");
    expect(names).not.toContain("input_snapshot_json");
  });

  function definitionWith(nodes: WorkflowNode[], edges: WorkflowDefinition["edges"]): WorkflowDefinition {
    return { schema_version: 1, meta: { name: "t" }, regions: [], nodes, edges, layout: {} };
  }

  it("投影输出按定义收窄，聚合自动命名并推导类型", () => {
    const definition = definitionWith(
      [
        baseNode({ id: "runs1" }),
        baseNode({
          id: "proj1",
          kind: "project",
          params: { columns: [{ name: "session_id" }, { name: "frames_run", as: "frames" }] },
        }),
        baseNode({
          id: "agg1",
          kind: "aggregate",
          params: {
            group_by: ["session_id"],
            aggregates: [{ fn: "avg", column: "frames" }],
          },
        }),
      ],
      [
        { id: "e1", source_node_id: "runs1", source_port_id: "out", target_node_id: "proj1", target_port_id: "in" },
        { id: "e2", source_node_id: "proj1", source_port_id: "out", target_node_id: "agg1", target_port_id: "in" },
      ],
    );
    const shapes = computeAnalysisShapes(definition);
    expect(shapes.get("proj1")?.map((column) => column.name)).toEqual(["session_id", "frames"]);
    const agg = shapes.get("agg1");
    expect(agg?.map((column) => column.name + ":" + column.type)).toEqual([
      "session_id:string",
      "avg_frames:float",
    ]);
  });

  it("空投影、空聚合与空计算列不可推导", () => {
    const cases: {
      id: string;
      kind: "project" | "aggregate" | "compute";
      params: Record<string, unknown>;
    }[] = [
      { id: "p1", kind: "project", params: { columns: [] } },
      { id: "a1", kind: "aggregate", params: {} },
      { id: "c1", kind: "compute", params: { columns: [] } },
    ];
    for (const item of cases) {
      const definition = definitionWith(
        [
          baseNode({ id: "runs1" }),
          baseNode({ id: item.id, kind: item.kind, params: item.params }),
        ],
        [
          {
            id: `e-${item.id}`,
            source_node_id: "runs1",
            source_port_id: "out",
            target_node_id: item.id,
            target_port_id: "in",
          },
        ],
      );
      expect(computeAnalysisShapes(definition).get(item.id)).toBeNull();
    }
  });

  it("过滤空条件组按恒真推导，非法算子参数不可推导", () => {
    const identity = definitionWith(
      [
        baseNode({ id: "runs1" }),
        baseNode({ id: "f1", kind: "filter", params: {} }),
      ],
      [
        {
          id: "e1",
          source_node_id: "runs1",
          source_port_id: "out",
          target_node_id: "f1",
          target_port_id: "in",
        },
      ],
    );
    expect(computeAnalysisShapes(identity).get("f1")).not.toBeNull();

    const invalid: {
      id: string;
      kind: "filter" | "sort" | "limit" | "join";
      params: Record<string, unknown>;
    }[] = [
      {
        id: "f1",
        kind: "filter",
        params: { conditions: [{ column: "state", op: "like", value: "x" }] },
      },
      { id: "s1", kind: "sort", params: { keys: [] } },
      { id: "l1", kind: "limit", params: { count: 0 } },
      {
        id: "j1",
        kind: "join",
        params: { left_key: "session_id", right_key: "session_id", mode: "full" },
      },
    ];
    for (const item of invalid) {
      const nodes = [baseNode({ id: "runs1" })];
      const edges = [];
      if (item.kind === "join") {
        nodes.push(
          baseNode({ id: "ev1", kind: "fetch", params: { source: "events" } }),
          baseNode({ id: item.id, kind: item.kind, params: item.params }),
        );
        edges.push(
          {
            id: "e1",
            source_node_id: "runs1",
            source_port_id: "out",
            target_node_id: item.id,
            target_port_id: "left",
          },
          {
            id: "e2",
            source_node_id: "ev1",
            source_port_id: "out",
            target_node_id: item.id,
            target_port_id: "right",
          },
        );
      } else {
        nodes.push(baseNode({ id: item.id, kind: item.kind, params: item.params }));
        edges.push({
          id: "e1",
          source_node_id: "runs1",
          source_port_id: "out",
          target_node_id: item.id,
          target_port_id: "in",
        });
      }
      const definition = definitionWith(nodes, edges);
      expect(computeAnalysisShapes(definition).get(item.id)).toBeNull();
    }
  });

  it("compute 非法表达式不可推导", () => {
    const definition = definitionWith(
      [
        baseNode({ id: "runs1" }),
        baseNode({
          id: "c1",
          kind: "compute",
          params: {
            columns: [
              {
                name: "bad",
                expr: { op: "nope", left: { col: "frames_run" }, right: { lit: 2 } },
              },
            ],
          },
        }),
      ],
      [
        {
          id: "e1",
          source_node_id: "runs1",
          source_port_id: "out",
          target_node_id: "c1",
          target_port_id: "in",
        },
      ],
    );
    expect(computeAnalysisShapes(definition).get("c1")).toBeNull();
  });

  it("事件记录来源非法事件类型、帧范围或提取列不可推导", () => {
    const cases: Record<string, unknown>[] = [
      { source: "events", event_types: "DAMAGE_RESOLVED" },
      { source: "events", payload_columns: [{ path: "x", name: "n", type: "date" }] },
      {
        source: "events",
        payload_columns: [{ event_type: "", path: "x", name: "n", type: "float" }],
      },
    ];
    for (const params of cases) {
      const node = baseNode({ id: "ev1", kind: "fetch", params });
      expect(fetchShape(node)).toBeNull();
    }
  });
});
