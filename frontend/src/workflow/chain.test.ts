import { describe, expect, it } from "vitest";
import { collectUpstreamNodes } from "./chain";
import type { WorkflowEdge, WorkflowNode } from "./types";

function makeNode(id: string, kind: string): WorkflowNode {
  return {
    id,
    kind,
    region_id: "region-1",
    position: { x: 0, y: 0 },
    params: {},
  };
}

function makeEdge(id: string, source: string, target: string): WorkflowEdge {
  return {
    id,
    source_node_id: source,
    source_port_id: "out",
    target_node_id: target,
    target_port_id: "in",
  };
}

describe("collectUpstreamNodes", () => {
  it("多输入合并且共享节点只出现一次", () => {
    const nodeById = new Map<string, WorkflowNode>([
      ["root", makeNode("root", "root")],
      ["char", makeNode("char", "character")],
      ["weapon", makeNode("weapon", "weapon")],
      ["target", makeNode("target", "target")],
    ]);
    const edges = [
      makeEdge("e1", "root", "char"),
      makeEdge("e2", "char", "target"),
      makeEdge("e3", "root", "weapon"),
      makeEdge("e4", "weapon", "target"),
    ];
    const incomingByTarget = new Map<string, WorkflowEdge[]>();
    for (const edge of edges) {
      const list = incomingByTarget.get(edge.target_node_id) ?? [];
      list.push(edge);
      incomingByTarget.set(edge.target_node_id, list);
    }

    const result = collectUpstreamNodes(
      [{ nodeId: "target", edgeId: "boundary-1" }],
      nodeById,
      incomingByTarget,
    );

    expect(result.map((item) => item.node.id)).toEqual([
      "root",
      "char",
      "weapon",
      "target",
    ]);
    expect(result.every((item) => item.edgeId === "boundary-1")).toBe(true);
  });
});
