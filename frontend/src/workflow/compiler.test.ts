import { describe, expect, it } from "vitest";
import type {
  WorkflowDefinition,
  WorkflowEdge,
  WorkflowNode,
  WorkflowRegion,
} from "./types";
import { compileConfigurationRegion, createSimulationInputSkeleton } from "./compiler";

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

describe("compileConfigurationRegion", () => {
  it("编译单成员输入文档", () => {
    const nodes = [
      makeNode("root", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("weapon", "weapon", { slot: 1, asset: "weapon:11512" }),
      makeNode("target", "target", { index: 0, level: 90 }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "region-1", "out"),
      makeEdge("e2", "char", "out", "region-1", "out"),
      makeEdge("e3", "weapon", "out", "region-1", "out"),
      makeEdge("e4", "target", "out", "region-1", "out"),
      makeEdge("e5", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(1);

    const member = result.members[0];
    expect(member.item_id).toBe("node:char+node:weapon+node:target");
    const input = member.input;
    expect(input.schema_version).toBe(2);
    expect(input.kind).toBe("simulation_input");
    const team = input.team as Array<Record<string, unknown>>;
    expect(team[0].slot).toBe(1);
    expect(team[0].character).toEqual({
      asset_key: "character:barbara",
      level: 90,
      constellation: 0,
      talents: { normal_attack: 1, elemental_skill: 1, elemental_burst: 1 },
    });
    expect(team[0].weapon).toEqual({ asset_key: "weapon:11512", level: 90, refinement: 1 });
    const targets = (input.scene as Record<string, unknown>).targets as Array<
      Record<string, unknown>
    >;
    expect(targets[0].level).toBe(90);
  });

  it("枚举写入 team 槽位后自动补齐 slot 字段", () => {
    const enumNode = makeNode("enum", "enum", {
      path: "team[1].character",
      value_type: "asset",
      values: [{ item_id: "e-1", value: "character:barbara", label: null }],
    });
    const edges = [
      makeEdge("e1", "enum", "out", "region-1", "out"),
      makeEdge("e2", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumNode, makeNode("sim", "simulation", {}, null)],
      edges,
    );

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    const team = result.members[0].input.team as Array<Record<string, unknown>>;
    expect(team[1].slot).toBe(2);
  });

  it("普通节点自定义路径覆盖默认路径", () => {
    const char = makeNode("char", "character", {
      slot: 1,
      asset: "character:barbara",
      path: "team[0].role",
    });
    const edges = [
      makeEdge("e1", "char", "out", "region-1", "out"),
      makeEdge("e2", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [char, makeNode("sim", "simulation", {}, null)],
      edges,
    );

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    const team = result.members[0].input.team as Array<Record<string, unknown>>;
    expect((team[0].role as Record<string, unknown>).asset_key).toBe("character:barbara");
    expect(team[0].character).toBeUndefined();
  });

  it("枚举与区间按不同路径叉乘且最后一组变化最快", () => {
    const enumNode = makeNode("enum", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [
        { item_id: "e-1", value: "character:barbara", label: "芭芭拉" },
        { item_id: "e-2", value: "character:kaeya", label: "凯亚" },
      ],
    });
    const rangeNode = makeNode("range", "range", {
      path: "scene.targets[0].level",
      start: 1,
      end: 10,
      step: 3,
    });
    const edges = [
      makeEdge("e1", "enum", "out", "region-1", "out"),
      makeEdge("e2", "range", "out", "region-1", "out"),
      makeEdge("e3", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumNode, rangeNode, makeNode("sim", "simulation", {}, null)],
      edges,
    );

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(8);
    expect(result.members[0].item_id).toBe("e-1+range:scene.targets[0].level:1");
    expect(result.members[1].item_id).toBe("e-1+range:scene.targets[0].level:4");
    expect(result.members[3].item_id).toBe("e-1+range:scene.targets[0].level:10");
    expect(result.members[4].item_id).toBe("e-2+range:scene.targets[0].level:1");

    const levels = result.members.slice(0, 4).map((member) => {
      const targets = (member.input.scene as Record<string, unknown>).targets as Array<
        Record<string, unknown>
      >;
      return targets[0].level;
    });
    expect(levels).toEqual([1, 4, 7, 10]);
  });

  it("同路径后写入者覆盖先生成者并返回警告", () => {
    const enumA = makeNode("enum-a", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [{ item_id: "x-1", value: "character:barbara", label: null }],
    });
    const enumB = makeNode("enum-b", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [{ item_id: "x-2", value: "character:kaeya", label: null }],
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

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(1);
    expect(result.members[0].item_id).toBe("x-2");
    expect(result.diagnostics.map((item) => item.code)).toContain("PATH_OVERRIDE");
  });

  it("区间十进制取值无浮点误差", () => {
    const rangeNode = makeNode("range", "range", {
      path: "scene.targets[0].level",
      start: 0.1,
      end: 0.3,
      step: 0.1,
    });
    const edges = [
      makeEdge("e1", "range", "out", "region-1", "out"),
      makeEdge("e2", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [rangeNode, makeNode("sim", "simulation", {}, null)],
      edges,
    );

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members.map((member) => member.item_id)).toEqual([
      "range:scene.targets[0].level:0.1",
      "range:scene.targets[0].level:0.2",
      "range:scene.targets[0].level:0.3",
    ]);
    const levels = result.members.map((member) => {
      const targets = (member.input.scene as Record<string, unknown>).targets as Array<
        Record<string, unknown>
      >;
      return targets[0].level;
    });
    expect(levels).toEqual([0.1, 0.2, 0.3]);
  });

  it("超过 200 成员时编译失败", () => {
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

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(false);
    expect(result.members).toEqual([]);
    expect(result.diagnostics.map((item) => item.code)).toContain("MEMBER_LIMIT_EXCEEDED");
  });

  it("无数据汇入时阻止运行", () => {
    const definition = makeDefinition(
      [makeRegion()],
      [makeNode("sim", "simulation", {}, null)],
      [],
    );
    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(false);
    expect(result.diagnostics.map((item) => item.code)).toContain("EMPTY_REGION");
  });

  it("只有根节点时输出骨架成员", () => {
    const nodes = [makeNode("root", "root"), makeNode("sim", "simulation", {}, null)];
    const edges = [
      makeEdge("e1", "root", "out", "region-1", "out"),
      makeEdge("e2", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(1);
    expect(result.members[0].item_id).toBe("root");
    expect(result.members[0].input).toEqual(createSimulationInputSkeleton());
  });

  it("元信息节点写入输入文档名称与描述", () => {
    const nodes = [
      makeNode("root", "root"),
      makeNode("meta", "meta", { name: "深渊满星队", description: "上半间" }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "region-1", "out"),
      makeEdge("e2", "meta", "out", "region-1", "out"),
      makeEdge("e3", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members[0].input.meta).toEqual({
      name: "深渊满星队",
      description: "上半间",
    });
  });

  it("枚举顺序调整后 item_id 稳定指向同一取值", () => {
    const build = (values: { item_id: string; value: string }[]) =>
      makeDefinition(
        [makeRegion()],
        [
          makeNode("enum", "enum", {
            path: "team[0].character",
            value_type: "asset",
            values: values.map((item) => ({ ...item, label: null })),
          }),
          makeNode("sim", "simulation", {}, null),
        ],
        [
          makeEdge("e1", "enum", "out", "region-1", "out"),
          makeEdge("e2", "region-1", "out", "sim", "in"),
        ],
      );

    const first = compileConfigurationRegion(
      build([
        { item_id: "e-1", value: "character:barbara" },
        { item_id: "e-2", value: "character:kaeya" },
      ]),
      "region-1",
    );
    const second = compileConfigurationRegion(
      build([
        { item_id: "e-2", value: "character:kaeya" },
        { item_id: "e-1", value: "character:barbara" },
      ]),
      "region-1",
    );

    const byId = (result: typeof first) =>
      new Map(result.members.map((member) => [member.item_id, member.input]));
    const firstMap = byId(first);
    const secondMap = byId(second);
    expect(secondMap.get("e-1")?.team).toEqual(firstMap.get("e-1")?.team);
    expect(secondMap.get("e-2")?.team).toEqual(firstMap.get("e-2")?.team);
  });

  it("区间参数调整后仍存活成员的 item_id 不变", () => {
    const build = (start: number) =>
      makeDefinition(
        [makeRegion()],
        [
          makeNode("range", "range", {
            path: "scene.targets[0].level",
            start,
            end: 10,
            step: 3,
          }),
          makeNode("sim", "simulation", {}, null),
        ],
        [
          makeEdge("e1", "range", "out", "region-1", "out"),
          makeEdge("e2", "region-1", "out", "sim", "in"),
        ],
      );

    const before = compileConfigurationRegion(build(1), "region-1");
    const after = compileConfigurationRegion(build(4), "region-1");
    const beforeIds = before.members.map((member) => member.item_id);
    const afterIds = after.members.map((member) => member.item_id);
    expect(beforeIds).toEqual([
      "range:scene.targets[0].level:1",
      "range:scene.targets[0].level:4",
      "range:scene.targets[0].level:7",
      "range:scene.targets[0].level:10",
    ]);
    expect(afterIds).toEqual([
      "range:scene.targets[0].level:4",
      "range:scene.targets[0].level:7",
      "range:scene.targets[0].level:10",
    ]);
  });

  it("节点链按顺序应用到根文档", () => {
    const nodes = [
      makeNode("root", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("weapon", "weapon", { slot: 1, asset: "weapon:11512" }),
      makeNode("target", "target", { index: 0, level: 90 }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "char", "in"),
      makeEdge("e2", "char", "out", "weapon", "in"),
      makeEdge("e3", "weapon", "out", "target", "in"),
      makeEdge("e4", "target", "out", "region-1", "out"),
      makeEdge("e5", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(1);
    expect(result.members[0].item_id).toBe("node:char+node:weapon+node:target");
    const team = result.members[0].input.team as Array<Record<string, unknown>>;
    expect(team[0].character).toBeDefined();
    expect(team[0].weapon).toBeDefined();
    const targets = (result.members[0].input.scene as Record<string, unknown>).targets as Array<
      Record<string, unknown>
    >;
    expect(targets[0].level).toBe(90);
  });

  it("链上枚举与区间按不同路径叉乘", () => {
    const nodes = [
      makeNode("root", "root"),
      makeNode("range", "range", {
        path: "scene.targets[0].level",
        start: 1,
        end: 10,
        step: 3,
      }),
      makeNode("enum", "enum", {
        path: "run_options.max_frames",
        value_type: "number",
        values: [
          { item_id: "e-1", value: 60, label: null },
          { item_id: "e-2", value: 120, label: null },
        ],
      }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "range", "in"),
      makeEdge("e2", "range", "out", "enum", "in"),
      makeEdge("e3", "enum", "out", "region-1", "out"),
      makeEdge("e4", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(8);
    expect(result.members[0].item_id).toContain("range:");
    expect(result.members[0].item_id).toContain("e-1");
    expect(result.members[1].item_id).toContain("e-2");
  });

  it("链上同路径后写入者覆盖并警告", () => {
    const nodes = [
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("enum", "enum", {
        path: "team[0].character",
        value_type: "asset",
        values: [{ item_id: "e-1", value: "character:kaeya", label: null }],
      }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "char", "out", "enum", "in"),
      makeEdge("e2", "enum", "out", "region-1", "out"),
      makeEdge("e3", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(1);
    expect(result.members[0].item_id).toBe("e-1");
    expect(result.diagnostics.map((item) => item.code)).toContain("PATH_OVERRIDE");
  });

  it("分支复制上游输出到各分支", () => {
    const nodes = [
      makeNode("root", "root"),
      makeNode("char", "character", { slot: 1, asset: "character:barbara" }),
      makeNode("target1", "target", { index: 0, level: 90 }),
      makeNode("target2", "target", { index: 1, level: 80 }),
      makeNode("sim", "simulation", {}, null),
    ];
    const edges = [
      makeEdge("e1", "root", "out", "char", "in"),
      makeEdge("e2", "char", "out", "target1", "in"),
      makeEdge("e3", "char", "out", "target2", "in"),
      makeEdge("e4", "target1", "out", "region-1", "out"),
      makeEdge("e5", "target2", "out", "region-1", "out"),
      makeEdge("e6", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition([makeRegion()], nodes, edges);

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(1);
    expect(result.members[0].item_id).toBe("node:char+node:target1+node:target2");
    const targets = (result.members[0].input.scene as Record<string, unknown>).targets as Array<
      Record<string, unknown>
    >;
    expect(targets[0].level).toBe(90);
    expect(targets[1].level).toBe(80);
  });

  it("多输入节点合并不同路径片段", () => {
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

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(1);
    expect(result.members[0].item_id).toBe("node:char+node:weapon+node:target");
    const team = result.members[0].input.team as Array<Record<string, unknown>>;
    expect(team[0].character).toBeDefined();
    expect(team[0].weapon).toBeDefined();
    const targets = (result.members[0].input.scene as Record<string, unknown>).targets as Array<
      Record<string, unknown>
    >;
    expect(targets[0].level).toBe(90);
  });

  it("多输入同路径覆盖并警告", () => {
    const enumA = makeNode("enum-a", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [{ item_id: "x-1", value: "character:barbara", label: null }],
    });
    const enumB = makeNode("enum-b", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [{ item_id: "x-2", value: "character:kaeya", label: null }],
    });
    const rangeNode = makeNode("range", "range", {
      path: "scene.targets[0].level",
      start: 1,
      end: 10,
      step: 3,
    });
    const edges = [
      makeEdge("e1", "enum-a", "out", "range", "in"),
      makeEdge("e2", "enum-b", "out", "range", "in"),
      makeEdge("e3", "range", "out", "region-1", "out"),
      makeEdge("e4", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumA, enumB, rangeNode, makeNode("sim", "simulation", {}, null)],
      edges,
    );

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(4);
    expect(result.members[0].item_id).toBe("x-2+range:scene.targets[0].level:1");
    expect(result.diagnostics.map((item) => item.code)).toContain("PATH_OVERRIDE");
  });

  it("多输入变体按不同路径叉乘", () => {
    const enumA = makeNode("enum-a", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [
        { item_id: "a-1", value: "character:barbara", label: null },
        { item_id: "a-2", value: "character:kaeya", label: null },
      ],
    });
    const enumB = makeNode("enum-b", "enum", {
      path: "scene.targets[0].level",
      value_type: "number",
      values: [
        { item_id: "b-1", value: 90, label: null },
        { item_id: "b-2", value: 80, label: null },
      ],
    });
    const runNode = makeNode("run", "run_options", { max_frames: 60 });
    const edges = [
      makeEdge("e1", "enum-a", "out", "run", "in"),
      makeEdge("e2", "enum-b", "out", "run", "in"),
      makeEdge("e3", "run", "out", "region-1", "out"),
      makeEdge("e4", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumA, enumB, runNode, makeNode("sim", "simulation", {}, null)],
      edges,
    );

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(4);
    expect(result.members[0].item_id).toBe("a-1+b-1+node:run");
    expect(result.members[3].item_id).toBe("a-2+b-2+node:run");
  });

  it("成员投影端口只输出对应成员", () => {
    const enumNode = makeNode("enum", "enum", {
      path: "team[0].character",
      value_type: "asset",
      values: [
        { item_id: "x-1", value: "character:barbara", label: "芭芭拉" },
        { item_id: "x-2", value: "character:kaeya", label: "凯亚" },
      ],
    });
    const target1 = makeNode("target1", "target", { index: 0, level: 90 });
    const target2 = makeNode("target2", "target", { index: 1, level: 80 });
    const edges = [
      makeEdge("e1", "enum", "out:x-1", "target1", "in"),
      makeEdge("e2", "enum", "out:x-2", "target2", "in"),
      makeEdge("e3", "target1", "out", "region-1", "out"),
      makeEdge("e4", "target2", "out", "region-1", "out"),
      makeEdge("e5", "region-1", "out", "sim", "in"),
    ];
    const definition = makeDefinition(
      [makeRegion()],
      [enumNode, target1, target2, makeNode("sim", "simulation", {}, null)],
      edges,
    );

    const result = compileConfigurationRegion(definition, "region-1");
    expect(result.ok).toBe(true);
    expect(result.members).toHaveLength(2);
    expect(result.members[0].item_id).toBe("x-1+node:target1");
    expect(result.members[1].item_id).toBe("x-2+node:target2");
    const firstTeam = result.members[0].input.team as Array<Record<string, unknown>>;
    expect((firstTeam[0].character as Record<string, unknown>).asset_key).toBe(
      "character:barbara",
    );
    const secondTeam = result.members[1].input.team as Array<Record<string, unknown>>;
    expect((secondTeam[0].character as Record<string, unknown>).asset_key).toBe(
      "character:kaeya",
    );
    const targets1 = (result.members[0].input.scene as Record<string, unknown>).targets as Array<
      Record<string, unknown>
    >;
    const targets2 = (result.members[1].input.scene as Record<string, unknown>).targets as Array<
      Record<string, unknown>
    >;
    expect(targets1[0].level).toBe(90);
    expect(targets2[1].level).toBe(80);
  });
});
