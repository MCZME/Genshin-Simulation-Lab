import { describe, expect, it } from "vitest";
import type {
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowRegion,
} from "./types";
import { validateWorkflow, validateWorkflowNodes } from "./validator";

function makeRegion(
  id = "region-1",
  kind: "configuration" | "analysis" = "configuration",
): WorkflowRegion {
  return { id, kind, name: "主配置", rect: { x: 0, y: 0, width: 800, height: 600 } };
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

function codes(definition: WorkflowDefinition): string[] {
  return validateWorkflow(definition).map((item) => item.code);
}

describe("validateWorkflow", () => {
  it("合法 MVP 工作流没有错误", () => {
    const region = makeRegion();
    const nodes = [
      makeNode("root", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("target", "target", { index: 0, level: 90 }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "region-1", "out"),
      makeEdge("e2", "char", "out", "region-1", "out"),
      makeEdge("e3", "target", "out", "region-1", "out"),
      makeEdge("e4", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([region], nodes, edges);
    const errors = validateWorkflow(definition).filter((item) => item.severity === "error");
    expect(errors).toEqual([]);
  });

  it("同一区域占用相同队伍槽位时报错", () => {
    const nodes = [
      makeNode("char1", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("char2", "character", { slot: 1, asset: "character:kaeya" }),
      makeNode("weapon", "weapon", { slot: 1, asset: "weapon:11512" }),
      makeNode("char3", "character", { slot: 2, asset: "character:diluc" }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "char1", "out", "region-1", "out"),
      makeEdge("e2", "char2", "out", "region-1", "out"),
      makeEdge("e3", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);
    const slotConflicts = validateWorkflow(definition).filter(
      (item) => item.code === "TEAM_SLOT_CONFLICT",
    );
    expect(slotConflicts.map((item) => item.node_id).sort()).toEqual([
      "char1",
      "char2",
    ]);
  });

  it("未接入数据链的同槽位武器不报槽位冲突", () => {
    // 决策 2.32：连接决定参与。未接线草稿不进入编译，也不参与跨节点冲突判定。
    const nodes = [
      makeNode("wired", "weapon", { slot: 1, asset: "weapon:11512" }),
      makeNode("floating", "weapon", { slot: 1, asset: "weapon:11513" }),
    ];
    const edges = [makeEdge("e1", "wired", "out", "region-1", "out")];
    const definition = makeDefinition([makeRegion()], nodes, edges);
    expect(codes(definition)).not.toContain("TEAM_SLOT_CONFLICT");
  });

  it("同槽位的角色武器圣遗物不视为冲突", () => {
    const nodes = [
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("weapon", "weapon", { slot: 1, asset: "weapon:11512" }),
      makeNode("artifact", "artifact", {
        slot: 1,
        sets: [{ asset_key: "artifact_set:15032", pieces: 4 }],
      }),
    ];
    const edges = [
      makeEdge("e1", "char", "out", "region-1", "out"),
      makeEdge("e2", "weapon", "out", "region-1", "out"),
      makeEdge("e3", "artifact", "out", "region-1", "out"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);
    expect(codes(definition)).not.toContain("TEAM_SLOT_CONFLICT");
  });

  it("不同区域可分别占用相同槽位", () => {
    const nodes = [
      makeNode("char1", "character", { slot: 1, asset: "character:barbara" }, "region-1"),
      makeNode("char2", "character", { slot: 1, asset: "character:kaeya" }, "region-2"),
    ];
    const edges = [
      makeEdge("e1", "char1", "out", "region-1", "out"),
      makeEdge("e2", "char2", "out", "region-2", "out"),
    ];
    const definition = makeDefinition(
      [makeRegion("region-1"), makeRegion("region-2")],
      nodes,
      edges,
    );
    expect(codes(definition)).not.toContain("TEAM_SLOT_CONFLICT");
  });

  it("角色槽位越界与天赋等级越界报参数错误", () => {
    const nodes = [
      makeNode("char", "character", {
        slot: 5,
        asset: "character:barbara",
        talents: { normal_attack: 11, elemental_skill: 10, elemental_burst: 1 },
      }),
      makeNode("sim", "simulation", {}, null),
    ];
    const definition = makeDefinition([makeRegion()], nodes, []);
    const params = validateWorkflow(definition).filter((item) => item.code === "PARAM_INVALID");
    expect(params.map((item) => item.path).sort()).toEqual([
      "slot",
      "talents.normal_attack",
    ]);
  });

  it("同一区域内节点链连线合法", () => {
    const nodes = [
      makeNode("root", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("target", "target", { index: 0, level: 90 }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "char", "in"),
      makeEdge("e2", "char", "out", "target", "in"),
      makeEdge("e3", "target", "out", "region-1", "out"),
      makeEdge("e4", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);
    const errors = validateWorkflow(definition).filter((item) => item.severity === "error");
    expect(errors).toEqual([]);
  });

  it("跨区域节点直接连线报错", () => {
    const nodes = [
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }, "region-1"),
      makeNode("target", "target", { index: 0, level: 90 }, "region-2"),
    ];
    const edges = [makeEdge("e1", "char", "out", "target", "in")];
    const definition = makeDefinition(
      [makeRegion("region-1"), makeRegion("region-2")],
      nodes,
      edges,
    );
    expect(codes(definition)).toContain("CROSS_REGION_CONNECTION");
  });

  it("未注册节点类型报错", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("x", "bogus")],
      [],
    );
    expect(codes(definition)).toContain("UNKNOWN_NODE_KIND");
  });

  it("重复 id 报错", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("a", "character", { slot: 1, asset: "character:barbara" }), makeNode("a", "target")],
      [],
    );
    expect(codes(definition)).toContain("DUPLICATE_ID");
  });

  it("游离节点参与连线报错", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("char", "character", { slot: 1, asset: "character:barbara" }, null)],
      [makeEdge("e1", "char", "out", "region-1", "out")],
    );
    expect(codes(definition)).toContain("FREE_NODE_CONNECTED");
  });

  it("配置节点放入分析区域报错", () => {
    const definition = makeDefinition(
      [makeRegion("region-1"), makeRegion("region-2", "analysis")],
      [makeNode("char", "character", { slot: 1, asset: "character:barbara" }, "region-2")],
      [],
    );
    expect(codes(definition)).toContain("REGION_KIND_MISMATCH");
  });

  it("模拟节点归属区域报错", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("sim", "simulation", {}, "region-1")],
      [],
    );
    expect(codes(definition)).toContain("CANVAS_NODE_REGION_INVALID");
  });

  it("未连接模拟节点的配置区域给警告", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("char", "character", { slot: 1, asset: "character:barbara" })],
      [makeEdge("e1", "char", "out", "region-1", "out")],
    );
    const diagnostics = validateWorkflow(definition);
    const notConnected = diagnostics.find((item) => item.code === "REGION_NOT_CONNECTED");
    expect(notConnected?.severity).toBe("warning");
  });

  it("模拟节点未连接配置区域时报批次无法成立", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [
        makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
        makeNode("sim", "simulation", {}, null),
      ],
      [makeEdge("e1", "char", "out", "region-1", "out")],
    );
    const diagnostics = validateWorkflow(definition);
    const emptyBatch = diagnostics.find((item) => item.code === "SIM_BATCH_EMPTY");
    expect(emptyBatch?.severity).toBe("error");
    expect(emptyBatch?.node_id).toBe("sim");
  });

  it("模拟节点并发度越界报参数错误", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("sim", "simulation", { concurrency: 32 }, null)],
      [],
    );
    const diagnostics = validateWorkflow(definition);
    const invalid = diagnostics.find(
      (item) => item.code === "PARAM_INVALID" && item.path === "concurrency",
    );
    expect(invalid?.severity).toBe("error");
  });

  it("连线引用不存在的端口报错", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("char", "character", { slot: 1, asset: "character:barbara" })],
      [makeEdge("e1", "region-1", "out", "char", "missing")],
    );
    expect(codes(definition)).toContain("PORT_NOT_FOUND");
  });

  it("检测工作流图环", () => {
    const nodes = [
      makeNode("sim1", "simulation", {}, null),
      makeNode("sim2", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "sim1", "out", "sim2", "in"),
      makeEdge("e2", "sim2", "out", "sim1", "in"),
    ];
    const definition = makeDefinition([], nodes, edges);
    expect(codes(definition)).toContain("CYCLE_DETECTED");
  });

  it("枚举与区间参数非法时报错", () => {
    const enumNode = makeNode("enum", "enum", {
      path: "bad..path",
      value_type: "asset",
      values: [],
    });
    const rangeNode = makeNode("range", "range", {
      path: "scene.targets[0].level",
      start: 1,
      end: 10,
      step: 0,
    });
    const definition = makeDefinition([makeRegion()], [enumNode, rangeNode], []);
    expect(codes(definition).filter((code) => code === "PARAM_INVALID").length).toBeGreaterThanOrEqual(2);
  });

  it("普通节点自定义路径语法错误时报 PARAM_INVALID", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("char", "character", { slot: 1, asset: "character:barbara", path: "bad..path" })],
      [],
    );
    expect(codes(definition)).toContain("PARAM_INVALID");
  });

  it("同一区域多个根节点报错", () => {
    // 两个根节点都连入同一条区域数据链时才视为多根冲突。
    const nodes = [
      makeNode("root1", "root"),
      makeNode("root2", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
    ];
    const edges = [
      makeEdge("e1", "root1", "out", "char", "in"),
      makeEdge("e2", "root2", "out", "char", "in"),
      makeEdge("e3", "char", "out", "region-1", "out"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);
    expect(codes(definition)).toContain("MULTIPLE_ROOT_NODES");
  });

  it("未接线的多余根节点不报错", () => {
    const nodes = [
      makeNode("root1", "root"),
      makeNode("root2", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
    ];
    const edges = [
      makeEdge("e1", "root1", "out", "char", "in"),
      makeEdge("e2", "char", "out", "region-1", "out"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);
    expect(codes(definition)).not.toContain("MULTIPLE_ROOT_NODES");
  });

  it("成员展开超过 200 报错", () => {
    const enumA = makeNode("enum-a", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: Array.from({ length: 15 }, (_, index) => ({
        item_id: `a-${index}`,
        value: `character:${index}`,
        label: null,
      })),
    });
    const enumB = makeNode("enum-b", "enum", {
      path: "scene.targets[0].level",
      value_type: "number",
      values: Array.from({ length: 15 }, (_, index) => ({
        item_id: `b-${index}`,
        value: index + 1,
        label: null,
      })),
    });
    const edges = [
      makeEdge("e1", "enum-a", "out", "region-1", "out"),
      makeEdge("e2", "enum-b", "out", "region-1", "out"),
      makeEdge("e3", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumA, enumB, makeNode("sim", "simulation", {}, null)],
      edges,
    );
    expect(codes(definition)).toContain("MEMBER_LIMIT_EXCEEDED");
  });

  it("空配置区域给出警告", () => {
    // 未连接区域：只有未连接警告，空汇入不再额外报（决策 2.32 收窄）。
    const unconnected = makeDefinition([makeRegion()], [], []);
    expect(codes(unconnected)).toContain("REGION_NOT_CONNECTED");
    expect(codes(unconnected)).not.toContain("EMPTY_REGION");

    // 连接了模拟节点的空区域：所连批次无法成立。
    const connected = makeDefinition(
      [makeRegion()],
      [makeNode("sim", "simulation", {}, null)],
      [makeEdge("e1", "region-1", "out", "sim", "in")],
    );
    expect(codes(connected)).toContain("EMPTY_REGION");
  });

  it("模拟节点输出可以连入分析区域边界", () => {
    const nodes = [makeNode("sim", "simulation", {}, null)];
    const edges = [makeEdge("e1", "sim", "out", "region-2", "in")];
    const definition = makeDefinition(
      [makeRegion("region-1"), makeRegion("region-2", "analysis")],
      nodes,
      edges,
    );
    expect(codes(definition)).not.toContain("ANALYSIS_NOT_IMPLEMENTED");
    expect(codes(definition)).not.toContain("ANALYSIS_BOUNDARY_SOURCE_INVALID");
  });

  it("区域小于内部节点边界时警告", () => {
    const region: WorkflowRegion = {
      id: "region-1",
      kind: "configuration",
      name: "主配置",
      rect: { x: 0, y: 0, width: 300, height: 200 },
    };
    const node: WorkflowNode = {
      id: "char",
      kind: "character",
      region_id: "region-1",
      position: { x: 100, y: 180 },
      params: { slot: 1, asset: "character:barbara" },
    };
    const definition = makeDefinition([region], [node], []);
    expect(codes(definition)).toContain("NODE_OUTSIDE_REGION");
  });

  it("多输入节点多条入线不报连接数错误", () => {
    const nodes = [
      makeNode("root", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("weapon", "weapon", { slot: 1, asset: "weapon:11512" }),
      makeNode("target", "target", { index: 0, level: 90 }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "char", "in"),
      makeEdge("e2", "char", "out", "target", "in"),
      makeEdge("e3", "root", "out", "weapon", "in"),
      makeEdge("e4", "weapon", "out", "target", "in"),
      makeEdge("e5", "target", "out", "region-1", "out"),
      makeEdge("e6", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);
    const errors = validateWorkflow(definition).filter((item) => item.severity === "error");
    expect(errors).toEqual([]);
  });

  it("成员投影端口合法连线没有错误", () => {
    const enumNode = makeNode("enum", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [
        { item_id: "x-1", value: "character:barbara", label: null },
        { item_id: "x-2", value: "character:kaeya", label: null },
      ],
    });
    const target = makeNode("target", "target", { index: 0, level: 90 });
    const edges = [
      makeEdge("e1", "enum", "out:x-1", "target", "in"),
      makeEdge("e2", "target", "out", "region-1", "out"),
      makeEdge("e3", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumNode, target, makeNode("sim", "simulation", {}, null)],
      edges,
    );
    const errors = validateWorkflow(definition).filter((item) => item.severity === "error");
    expect(errors).toEqual([]);
  });

  it("未知成员投影端口报错", () => {
    const enumNode = makeNode("enum", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [{ item_id: "x-1", value: "character:barbara", label: null }],
    });
    const target = makeNode("target", "target", { index: 0, level: 90 });
    const edges = [
      makeEdge("e1", "enum", "out:missing", "target", "in"),
      makeEdge("e2", "target", "out", "region-1", "out"),
      makeEdge("e3", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumNode, target, makeNode("sim", "simulation", {}, null)],
      edges,
    );
    expect(codes(definition)).toContain("PORT_NOT_FOUND");
  });

  it("按键轨迹未闭合按下事件报错", () => {
    const node = makeNode("trace", "input_trace", {
      items: [{ frame: 1, events: [{ key: "keyboard.e", phase: "press" }] }],
    });
    const definition = makeDefinition([makeRegion()], [node], []);
    expect(codes(definition)).toContain("PARAM_INVALID");
  });

  it("按键轨迹不支持的按键报错", () => {
    const node = makeNode("trace", "input_trace", {
      items: [{ frame: 1, events: [{ key: "keyboard.w", phase: "press" }] }],
    });
    const definition = makeDefinition([makeRegion()], [node], []);
    expect(codes(definition)).toContain("PARAM_INVALID");
  });

});

describe("validateWorkflowNodes", () => {
  it("编辑期只报节点自身参数/路径，不报跨节点槽位冲突", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [
        makeNode("w1", "weapon", { slot: 1, asset: "weapon:a" }),
        makeNode("w2", "weapon", { slot: 1, asset: "weapon:b" }),
      ],
      [],
    );
    const codes = validateWorkflowNodes(definition).map((item) => item.code);
    expect(codes).not.toContain("TEAM_SLOT_CONFLICT");
  });

  it("未注册节点类型仍是节点级错误", () => {
    const definition = makeDefinition([makeRegion()], [makeNode("x", "bogus")], []);
    const codes = validateWorkflowNodes(definition).map((item) => item.code);
    expect(codes).toContain("UNKNOWN_NODE_KIND");
  });

  it("圣遗物节点只配置属性或只配置套装均合法", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [
        makeNode("stats-only", "artifact", {
          slot: 1,
          sets: [],
          stats: { crit_rate: 0.311 },
        }),
        makeNode("sets-only", "artifact", {
          slot: 1,
          sets: [{ asset_key: "artifact_set:15032", pieces: 4 }],
          stats: {},
        }),
      ],
      [],
    );
    const params = validateWorkflowNodes(definition).filter(
      (item) => item.code === "PARAM_INVALID",
    );
    expect(params).toEqual([]);
  });

  it("圣遗物节点套装与属性均为空时报错", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("empty", "artifact", { slot: 1, sets: [], stats: {} })],
      [],
    );
    const errors = validateWorkflowNodes(definition).filter(
      (item) => item.code === "PARAM_INVALID",
    );
    expect(errors).toHaveLength(1);
    expect(errors[0]?.message).toContain("套装效果与属性至少配置一项");
  });

  it("圣遗物词条非法时报参数错误", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [
        makeNode("bad-stats", "artifact", {
          slot: 1,
          sets: [],
          stats: { bogus: 1, crit_rate: -0.1, atk_percent: "20" },
        }),
      ],
      [],
    );
    const paths = validateWorkflowNodes(definition)
      .filter((item) => item.code === "PARAM_INVALID")
      .map((item) => item.path)
      .sort();
    expect(paths).toEqual(["stats.atk_percent", "stats.bogus", "stats.crit_rate"]);
  });

  it("圣遗物件数与套装行数越界时报参数错误", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [
        makeNode("bad-pieces", "artifact", {
          slot: 1,
          sets: [{ asset_key: "artifact_set:15032", pieces: 3 }],
          stats: {},
        }),
        makeNode("too-many-sets", "artifact", {
          slot: 1,
          sets: [
            { asset_key: "artifact_set:15032", pieces: 2 },
            { asset_key: "artifact_set:15033", pieces: 2 },
            { asset_key: "artifact_set:15034", pieces: 2 },
          ],
          stats: {},
        }),
      ],
      [],
    );
    const paths = validateWorkflowNodes(definition)
      .filter((item) => item.code === "PARAM_INVALID")
      .map((item) => item.path)
      .sort();
    expect(paths).toEqual(["sets", "sets[0].pieces"]);
  });
});
