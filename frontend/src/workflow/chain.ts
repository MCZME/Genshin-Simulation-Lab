import type { WorkflowEdge, WorkflowNode } from "./types";
import { getNodeKindSpec } from "./registry";

export interface UpstreamNode {
  node: WorkflowNode;
  /** 首次到达该节点所使用的区域边界连线 id，用于诊断定位。 */
  edgeId: string;
}

/**
 * 从一组尾节点沿输入端口反向收集上游节点，返回适合按序应用的顺序。
 *
 * 节点按方法语义处理：其全部输入（按端口顺序，端口内按连线顺序）先于
 * 自身应用，因此返回顺序是“所有上游先于下游”的拓扑序。同一节点只出现
 * 一次，共享子图不会被重复应用；visited 同时防御环路导致的不终止。
 */
export function collectUpstreamNodes(
  tails: Array<{ nodeId: string; edgeId: string }>,
  nodeById: Map<string, WorkflowNode>,
  incomingByTarget: Map<string, WorkflowEdge[]>,
): UpstreamNode[] {
  const ordered: UpstreamNode[] = [];
  const visited = new Set<string>();

  function visit(nodeId: string, edgeId: string) {
    if (visited.has(nodeId)) {
      return;
    }
    visited.add(nodeId);
    const node = nodeById.get(nodeId);
    if (node === undefined) {
      return;
    }
    for (const edge of orderedIncomingEdges(node, incomingByTarget, nodeById)) {
      visit(edge.source_node_id, edgeId);
    }
    ordered.push({ node, edgeId });
  }

  for (const tail of tails) {
    visit(tail.nodeId, tail.edgeId);
  }
  return ordered;
}

export function orderedIncomingEdges(
  target: WorkflowNode,
  incomingByTarget: Map<string, WorkflowEdge[]>,
  nodeById: Map<string, WorkflowNode>,
): WorkflowEdge[] {
  const edges = incomingByTarget.get(target.id) ?? [];
  const spec = getNodeKindSpec(target.kind);
  if (spec === null || spec.region === "bridge") {
    return edges.filter((edge) => nodeById.has(edge.source_node_id));
  }
  const portIndex = new Map(spec.ports.inputs.map((port, index) => [port.id, index]));
  return edges
    .map((edge, index) => ({ edge, index }))
    .filter(({ edge }) => nodeById.has(edge.source_node_id))
    .sort((a, b) => {
      const aIndex = portIndex.get(a.edge.target_port_id) ?? Number.MAX_SAFE_INTEGER;
      const bIndex = portIndex.get(b.edge.target_port_id) ?? Number.MAX_SAFE_INTEGER;
      return aIndex - bIndex || a.index - b.index;
    })
    .map(({ edge }) => edge);
}
